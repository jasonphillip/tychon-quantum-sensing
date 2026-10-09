#!/usr/bin/env python3
"""Scalar residual correction: CNN/MLP as PID error de-embedder.

Trains both FCNN (2-channel) and MLP to predict ΔB = |B_true| - B_PID,
the scalar correction to the PID's line-pulling error.

Usage:
    python experiments/scalar_residual_comparison.py
"""

from __future__ import annotations

import logging
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

from tychon_odmr_ml.evaluation.residual_dataset import (
    ResidualDataset,
    generate_pid_labels,
)
from tychon_odmr_ml.models.fcnn import OdmrFCNN
from tychon_odmr_ml.models.mlp import OdmrMLP
from tychon_odmr_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from tychon_odmr_ml.training.qat import load_clean_weights, prepare_model_qat
from tychon_odmr_ml.validation.ops_guard import check_model_ops

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path.home() / "projects/tychon-shared-data/production_50k"
ARTIFACT_DIR = Path(__file__).resolve().parent / "scalar_residual"
NAS_DIR = Path("/mnt/nas/projects/tychon-artifacts/models")


# ---------------------------------------------------------------------------
# Dict-compatible Huber loss wrapper (matches CompositeAngularHuberLoss API)
# ---------------------------------------------------------------------------
class ScalarHuberLoss(nn.Module):
    """Huber loss that returns a dict compatible with the training loop."""

    def __init__(self, delta: float = 5.0) -> None:
        super().__init__()
        self.huber = nn.HuberLoss(reduction="mean", delta=delta)

    def forward(self, pred: torch.Tensor, true: torch.Tensor) -> dict[str, torch.Tensor]:
        loss = self.huber(pred, true)
        return {"loss": loss, "angular": torch.tensor(0.0), "huber": loss}


# ---------------------------------------------------------------------------
# Scalar validation function
# ---------------------------------------------------------------------------
def validate_scalar(
    model: nn.Module, val_loader: DataLoader, device: torch.device
) -> dict[str, float]:
    """Compute MAE and RMSE on scalar residual predictions."""
    model.eval()
    all_pred, all_true = [], []
    with torch.no_grad():
        for batch in val_loader:
            x = batch["spectra"].to(device)
            y = batch["b_field_uT"].to(device)
            pred = model(x)
            all_pred.append(pred)
            all_true.append(y)
    pred = torch.cat(all_pred)
    true = torch.cat(all_true)
    mae = (pred - true).abs().mean().item()
    rmse = ((pred - true) ** 2).mean().sqrt().item()
    return {"mae_uT": mae, "rmse_uT": rmse}


# ---------------------------------------------------------------------------
# Collate for residual dataset
# ---------------------------------------------------------------------------
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
        input_names=["input"], output_names=["delta_b_uT"],
        dynamic_axes={"input": {0: "batch"}, "delta_b_uT": {0: "batch"}},
        opset_version=17,
    )
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    log.info("  ONNX: %s (%.1f KB)", onnx_path, onnx_path.stat().st_size / 1024)


def convert_mlp_to_tflite_int8(model: nn.Module, cal: np.ndarray, path: Path) -> None:
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


