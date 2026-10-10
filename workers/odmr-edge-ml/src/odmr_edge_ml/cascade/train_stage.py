"""Train one cascade stage end-to-end and emit deployable INT8 artifacts.

Encapsulates the per-stage training recipe used by both the production
``scalar_residual_v2.py`` script and the cascade orchestrator
``cascade_v1_train.py``: build OdmrFCNNv2, ops-guard the equivalent
export model, prepare QAT, instrument the σ parameter, train via the
canonical ``training.loop.train``, extract clean weights, export ONNX +
TFLite INT8, write the σ-trajectory CSV.

Deliberately *does not* know anything cascade-specific. The caller
supplies labels (so FINE can supply its own quantized-residual labels)
and the output directory, and gets back paths + the learned sigma.
"""

from __future__ import annotations

import logging
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler

from odmr_edge_ml.cascade.fine_labels import _run_tflite_int8
from odmr_edge_ml.export import export_onnx as _export_onnx_module
from odmr_edge_ml.models.fcnn import OdmrFCNN
from odmr_edge_ml.models.fcnn_v2 import OdmrFCNNv2
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.training.qat import extract_clean_state_dict, prepare_model_qat
from odmr_edge_ml.validation.ops_guard import check_model_ops
from odmr_edge_ml.validation.tflite_ops import verify_tflite_ops

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

log = logging.getLogger(__name__)


@dataclass
class StageResult:
    name: str
    clean_model: nn.Module
    learned_sigma: float
    onnx_path: Path
    tflite_path: Path
    sigma_trajectory_csv: Path
    val_metrics: dict[str, float]
    export_val_mae_uT: dict[str, float]
    training_time_s: float
    n_params: int
    sigma_trajectory: list[tuple[int, float, float]] = field(default_factory=list)


class _ScalarHuberLoss(nn.Module):
    """Local copy of ScalarHuberLoss to avoid coupling cascade to experiments/."""

    def __init__(self, delta: float = 10.0) -> None:
        super().__init__()
        self.huber = nn.HuberLoss(reduction="mean", delta=delta)

    def forward(
        self, pred: torch.Tensor, true: torch.Tensor,
    ) -> dict[str, torch.Tensor]:
        loss = self.huber(pred, true)
        return {"loss": loss, "angular": torch.tensor(0.0), "huber": loss}


def _validate_scalar(
    model: nn.Module, val_loader: DataLoader, device: torch.device,
) -> dict[str, float]:
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


def _collate(batch: list[dict]) -> dict[str, torch.Tensor]:
    return {
        "spectra": torch.stack([s["spectra"] for s in batch]),
        "b_field_uT": torch.stack([s["b_field_uT"] for s in batch]),
    }


class _ResidualTensorDataset(Dataset):
    """Wrap (combined, label) tensors into the dict format the loop expects."""

    def __init__(self, combined: torch.Tensor, labels: torch.Tensor) -> None:
        self.spectra = combined
        self.labels = labels

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        return {"spectra": self.spectra[idx], "b_field_uT": self.labels[idx]}


def _gaussian_anchor(
    lock_bins: np.ndarray, input_dim: int, sigma: float,
) -> np.ndarray:
    bins = np.arange(input_dim, dtype=np.float32)[None, :]
    centers = lock_bins.astype(np.float32).reshape(-1, 1)
    sigma_eff = float(max(sigma, 0.1))
    return np.exp(-0.5 * ((bins - centers) / sigma_eff) ** 2).astype(np.float32)


