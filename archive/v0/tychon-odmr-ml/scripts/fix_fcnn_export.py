#!/usr/bin/env python3
"""Fix FCNN TFLite export for vnnx_compile compatibility.

Problem: The original TFLite contains SHAPE/STRIDED_SLICE/PACK ops from
PyTorch's view() reshape (dynamic batch dimension query). The PolarFire
VNNX compiler does not support these ops.

Fix: Build a Keras model that accepts pre-shaped (B, 1, 100, 2) NHWC input
directly — no reshape needed. Copy trained conv weights from the QAT
checkpoint, use static Reshape instead of Flatten at output, and convert
to TFLite INT8 with only vnnx-compatible ops.

Input shape mapping:
  PyTorch forward:  (B, 200) → view → (B, 2, 1, 100) NCHW
  This export:      (B, 1, 100, 2) NHWC — pre-shaped, no view()

Usage:
    python scripts/fix_fcnn_export.py
"""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import numpy as np
import torch

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from tychon_odmr_ml.models.fcnn import OdmrFCNN

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = PROJECT_ROOT / "experiments/scalar_residual/fcnn/checkpoints/best_model.pt"
DATA_DIR = Path.home() / "projects/tychon-shared-data/golden"
OUTPUT_DIR = PROJECT_ROOT / "experiments/scalar_residual/fcnn"
NAS_TFLITE = Path("/mnt/nas/projects/tychon-artifacts/models/fcnn_residual_v3_int8.tflite")

# Model config — must match what was trained
INPUT_DIM = 100
OUTPUT_DIM = 1
IN_CHANNELS = 2


def _load_pytorch_model() -> OdmrFCNN:
    """Load trained weights from QAT checkpoint into a clean OdmrFCNN."""
    model = OdmrFCNN(
        input_dim=INPUT_DIM, output_dim=OUTPUT_DIM, in_channels=IN_CHANNELS,
    )
    ckpt = torch.load(CHECKPOINT, map_location="cpu", weights_only=True)

    # Checkpoint format: {"epoch", "model_state_dict", "optimizer_state_dict", ...}
    sd = ckpt.get("model_state_dict", ckpt)

    # Strip QAT artifacts (FakeQuantize, observers)
    skip = ("fake_quant", "activation_post_process", "observer")
    clean_sd = {
        k: v for k, v in sd.items()
        if not any(pat in k for pat in skip)
    }
    model.load_state_dict(clean_sd, strict=True)
    model.eval()
    log.info("Loaded checkpoint: %s (%d keys)", CHECKPOINT.name, len(clean_sd))
    return model


