#!/usr/bin/env python3
"""Phase B export recovery (v2 on Dataset A) — vnnx-compatible variant.

The full training run finished cleanly (Apr 28, 250s wall, σ 1.500→1.268)
but two follow-up issues kept the deployment artifacts incomplete:

  1. The in-line export step crashed with KeyError('sigma') because
     torch.compile prefixed all state_dict keys with '_orig_mod.' and the
     existing extract_clean_state_dict() did not strip that prefix.

  2. Even after fixing #1, the in-line `convert_fcnn_to_tflite_int8`
     (scalar_residual_v2.py:231) builds a Keras model with a *dynamic*
     batch dimension (`Input(shape=(1, 100, 2))`). vnnx_compile -c V250
     then rejects the resulting TFLite with SHAPE / STRIDED_SLICE / PACK
     errors (the same gotcha CLAUDE.md flags for v1's TFLite export and
     scripts/fix_fcnn_export.py works around).

This recovery script:
  • Loads best_model_dataset_a.pt (saved before the crash).
  • Strips the '_orig_mod.' prefix and FX-QAT observer keys.
  • Loads weights into a clean OdmrFCNN (same architecture as v1's deploy
    target — anchor σ moves to host-side preprocessing).
  • Re-exports to TFLite INT8 using the static-batch Keras pattern from
    scripts/fix_fcnn_export.py (batch_shape=(1, 1, 100, 2), no Flatten).
  • Verifies the resulting TFLite contains no banned dynamic-shape ops.
  • Mirrors to NAS as fcnn_v2_residual_dataset_a{_int8.tflite,.onnx}.
"""

from __future__ import annotations

import logging
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from odmr_edge_ml.evaluation.residual_dataset import ResidualDataset  # noqa: E402
from odmr_edge_ml.export import export_onnx as _export_onnx_module  # noqa: E402
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402
from scalar_residual_v2 import CLAMP_UT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

INPUT_DIM = 100
OUTPUT_DIM = 1
IN_CHANNELS = 2

CKPT = Path(
    "~/projects/odmr-edge-ml/experiments/"
    "scalar_residual_v2_dataset_a/checkpoints/best_model_dataset_a.pt"
)
DATA_DIR = Path("~/projects/odmr-edge-ml/data/production_50k_v2_aic")
EXPORT_SUBDIR = Path(
    "~/projects/odmr-edge-ml/experiments/"
    "scalar_residual_v2_dataset_a/checkpoints/production_50k_v2_aic_export"
)
NAS_DIR = Path("/mnt/nas/projects/tychon-artifacts/models")
LOCAL_EXPORTS = Path("~/projects/odmr-edge-ml/exports")


def strip_compile_qat_keys(sd: dict) -> dict:
    """Strip torch.compile '_orig_mod.' prefix and FX-QAT observer keys."""
    skip = ("fake_quant", "activation_post_process", "observer")
    out: dict = {}
    for k, v in sd.items():
        if any(p in k for p in skip):
            continue
        new_key = k[len("_orig_mod."):] if k.startswith("_orig_mod.") else k
        out[new_key] = v
    return out


def build_keras_static_batch(pt_model: OdmrFCNN):
    """Build vnnx-compatible Keras with batch_shape=(1,1,100,2), no Flatten."""
    import tensorflow as tf

    pt_convs = list(pt_model.convs) + [pt_model.conv_head]

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
    tf_model = tf.keras.Model(inputs=inp, outputs=x, name="fcnn_v2_dataset_a")

    tf_conv_layers = [
        layer for layer in tf_model.layers
        if isinstance(layer, tf.keras.layers.Conv2D)
    ]
    assert len(tf_conv_layers) == len(pt_convs), "Conv layer count mismatch"

    for pt_conv, tf_layer in zip(pt_convs, tf_conv_layers):
        w = pt_conv.weight.detach().numpy().transpose(2, 3, 1, 0)
        b = pt_conv.bias.detach().numpy()
        tf_layer.set_weights([w, b])

    log.info(
        "Keras (static batch=1): %d conv layers, input=(1,1,%d,%d)",
        len(tf_conv_layers), INPUT_DIM, IN_CHANNELS,
    )
    return tf_model


def flat_to_nhwc(flat: np.ndarray) -> np.ndarray:
    return flat.reshape(-1, IN_CHANNELS, 1, INPUT_DIM).transpose(0, 2, 3, 1)


def verify_fidelity(pt_model: OdmrFCNN, tf_model, cal_flat: np.ndarray) -> None:
    n = min(16, len(cal_flat))
    sample = cal_flat[:n].astype(np.float32)

    with torch.no_grad():
        pt_out = pt_model(torch.from_numpy(sample)).detach().numpy()
    tf_out = tf_model.predict(flat_to_nhwc(sample), batch_size=1, verbose=0)
    tf_out = tf_out.reshape(-1, OUTPUT_DIM)

    max_diff = np.abs(pt_out - tf_out).max()
    log.info("PT↔Keras fidelity: max |Δ| = %.2e (n=%d)", max_diff, n)
    if max_diff >= 1e-4:
        log.error("FIDELITY FAILED at %.2e (>1e-4)", max_diff)
        sys.exit(1)