def _convert_to_tflite_int8(
    clean_model: nn.Module, calibration_nhwc: np.ndarray, path: Path,
) -> None:
    """Static-batch Keras export pattern; mirrors scalar_residual_v2:258-293.

    Calibration input is NHWC (M, 1, input_dim, in_channels=2).
    """
    import tensorflow as tf

    pt_convs = list(clean_model.convs) + [clean_model.conv_head]
    in_ch = clean_model.in_channels
    input_dim = clean_model.input_dim
    inp = tf.keras.layers.Input(
        batch_shape=(1, 1, input_dim, in_ch), name="odmr_input",
    )
    x = inp
    for i, pt_c in enumerate(pt_convs):
        is_last = i == len(pt_convs) - 1
        act = None if is_last else "relu"
        x = tf.keras.layers.Conv2D(
            pt_c.out_channels, pt_c.kernel_size, strides=pt_c.stride,
            activation=act, padding="valid",
            name=f"conv_{i}" if not is_last else "conv_head",
        )(x)
    tf_model = tf.keras.Model(inputs=inp, outputs=x)
    tf_conv_layers = [
        layer for layer in tf_model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    for pt_c, tf_l in zip(pt_convs, tf_conv_layers):
        w = pt_c.weight.detach().numpy().transpose(2, 3, 1, 0)
        tf_l.set_weights([w, pt_c.bias.detach().numpy()])

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def rep():
        n = min(len(calibration_nhwc), 1000)
        for i in range(n):
            yield [calibration_nhwc[i:i + 1].astype(np.float32)]

    converter.representative_dataset = rep
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite = converter.convert()
    path.write_bytes(tflite)
    verify_tflite_ops(tflite)
    log.info("  TFLite INT8: %s (%.1f KB)", path, path.stat().st_size / 1024)


def train_stage(
    *,
    name: str,
    train_spectra_norm: np.ndarray,   # (N, input_dim) symmetric-norm spectra
    train_lock_bins: np.ndarray,      # (N,)
    train_labels_uT: np.ndarray,      # (N,) clipped to ±clamp by caller
    val_spectra_norm: np.ndarray,
    val_lock_bins: np.ndarray,
    val_labels_uT: np.ndarray,
    output_dir: Path,
    device: torch.device,
    input_dim: int = 100,
    epochs: int = 100,
    batch_size: int = 64,
    lr: float = 1e-3,
    weight_decay: float = 1e-3,
    huber_delta: float = 10.0,
    seed: int = 42,
    use_compile: bool | None = None,
    num_workers: int = 4,
    use_autocast: bool | None = None,
    train_sample_weights: np.ndarray | None = None,
) -> StageResult:
    """Train one cascade stage and export INT8 artifacts.

    Caller responsibilities:
      * Spectra are already symmetrically-normalized.
      * Labels are already clipped to the desired ±clamp_uT range.
      * For FINE: labels = clip(b_true - b_pid - dequant(coarse_int8(x)), ±clamp).
    """
    output_dir = Path(output_dir)
    (output_dir / "checkpoints").mkdir(parents=True, exist_ok=True)

    log.info("[stage=%s] starting (%d train / %d val, input_dim=%d)",
             name, len(train_spectra_norm), len(val_spectra_norm), input_dim)

    # ---------- Build datasets in the (spectrum||lock_bin) 101-dim form ----
    def _combine(spectra: np.ndarray, lock_bins: np.ndarray) -> torch.Tensor:
        lock_col = lock_bins[:, None].astype(np.float32)
        combined = np.concatenate([spectra.astype(np.float32), lock_col], axis=1)
        return torch.from_numpy(combined).float()

    train_x = _combine(train_spectra_norm, train_lock_bins)
    val_x = _combine(val_spectra_norm, val_lock_bins)
    train_y = torch.from_numpy(train_labels_uT[:, None]).float()
    val_y = torch.from_numpy(val_labels_uT[:, None]).float()

    train_ds = _ResidualTensorDataset(train_x, train_y)
    val_ds = _ResidualTensorDataset(val_x, val_y)

    if train_sample_weights is not None:
        if train_sample_weights.shape != (len(train_x),):
            raise ValueError(
                f"train_sample_weights shape {train_sample_weights.shape} "
                f"!= ({len(train_x)},)"
            )
        sampler = WeightedRandomSampler(
            weights=torch.from_numpy(
                train_sample_weights.astype(np.float64),
            ),
            num_samples=len(train_x),
            replacement=True,
        )
        log.info(
            "[stage=%s] using WeightedRandomSampler (weights mean=%.4f, "
            "min=%.4f, max=%.4f, max/median=%.2f)",
            name,
            float(train_sample_weights.mean()),
            float(train_sample_weights.min()),
            float(train_sample_weights.max()),
            float(train_sample_weights.max() / max(np.median(train_sample_weights), 1e-12)),
        )
        train_loader = DataLoader(
            train_ds, batch_size=batch_size, sampler=sampler,
            collate_fn=_collate, pin_memory=True, num_workers=num_workers,
        )
    else:
        train_loader = DataLoader(
            train_ds, batch_size=batch_size, shuffle=True, collate_fn=_collate,
            pin_memory=True, num_workers=num_workers,
        )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, collate_fn=_collate,
        pin_memory=True, num_workers=num_workers,
    )

    # ---------- Build model + ops_guard the export shape ------------------
    model = OdmrFCNNv2(input_dim=input_dim, output_dim=1)
    n_params = sum(p.numel() for p in model.parameters())
    log.info("[stage=%s] OdmrFCNNv2: %d params (sigma init=%.2f)",
             name, n_params, model.sigma.item())

    export_check = OdmrFCNN(input_dim=input_dim, output_dim=1, in_channels=2)
    report = check_model_ops(export_check, input_shape=(1, 2 * input_dim))
    if not report.is_compatible:
        raise RuntimeError(
            f"[stage={name}] export model fails V250 ops_guard: {report.disallowed}"
        )
    del export_check
    init_weights_kaiming_he(model)

    # ---------- QAT + σ instrumentation -----------------------------------
    qat_model = prepare_model_qat(
        model, example_input=torch.randn(1, input_dim + 1),
    )
    sigma_param = next(
        (p for n, p in qat_model.named_parameters() if n.endswith("sigma")),
        None,
    )
    sigma_traj: list[tuple[int, float, float]] = []
    sigma_step = [0]
    if sigma_param is not None:
        def _hook(grad: torch.Tensor) -> torch.Tensor:
            sigma_traj.append((
                sigma_step[0],
                float(sigma_param.item()),
                float(grad.detach().norm().item()),
            ))
            sigma_step[0] += 1
            return grad
        sigma_param.register_hook(_hook)

    # ---------- GPU + optional torch.compile ------------------------------
    qat_model = qat_model.to(device)
    if use_compile is None:
        use_compile = device.type == "cuda"
    if use_compile:
        try:
            qat_model = torch.compile(qat_model)
        except Exception as exc:
            log.warning("[stage=%s] torch.compile failed (%s)", name, exc)

    # ---------- Train -----------------------------------------------------
    config = TrainConfig(
        lr=lr, weight_decay=weight_decay, epochs=epochs, T_max=epochs,
        eta_min=1e-5, batch_size=batch_size, val_every=max(1, epochs // 10),
        log_every=max(1, epochs // 10), alpha=0.7, huber_delta=huber_delta,
        seed=seed, checkpoint_dir=str(output_dir / "checkpoints"),
    )
    criterion = _ScalarHuberLoss(delta=huber_delta)
    # bf16 autocast on CUDA leaves checkpoints that do not reproduce the in-process
    # validation (plan N, 2026-10-10); use_autocast=False trains in fp32.
    autocast_enabled = (device.type == "cuda") if use_autocast is None else bool(use_autocast)
    t0 = time.time()
    with torch.autocast(
        device_type=device.type, dtype=torch.bfloat16, enabled=autocast_enabled,
    ):
        results = train(
            qat_model, train_loader, val_loader, config, device,
            criterion=criterion, val_fn=_validate_scalar,
        )
    training_time_s = time.time() - t0

    # ---------- Write σ trajectory CSV ------------------------------------
    sigma_csv = output_dir / "checkpoints" / f"sigma_trajectory_{name}.csv"
    with sigma_csv.open("w") as f:
        f.write("step,sigma,grad_norm\n")
        for step, sval, gn in sigma_traj:
            f.write(f"{step},{sval:.10f},{gn:.10g}\n")

    # ---------- Extract clean weights + build OdmrFCNN export model -------
    clean_sd = extract_clean_state_dict(qat_model)
    learned_sigma = float(clean_sd["sigma"].item())
    log.info("[stage=%s] learned sigma: %.4f", name, learned_sigma)

    clean = OdmrFCNN(input_dim=input_dim, output_dim=1, in_channels=2)
    export_sd = {k: v for k, v in clean_sd.items() if k in clean.state_dict()}
    clean.load_state_dict(export_sd, strict=True)
    clean.eval()

    # ---------- Export ONNX -----------------------------------------------
    onnx_path = output_dir / f"{name}.onnx"
    _export_onnx_module(
        clean, onnx_path, input_shape=(1, 2 * input_dim), skip_ops_check=True,
    )

    # ---------- Build calibration with LEARNED sigma → TFLite INT8 --------
    cal_anchors = _gaussian_anchor(
        train_lock_bins[:1000], input_dim, learned_sigma,
    )
    cal_combined = np.concatenate(
        [train_spectra_norm[:1000].astype(np.float32), cal_anchors], axis=1,
    )
    # (M, 200) → (M, 1, 100, 2) NHWC
    cal_nhwc = cal_combined.reshape(-1, 2, 1, input_dim).transpose(0, 2, 3, 1)
    tflite_path = output_dir / f"{name}_int8.tflite"
    _convert_to_tflite_int8(clean, cal_nhwc, tflite_path)

    val_metrics = results.get("final_val_metrics") or {}
    val_anchors = _gaussian_anchor(val_lock_bins, input_dim, learned_sigma)
    val_combined = np.concatenate(
        [val_spectra_norm.astype(np.float32), val_anchors], axis=1,
    )
    with torch.no_grad():
        float_preds = np.concatenate([
            clean(torch.from_numpy(batch)).numpy().reshape(-1)
            for batch in np.array_split(val_combined, range(batch_size, len(val_combined), batch_size))
        ])
    int8_preds = _run_tflite_int8(
        tflite_path, val_spectra_norm.astype(np.float32), val_anchors,
    )
    val_truth = val_labels_uT.reshape(-1)
    export_val_mae_uT = {
        "float": float(np.mean(np.abs(float_preds - val_truth))),
        "int8": float(np.mean(np.abs(int8_preds - val_truth))),
    }
    in_process_mae = val_metrics.get("mae_uT", float("nan"))
    for artifact, export_mae in export_val_mae_uT.items():
        if abs(export_mae - in_process_mae) > max(5.0, 0.5 * in_process_mae):
            log.warning(
                "[stage=%s] %s export val MAE %.4f µT differs from in-process %.4f µT",
                name, artifact, export_mae, in_process_mae,
            )
    log.info("[stage=%s] val MAE: %.4f µT (%.1fs total)",
             name, val_metrics.get("mae_uT", float("nan")), training_time_s)

    return StageResult(
        name=name,
        clean_model=clean,
        learned_sigma=learned_sigma,
        onnx_path=onnx_path,
        tflite_path=tflite_path,
        sigma_trajectory_csv=sigma_csv,
        val_metrics=val_metrics,
        export_val_mae_uT=export_val_mae_uT,
        training_time_s=training_time_s,
        n_params=n_params,
        sigma_trajectory=sigma_traj,
    )
