#!/usr/bin/env python3
"""End-to-end pipeline validation: golden dataset → train → ONNX → TFLite INT8 → NAS.

Throwaway script proving data flows through the full export pipeline.
Model quality is irrelevant — this validates the pipeline, not convergence.

Usage:
    python experiments/pipeline_validation.py
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

# Reuse repo utilities
from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.validation.ops_guard import check_model_ops

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data/golden"
ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
EXPORT_DIR = Path(__file__).resolve().parent.parent / "exports"


# ---------------------------------------------------------------------------
# Dataset (self-contained, adapted from scripts/run_first_train.py)
# ---------------------------------------------------------------------------
class GoldenDataset(Dataset):
    """PyTorch Dataset for golden HDF5 data with µT conversion."""

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
    # Validate
    onnx_model = onnx.load(str(onnx_path))
    onnx.checker.check_model(onnx_model)
    size_kb = onnx_path.stat().st_size / 1024
    log.info("ONNX exported: %s (%.1f KB)", onnx_path, size_kb)


def convert_to_tflite_int8(
    model: nn.Module,
    calibration_spectra: np.ndarray,
    tflite_path: Path,
) -> None:
    """Convert PyTorch MLP to TFLite INT8 via weight-copy to Keras.

    Weight-copy approach because onnx2tf/onnx-tf have compatibility issues
    with Python 3.13 + ONNX 1.21 + TF 2.21. For this MLP architecture
    (Linear→ReLU chains), the transfer is trivial and bit-exact.
    """
    import tensorflow as tf

    # Build equivalent Keras model and copy weights
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
    # Build the model by calling it once
    tf_model(tf.zeros((1, 100)))

    # Copy weights: PyTorch Linear stores (out, in), Keras Dense expects (in, out)
    for tf_layer, pt_linear in zip(tf_model.layers, pt_linears):
        w = pt_linear.weight.detach().numpy().T  # (in, out)
        b = pt_linear.bias.detach().numpy()
        tf_layer.set_weights([w, b])

    # Verify weight-copy fidelity
    test_input = calibration_spectra[:1].astype(np.float32)
    pt_out = model(torch.from_numpy(test_input)).detach().numpy()
    tf_out = tf_model(test_input).numpy()
    max_diff = np.abs(pt_out - tf_out).max()
    log.info("Weight-copy fidelity check: max |PT - TF| = %.2e", max_diff)
    if max_diff > 1e-4:
        log.warning("Weight copy divergence > 1e-4 — investigate!")

    # Convert to TFLite INT8
    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def representative_dataset():
        for i in range(len(calibration_spectra)):
            yield [calibration_spectra[i : i + 1].astype(np.float32)]

    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_model = converter.convert()
    tflite_path.write_bytes(tflite_model)

    size_kb = tflite_path.stat().st_size / 1024
    log.info("TFLite INT8 exported: %s (%.1f KB)", tflite_path, size_kb)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    log.info("=" * 60)
    log.info("PIPELINE VALIDATION: golden → train → ONNX → TFLite INT8 → NAS")
    log.info("=" * 60)

    # ── Step 1: Load data ──────────────────────────────────────
    log.info("[1/6] Loading golden dataset from %s", DATA_DIR)
    train_ds = GoldenDataset(DATA_DIR, split="train")
    val_ds = GoldenDataset(DATA_DIR, split="val")
    train_loader = DataLoader(
        train_ds, batch_size=32, shuffle=True, collate_fn=collate_with_meta,
        pin_memory=True, num_workers=4,
    )
    val_loader = DataLoader(
        val_ds, batch_size=32, shuffle=False, collate_fn=collate_with_meta,
        pin_memory=True, num_workers=4,
    )
    log.info("  Train: %d samples, Val: %d samples", len(train_ds), len(val_ds))

    # ── Step 2: Create model & ops guard ───────────────────────
    log.info("[2/6] Creating OdmrMLP([64, 32]) and running ops_guard")
    model = OdmrMLP(input_dim=100, output_dim=3, hidden_dims=[64, 32])
    init_weights_kaiming_he(model)
    n_params = sum(p.numel() for p in model.parameters())
    log.info("  Parameters: %d", n_params)

    report = check_model_ops(model, input_shape=(1, 100))
    log.info("  Ops guard: compatible=%s", report.is_compatible)
    log.info("    Allowed: %s", report.allowed)
    if report.disallowed:
        log.error("    DISALLOWED: %s", report.disallowed)
        sys.exit(1)
    if report.unknown:
        log.warning("    Unknown: %s", report.unknown)

    # ── Step 3: Train briefly ──────────────────────────────────
    log.info("[3/6] Training for 50 epochs (pipeline validation, not convergence)")
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    config = TrainConfig(
        epochs=50,
        batch_size=32,
        val_every=10,
        log_every=5,
        checkpoint_dir=str(ARTIFACT_DIR / "checkpoints"),
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("Device: %s", device)
    results = train(model, train_loader, val_loader, config, device)

    log.info("  Final train loss: %.6f", results["final_train_loss"])
    log.info("  Best val angle err: %.4f°", results["best_val_angle_err"])
    log.info("  Training time: %.1fs", results["training_time_s"])

    # Verify loss decreased
    history = results["epoch_history"]
    first_loss = history[0]["train_loss"]
    last_loss = history[-1]["train_loss"]
    if last_loss < first_loss:
        log.info("  ✓ Loss decreased: %.4f → %.4f", first_loss, last_loss)
    else:
        log.warning("  ✗ Loss did NOT decrease: %.4f → %.4f", first_loss, last_loss)

    # ── Step 4: Export ONNX ────────────────────────────────────
    log.info("[4/6] Exporting ONNX")
    onnx_path = ARTIFACT_DIR / "model.onnx"
    export_onnx(model, onnx_path)

    # ── Step 5: Convert to TFLite INT8 ─────────────────────────
    log.info("[5/6] Converting to TFLite INT8")
    # Use normalized train spectra as calibration data
    calibration_spectra = train_ds.spectra.numpy()
    tflite_path = ARTIFACT_DIR / "model_int8.tflite"
    convert_to_tflite_int8(model, calibration_spectra, tflite_path)

    # Verify TFLite loads
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_path=str(tflite_path))
    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    log.info(
        "  TFLite input: dtype=%s, shape=%s",
        input_details[0]["dtype"],
        input_details[0]["shape"],
    )
    log.info(
        "  TFLite output: dtype=%s, shape=%s",
        output_details[0]["dtype"],
        output_details[0]["shape"],
    )

    # ── Step 6: Copy to exports ──────────────────────────────────
    log.info("[6/6] Copying artifacts to exports")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)

    exp_tflite = EXPORT_DIR / "pipeline_validation_int8.tflite"
    exp_onnx = EXPORT_DIR / "pipeline_validation.onnx"
    shutil.copy2(tflite_path, exp_tflite)
    shutil.copy2(onnx_path, exp_onnx)
    log.info("  → %s (%.1f KB)", exp_tflite, exp_tflite.stat().st_size / 1024)
    log.info("  → %s (%.1f KB)", exp_onnx, exp_onnx.stat().st_size / 1024)

    # ── Summary ────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("PIPELINE VALIDATION COMPLETE")
    log.info("  Ops guard:      PASS")
    log.info("  Training:       loss %.4f → %.4f", first_loss, last_loss)
    log.info("  ONNX:           %s", onnx_path)
    log.info("  TFLite INT8:    %s", tflite_path)
    log.info("  Export dir:     %s", EXPORT_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
