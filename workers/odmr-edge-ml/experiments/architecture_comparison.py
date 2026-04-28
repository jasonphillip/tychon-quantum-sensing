#!/usr/bin/env python3
"""Architecture comparison: MLP vs Fully Convolutional CNN on 50K production dataset.

Both architectures use QAT (symmetric INT8) from epoch 1, then export through:
PyTorch → ONNX → TFLite INT8 → VectorBlox V250 compilation.

Usage:
    python experiments/architecture_comparison.py
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

# Suppress FX QAT deprecation noise (functional on torch 2.11)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

# Repo utilities
from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.models.fcnn import OdmrFCNN
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.training.qat import load_clean_weights, prepare_model_qat
from odmr_edge_ml.validation.ops_guard import check_model_ops

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data/production_50k"
ARTIFACT_DIR = Path(__file__).resolve().parent / "architecture_comparison"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"


# ---------------------------------------------------------------------------
# Dataset (adapted from pipeline_validation.py GoldenDataset)
# ---------------------------------------------------------------------------
class ProductionDataset(Dataset):
    """PyTorch Dataset for production HDF5 data with uT conversion."""

    def __init__(self, data_dir: Path, split: str = "train") -> None:
        h5_path = data_dir / "dataset.h5"
        with h5py.File(h5_path, "r") as f:
            g = f[split]
            spectra_raw = g["spectra"][:]
            labels_T = g["labels"][:]
            corruption_params = g["corruption_params"][:]

        spectra = DatasetLoader.normalize_spectra(spectra_raw)
        labels_uT = labels_T * 1e6

        # Fold Bz sign ambiguity
        if labels_uT[:, 2].min() < 0 and labels_uT[:, 2].max() > 0:
            neg_mask = labels_uT[:, 2] < 0
            labels_uT[neg_mask] *= -1.0

        self.spectra = torch.from_numpy(spectra).float()
        self.labels_uT = torch.from_numpy(labels_uT).float()
        self.corruption_params = torch.from_numpy(corruption_params).float()

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {
            "spectra": self.spectra[idx],
            "b_field_uT": self.labels_uT[idx],
            "meta": {"corruption_params": self.corruption_params[idx]},
        }


def collate_with_meta(batch: list[dict]) -> dict:
    """Stack tensors and nested meta dicts."""
    spectra = torch.stack([s["spectra"] for s in batch])
    b_field_uT = torch.stack([s["b_field_uT"] for s in batch])
    result: dict = {"spectra": spectra, "b_field_uT": b_field_uT}
    if "meta" in batch[0] and batch[0]["meta"] is not None:
        meta: dict = {}
        for key in batch[0]["meta"]:
            values = [s["meta"][key] for s in batch]
            if isinstance(values[0], torch.Tensor):
                meta[key] = torch.stack(values)
            else:
                meta[key] = values
        result["meta"] = meta
    return result


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def export_onnx(model: nn.Module, onnx_path: Path) -> None:
    """Export PyTorch model to ONNX."""
    import onnx

    model.eval()
    dummy = torch.randn(1, 100)
    torch.onnx.export(
        model,
        (dummy,),
        str(onnx_path),
        input_names=["spectrum"],
        output_names=["b_field_uT"],
        dynamic_axes={"spectrum": {0: "batch"}, "b_field_uT": {0: "batch"}},
        opset_version=17,
    )
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    size_kb = onnx_path.stat().st_size / 1024
    log.info("  ONNX exported: %s (%.1f KB)", onnx_path, size_kb)


def convert_mlp_to_tflite_int8(
    model: nn.Module,
    calibration_spectra: np.ndarray,
    tflite_path: Path,
) -> None:
    """Convert PyTorch MLP to TFLite INT8 via weight-copy to Keras."""
    import tensorflow as tf

    layers: list[tf.keras.layers.Layer] = []
    pt_linears: list[nn.Linear] = [
        m for m in model.modules() if isinstance(m, nn.Linear)
    ]

    for i, linear in enumerate(pt_linears):
        is_last = i == len(pt_linears) - 1
        activation = None if is_last else "relu"
        in_features = linear.in_features
        out_features = linear.out_features

        if i == 0:
            layer = tf.keras.layers.Dense(
                out_features, activation=activation, input_shape=(in_features,)
            )
        else:
            layer = tf.keras.layers.Dense(out_features, activation=activation)
        layers.append(layer)

    tf_model = tf.keras.Sequential(layers)
    tf_model(tf.zeros((1, 100)))

    # Copy weights: PyTorch (out, in) -> Keras (in, out)
    for tf_layer, pt_linear in zip(tf_model.layers, pt_linears):
        w = pt_linear.weight.detach().numpy().T
        b = pt_linear.bias.detach().numpy()
        tf_layer.set_weights([w, b])

    # Verify fidelity
    test_input = calibration_spectra[:4].astype(np.float32)
    pt_out = model(torch.from_numpy(test_input)).detach().numpy()
    tf_out = tf_model(test_input).numpy()
    max_diff = np.abs(pt_out - tf_out).max()
    log.info("  MLP weight-copy fidelity: max |PT - TF| = %.2e", max_diff)
    assert max_diff < 1e-4, f"Weight copy divergence: {max_diff}"

    _convert_keras_to_tflite_int8(tf_model, calibration_spectra, tflite_path)


def convert_fcnn_to_tflite_int8(
    model: OdmrFCNN,
    calibration_spectra: np.ndarray,
    tflite_path: Path,
) -> None:
    """Convert PyTorch FCNN to TFLite INT8 via weight-copy to Keras.

    Keras uses channels_last (NHWC). Input is *fixed-batch*
    (1, 1, 100, in_channels) and the trailing Flatten is dropped so the
    converter never emits SHAPE / STRIDED_SLICE / PACK ops — see
    scripts/fix_fcnn_export.py for the reference pattern.

    Weights are transposed from PyTorch (C_out, C_in, kH, kW) to Keras
    (kH, kW, C_in, C_out). For fidelity verification we run the Keras model
    one sample at a time because the fixed-batch input forbids batched eval.
    """
    import tensorflow as tf

    in_ch = model.in_channels
    pt_convs: list[nn.Conv2d] = list(model.convs) + [model.conv_head]

    # Fixed batch=1 NHWC input — eliminates dynamic shape ops.
    inp = tf.keras.layers.Input(
        batch_shape=(1, 1, 100, in_ch), name="odmr_input",
    )
    x = inp
    for i, pt_conv in enumerate(pt_convs):
        is_last = i == len(pt_convs) - 1
        activation = None if is_last else "relu"
        x = tf.keras.layers.Conv2D(
            filters=pt_conv.out_channels,
            kernel_size=pt_conv.kernel_size,
            strides=pt_conv.stride,
            activation=activation,
            padding="valid",
            name=f"conv_{i}" if not is_last else "conv_head",
        )(x)
    tf_model = tf.keras.Model(inputs=inp, outputs=x)

    # Copy weights: PT (C_out, C_in, kH, kW) -> Keras (kH, kW, C_in, C_out)
    tf_conv_layers = [
        layer for layer in tf_model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    for pt_conv, tf_layer in zip(pt_convs, tf_conv_layers):
        w = pt_conv.weight.detach().numpy().transpose(2, 3, 1, 0)
        b = pt_conv.bias.detach().numpy()
        tf_layer.set_weights([w, b])

    # Fidelity check (one sample at a time because batch is fixed at 1).
    test_np = calibration_spectra[:4].astype(np.float32)
    pt_out = model(torch.from_numpy(test_np)).detach().numpy()
    tf_in = test_np.reshape(-1, 1, 100, in_ch)
    tf_outs = np.stack([
        tf_model(tf_in[i:i + 1]).numpy().reshape(-1) for i in range(len(tf_in))
    ])
    tf_out = tf_outs.reshape(pt_out.shape)
    max_diff = np.abs(pt_out - tf_out).max()
    log.info("  FCNN weight-copy fidelity: max |PT - TF| = %.2e", max_diff)
    assert max_diff < 1e-4, f"Weight copy divergence: {max_diff}"

    # Calibration data reshaped for NHWC.
    cal_nhwc = calibration_spectra.reshape(-1, 1, 100, in_ch)
    _convert_keras_to_tflite_int8(tf_model, cal_nhwc, tflite_path)


def _convert_keras_to_tflite_int8(
    tf_model,
    calibration_data: np.ndarray,
    tflite_path: Path,
) -> None:
    """Convert Keras model to TFLite INT8 with representative dataset."""
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset():
        for i in range(min(len(calibration_data), 1000)):
            yield [calibration_data[i : i + 1].astype(np.float32)]

    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_model = converter.convert()
    tflite_path.write_bytes(tflite_model)

    size_kb = tflite_path.stat().st_size / 1024
    log.info("  TFLite INT8: %s (%.1f KB)", tflite_path, size_kb)


# ---------------------------------------------------------------------------
# Train + export one architecture
# ---------------------------------------------------------------------------
def run_architecture(
    name: str,
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    calibration_spectra: np.ndarray,
    device: torch.device,
) -> dict:
    """Train one architecture with QAT and export full pipeline."""
    arch_dir = ARTIFACT_DIR / name
    arch_dir.mkdir(parents=True, exist_ok=True)

    n_params = sum(p.numel() for p in model.parameters())
    log.info("=" * 60)
    log.info("ARCHITECTURE: %s (%d parameters)", name.upper(), n_params)
    log.info("=" * 60)

    # ── Ops guard ─────────────────────────────────────────────
    log.info("[1/6] Running ops_guard")
    report = check_model_ops(model, input_shape=(1, 100))
    log.info("  Compatible: %s | Allowed: %s", report.is_compatible, report.allowed)
    if report.disallowed:
        log.error("  DISALLOWED: %s", report.disallowed)
        sys.exit(1)
    if report.unknown:
        log.warning("  Unknown: %s", report.unknown)

    # ── Kaiming He init ───────────────────────────────────────
    log.info("[2/6] Initializing weights (Kaiming He)")
    init_weights_kaiming_he(model)

    # ── QAT preparation ──────────────────────────────────────
    log.info("[3/6] Preparing QAT (symmetric INT8, FX graph mode)")
    qat_model = prepare_model_qat(model, example_input=torch.randn(1, 100))

    # ── Training ──────────────────────────────────────────────
    log.info("[4/6] Training for 100 epochs with QAT")
    config = TrainConfig(
        lr=1e-3,
        weight_decay=1e-3,
        epochs=100,
        T_max=100,
        eta_min=1e-5,
        batch_size=64,
        val_every=10,
        log_every=5,
        alpha=0.7,
        huber_delta=1.0,
        seed=42,
        checkpoint_dir=str(arch_dir / "checkpoints"),
    )
    results = train(qat_model, train_loader, val_loader, config, device)

    log.info("  Final train loss: %.6f", results["final_train_loss"])
    log.info("  Best val angle err: %.4f deg", results["best_val_angle_err"])
    log.info("  Training time: %.1fs", results["training_time_s"])

    # ── Export: load clean weights ────────────────────────────
    log.info("[5/6] Exporting (ONNX + TFLite INT8)")

    if name == "mlp":
        clean_model = OdmrMLP(input_dim=100, output_dim=3, hidden_dims=[64, 32])
    else:
        clean_model = OdmrFCNN(input_dim=100, output_dim=3)
    load_clean_weights(clean_model, qat_model)
    clean_model.eval()

    # ONNX
    onnx_path = arch_dir / "model.onnx"
    export_onnx(clean_model, onnx_path)

    # TFLite INT8
    tflite_path = arch_dir / "model_int8.tflite"
    if name == "mlp":
        convert_mlp_to_tflite_int8(clean_model, calibration_spectra, tflite_path)
    else:
        convert_fcnn_to_tflite_int8(clean_model, calibration_spectra, tflite_path)

    # ── Copy to exports ──────────────────────────────────────
    log.info("[6/6] Copying to exports")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    exp_tflite = EXPORT_DIR / f"{name}_50k_int8.tflite"
    exp_onnx = EXPORT_DIR / f"{name}_50k.onnx"
    shutil.copy2(tflite_path, exp_tflite)
    shutil.copy2(onnx_path, exp_onnx)
    log.info("  -> %s (%.1f KB)", exp_tflite, exp_tflite.stat().st_size / 1024)
    log.info("  -> %s (%.1f KB)", exp_onnx, exp_onnx.stat().st_size / 1024)

    return {
        "name": name,
        "n_params": n_params,
        "results": results,
        "onnx_path": onnx_path,
        "tflite_path": tflite_path,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("ARCHITECTURE COMPARISON: MLP vs FCNN on 50K Production Dataset")
    log.info("=" * 60)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("Device: %s", device)

    # ── Load data ─────────────────────────────────────────────
    log.info("Loading production 50K dataset from %s", DATA_DIR)
    train_ds = ProductionDataset(DATA_DIR, split="train")
    val_ds = ProductionDataset(DATA_DIR, split="val")
    log.info("  Train: %d samples, Val: %d samples", len(train_ds), len(val_ds))

    train_loader = DataLoader(
        train_ds, batch_size=64, shuffle=True, collate_fn=collate_with_meta,
        pin_memory=True, num_workers=4,
    )
    val_loader = DataLoader(
        val_ds, batch_size=64, shuffle=False, collate_fn=collate_with_meta,
        pin_memory=True, num_workers=4,
    )

    # Calibration data for TFLite (subsample for speed)
    calibration_spectra = train_ds.spectra.numpy()[:1000]

    # ── Architecture 1: MLP ───────────────────────────────────
    mlp = OdmrMLP(input_dim=100, output_dim=3, hidden_dims=[64, 32])
    mlp_result = run_architecture(
        "mlp", mlp, train_loader, val_loader, calibration_spectra, device
    )

    # ── Architecture 2: FCNN ──────────────────────────────────
    fcnn = OdmrFCNN(input_dim=100, output_dim=3)
    fcnn_result = run_architecture(
        "fcnn", fcnn, train_loader, val_loader, calibration_spectra, device
    )

    # ── Comparison Report ─────────────────────────────────────
    log.info("")
    log.info("=" * 70)
    log.info("COMPARISON REPORT")
    log.info("=" * 70)
    log.info("")
    log.info("%-25s %15s %15s", "", "MLP", "FCNN")
    log.info("-" * 55)

    mlp_r = mlp_result["results"]
    fcnn_r = fcnn_result["results"]

    log.info("%-25s %15d %15d", "Parameters",
             mlp_result["n_params"], fcnn_result["n_params"])
    log.info("%-25s %15.1fs %15.1fs", "Training time",
             mlp_r["training_time_s"], fcnn_r["training_time_s"])
    log.info("%-25s %15.6f %15.6f", "Final train loss",
             mlp_r["final_train_loss"], fcnn_r["final_train_loss"])
    log.info("%-25s %15.4f %15.4f", "Best val angle err (deg)",
             mlp_r["best_val_angle_err"], fcnn_r["best_val_angle_err"])

    if mlp_r["final_val_metrics"] and fcnn_r["final_val_metrics"]:
        mlp_v = mlp_r["final_val_metrics"]
        fcnn_v = fcnn_r["final_val_metrics"]
        log.info("%-25s %15.4f %15.4f", "Final angle err (deg)",
                 mlp_v["angle_err_deg"], fcnn_v["angle_err_deg"])
        log.info("%-25s %15.1f %15.1f", "Final mag err (nT)",
                 mlp_v["magnitude_err_nT"], fcnn_v["magnitude_err_nT"])
        log.info("%-25s %15.1f %15.1f", "Final Bx err (nT)",
                 mlp_v["bx_err_nT"], fcnn_v["bx_err_nT"])
        log.info("%-25s %15.1f %15.1f", "Final By err (nT)",
                 mlp_v["by_err_nT"], fcnn_v["by_err_nT"])
        log.info("%-25s %15.1f %15.1f", "Final Bz err (nT)",
                 mlp_v["bz_err_nT"], fcnn_v["bz_err_nT"])
        if "fano_bias_nT" in mlp_v:
            log.info("%-25s %15.1f %15.1f", "Fano bias (nT)",
                     mlp_v["fano_bias_nT"], fcnn_v["fano_bias_nT"])
        if "heading_bias_deg" in mlp_v:
            log.info("%-25s %15.4f %15.4f", "Heading bias (deg)",
                     mlp_v["heading_bias_deg"], fcnn_v["heading_bias_deg"])

    log.info("")
    log.info("%-25s %s", "MLP ONNX", mlp_result["onnx_path"])
    log.info("%-25s %s", "MLP TFLite", mlp_result["tflite_path"])
    log.info("%-25s %s", "FCNN ONNX", fcnn_result["onnx_path"])
    log.info("%-25s %s", "FCNN TFLite", fcnn_result["tflite_path"])
    log.info("%-25s %s", "Export dir", EXPORT_DIR)
    log.info("")

    # Loss curve summary (first and last epoch for each)
    log.info("LOSS CURVES (first -> last):")
    for res in [mlp_result, fcnn_result]:
        hist = res["results"]["epoch_history"]
        first = hist[0]["train_loss"]
        last = hist[-1]["train_loss"]
        log.info("  %s: %.6f -> %.6f (%.1fx reduction)",
                 res["name"].upper(), first, last, first / max(last, 1e-10))

    log.info("")
    log.info("=" * 70)
    log.info("DONE. TFLite models ready for vnnx_compile -c V250.")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
