#!/usr/bin/env python3
"""Scalar residual v2: physics-informed loss improvements.

Three changes over v1 (scalar_residual_comparison.py):
1. Target clipping to ±2.25 µT (sector clamp at deployment)
2. Huber delta 10.0 (quadratic regime for all clipped errors)
3. Learnable anchor sigma (network tunes spatial attention width)

Usage:
    python experiments/scalar_residual_v2.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import time
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

from odmr_edge_ml.evaluation.residual_dataset import (
    ResidualDataset,
    _normalize_symmetric,
    generate_pid_labels,
)
from odmr_edge_ml.models.fcnn import OdmrFCNN
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.training.qat import extract_clean_state_dict, prepare_model_qat
from odmr_edge_ml.export import export_onnx as _export_onnx_module
from odmr_edge_ml.validation.ops_guard import check_model_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data/production_50k"
ARTIFACT_DIR = Path(__file__).resolve().parent / "scalar_residual_v2"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
V1_CKPT = Path(__file__).resolve().parent / "scalar_residual/fcnn/checkpoints/best_model.pt"
V1_SWEEP = Path(__file__).resolve().parent / "heading_sweep_results.npz"

# Sector clamp: ±4.5% of 50 µT deployment field.
# Widening to ±15 µT for full 360° heading sweeps is under evaluation.
# See Gemini ±30% Circle Criterion analysis for INT8 resolution trade-offs:
# current resolution ~17.6 nT/level vs ~117.6 nT/level at ±15 µT.
CLAMP_UT = 2.25


# ---------------------------------------------------------------------------
# ResidualDatasetV2: spectrum(100) + lock_bin(1), clipped labels
# ---------------------------------------------------------------------------
class ResidualDatasetV2(Dataset):
    """Dataset for learnable-sigma FCNN.

    Returns 101-dim input: spectrum_norm(100) || lock_bin(1).
    Labels clipped to ±CLAMP_UT. Anchor computed by model, not dataset.
    """

    def __init__(self, data_dir: Path, split: str = "train") -> None:
        npz_path = data_dir / "pid_residuals.npz"
        if not npz_path.exists():
            log.info("PID labels not found, generating...")
            generate_pid_labels(data_dir)

        npz = np.load(npz_path)
        lock_bins = npz[f"{split}_lock_bins"]
        delta_b = npz[f"{split}_delta_b_uT"]

        with h5py.File(data_dir / "dataset.h5", "r") as f:
            spectra_raw = f[split]["spectra"][:]

        spectra_norm = _normalize_symmetric(spectra_raw)

        # Pack spectrum(100) + lock_bin(1)
        lock_col = lock_bins[:, None].astype(np.float32)
        combined = np.concatenate([spectra_norm, lock_col], axis=1)  # (N, 101)

        # Clip labels to sector clamp range
        clipped = np.clip(delta_b, -CLAMP_UT, CLAMP_UT)
        n_clipped = int(np.sum(np.abs(delta_b) > CLAMP_UT))
        log.info(
            "%s: clipped %d/%d samples (%.1f%%) to ±%.2f µT",
            split, n_clipped, len(delta_b),
            100.0 * n_clipped / len(delta_b), CLAMP_UT,
        )

        self.spectra = torch.from_numpy(combined).float()
        self.labels = torch.from_numpy(clipped[:, None]).float()

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {"spectra": self.spectra[idx], "b_field_uT": self.labels[idx]}


# ---------------------------------------------------------------------------
# OdmrFCNNv2: learnable sigma, anchor computed in forward pass
# ---------------------------------------------------------------------------
class OdmrFCNNv2(nn.Module):
    """FCNN with learnable anchor sigma.

    Takes (batch, 101) input: [spectrum(100), lock_bin(1)].
    Computes Gaussian anchor with learnable sigma, then runs identical
    conv pipeline to OdmrFCNN(input_dim=100, in_channels=2).

    Attribute names (convs, relus, conv_head) match OdmrFCNN for weight
    transfer during export.
    """

    def __init__(
        self,
        input_dim: int = 100,
        output_dim: int = 1,
        channels: list[int] | None = None,
        kernel_size: int = 5,
        stride: int = 2,
    ) -> None:
        super().__init__()
        if channels is None:
            channels = [8, 16, 24]

        self.input_dim = input_dim
        self.in_channels = 2
        self.sigma = nn.Parameter(torch.tensor(1.5))
        self.register_buffer("bins", torch.arange(input_dim, dtype=torch.float32))

        # Conv layers — identical to OdmrFCNN(in_channels=2)
        self.convs = nn.ModuleList()
        self.relus = nn.ModuleList()
        spatial = input_dim
        prev_c = 2
        for c in channels:
            self.convs.append(
                nn.Conv2d(prev_c, c, kernel_size=(1, kernel_size), stride=(1, stride))
            )
            self.relus.append(nn.ReLU())
            spatial = (spatial - kernel_size) // stride + 1
            prev_c = c

        self.conv_head = nn.Conv2d(prev_c, output_dim, kernel_size=(1, spatial))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        spectrum = x[:, :self.input_dim]   # (batch, 100)
        lock_bin = x[:, self.input_dim:]   # (batch, 1)

        sigma = self.sigma.clamp(min=0.1)
        anchor = torch.exp(
            -0.5 * ((self.bins[None, :] - lock_bin) / sigma) ** 2
        )  # (batch, 100)

        combined = torch.cat([spectrum, anchor], dim=1)  # (batch, 200)
        x = combined.view(x.size(0), 2, 1, self.input_dim)

        for conv, relu in zip(self.convs, self.relus):
            x = relu(conv(x))
        x = self.conv_head(x)  # (batch, output_dim, 1, 1)
        return x.flatten(1)


# ---------------------------------------------------------------------------
# Loss & validation (same API as v1)
# ---------------------------------------------------------------------------
class ScalarHuberLoss(nn.Module):
    """Huber loss returning dict compatible with training loop."""

    def __init__(self, delta: float = 10.0) -> None:
        super().__init__()
        self.huber = nn.HuberLoss(reduction="mean", delta=delta)

    def forward(
        self, pred: torch.Tensor, true: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        loss = self.huber(pred, true)
        return {"loss": loss, "angular": torch.tensor(0.0), "huber": loss}


def validate_scalar(
    model: nn.Module, val_loader: DataLoader, device: torch.device,
) -> dict[str, float]:
    """MAE and RMSE on scalar residual predictions."""
    model.eval()
    all_pred, all_true = [], []
    with torch.no_grad():
        for batch in val_loader:
            x = batch["spectra"].to(device)
            y = batch["b_field_uT"].to(device)
            all_pred.append(model(x))
            all_true.append(y)
    pred = torch.cat(all_pred)
    true = torch.cat(all_true)
    mae = (pred - true).abs().mean().item()
    rmse = ((pred - true) ** 2).mean().sqrt().item()
    return {"mae_uT": mae, "rmse_uT": rmse}


def collate_residual(batch: list[dict]) -> dict:
    spectra = torch.stack([s["spectra"] for s in batch])
    b_field_uT = torch.stack([s["b_field_uT"] for s in batch])
    return {"spectra": spectra, "b_field_uT": b_field_uT}


# ---------------------------------------------------------------------------
# Export helpers (copied from v1 for self-containedness)
# ---------------------------------------------------------------------------
def export_onnx(model: nn.Module, onnx_path: Path, input_dim: int) -> None:
    """Delegate to the canonical export module in src/."""
    _export_onnx_module(
        model, onnx_path, input_shape=(1, input_dim), skip_ops_check=True,
    )


def convert_fcnn_to_tflite_int8(
    model: OdmrFCNN, cal: np.ndarray, path: Path,
) -> None:
    import tensorflow as tf

    pt_convs = list(model.convs) + [model.conv_head]
    in_ch = model.in_channels
    inp = tf.keras.layers.Input(shape=(1, 100, in_ch))
    x = inp
    for i, pt_c in enumerate(pt_convs):
        is_last = i == len(pt_convs) - 1
        act = None if is_last else "relu"
        x = tf.keras.layers.Conv2D(
            pt_c.out_channels, pt_c.kernel_size, strides=pt_c.stride,
            activation=act, padding="valid",
        )(x)
    x = tf.keras.layers.Flatten()(x)
    tf_model = tf.keras.Model(inputs=inp, outputs=x)
    tf_conv_layers = [
        layer for layer in tf_model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    for pt_c, tf_l in zip(pt_convs, tf_conv_layers):
        w = pt_c.weight.detach().numpy().transpose(2, 3, 1, 0)
        tf_l.set_weights([w, pt_c.bias.detach().numpy()])
    # (N, 200) → (N, 2, 1, 100) NCHW → (N, 1, 100, 2) NHWC
    cal_nhwc = cal.reshape(-1, in_ch, 1, 100).transpose(0, 2, 3, 1)
    _to_tflite_int8(tf_model, cal_nhwc, path)


def _to_tflite_int8(tf_model, cal: np.ndarray, path: Path) -> None:
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def rep():
        for i in range(min(len(cal), 1000)):
            yield [cal[i:i + 1].astype(np.float32)]

    converter.representative_dataset = rep
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite = converter.convert()
    path.write_bytes(tflite)
    log.info("  TFLite INT8: %s (%.1f KB)", path, path.stat().st_size / 1024)


# ---------------------------------------------------------------------------
# Heading sweep v2
# ---------------------------------------------------------------------------
def run_heading_sweep(
    clean_model: nn.Module, learned_sigma: float,
) -> dict | None:
    """Run 1440-angle heading sweep with v2 clean model and learned sigma."""
    try:
        from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
        from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
        from nv_sensor_sim.physics.lineshape import corrupt_spectrum
        from nv_sensor_sim.physics.noise_injection import sample_ou_trajectory_pair

        from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
    except ImportError:
        log.warning("nv_sensor_sim not available — skipping heading sweep")
        return None

    N_ANGLES = 1440
    B_MAG_T = 50e-6
    B_MAG_UT = 50.0
    N_FREQ = 100
    SEED = 42

    E1 = np.array([0.0, 0.0, 1.0])
    E2 = np.array([1.0, 1.0, 0.0]) / np.sqrt(2.0)

    ou_config = OUNoiseConfig(
        alpha_B1=-0.03, T_mean_C=20.0, delta_T_orb_C=15.0, tau_orb_s=5400.0,
        B1_nominal=1.0, theta_T=0.1, sigma_T=0.5, theta_B1=1.0, sigma_B1=0.05,
        trajectory_dt_s=1.0, enable_thermal_noise=True, enable_mw_noise=True,
    )
    output_path = Path(__file__).resolve().parent / "heading_sweep_v2_results.npz"

    log.info("=" * 60)
    log.info("HEADING SWEEP V2 (learned sigma=%.4f)", learned_sigma)
    log.info("=" * 60)

    sim_config = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, B_MAG_T]),
        temperature_K=300.0,
        mw_freq_range_Hz=(2.82e9, 2.92e9),
        n_freq_points=N_FREQ,
        p1_concentration_ppm=50.0,
        include_nitrogen=False,
        use_optics=False,
    )
    adapter = SimOSAdapter(sim_config)
    _, b1_trajectory = sample_ou_trajectory_pair(ou_config, N_ANGLES, seed=SEED)

    freqs, _ = adapter.generate_odmr_spectrum(
        temperature_K=300.0, p1_ppm=50.0, mw_scale=1.0,
    )
    pid = DerivativeZeroCrossingPID(freqs)

    angles_deg = np.linspace(0.0, 360.0, N_ANGLES, endpoint=False)
    angles_rad = np.deg2rad(angles_deg)
    b_vecs = np.zeros((N_ANGLES, 3))
    spectra = np.zeros((N_ANGLES, N_FREQ))
    pid_estimates_uT = np.zeros(N_ANGLES)
    pid_lock_bins = np.zeros(N_ANGLES, dtype=int)
    pid_n_dips = np.zeros(N_ANGLES, dtype=int)
    fcnn_delta_b_uT = np.zeros(N_ANGLES)
    mw_power_scales = np.zeros(N_ANGLES)

    t0 = time.monotonic()
    for i in range(N_ANGLES):
        theta = angles_rad[i]
        B_vec = B_MAG_T * (np.cos(theta) * E1 + np.sin(theta) * E2)
        b_vecs[i] = B_vec
        sim_config.B_field_T = B_vec

        mw_scale = float(b1_trajectory[i])
        mw_power_scales[i] = mw_scale

        _, signal, _ = corrupt_spectrum(
            adapter, sim_config,
            b1_gradient_frac=0.15, b_perp_T=0.0,
            p1_ppm=50.0, n_spatial_bins=10,
            mw_power_scale=mw_scale,
        )
        spectra[i] = signal

        result = pid.estimate(signal)
        pid_estimates_uT[i] = result.b_mag_uT
        pid_lock_bins[i] = result.lock_bin
        pid_n_dips[i] = result.n_dips

        # Preprocess with learned sigma
        s_min, s_max = signal.min(), signal.max()
        denom = s_max - s_min if s_max != s_min else 1.0
        spec_norm = 2.0 * (signal - s_min) / denom - 1.0
        bins = np.arange(N_FREQ)
        anchor = np.exp(-0.5 * ((bins - result.lock_bin) / learned_sigma) ** 2)
        x = np.concatenate([spec_norm, anchor])
        x_t = torch.from_numpy(x).float().unsqueeze(0)

        with torch.no_grad():
            delta_b = clean_model(x_t).item()
        fcnn_delta_b_uT[i] = np.clip(delta_b, -CLAMP_UT, CLAMP_UT)

        if (i + 1) % 360 == 0:
            log.info("  %d / %d angles (%.0f°)", i + 1, N_ANGLES, angles_deg[i])

    elapsed = time.monotonic() - t0

    pid_error_uT = np.abs(pid_estimates_uT - B_MAG_UT)
    cnn_pid_uT = pid_estimates_uT + fcnn_delta_b_uT
    cnn_error_uT = np.abs(cnn_pid_uT - B_MAG_UT)

    np.savez(
        output_path,
        angles_deg=angles_deg, b_vecs_T=b_vecs, frequencies_Hz=freqs,
        spectra=spectra, pid_estimates_uT=pid_estimates_uT,
        pid_lock_bins=pid_lock_bins, pid_n_dips=pid_n_dips,
        fcnn_delta_b_uT=fcnn_delta_b_uT, cnn_pid_estimates_uT=cnn_pid_uT,
        pid_error_uT=pid_error_uT, cnn_error_uT=cnn_error_uT,
        mw_power_scales=mw_power_scales,
        b_mag_true_uT=np.float64(B_MAG_UT), seed=np.int64(SEED),
        learned_sigma=np.float64(learned_sigma),
    )

    improvement = (1.0 - cnn_error_uT.mean() / pid_error_uT.mean()) * 100.0
    log.info("  Sweep time: %.1fs", elapsed)
    log.info("")
    log.info("  %-20s %10s %10s %10s %10s", "", "MAE", "Max", "P50", "P95")
    log.info("  " + "-" * 60)
    log.info(
        "  %-20s %9.3f %9.3f %9.3f %9.3f", "PID-only (µT)",
        pid_error_uT.mean(), pid_error_uT.max(),
        np.percentile(pid_error_uT, 50), np.percentile(pid_error_uT, 95),
    )
    log.info(
        "  %-20s %9.3f %9.3f %9.3f %9.3f", "FCNN v2+PID (µT)",
        cnn_error_uT.mean(), cnn_error_uT.max(),
        np.percentile(cnn_error_uT, 50), np.percentile(cnn_error_uT, 95),
    )
    log.info("  Heading error reduction: %.1f%%", improvement)
    log.info("  Saved: %s", output_path)

    return {
        "pid_error_uT": pid_error_uT,
        "cnn_error_uT": cnn_error_uT,
        "improvement": improvement,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("SCALAR RESIDUAL V2: PHYSICS-INFORMED IMPROVEMENTS")
    log.info("=" * 60)
    log.info("  Target clamp: ±%.2f µT", CLAMP_UT)
    log.info("  Huber delta: 10.0")
    log.info("  Learnable sigma (init 1.5)")

    device = torch.device("cpu")

    # -- PID labels --
    npz_path = DATA_DIR / "pid_residuals.npz"
    if not npz_path.exists():
        log.info("Generating PID labels...")
        generate_pid_labels(DATA_DIR)

    npz = np.load(npz_path)
    pid_mae_val = float(np.abs(npz["val_delta_b_uT"]).mean())
    pid_mae_val_clipped = float(
        np.abs(np.clip(npz["val_delta_b_uT"], -CLAMP_UT, CLAMP_UT)).mean()
    )
    log.info(
        "PID baseline val MAE: %.2f µT (unclipped), %.2f µT (clipped)",
        pid_mae_val, pid_mae_val_clipped,
    )

    # -- Datasets --
    train_ds = ResidualDatasetV2(DATA_DIR, "train")
    val_ds = ResidualDatasetV2(DATA_DIR, "val")
    log.info(
        "Train: %d, Val: %d, input dim: %d",
        len(train_ds), len(val_ds), train_ds.spectra.shape[1],
    )

    train_loader = DataLoader(
        train_ds, batch_size=64, shuffle=True, collate_fn=collate_residual,
    )
    val_loader = DataLoader(
        val_ds, batch_size=64, shuffle=False, collate_fn=collate_residual,
    )

    # -- Model --
    model = OdmrFCNNv2(input_dim=100, output_dim=1)
    n_params = sum(p.numel() for p in model.parameters())
    log.info("OdmrFCNNv2: %d params (sigma init=%.2f)", n_params, model.sigma.item())

    # Ops guard on the equivalent export model
    export_check = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    report = check_model_ops(export_check, input_shape=(1, 200))
    log.info("Ops guard (export model): compatible=%s", report.is_compatible)
    if report.disallowed:
        log.error("DISALLOWED ops: %s", report.disallowed)
        sys.exit(1)
    del export_check

    init_weights_kaiming_he(model)

    # -- QAT --
    log.info("Preparing QAT (symmetric INT8)")
    qat_model = prepare_model_qat(model, example_input=torch.randn(1, 101))

    # -- Train --
    config = TrainConfig(
        lr=1e-3, weight_decay=1e-3, epochs=100, T_max=100, eta_min=1e-5,
        batch_size=64, val_every=10, log_every=10, alpha=0.7,
        huber_delta=10.0, seed=42,
        checkpoint_dir=str(ARTIFACT_DIR / "checkpoints"),
    )
    criterion = ScalarHuberLoss(delta=10.0)
    results = train(
        qat_model, train_loader, val_loader, config, device,
        criterion=criterion, val_fn=validate_scalar,
    )

    log.info("Final train loss: %.6f", results["final_train_loss"])
    log.info("Training time: %.1fs", results["training_time_s"])
    v2_metrics = results["final_val_metrics"]
    if v2_metrics:
        log.info(
            "v2 val MAE: %.4f µT, RMSE: %.4f µT",
            v2_metrics["mae_uT"], v2_metrics.get("rmse_uT", 0),
        )

    # -- Extract learned sigma & build clean export model --
    clean_sd = extract_clean_state_dict(qat_model)
    learned_sigma = clean_sd["sigma"].item()
    log.info("Learned sigma: %.4f (init was 1.5)", learned_sigma)

    clean = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    export_sd = {k: v for k, v in clean_sd.items() if k in clean.state_dict()}
    clean.load_state_dict(export_sd, strict=True)
    clean.eval()

    # -- Export ONNX + TFLite INT8 --
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    onnx_path = ARTIFACT_DIR / "model.onnx"
    export_onnx(clean, onnx_path, input_dim=200)

    tflite_path = ARTIFACT_DIR / "model_int8.tflite"
    # Calibration data uses learned sigma for anchor construction
    cal_ds = ResidualDataset(DATA_DIR, "train", sigma=learned_sigma)
    calibration = cal_ds.spectra.numpy()[:1000]
    convert_fcnn_to_tflite_int8(clean, calibration, tflite_path)

    # Deployment metadata
    np.savez(
        ARTIFACT_DIR / "deployment_metadata.npz",
        learned_sigma=np.float64(learned_sigma),
        clamp_uT=np.float64(CLAMP_UT),
        input_dim=np.int64(200),
        model_version="v2",
    )

    # Copy to exports
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        exp_tflite = EXPORT_DIR / "fcnn_v2_residual_int8.tflite"
        exp_onnx = EXPORT_DIR / "fcnn_v2_residual.onnx"
        shutil.copy2(tflite_path, exp_tflite)
        shutil.copy2(onnx_path, exp_onnx)
        log.info("Export: %s (%.1f KB)", exp_tflite, exp_tflite.stat().st_size / 1024)
    except OSError as e:
        log.warning("Export copy failed: %s", e)

    # ==================================================================
    # V1 vs V2 comparison
    # ==================================================================
    log.info("")
    log.info("=" * 70)
    log.info("V1 vs V2 COMPARISON")
    log.info("=" * 70)

    v1_mae = None
    if V1_CKPT.exists():
        ckpt = torch.load(V1_CKPT, map_location="cpu", weights_only=False)
        sd = ckpt["model_state_dict"]
        skip = ("fake_quant", "activation_post_process", "observer")
        v1_sd = {k: v for k, v in sd.items() if not any(p in k for p in skip)}
        v1_model = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
        v1_model.load_state_dict(v1_sd, strict=True)
        v1_model.eval()

        # Evaluate v1 on its own dataset (200-dim, unclipped labels)
        v1_ds = ResidualDataset(DATA_DIR, "val")
        v1_loader = DataLoader(
            v1_ds, batch_size=64, shuffle=False, collate_fn=collate_residual,
        )
        v1_metrics = validate_scalar(v1_model, v1_loader, device)
        v1_mae = v1_metrics["mae_uT"]
    else:
        log.warning("v1 checkpoint not found: %s", V1_CKPT)

    v2_mae = v2_metrics.get("mae_uT", 0.0) if v2_metrics else 0.0

    log.info("")
    log.info("%-30s %12s %12s", "", "v1", "v2")
    log.info("-" * 54)
    if v1_mae is not None:
        log.info("%-30s %12.4f %12.4f", "Val MAE (µT)", v1_mae, v2_mae)
        log.info(
            "%-30s %11.1f%% %11.1f%%", "vs PID baseline",
            (1 - v1_mae / pid_mae_val) * 100,
            (1 - v2_mae / pid_mae_val_clipped) * 100,
        )
    else:
        log.info("%-30s %12s %12.4f", "Val MAE (µT)", "N/A", v2_mae)
    log.info("%-30s %12s %12.4f", "Learned sigma", "1.5 (fixed)", learned_sigma)
    log.info("%-30s %12s %12s", "Target clamp", "none", f"±{CLAMP_UT}")
    log.info("%-30s %12s %12s", "Huber delta", "5.0", "10.0")

    # ==================================================================
    # Heading sweep
    # ==================================================================
    sweep_v2 = run_heading_sweep(clean, learned_sigma)

    if sweep_v2 is not None and V1_SWEEP.exists():
        v1_data = np.load(V1_SWEEP)
        v1_pid = v1_data["pid_error_uT"]
        v1_cnn = v1_data["cnn_error_uT"]
        v2_pid = sweep_v2["pid_error_uT"]
        v2_cnn = sweep_v2["cnn_error_uT"]

        log.info("")
        log.info("=" * 70)
        log.info("HEADING SWEEP: V1 vs V2")
        log.info("=" * 70)
        log.info("%-25s %10s %10s %10s %10s", "", "MAE", "Max", "P50", "P95")
        log.info("-" * 65)
        log.info(
            "%-25s %9.3f %9.3f %9.3f %9.3f", "PID-only (µT)",
            v1_pid.mean(), v1_pid.max(),
            np.percentile(v1_pid, 50), np.percentile(v1_pid, 95),
        )
        log.info(
            "%-25s %9.3f %9.3f %9.3f %9.3f", "v1 FCNN+PID (µT)",
            v1_cnn.mean(), v1_cnn.max(),
            np.percentile(v1_cnn, 50), np.percentile(v1_cnn, 95),
        )
        log.info(
            "%-25s %9.3f %9.3f %9.3f %9.3f", "v2 FCNN+PID (µT)",
            v2_cnn.mean(), v2_cnn.max(),
            np.percentile(v2_cnn, 50), np.percentile(v2_cnn, 95),
        )
        log.info("")
        v1_improve = (1 - v1_cnn.mean() / v1_pid.mean()) * 100
        v2_improve = (1 - v2_cnn.mean() / v2_pid.mean()) * 100
        log.info("  v1 heading reduction: %.1f%%", v1_improve)
        log.info("  v2 heading reduction: %.1f%%", v2_improve)
        log.info("  Target: >50%% — %s", "PASS" if v2_improve > 50 else "NOT YET")

    log.info("")
    log.info("=" * 70)
    log.info("Done. Artifacts: %s", ARTIFACT_DIR)
    log.info("Exports: %s", EXPORT_DIR)
    log.info("=" * 70)


if __name__ == "__main__":
    main()