def convert_fcnn_to_tflite_int8(model: OdmrFCNN, cal: np.ndarray, path: Path) -> None:
    import tensorflow as tf

    pt_convs = list(model.convs) + [model.conv_head]
    # Keras channels_last: (batch, H=1, W=100, C=in_channels)
    in_ch = model.in_channels
    inp = tf.keras.layers.Input(shape=(1, 100, in_ch))
    x = inp
    for i, pt_c in enumerate(pt_convs):
        is_last = i == len(pt_convs) - 1
        act = None if is_last else "relu"
        x = tf.keras.layers.Conv2D(
            pt_c.out_channels, pt_c.kernel_size, strides=pt_c.stride,
            activation=act, padding="valid")(x)
    x = tf.keras.layers.Flatten()(x)
    tf_model = tf.keras.Model(inputs=inp, outputs=x)
    tf_conv_layers = [l for l in tf_model.layers if isinstance(l, tf.keras.layers.Conv2D)]
    for pt_c, tf_l in zip(pt_convs, tf_conv_layers):
        w = pt_c.weight.detach().numpy().transpose(2, 3, 1, 0)
        tf_l.set_weights([w, pt_c.bias.detach().numpy()])
    # Reshape calibration: (N, 200) → (N, 1, 100, 2) NHWC
    cal_nhwc = cal.reshape(-1, in_ch, 1, 100).transpose(0, 2, 3, 1)
    _to_tflite_int8(tf_model, cal_nhwc, path)


def _to_tflite_int8(tf_model, cal: np.ndarray, path: Path) -> None:
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    def rep():
        for i in range(min(len(cal), 1000)):
            yield [cal[i:i+1].astype(np.float32)]
    converter.representative_dataset = rep
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8
    tflite = converter.convert()
    path.write_bytes(tflite)
    log.info("  TFLite INT8: %s (%.1f KB)", path, path.stat().st_size / 1024)


