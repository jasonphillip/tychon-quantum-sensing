#!/usr/bin/env python3
"""Prepare original held-out residual inputs and evaluate each deployment stage."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import h5py
import numpy as np
import torch

import fcnn_v2_int8_float_equivalence as harness

ROOT = Path(__file__).resolve().parents[1]
DATASET = Path("~/projects/tychon-shared-data/production_50k_v2_aic")
DATASET_MD5 = "b350320066a4c6a4553f05cd1f469704"
MODEL = ROOT / "exports/fcnn_v2_residual_dataset_a_int8.tflite"
CHECKPOINT = ROOT / "checkpoints/best_model_dataset_a.pt"
CHECKPOINT_SOURCE = Path(
    "~/projects/odmr-edge-ml/experiments/"
    "scalar_residual_v2_dataset_a/checkpoints/best_model_dataset_a.pt"
)


def tf_python() -> str:
    """Pick an interpreter that can run the TFLite step."""
    if os.environ.get("ODMR_TF_PYTHON"):
        return os.environ["ODMR_TF_PYTHON"]
    for module in ("tflite_runtime", "tensorflow"):
        try:
            if importlib.util.find_spec(module) is not None:
                return sys.executable
        except (ImportError, ValueError):
            pass
    fallback = Path("~/miniconda3/envs/tfc2/bin/python3")
    if fallback.exists():
        return str(fallback)
    raise RuntimeError("no TFLite-capable interpreter; set ODMR_TF_PYTHON")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_split_md5(group: h5py.Group) -> str:
    """Use the simulator's key/dtype/shape/bytes content-hash convention."""
    digest = hashlib.md5()
    for key in sorted(group):
        value = np.ascontiguousarray(group[key][:])
        digest.update(f"test/{key}".encode())
        digest.update(str(value.dtype).encode())
        digest.update(str(value.shape).encode())
        digest.update(value.tobytes())
    return digest.hexdigest()