def _build_keras_model(pt_model: OdmrFCNN):
    """Build a Keras Conv2D model with static NHWC input and copy weights."""
    import tensorflow as tf

    pt_convs = list(pt_model.convs) + [pt_model.conv_head]

    # Fixed batch=1, static NHWC input: (1, 1, 100, 2) — no reshape needed.
    # Fixed batch eliminates all dynamic shape ops (SHAPE/STRIDED_SLICE/PACK).
    inp = tf.keras.layers.Input(
        batch_shape=(1, 1, INPUT_DIM, IN_CHANNELS), name="odmr_input",
    )
    x = inp
    for i, pt_conv in enumerate(pt_convs):
        is_last = i == len(pt_convs) - 1
        x = tf.keras.layers.Conv2D(
            filters=pt_conv.out_channels,
            kernel_size=pt_conv.kernel_size,
            strides=pt_conv.stride,
            activation=None if is_last else "relu",
            padding="valid",
            name=f"conv_{i}" if not is_last else "conv_head",
        )(x)

    # No Flatten/Reshape — output stays (1, 1, 1, 1) to avoid any dynamic
    # shape ops. The FPGA reads the single scalar from the 4D tensor directly.
    tf_model = tf.keras.Model(inputs=inp, outputs=x, name="fcnn_residual_v3")

    # Copy weights: PyTorch (C_out, C_in, kH, kW) → Keras (kH, kW, C_in, C_out)
    tf_conv_layers = [
        layer for layer in tf_model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    assert len(tf_conv_layers) == len(pt_convs), "Conv layer count mismatch"

    for pt_conv, tf_layer in zip(pt_convs, tf_conv_layers):
        w = pt_conv.weight.detach().numpy().transpose(2, 3, 1, 0)
        b = pt_conv.bias.detach().numpy()
        tf_layer.set_weights([w, b])

    log.info("Built Keras model with %d conv layers, static input (1, %d, %d)",
             len(tf_conv_layers), INPUT_DIM, IN_CHANNELS)
    return tf_model


def _flat_to_nhwc(flat: np.ndarray) -> np.ndarray:
    """Reshape (N, 200) flat input to (N, 1, 100, 2) NHWC.

    Flat layout: [spectrum_0..99, anchor_0..99]
    NCHW:  (N, 2, 1, 100)  — channel 0 = spectrum, channel 1 = anchor
    NHWC:  (N, 1, 100, 2)  — transpose axes (0, 2, 3, 1)
    """
    return flat.reshape(-1, IN_CHANNELS, 1, INPUT_DIM).transpose(0, 2, 3, 1)


def _verify_fidelity(pt_model: OdmrFCNN, tf_model, cal_flat: np.ndarray) -> None:
    """Verify Keras model matches PyTorch output within tolerance."""
    n = min(16, len(cal_flat))
    sample = cal_flat[:n].astype(np.float32)

    pt_out = pt_model(torch.from_numpy(sample)).detach().numpy()
    # Keras output is (N, 1, 1, 1) — squeeze to (N, 1) to compare with PyTorch
    tf_out = tf_model.predict(_flat_to_nhwc(sample), batch_size=1).reshape(-1, OUTPUT_DIM)

    max_diff = np.abs(pt_out - tf_out).max()
    log.info("Weight-copy fidelity: max |PT - TF| = %.2e", max_diff)
    if max_diff >= 1e-4:
        log.error("FIDELITY CHECK FAILED — divergence %.2e exceeds 1e-4", max_diff)
        sys.exit(1)


def _convert_to_tflite_int8(tf_model, cal_nhwc: np.ndarray, path: Path) -> bytes:
    """Convert Keras model to TFLite INT8 with representative dataset."""
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    n_cal = min(len(cal_nhwc), 1000)

    def representative_dataset():
        for i in range(n_cal):
            yield [cal_nhwc[i : i + 1].astype(np.float32)]

    converter.representative_dataset = representative_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_bytes = converter.convert()
    path.write_bytes(tflite_bytes)
    size_kb = path.stat().st_size / 1024
    log.info("TFLite INT8: %s (%.1f KB, %d cal samples)", path, size_kb, n_cal)
    return tflite_bytes


def _verify_ops(tflite_bytes: bytes) -> None:
    """Check TFLite model for ops incompatible with vnnx_compile."""
    import tensorflow as tf

    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()

    # Collect op names from all operator details
    ops: set[str] = set()
    for detail in interpreter._get_ops_details():
        ops.add(detail["op_name"])

    log.info("TFLite ops: %s", sorted(ops))

    # These ops come from dynamic shape computation — vnnx_compile rejects them
    banned = {"SHAPE", "STRIDED_SLICE", "PACK"}
    found = ops & banned
    if found:
        log.error("BANNED OPS FOUND: %s — vnnx_compile will reject this model!", found)
        sys.exit(1)

    log.info("Op check passed — no dynamic shape ops")


def main() -> None:
    # 1. Load PyTorch model with trained weights
    pt_model = _load_pytorch_model()

    # 2. Build Keras model with static input shape, copy weights
    tf_model = _build_keras_model(pt_model)

    # 3. Load calibration data
    from tychon_odmr_ml.evaluation.residual_dataset import ResidualDataset

    train_ds = ResidualDataset(DATA_DIR, "train")
    cal_flat = train_ds.spectra.numpy().astype(np.float32)
    log.info("Calibration data: %d samples, shape %s", len(cal_flat), cal_flat.shape)

    # 4. Verify Keras matches PyTorch
    _verify_fidelity(pt_model, tf_model, cal_flat)

    # 5. Convert to TFLite INT8
    cal_nhwc = _flat_to_nhwc(cal_flat)
    tflite_path = OUTPUT_DIR / "model_v3_int8.tflite"
    tflite_bytes = _convert_to_tflite_int8(tf_model, cal_nhwc, tflite_path)

    # 6. Verify no banned ops
    _verify_ops(tflite_bytes)

    # 7. Copy to NAS
    NAS_TFLITE.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tflite_path, NAS_TFLITE)
    log.info("Copied to NAS: %s", NAS_TFLITE)

    print(f"\nDone. vnnx-compatible TFLite at:")
    print(f"  local: {tflite_path}")
    print(f"  NAS:   {NAS_TFLITE}")


if __name__ == "__main__":
    main()
