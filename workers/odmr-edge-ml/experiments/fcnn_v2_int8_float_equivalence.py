#!/usr/bin/env python3
"""Compare deployed FCNN v2 float checkpoint vs INT8 TFLite on Dataset A.

This is an honesty harness: it does not claim "bit-exact INT8 == float".
It reports the float-vs-INT8 output gap, TFLite saturation, and the
deployed safety-clamped accuracy on the production_50k_v2_aic split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import h5py
import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

INPUT_DIM = 100
IN_CHANNELS = 2
OUTPUT_DIM = 1
DEFAULT_SIGMA = 1.267999
DEFAULT_CLAMP_UT = 2.25


def strip_compile_qat_keys(sd: dict) -> dict:
    skip = ("fake_quant", "activation_post_process", "observer")
    out: dict = {}
    for key, value in sd.items():
        if any(part in key for part in skip):
            continue
        out[key[len("_orig_mod."):] if key.startswith("_orig_mod.") else key] = value
    return out


def load_float_model(ckpt_path: Path) -> OdmrFCNN:
    ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    clean = strip_compile_qat_keys(ckpt["model_state_dict"])
    model = OdmrFCNN(
        input_dim=INPUT_DIM,
        output_dim=OUTPUT_DIM,
        in_channels=IN_CHANNELS,
        init_weights=False,
    )
    target = set(model.state_dict().keys())
    export_sd = {key: value for key, value in clean.items() if key in target}
    model.load_state_dict(export_sd, strict=True)
    model.eval()
    return model


def preprocess(spectra: np.ndarray, lock_bins: np.ndarray, sigma: float) -> np.ndarray:
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    spec_norm = 2.0 * (spectra - s_min) / denom - 1.0

    bins = np.arange(spectra.shape[1], dtype=np.float32)[None, :]
    centers = lock_bins.astype(np.float32).reshape(-1, 1)
    anchor = np.exp(-0.5 * ((bins - centers) / float(sigma)) ** 2)
    return np.concatenate([spec_norm, anchor], axis=1).astype(np.float32)


def flat_to_nhwc(flat: np.ndarray) -> np.ndarray:
    return flat.reshape(-1, IN_CHANNELS, 1, INPUT_DIM).transpose(0, 2, 3, 1)


def load_interpreter(tflite_path: Path):
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter  # type: ignore[no-redef]
    interp = Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    return interp


def quantize_array(x: np.ndarray, scale: float, zero_point: int, dtype: np.dtype) -> np.ndarray:
    info = np.iinfo(dtype)
    q = np.round(x / scale + zero_point)
    return np.clip(q, info.min, info.max).astype(dtype)


def run_tflite(interp, flat: np.ndarray) -> tuple[np.ndarray, dict]:
    in_det = interp.get_input_details()[0]
    out_det = interp.get_output_details()[0]
    in_scale, in_zp = in_det["quantization"]
    out_scale, out_zp = out_det["quantization"]
    in_dtype = in_det["dtype"]
    out_dtype = out_det["dtype"]

    x = flat_to_nhwc(flat)
    y = np.zeros((x.shape[0],), dtype=np.float32)
    raw_out = np.zeros((x.shape[0],), dtype=out_dtype)
    input_at_min = 0
    input_at_max = 0
    info_in = np.iinfo(in_dtype)

    for i in range(x.shape[0]):
        qx = quantize_array(x[i : i + 1], in_scale, int(in_zp), in_dtype)
        input_at_min += int(np.sum(qx == info_in.min))
        input_at_max += int(np.sum(qx == info_in.max))
        interp.set_tensor(in_det["index"], qx)
        interp.invoke()
        qy = interp.get_tensor(out_det["index"]).reshape(-1)[0]
        raw_out[i] = qy
        y[i] = (float(qy) - int(out_zp)) * float(out_scale)

    info_out = np.iinfo(out_dtype)
    sat_low = int(np.sum(raw_out == info_out.min))
    sat_high = int(np.sum(raw_out == info_out.max))
    stats = {
        "input_scale": float(in_scale),
        "input_zero_point": int(in_zp),
        "output_scale": float(out_scale),
        "output_zero_point": int(out_zp),
        "input_values_at_min": input_at_min,
        "input_values_at_max": input_at_max,
        "output_at_min": sat_low,
        "output_at_max": sat_high,
        "output_saturation_fraction": (sat_low + sat_high) / float(len(raw_out)),
    }
    return y, stats


def summarize_error(diff: np.ndarray) -> dict:
    abs_diff = np.abs(diff)
    return {
        "mae_uT": float(np.mean(abs_diff)),
        "rmse_uT": float(math.sqrt(np.mean(diff * diff))),
        "max_abs_uT": float(np.max(abs_diff)),
        "p50_abs_uT": float(np.percentile(abs_diff, 50)),
        "p95_abs_uT": float(np.percentile(abs_diff, 95)),
        "p99_abs_uT": float(np.percentile(abs_diff, 99)),
    }


def mae_summary(name: str, pred_delta: np.ndarray, b_pid: np.ndarray, b_true: np.ndarray,
                clamp_uT: float) -> dict:
    pred_clamped = np.clip(pred_delta, -clamp_uT, clamp_uT)
    baseline = np.abs(b_pid - b_true)
    raw_err = np.abs(b_pid + pred_delta - b_true)
    clamped_err = np.abs(b_pid + pred_clamped - b_true)
    return {
        "name": name,
        "pid_baseline_mae_uT": float(np.mean(baseline)),
        "raw_mae_uT": float(np.mean(raw_err)),
        "raw_reduction_pct": float((1.0 - np.mean(raw_err) / np.mean(baseline)) * 100.0),
        "clamped_mae_uT": float(np.mean(clamped_err)),
        "clamped_reduction_pct": float((1.0 - np.mean(clamped_err) / np.mean(baseline)) * 100.0),
        "raw_exceeds_clamp_fraction": float(np.mean(np.abs(pred_delta) > clamp_uT)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path(
        "~/projects/tychon-shared-data/production_50k_v2_aic"
    ))
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--ckpt", type=Path, default=REPO_ROOT / (
        "experiments/scalar_residual_v2_dataset_a/checkpoints/best_model_dataset_a.pt"
    ))
    parser.add_argument("--tflite", type=Path, default=REPO_ROOT / (
        "exports/fcnn_v2_residual_dataset_a_int8.tflite"
    ))
    parser.add_argument("--sigma", type=float, default=DEFAULT_SIGMA)
    parser.add_argument("--clamp-uT", type=float, default=DEFAULT_CLAMP_UT)
    parser.add_argument("--limit", type=int, default=0, help="0 means full split")
    parser.add_argument("--out", type=Path, default=REPO_ROOT / (
        "experiments/fcnn_v2_int8_float_equivalence_2026-06-21.json"
    ))
    args = parser.parse_args()

    with h5py.File(args.dataset / "dataset.h5", "r") as h:
        spectra = h[f"{args.split}/spectra"][:]
    pid = np.load(args.dataset / "pid_residuals.npz")
    lock_bins = pid[f"{args.split}_lock_bins"].astype(np.int64)
    b_pid = pid[f"{args.split}_b_pid_uT"].astype(np.float32)
    b_true = pid[f"{args.split}_b_mag_uT"].astype(np.float32)

    if args.limit and args.limit > 0:
        n = int(args.limit)
        spectra = spectra[:n]
        lock_bins = lock_bins[:n]
        b_pid = b_pid[:n]
        b_true = b_true[:n]

    x = preprocess(spectra, lock_bins, args.sigma)
    model = load_float_model(args.ckpt)
    with torch.no_grad():
        float_delta = model(torch.from_numpy(x)).detach().cpu().numpy().reshape(-1)

    interp = load_interpreter(args.tflite)
    int8_delta, quant_stats = run_tflite(interp, x)

    diff = int8_delta - float_delta
    result = {
        "dataset": str(args.dataset),
        "split": args.split,
        "n": int(len(x)),
        "ckpt": str(args.ckpt),
        "ckpt_sha256": hashlib.sha256(args.ckpt.read_bytes()).hexdigest(),
        "tflite": str(args.tflite),
        "tflite_sha256": hashlib.sha256(args.tflite.read_bytes()).hexdigest(),
        "sigma": float(args.sigma),
        "clamp_uT": float(args.clamp_uT),
        "float_vs_int8_delta": summarize_error(diff),
        "quantization": quant_stats,
        "float_accuracy": mae_summary("float", float_delta, b_pid, b_true, args.clamp_uT),
        "int8_accuracy": mae_summary("int8", int8_delta, b_pid, b_true, args.clamp_uT),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