def prepare(out: Path, rows: int, dataset: Path = DATASET) -> dict:
    if not 1 <= rows <= 512:
        raise ValueError("--rows must be between 1 and 512")
    with h5py.File(dataset / "dataset.h5", "r") as source:
        test = source["test"]
        dataset_md5 = test_split_md5(test)
        if dataset_md5 != DATASET_MD5:
            raise ValueError(f"original test split md5 mismatch: {dataset_md5}")
        spectra = test["spectra"][:rows]
    with np.load(dataset / "pid_residuals.npz") as labels:
        lock_bins = labels["test_lock_bins"][:rows]
        b_pid = labels["test_b_pid_uT"][:rows]
        b_true = labels["test_b_mag_uT"][:rows]
        delta = labels["test_delta_b_uT"][:rows]
    if not np.allclose(delta, b_true - b_pid, rtol=0, atol=1e-10):
        raise ValueError("residual label differs from B_true - B_PID")

    flat = harness.preprocess(spectra, lock_bins, harness.DEFAULT_SIGMA)
    nhwc = harness.flat_to_nhwc(flat)
    interpreter = harness.load_interpreter(MODEL)
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    input_scale, input_zp = input_detail["quantization"]
    output_scale, output_zp = output_detail["quantization"]
    if input_scale <= 0 or output_scale <= 0:
        raise ValueError("model input and output must have positive quantization scales")
    if input_detail["dtype"] != np.int8 or output_detail["dtype"] != np.int8:
        raise ValueError("model input and output must be int8")
    if tuple(nhwc.shape[1:]) != tuple(input_detail["shape"][1:]):
        raise ValueError("preprocessed input does not match the model tensor")
    quantized = harness.quantize_array(
        nhwc, float(input_scale), int(input_zp), input_detail["dtype"]
    )

    float_model = harness.load_float_model(CHECKPOINT)
    with torch.no_grad():
        float_delta = float_model(torch.from_numpy(flat)).detach().cpu().numpy().reshape(-1)
    raw = np.empty(rows, dtype=np.int8)
    for index, sample in enumerate(quantized):
        interpreter.set_tensor(input_detail["index"], sample[None, ...])
        interpreter.invoke()
        raw[index] = interpreter.get_tensor(output_detail["index"]).reshape(-1)[0]
    cpu_delta = (raw.astype(np.float64) - int(output_zp)) * float(output_scale)

    out.mkdir(parents=True, exist_ok=True)
    np.save(out / "input.int8.npy", quantized)
    np.savez(out / "labels.npz", delta_b_uT=delta, b_pid_uT=b_pid, b_true_uT=b_true)
    np.savez(out / "float_pred.npz", delta_b_uT=float_delta)
    np.savez(out / "tflite_pred.npz", delta_b_uT=cpu_delta, raw_int8=raw)
    manifest = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "dataset": str(dataset),
        "dataset_md5": dataset_md5,
        "dataset_split": "test",
        "row_indices": list(range(rows)),
        "model_path": str(MODEL),
        "model_sha256": sha256(MODEL),
        "checkpoint_path": str(CHECKPOINT_SOURCE),
        "checkpoint_sha256": sha256(CHECKPOINT),
        "input_scale": float(input_scale),
        "input_zero_point": int(input_zp),
        "output_scale": float(output_scale),
        "output_zero_point": int(output_zp),
        "samples": rows,
        "shape": list(quantized.shape),
        "dtype": str(quantized.dtype),
        "layout": "NHWC model tensor order",
        "npy_sha256": sha256(out / "input.int8.npy"),
        "payload_sha256": hashlib.sha256(quantized.tobytes()).hexdigest(),
        "quantization": {"scale": float(input_scale), "zero_point": int(input_zp)},
        "selection": {"split": "test", "method": "first", "seed": None, "indices": list(range(rows))},
    }
    (out / "input.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def _vector(values: np.ndarray, count: int, name: str) -> np.ndarray:
    result = np.asarray(values).reshape(-1)
    if result.size != count:
        raise ValueError(f"{name}: expected {count} scalar outputs, got {result.size}")
    if not np.all(np.isfinite(result)):
        raise ValueError(f"{name}: nonfinite output")
    return result


def _metrics(error: np.ndarray, clipped: int) -> dict:
    absolute = np.abs(error.astype(np.float64))
    return {
        "mae_uT": float(np.mean(absolute)),
        "rmse_uT": float(np.sqrt(np.mean(absolute**2))),
        "p90_uT": float(np.percentile(absolute, 90)),
        "worst_uT": float(np.max(absolute)),
        "clipped_outputs": clipped,
    }


def _accuracy(prediction: np.ndarray, label: np.ndarray, pid: np.ndarray,
              true: np.ndarray) -> dict:
    prediction = prediction.astype(np.float64)
    clipped = np.clip(prediction, -harness.DEFAULT_CLAMP_UT, harness.DEFAULT_CLAMP_UT)
    count = int(np.count_nonzero(prediction != clipped))
    return {
        "residual": _metrics(prediction - label, count),
        "final_field": _metrics(pid + clipped - np.abs(true), count),
    }


def _criterion(passed: bool | None, detail: str) -> dict:
    return {"status": "NOT RUN" if passed is None else ("PASS" if passed else "FAIL"),
            "detail": detail}


def evaluate(run: Path) -> dict:
    manifest = json.loads((run / "input.manifest.json").read_text())
    count = len(manifest["row_indices"])
    if manifest["row_indices"] != list(range(count)) or count < 1:
        raise ValueError("manifest must select contiguous original test rows")
    inputs = np.load(run / "input.int8.npy", allow_pickle=False)
    if list(inputs.shape) != manifest["shape"] or str(inputs.dtype) != manifest["dtype"]:
        raise ValueError("input tensor differs from manifest")
    if sha256(run / "input.int8.npy") != manifest["npy_sha256"]:
        raise ValueError("input payload hash differs from manifest")
    with np.load(run / "labels.npz", allow_pickle=False) as data:
        label = _vector(data["delta_b_uT"], count, "label")
        pid = _vector(data["b_pid_uT"], count, "B_PID")
        true = _vector(data["b_true_uT"], count, "B_true")
    with np.load(run / "float_pred.npz", allow_pickle=False) as data:
        floating = _vector(data["delta_b_uT"], count, "float")
    with np.load(run / "tflite_pred.npz", allow_pickle=False) as data:
        cpu_raw = _vector(data["raw_int8"], count, "INT8 CPU raw")
        cpu = _vector(data["delta_b_uT"], count, "INT8 CPU")
    output_scale = float(manifest["output_scale"])
    output_zp = int(manifest["output_zero_point"])
    if cpu_raw.dtype != np.int8 or output_scale <= 0:
        raise ValueError("invalid INT8 CPU output or output scale")
    if not np.allclose(cpu, (cpu_raw.astype(np.float64) - output_zp) * output_scale, atol=1e-8):
        raise ValueError("INT8 CPU output does not match raw output")

    stages = {"float": _accuracy(floating, label, pid, true),
              "int8_cpu": _accuracy(cpu, label, pid, true),
              "simulator": "not run", "kit": "not run"}
    sim_raw = None
    if (run / "sim.npz").exists():
        if (run / "sim.json").exists():
            sim_meta = json.loads((run / "sim.json").read_text())
            if sim_meta.get("status") != "completed":
                raise ValueError("simulator metadata does not confirm completion")
            expected_sha = sim_meta.get("output", {}).get("sha256")
            if expected_sha and sha256(run / "sim.npz") != expected_sha:
                raise ValueError("simulator output hash differs from metadata")
        with np.load(run / "sim.npz", allow_pickle=False) as data:
            sim_raw = _vector(data["outputs"], count, "simulator raw")
        if sim_raw.dtype != np.int8:
            raise ValueError("simulator output must be int8")
        sim = (sim_raw.astype(np.float64) - output_zp) * output_scale
        stages["simulator"] = _accuracy(sim, label, pid, true)
    hw_raw = None
    if (run / "hw.bin").exists():
        hw_raw = _vector(np.fromfile(run / "hw.bin", dtype=np.int8), count, "kit raw")
        hw = (hw_raw.astype(np.float64) - output_zp) * output_scale
        stages["kit"] = _accuracy(hw, label, pid, true)

    latency = "not run"
    if (run / "hw.json").exists():
        hw_json = json.loads((run / "hw.json").read_text())
        if hw_raw is not None:
            if hw_json.get("exit_code") != 0 or hw_json.get("completed") != count:
                raise ValueError("kit metadata does not confirm every output")
        wall = np.asarray(hw_json.get("wall_ms", []), dtype=np.float64)
        if wall.size:
            if wall.size != count or not np.all(np.isfinite(wall)):
                raise ValueError("kit latency count or values invalid")
            latency = {"median_ms": float(np.median(wall)),
                       "p90_ms": float(np.percentile(wall, 90)),
                       "max_ms": float(np.max(wall))}

    gap = np.abs(floating - cpu)
    cpu_sim_lsb = None if sim_raw is None else int(np.max(np.abs(
        cpu_raw.astype(np.int16) - sim_raw.astype(np.int16))))
    sim_kit_lsb = None if sim_raw is None or hw_raw is None else int(np.max(np.abs(
        sim_raw.astype(np.int16) - hw_raw.astype(np.int16))))
    kit_mae = None if hw_raw is None else stages["kit"]["final_field"]["mae_uT"]
    float_mae = stages["float"]["final_field"]["mae_uT"]
    criteria = {
        "i_float_vs_int8": _criterion(bool(np.max(gap) <= 5.0 and np.mean(gap) <= 0.5),
            "float vs INT8-CPU residual: max <= 5 uT and MAE <= 0.5 uT"),
        "ii_cpu_vs_simulator": _criterion(None if cpu_sim_lsb is None else cpu_sim_lsb == 0,
            "INT8-CPU vs simulator: 0 LSB"),
        "iii_simulator_vs_kit": _criterion(None if sim_kit_lsb is None else sim_kit_lsb == 0,
            "simulator vs kit: 0 LSB"),
        "iv_kit_final_field": _criterion(None if kit_mae is None else kit_mae <= float_mae + 0.2,
            "kit final-field MAE <= float final-field MAE + 0.2 uT"),
    }
    result = {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "samples": count, "dataset_md5": manifest["dataset_md5"],
        "model_sha256": manifest["model_sha256"],
        "checkpoint_sha256": manifest["checkpoint_sha256"],
        "pid_only_mae_uT": float(np.mean(np.abs(pid - np.abs(true)))),
        "stages": stages,
        "parity": {"cpu_vs_simulator_max_abs_lsb": cpu_sim_lsb,
                   "simulator_vs_kit_max_abs_lsb": sim_kit_lsb,
                   "float_vs_int8_max_abs_uT": float(np.max(gap)),
                   "float_vs_int8_mae_uT": float(np.mean(gap))},
        "kit_latency": latency, "criteria": criteria,
        "chain_status": ("PASS" if all(c["status"] == "PASS" for c in criteria.values())
                         else "FAIL" if any(c["status"] == "FAIL" for c in criteria.values())
                         else "NOT RUN"),
    }
    (run / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# Deployed residual model evaluation", "", f"Rows: {count}; PID-only MAE: {result['pid_only_mae_uT']:.6f} uT", "",
             "| Stage | Residual MAE/RMSE/p90/worst (uT) | Final-field MAE/RMSE/p90/worst (uT) | Clipped |",
             "|---|---|---|---:|"]
    for name, stage in stages.items():
        if stage == "not run":
            lines.append(f"| {name} | not run | not run | not run |")
            continue
        def fmt(metric: dict) -> str:
            return "/".join(f"{metric[key]:.6f}" for key in ("mae_uT", "rmse_uT", "p90_uT", "worst_uT"))
        lines.append(f"| {name} | {fmt(stage['residual'])} | {fmt(stage['final_field'])} | {stage['residual']['clipped_outputs']} |")
    lines += ["", f"CPU vs simulator max: {cpu_sim_lsb} LSB; simulator vs kit max: {sim_kit_lsb} LSB",
              f"Float vs INT8 max: {np.max(gap):.6f} uT; MAE: {np.mean(gap):.6f} uT",
              f"Kit latency: {latency}", ""]
    for key, criterion in criteria.items():
        lines.append(f"{criterion['status']}: {key}: {criterion['detail']}")
    lines.append(f"Chain: {result['chain_status']}")
    (run / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--evaluate", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--rows", type=int, default=512, help="first N original test rows; default 512")
    args = parser.parse_args()
    if args.prepare:
        if args.out is None or args.run is not None:
            parser.error("--prepare requires --out and forbids --run")
        print(json.dumps(prepare(args.out, args.rows), indent=2))
    else:
        if args.run is None or args.out is not None:
            parser.error("--evaluate requires --run and forbids --out")
        evaluate(args.run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