def convert_to_tflite_int8(tf_model, cal_nhwc: np.ndarray, path: Path) -> bytes:
    import tensorflow as tf

    converter = tf.lite.TFLiteConverter.from_keras_model(tf_model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    n_cal = min(len(cal_nhwc), 1000)

    def rep():
        for i in range(n_cal):
            yield [cal_nhwc[i:i + 1].astype(np.float32)]

    converter.representative_dataset = rep
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    tflite_bytes = converter.convert()
    path.write_bytes(tflite_bytes)
    log.info(
        "TFLite INT8: %s (%.1f KB, %d cal)", path,
        path.stat().st_size / 1024, n_cal,
    )
    return tflite_bytes


def verify_ops(tflite_bytes: bytes) -> None:
    import tensorflow as tf

    interp = tf.lite.Interpreter(model_content=tflite_bytes)
    interp.allocate_tensors()
    ops = {d["op_name"] for d in interp._get_ops_details()}
    log.info("TFLite ops: %s", sorted(ops))

    banned = {"SHAPE", "STRIDED_SLICE", "PACK"}
    bad = ops & banned
    if bad:
        log.error("BANNED OPS PRESENT: %s", bad)
        sys.exit(1)
    log.info("vnnx op-compat check: PASS (no dynamic-shape ops)")


def main() -> None:
    if not CKPT.exists():
        log.error("Checkpoint not found: %s", CKPT)
        sys.exit(1)

    ck = torch.load(CKPT, map_location="cpu", weights_only=False)
    raw_sd = ck["model_state_dict"]
    clean_sd = strip_compile_qat_keys(raw_sd)
    learned_sigma = float(clean_sd["sigma"].item())
    log.info("Recovered σ from checkpoint: %.6f", learned_sigma)

    clean = OdmrFCNN(input_dim=INPUT_DIM, output_dim=OUTPUT_DIM, in_channels=IN_CHANNELS)
    target_keys = set(clean.state_dict().keys())
    export_sd = {k: v for k, v in clean_sd.items() if k in target_keys}
    extra = set(clean_sd.keys()) - target_keys
    log.info("Loading export weights: %d matched, %d dropped (v2-only): %s",
             len(export_sd), len(extra), sorted(extra))
    clean.load_state_dict(export_sd, strict=True)
    clean.eval()

    EXPORT_SUBDIR.mkdir(parents=True, exist_ok=True)

    # ONNX (informational; vnnx pipeline goes via TFLite).
    onnx_path = EXPORT_SUBDIR / "model.onnx"
    _export_onnx_module(clean, onnx_path, input_shape=(1, 200), skip_ops_check=True)
    log.info("ONNX: %s", onnx_path)

    # TFLite INT8 — static-batch Keras pattern (vnnx-compatible).
    tf_model = build_keras_static_batch(clean)

    cal_ds = ResidualDataset(DATA_DIR, "train", sigma=learned_sigma)
    cal_flat = cal_ds.spectra.numpy().astype(np.float32)
    verify_fidelity(clean, tf_model, cal_flat)

    cal_nhwc = flat_to_nhwc(cal_flat)
    tflite_path = EXPORT_SUBDIR / "model_int8.tflite"
    tflite_bytes = convert_to_tflite_int8(tf_model, cal_nhwc, tflite_path)
    verify_ops(tflite_bytes)

    # Deployment metadata.
    np.savez(
        EXPORT_SUBDIR / "deployment_metadata.npz",
        learned_sigma=np.float64(learned_sigma),
        clamp_uT=np.float64(CLAMP_UT),
        input_dim=np.int64(200),
        model_version="v2_dataset_a",
        dataset_name="production_50k_v2_aic",
        keras_input_layout="(1, 1, 100, 2) NHWC, fixed batch",
    )
    log.info("Deployment metadata saved")

    # Local + NAS mirrors.
    LOCAL_EXPORTS.mkdir(parents=True, exist_ok=True)
    for src, dst_name in [
        (tflite_path, "fcnn_v2_residual_dataset_a_int8.tflite"),
        (onnx_path, "fcnn_v2_residual_dataset_a.onnx"),
    ]:
        dst = LOCAL_EXPORTS / dst_name
        shutil.copy2(src, dst)
        log.info("Local mirror: %s", dst)

    if NAS_DIR.exists():
        for src, dst_name in [
            (tflite_path, "fcnn_v2_residual_dataset_a_int8.tflite"),
            (onnx_path, "fcnn_v2_residual_dataset_a.onnx"),
        ]:
            dst = NAS_DIR / dst_name
            shutil.copy2(src, dst)
            log.info("NAS mirror: %s", dst)
    else:
        log.warning("NAS dir not mounted: %s", NAS_DIR)


if __name__ == "__main__":
    main()