# ---------------------------------------------------------------------------
# Train + export one architecture
# ---------------------------------------------------------------------------
def run_architecture(
    name: str, model: nn.Module, input_dim: int,
    train_loader: DataLoader, val_loader: DataLoader,
    calibration: np.ndarray, device: torch.device,
) -> dict:
    arch_dir = ARTIFACT_DIR / name
    arch_dir.mkdir(parents=True, exist_ok=True)
    n_params = sum(p.numel() for p in model.parameters())

    log.info("=" * 60)
    log.info("ARCHITECTURE: %s (%d params)", name.upper(), n_params)
    log.info("=" * 60)

    # Ops guard
    report = check_model_ops(model, input_shape=(1, input_dim))
    log.info("  Ops guard: compatible=%s, allowed=%s", report.is_compatible, report.allowed)
    if report.disallowed:
        log.error("  DISALLOWED: %s", report.disallowed)
        sys.exit(1)

    init_weights_kaiming_he(model)

    # QAT
    log.info("  Preparing QAT (symmetric INT8)")
    qat_model = prepare_model_qat(model, example_input=torch.randn(1, input_dim))

    # Train
    config = TrainConfig(
        lr=1e-3, weight_decay=1e-3, epochs=100, T_max=100, eta_min=1e-5,
        batch_size=64, val_every=10, log_every=10, alpha=0.7,
        huber_delta=5.0, seed=42,
        checkpoint_dir=str(arch_dir / "checkpoints"),
    )
    criterion = ScalarHuberLoss(delta=5.0)
    results = train(
        qat_model, train_loader, val_loader, config, device,
        criterion=criterion, val_fn=validate_scalar,
    )

    log.info("  Final train loss: %.6f", results["final_train_loss"])
    log.info("  Training time: %.1fs", results["training_time_s"])
    if results["final_val_metrics"]:
        log.info("  Final val MAE: %.2f uT, RMSE: %.2f uT",
                 results["final_val_metrics"]["mae_uT"],
                 results["final_val_metrics"]["rmse_uT"])

    # Export clean model
    if name == "mlp":
        clean = OdmrMLP(input_dim=input_dim, output_dim=1, hidden_dims=[64, 32])
    else:
        clean = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    load_clean_weights(clean, qat_model)
    clean.eval()

    onnx_path = arch_dir / "model.onnx"
    export_onnx(clean, onnx_path, input_dim)

    tflite_path = arch_dir / "model_int8.tflite"
    if name == "mlp":
        convert_mlp_to_tflite_int8(clean, calibration, tflite_path)
    else:
        convert_fcnn_to_tflite_int8(clean, calibration, tflite_path)

    # Copy to NAS
    NAS_DIR.mkdir(parents=True, exist_ok=True)
    nas_tflite = NAS_DIR / f"{name}_residual_int8.tflite"
    nas_onnx = NAS_DIR / f"{name}_residual.onnx"
    shutil.copy2(tflite_path, nas_tflite)
    shutil.copy2(onnx_path, nas_onnx)
    log.info("  NAS: %s (%.1f KB)", nas_tflite, nas_tflite.stat().st_size / 1024)

    return {"name": name, "n_params": n_params, "results": results}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("SCALAR RESIDUAL COMPARISON: MLP vs FCNN")
    log.info("=" * 60)

    device = torch.device("cpu")

    # Generate PID labels if needed
    npz_path = DATA_DIR / "pid_residuals.npz"
    if not npz_path.exists():
        log.info("Generating PID labels...")
        generate_pid_labels(DATA_DIR)

    # Load PID stats
    npz = np.load(npz_path)
    pid_mae_train = np.abs(npz["train_delta_b_uT"]).mean()
    pid_mae_val = np.abs(npz["val_delta_b_uT"]).mean()
    log.info("PID baseline MAE: train=%.2f uT, val=%.2f uT", pid_mae_train, pid_mae_val)
    log.info("Residual range: [%.1f, %.1f] uT",
             npz["train_delta_b_uT"].min(), npz["train_delta_b_uT"].max())

    # Load datasets
    train_ds = ResidualDataset(DATA_DIR, "train")
    val_ds = ResidualDataset(DATA_DIR, "val")
    log.info("Train: %d, Val: %d, input dim: %d", len(train_ds), len(val_ds),
             train_ds.spectra.shape[1])

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True, collate_fn=collate_residual)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, collate_fn=collate_residual)

    calibration = train_ds.spectra.numpy()[:1000]

    # MLP: input_dim=200, output_dim=1
    mlp = OdmrMLP(input_dim=200, output_dim=1, hidden_dims=[64, 32])
    mlp_result = run_architecture(
        "mlp", mlp, 200, train_loader, val_loader, calibration, device)

    # FCNN: 2-channel input, 1 scalar output
    fcnn = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    fcnn_result = run_architecture(
        "fcnn", fcnn, 200, train_loader, val_loader, calibration, device)

    # Report
    log.info("")
    log.info("=" * 70)
    log.info("COMPARISON REPORT")
    log.info("=" * 70)
    log.info("%-30s %12s %12s %12s", "", "PID alone", "MLP", "FCNN")
    log.info("-" * 66)

    mlp_v = mlp_result["results"]["final_val_metrics"]
    fcnn_v = fcnn_result["results"]["final_val_metrics"]

    log.info("%-30s %12s %12d %12d", "Parameters", "—",
             mlp_result["n_params"], fcnn_result["n_params"])
    log.info("%-30s %12.2f %12.2f %12.2f", "Val MAE (uT)",
             pid_mae_val, mlp_v.get("mae_uT", 0), fcnn_v.get("mae_uT", 0))
    log.info("%-30s %12s %12.2f %12.2f", "Val RMSE (uT)", "—",
             mlp_v.get("rmse_uT", 0), fcnn_v.get("rmse_uT", 0))

    mlp_improve = (1 - mlp_v.get("mae_uT", pid_mae_val) / pid_mae_val) * 100
    fcnn_improve = (1 - fcnn_v.get("mae_uT", pid_mae_val) / pid_mae_val) * 100
    log.info("%-30s %12s %11.1f%% %11.1f%%", "Improvement over PID", "—",
             mlp_improve, fcnn_improve)

    log.info("")
    log.info("%-30s %12.1fs %12.1fs", "Training time",
             mlp_result["results"]["training_time_s"],
             fcnn_result["results"]["training_time_s"])
    log.info("")
    log.info("NAS artifacts: %s", NAS_DIR)
    log.info("Ready for vnnx_compile -c V250 on Beelink.")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
