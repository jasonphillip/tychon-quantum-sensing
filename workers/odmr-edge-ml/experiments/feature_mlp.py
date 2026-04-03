#!/usr/bin/env python3
"""Physics-informed feature MLP: 5 spectral features → scalar ΔB residual.

Trains tiny MLPs on handcrafted physics features instead of raw 100-point
spectra. Validates on the 50K production dataset and evaluates heading
error reduction on the 360° sweep.

Training matrix:
  A1: 5→[16,8]→1 (241 params), unclipped labels
  A2: 5→[16,8]→1 (241 params), ±15 µT clipped
  B1: 5→[32,16]→1 (737 params), unclipped labels
  B2: 5→[32,16]→1 (737 params), ±15 µT clipped

Usage:
    python experiments/feature_mlp.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

from odmr_edge_ml.evaluation.feature_extraction import (
    FEATURE_NAMES,
    FeatureNormalizer,
    extract_features_batch,
)
from odmr_edge_ml.evaluation.residual_dataset import generate_pid_labels
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.training.qat import extract_clean_state_dict, prepare_model_qat
from odmr_edge_ml.validation.ops_guard import check_model_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data/production_50k"
ARTIFACT_DIR = Path(__file__).resolve().parent / "feature_mlp"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"
V1_SWEEP = Path(__file__).resolve().parent / "heading_sweep_results.npz"

CLAMP_LEVELS = [2.25, 5.0, 10.0, 15.0, 20.0, None]


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------
class FeatureDataset(Dataset):
    """5-feature dataset for scalar PID residual correction.

    Returns {"spectra": tensor(5,), "b_field_uT": tensor(1,)} to match
    the existing training loop's expected batch format.
    """

    def __init__(
        self,
        data_dir: Path,
        split: str,
        normalizer: FeatureNormalizer,
        clamp_uT: float | None = None,
    ) -> None:
        npz_path = data_dir / "pid_residuals.npz"
        if not npz_path.exists():
            log.info("PID labels not found, generating...")
            generate_pid_labels(data_dir)

        npz = np.load(npz_path)
        lock_bins = npz[f"{split}_lock_bins"]
        delta_b = npz[f"{split}_delta_b_uT"]

        with h5py.File(data_dir / "dataset.h5", "r") as f:
            spectra_raw = f[split]["spectra"][:]

        # Extract & normalize features
        raw_features = extract_features_batch(spectra_raw, lock_bins)
        normed = normalizer.transform(raw_features)

        # Optionally clip labels
        if clamp_uT is not None:
            n_clipped = int(np.sum(np.abs(delta_b) > clamp_uT))
            log.info(
                "%s: clipped %d/%d (%.1f%%) to ±%.1f µT",
                split, n_clipped, len(delta_b),
                100.0 * n_clipped / len(delta_b), clamp_uT,
            )
            delta_b = np.clip(delta_b, -clamp_uT, clamp_uT)

        self.features = torch.from_numpy(normed).float()
        self.labels = torch.from_numpy(delta_b[:, None]).float()

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, idx: int) -> dict:
        return {"spectra": self.features[idx], "b_field_uT": self.labels[idx]}


# ---------------------------------------------------------------------------
# Loss & validation (same API as scalar_residual_v2)
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
# Export helpers
# ---------------------------------------------------------------------------
def export_onnx(model: nn.Module, onnx_path: Path, input_dim: int) -> None:
    import onnx

    model.eval()
    dummy = torch.randn(1, input_dim)
    torch.onnx.export(
        model, (dummy,), str(onnx_path),
        input_names=["features"], output_names=["delta_b_uT"],
        dynamic_axes={"features": {0: "batch"}, "delta_b_uT": {0: "batch"}},
        opset_version=17,
    )
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    log.info("  ONNX: %s (%.1f KB)", onnx_path, onnx_path.stat().st_size / 1024)


def convert_mlp_to_tflite_int8(
    model: nn.Module, cal: np.ndarray, path: Path,
) -> None:
    import tensorflow as tf

    pt_linears = [m for m in model.modules() if isinstance(m, nn.Linear)]
    layers = []
    for i, lin in enumerate(pt_linears):
        is_last = i == len(pt_linears) - 1
        act = None if is_last else "relu"
        if i == 0:
            layers.append(tf.keras.layers.Dense(
                lin.out_features, activation=act, input_shape=(lin.in_features,)))
        else:
            layers.append(tf.keras.layers.Dense(lin.out_features, activation=act))
    tf_model = tf.keras.Sequential(layers)
    tf_model(tf.zeros((1, cal.shape[1])))
    for tf_l, pt_l in zip(tf_model.layers, pt_linears):
        tf_l.set_weights([pt_l.weight.detach().numpy().T, pt_l.bias.detach().numpy()])
    _to_tflite_int8(tf_model, cal, path)


def _to_tflite_int8(tf_model, cal: np.ndarray, path: Path) -> None:  # type: ignore[no-untyped-def]
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
# Train one model variant
# ---------------------------------------------------------------------------
def train_one_model(
    name: str,
    hidden_dims: list[int],
    clamp_uT: float | None,
    normalizer: FeatureNormalizer,
    device: torch.device,
) -> dict:
    """Train a single feature MLP variant and return results."""
    clamp_str = f"±{clamp_uT}" if clamp_uT else "unclipped"
    log.info("")
    log.info("=" * 60)
    log.info("TRAINING: %s  hidden=%s  clamp=%s", name, hidden_dims, clamp_str)
    log.info("=" * 60)

    # Datasets
    train_ds = FeatureDataset(DATA_DIR, "train", normalizer, clamp_uT)
    val_ds = FeatureDataset(DATA_DIR, "val", normalizer, clamp_uT)
    test_ds = FeatureDataset(DATA_DIR, "test", normalizer, clamp_uT)

    train_loader = DataLoader(
        train_ds, batch_size=64, shuffle=True, collate_fn=collate_residual,
    )
    val_loader = DataLoader(
        val_ds, batch_size=64, shuffle=False, collate_fn=collate_residual,
    )
    test_loader = DataLoader(
        test_ds, batch_size=64, shuffle=False, collate_fn=collate_residual,
    )

    # Model
    model = OdmrMLP(input_dim=5, output_dim=1, hidden_dims=hidden_dims)
    n_params = sum(p.numel() for p in model.parameters())
    log.info("  %s: %d params", name, n_params)

    # Ops guard
    report = check_model_ops(model, input_shape=(1, 5))
    log.info("  Ops guard: compatible=%s", report.is_compatible)
    if report.disallowed:
        log.error("  DISALLOWED ops: %s", report.disallowed)
        sys.exit(1)

    init_weights_kaiming_he(model)

    # QAT
    qat_model = prepare_model_qat(model, example_input=torch.randn(1, 5))

    # Train
    ckpt_dir = str(ARTIFACT_DIR / name / "checkpoints")
    config = TrainConfig(
        lr=1e-2, weight_decay=1e-3, epochs=200, T_max=200, eta_min=1e-5,
        batch_size=64, val_every=10, log_every=20, alpha=0.7,
        huber_delta=10.0, seed=42,
        checkpoint_dir=ckpt_dir,
    )
    criterion = ScalarHuberLoss(delta=10.0)
    results = train(
        qat_model, train_loader, val_loader, config, device,
        criterion=criterion, val_fn=validate_scalar,
    )

    # Extract clean model
    clean_sd = extract_clean_state_dict(qat_model)
    clean_model = OdmrMLP(input_dim=5, output_dim=1, hidden_dims=hidden_dims)
    clean_model.load_state_dict(clean_sd, strict=True)
    clean_model.eval()

    # Evaluate on all splits
    train_metrics = validate_scalar(clean_model, train_loader, device)
    val_metrics = validate_scalar(clean_model, val_loader, device)
    test_metrics = validate_scalar(clean_model, test_loader, device)

    log.info("  Train MAE: %.4f µT", train_metrics["mae_uT"])
    log.info("  Val   MAE: %.4f µT", val_metrics["mae_uT"])
    log.info("  Test  MAE: %.4f µT", test_metrics["mae_uT"])

    return {
        "name": name,
        "hidden_dims": hidden_dims,
        "n_params": n_params,
        "clamp_uT": clamp_uT,
        "clean_model": clean_model,
        "train_mae": train_metrics["mae_uT"],
        "val_mae": val_metrics["mae_uT"],
        "test_mae": test_metrics["mae_uT"],
        "training_time_s": results["training_time_s"],
    }


# ---------------------------------------------------------------------------
# Heading sweep evaluation
# ---------------------------------------------------------------------------
def evaluate_heading_sweep(
    model: nn.Module,
    normalizer: FeatureNormalizer,
    clamp_levels: list[float | None],
    sweep_path: Path,
) -> dict:
    """Evaluate model on saved heading sweep data at multiple clamp levels."""
    data = np.load(sweep_path)
    spectra = data["spectra"]        # (1440, 100)
    lock_bins = data["pid_lock_bins"]  # (1440,)
    pid_uT = data["pid_estimates_uT"]  # (1440,)
    b_true_uT = float(data["b_mag_true_uT"])

    # Extract & normalize features
    raw_features = extract_features_batch(spectra, lock_bins)
    normed = normalizer.transform(raw_features)
    x = torch.from_numpy(normed).float()

    # Predict
    model.eval()
    with torch.no_grad():
        delta_b = model(x).squeeze(-1).numpy()  # (1440,)

    pid_error = np.abs(pid_uT - b_true_uT)
    pid_mae = pid_error.mean()

    results = {}
    for clamp in clamp_levels:
        if clamp is not None:
            delta_clamped = np.clip(delta_b, -clamp, clamp)
            key = f"±{clamp}"
        else:
            delta_clamped = delta_b
            key = "unclamped"

        corrected = pid_uT + delta_clamped
        error = np.abs(corrected - b_true_uT)
        mae = error.mean()
        reduction = (1.0 - mae / pid_mae) * 100.0

        results[key] = {
            "mae": mae,
            "max": error.max(),
            "p50": float(np.percentile(error, 50)),
            "p95": float(np.percentile(error, 95)),
            "reduction": reduction,
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 70)
    log.info("PHYSICS-INFORMED FEATURE MLP")
    log.info("=" * 70)

    device = torch.device("cpu")

    # -- PID labels --
    npz_path = DATA_DIR / "pid_residuals.npz"
    if not npz_path.exists():
        log.info("Generating PID labels...")
        generate_pid_labels(DATA_DIR)

    npz = np.load(npz_path)
    pid_mae_val = float(np.abs(npz["val_delta_b_uT"]).mean())
    log.info("PID baseline val MAE: %.2f µT", pid_mae_val)

    # -- Extract features from training set to fit normalizer --
    with h5py.File(DATA_DIR / "dataset.h5", "r") as f:
        train_spectra = f["train"]["spectra"][:]

    train_lock_bins = npz["train_lock_bins"]
    train_features = extract_features_batch(train_spectra, train_lock_bins)

    normalizer = FeatureNormalizer()
    normalizer.fit(train_features)

    log.info("")
    log.info("Feature statistics (training set, %d samples):", len(train_features))
    for j, name in enumerate(FEATURE_NAMES):
        col = train_features[:, j]
        log.info(
            "  %-15s mean=%.6f  std=%.6f  range=[%.6f, %.6f]",
            name, col.mean(), col.std(), col.min(), col.max(),
        )
    log.info("")
    log.info("Normalizer mean: %s", normalizer.mean_)
    log.info("Normalizer std:  %s", normalizer.std_)

    # -- Feature-target correlations --
    delta_b_train = npz["train_delta_b_uT"]
    log.info("")
    log.info("Feature-target correlations (Pearson r with delta_b):")
    for j, name in enumerate(FEATURE_NAMES):
        r = np.corrcoef(train_features[:, j], delta_b_train)[0, 1]
        log.info("  %-15s r=%.4f", name, r)

    # -- Train 4 models --
    model_configs = [
        ("a1_unclipped",  [16, 8],  None),
        ("a2_clipped15",  [16, 8],  15.0),
        ("b1_unclipped",  [32, 16], None),
        ("b2_clipped15",  [32, 16], 15.0),
    ]

    all_results = []
    for name, hidden, clamp in model_configs:
        res = train_one_model(name, hidden, clamp, normalizer, device)
        all_results.append(res)

    # -- Heading sweep evaluation --
    if not V1_SWEEP.exists():
        log.warning("Heading sweep data not found: %s", V1_SWEEP)
        log.warning("Run experiments/heading_sweep.py first.")
        return

    log.info("")
    log.info("=" * 70)
    log.info("HEADING SWEEP EVALUATION")
    log.info("=" * 70)

    sweep_data = np.load(V1_SWEEP)
    pid_sweep_mae = np.abs(sweep_data["pid_estimates_uT"] - float(sweep_data["b_mag_true_uT"])).mean()
    log.info("PID-only sweep MAE: %.3f µT", pid_sweep_mae)

    # V1 FCNN results for comparison
    v1_cnn_error = sweep_data["cnn_error_uT"]
    v1_mae = v1_cnn_error.mean()
    v1_reduction = (1.0 - v1_mae / pid_sweep_mae) * 100.0

    best_model_name = None
    best_reduction = -999.0
    best_clamp = None

    for res in all_results:
        sweep_results = evaluate_heading_sweep(
            res["clean_model"], normalizer, CLAMP_LEVELS, V1_SWEEP,
        )
        res["sweep"] = sweep_results

        log.info("")
        log.info("--- %s (%d params, clamp=%s) ---",
                 res["name"], res["n_params"],
                 f"±{res['clamp_uT']}" if res["clamp_uT"] else "unclipped")
        log.info("  %-12s %8s %8s %8s %8s %10s",
                 "Clamp", "MAE", "Max", "P50", "P95", "Reduction")
        log.info("  " + "-" * 60)
        for key, vals in sweep_results.items():
            log.info("  %-12s %7.3f %7.3f %7.3f %7.3f %9.1f%%",
                     key, vals["mae"], vals["max"], vals["p50"], vals["p95"],
                     vals["reduction"])
            if vals["reduction"] > best_reduction:
                best_reduction = vals["reduction"]
                best_model_name = res["name"]
                best_clamp = key

    # -- Summary table --
    log.info("")
    log.info("=" * 70)
    log.info("SUMMARY: HEADING SWEEP COMPARISON")
    log.info("=" * 70)
    log.info("  %-30s %7s %9s %9s %10s",
             "", "Params", "Val MAE", "Sweep MAE", "Reduction")
    log.info("  " + "-" * 65)
    log.info("  %-30s %7s %8.2f %9.3f %10s",
             "PID-only", "—", pid_mae_val, pid_sweep_mae, "—")
    log.info("  %-30s %7d %8s %9.3f %9.1f%%",
             "FCNN v1 (200-dim)", 3299, "—", v1_mae, v1_reduction)

    for res in all_results:
        # Use unclamped sweep result for the summary
        unclamped = res["sweep"]["unclamped"]
        log.info("  %-30s %7d %8.4f %9.3f %9.1f%%",
                 f"Feature MLP {res['name']}",
                 res["n_params"], res["val_mae"],
                 unclamped["mae"], unclamped["reduction"])

    log.info("")
    log.info("Best heading reduction: %.1f%% (%s at clamp %s)",
             best_reduction, best_model_name, best_clamp)

    # -- Export best model --
    best_res = next(r for r in all_results if r["name"] == best_model_name)
    best_model = best_res["clean_model"]

    log.info("")
    log.info("=" * 70)
    log.info("EXPORTING BEST MODEL: %s", best_model_name)
    log.info("=" * 70)

    best_dir = ARTIFACT_DIR / "best"
    best_dir.mkdir(parents=True, exist_ok=True)

    # ONNX
    onnx_path = best_dir / "model.onnx"
    export_onnx(best_model, onnx_path, input_dim=5)

    # TFLite INT8
    tflite_path = best_dir / "model_int8.tflite"
    train_normed = normalizer.transform(train_features)[:1000]
    convert_mlp_to_tflite_int8(best_model, train_normed, tflite_path)

    # Save normalizer
    norm_path = best_dir / "normalizer.npz"
    normalizer.save(norm_path)

    # Deployment metadata
    np.savez(
        best_dir / "deployment_metadata.npz",
        normalizer_mean=normalizer.mean_,
        normalizer_std=normalizer.std_,
        feature_names=np.array(FEATURE_NAMES),
        best_clamp=str(best_clamp),
        input_dim=np.int64(5),
        hidden_dims=np.array(best_res["hidden_dims"]),
        n_params=np.int64(best_res["n_params"]),
        model_version="feature_mlp_v1",
        val_mae_uT=np.float64(best_res["val_mae"]),
        test_mae_uT=np.float64(best_res["test_mae"]),
        heading_reduction_pct=np.float64(best_reduction),
    )
    log.info("  Metadata: %s", best_dir / "deployment_metadata.npz")

    # Copy to exports
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        exp_tflite = EXPORT_DIR / "feature_mlp_residual_int8.tflite"
        exp_onnx = EXPORT_DIR / "feature_mlp_residual.onnx"
        shutil.copy2(tflite_path, exp_tflite)
        shutil.copy2(onnx_path, exp_onnx)
        log.info("  Export: %s", exp_tflite)
    except OSError as e:
        log.warning("  Export copy failed: %s", e)

    # -- Save all results --
    results_path = ARTIFACT_DIR / "results.npz"
    save_dict = {}
    for res in all_results:
        prefix = res["name"]
        save_dict[f"{prefix}_val_mae"] = np.float64(res["val_mae"])
        save_dict[f"{prefix}_test_mae"] = np.float64(res["test_mae"])
        save_dict[f"{prefix}_train_mae"] = np.float64(res["train_mae"])
        save_dict[f"{prefix}_n_params"] = np.int64(res["n_params"])
        for clamp_key, vals in res["sweep"].items():
            ck = clamp_key.replace("±", "pm").replace("unclamped", "unc")
            save_dict[f"{prefix}_sweep_{ck}_mae"] = np.float64(vals["mae"])
            save_dict[f"{prefix}_sweep_{ck}_reduction"] = np.float64(vals["reduction"])
    save_dict["pid_sweep_mae"] = np.float64(pid_sweep_mae)
    save_dict["fcnn_v1_sweep_mae"] = np.float64(v1_mae)
    save_dict["fcnn_v1_reduction"] = np.float64(v1_reduction)
    np.savez(results_path, **save_dict)
    log.info("  Results: %s", results_path)

    log.info("")
    log.info("=" * 70)
    log.info("Done. Artifacts: %s", ARTIFACT_DIR)
    log.info("=" * 70)


if __name__ == "__main__":
    main()
