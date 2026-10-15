#!/usr/bin/env python3
"""Verify published kit arithmetic from saved arrays, without inference or network I/O."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np

ROWS = 512
CLAMP_UT = 2.25
METRICS = ("mae_uT", "rmse_uT", "p90_uT", "worst_uT")
ARRAY_FILES = ("labels.npz", "float_pred.npz", "tflite_pred.npz")
KIT_FILES = ("hw.bin", "hw.json", "sim.npz", "sim.json", "input.int8.npy")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path: Path, expected: str, size: int | None = None) -> None:
    require(path.is_file(), f"missing evidence: {path}")
    require(len(expected) == 64 and all(c in "0123456789abcdef" for c in expected),
            f"invalid expected SHA256: {path.name}")
    if size is not None:
        require(path.stat().st_size == size, f"size mismatch: {path.name}")
    require(sha256(path) == expected, f"SHA256 mismatch: {path.name}")


def finite_number(value: object, name: str) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool),
            f"{name}: expected number")
    number = float(value)
    require(math.isfinite(number), f"{name}: nonfinite number")
    return number


def same_number(actual: object, expected: object, name: str, atol: float) -> None:
    got = finite_number(actual, name)
    want = finite_number(expected, f"reference {name}")
    require(abs(got - want) <= atol, f"{name}: {got} differs from {want} by more than {atol}")


def load_npz(path: Path, spec: dict) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as archive:
        require(set(archive.files) == set(spec), f"{path.name}: missing or extra keys")
        arrays = {key: archive[key] for key in spec}
    for key, array in arrays.items():
        item = spec[key]
        require(list(array.shape) == item["shape"], f"{path.name}/{key}: wrong shape")
        require(str(array.dtype) == item["dtype"], f"{path.name}/{key}: wrong dtype")
        require(np.all(np.isfinite(array)), f"{path.name}/{key}: nonfinite values")
    return arrays


def scalar_vector(array: np.ndarray, name: str) -> np.ndarray:
    require(array.shape == (ROWS,), f"{name}: expected 512 scalar rows")
    return array.astype(np.float64)


def metrics(error: np.ndarray, clipped: int | None = None) -> dict:
    absolute = np.abs(error.astype(np.float64))
    result = {
        "mae_uT": float(np.mean(absolute)),
        "rmse_uT": float(np.sqrt(np.mean(absolute**2))),
        "p90_uT": float(np.percentile(absolute, 90)),
        "worst_uT": float(np.max(absolute)),
    }
    if clipped is not None:
        result["clipped_outputs"] = clipped
    return result


def accuracy(prediction: np.ndarray, label: np.ndarray,
             pid: np.ndarray, truth: np.ndarray) -> dict:
    clipped = np.clip(prediction, -CLAMP_UT, CLAMP_UT)
    count = int(np.count_nonzero(prediction != clipped))
    return {
        "residual": metrics(prediction - label, count),
        "final_field": metrics(pid + clipped - np.abs(truth), count),
    }


def compare_metrics(actual: dict, expected: dict, name: str, atol: float) -> None:
    for key in METRICS:
        same_number(actual[key], expected[key], f"{name}.{key}", atol)
    if "clipped_outputs" in expected:
        require(actual["clipped_outputs"] == expected["clipped_outputs"],
                f"{name}.clipped_outputs mismatch")


def checkout_root(path: Path) -> Path | None:
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return None


def output_path(path: Path, run: Path, kit: Path) -> Path:
    require(not any(parent.is_symlink() for parent in (path.parent, *path.parent.parents)),
            "--out cannot have a symlinked parent")
    out = path.parent.resolve() / path.name
    roots = {root for source in (Path(__file__).resolve(), run, kit)
             if (root := checkout_root(source)) is not None}
    require(not any(out.is_relative_to(root) for root in (*roots, run, kit)),
            "--out must be outside the script, run, and hardware checkout roots and evidence directories")
    return out


def verify(args: argparse.Namespace) -> dict:
    run = args.run_dir.resolve()
    kit = args.hardware_evidence_dir.resolve()
    output_path(args.out, run, kit)
    require(args.atol_uT >= 0 and math.isfinite(args.atol_uT), "invalid --atol-uT")
    require(args.verify_sha256, "--verify-sha256 is required for publication acceptance")
    require(args.no_network, "--no-network is required for publication acceptance")

    arrays_manifest = json.loads((run / "ARRAYS.manifest.json").read_text())
    require(arrays_manifest["samples"] == ROWS, "array manifest must specify 512 rows")
    require(set(arrays_manifest["arrays"]) == set(ARRAY_FILES), "array manifest file set mismatch")
    kit_manifest = arrays_manifest["external_kit_evidence"]
    require(kit_manifest["revision"] == "53acad6aff3424e36662972348ef535392f4859b",
            "unexpected kit revision")
    require(set(kit_manifest["files"]) == set(KIT_FILES), "kit evidence file set mismatch")

    # Hash all required evidence before np.load, np.fromfile, or numeric JSON parsing.
    for name in ARRAY_FILES:
        item = arrays_manifest["arrays"][name]
        require_hash(run / name, item["sha256"], item["size_bytes"])
    for name in KIT_FILES:
        item = kit_manifest["files"][name]
        require(item["path"] == f"evidence/2026-10-14-deployed-fcnn/{name}",
                f"unexpected kit path: {name}")
        require_hash(kit / name, item["sha256"], item["size_bytes"])
    references = {
        "input.manifest.json": run / "input.manifest.json",
        "results.json": args.expected_results,
        "kit_constant_baselines_2026-10.json": args.expected_constants,
    }
    for name, path in references.items():
        require_hash(path, arrays_manifest["reference_files"][name])

    input_manifest = json.loads(references["input.manifest.json"].read_text())
    expected = json.loads(args.expected_results.read_text())
    constants = json.loads(args.expected_constants.read_text())
    indices = list(range(ROWS))
    require(input_manifest["samples"] == expected["samples"] == constants["n_test"] == ROWS,
            "sample count mismatch")
    require(input_manifest["dataset_split"] == "test", "wrong dataset split")
    require(input_manifest["row_indices"] == indices, "input row indices are not 0-511")
    require(input_manifest["selection"]["indices"] == indices, "input selection differs")
    require(constants["selection"]["row_indices"] == indices, "constant selection differs")
    require(constants["selection"]["split"] == "test", "constant split differs")
    require(input_manifest["shape"] == [512, 1, 100, 2], "NHWC input shape mismatch")
    require(input_manifest["dtype"] == "int8", "NHWC input dtype mismatch")
    require(constants["rules_fixed_before_scoring"] ==
            ["training mean magnitude", "training median magnitude"], "fixed rules mismatch")
    require(constants["n_train"] == 40000, "training count mismatch")
    require(constants["source_file_sha256"]["labels.npz"] ==
            arrays_manifest["arrays"]["labels.npz"]["sha256"], "label provenance hash mismatch")
    require(constants["source_file_sha256"]["hw.bin"] ==
            kit_manifest["files"]["hw.bin"]["sha256"], "hardware provenance hash mismatch")
    require(constants["input_nhwc_payload_sha256"] == input_manifest["payload_sha256"],
            "input payload provenance mismatch")

    labels = load_npz(run / "labels.npz", arrays_manifest["arrays"]["labels.npz"]["keys"])
    floating_file = load_npz(run / "float_pred.npz",
                             arrays_manifest["arrays"]["float_pred.npz"]["keys"])
    cpu_file = load_npz(run / "tflite_pred.npz",
                        arrays_manifest["arrays"]["tflite_pred.npz"]["keys"])
    sim_file = load_npz(kit / "sim.npz", kit_manifest["files"]["sim.npz"]["keys"])
    label = scalar_vector(labels["delta_b_uT"], "label")
    pid = scalar_vector(labels["b_pid_uT"], "PID")
    truth = scalar_vector(labels["b_true_uT"], "truth")
    require(hashlib.sha256(np.ascontiguousarray(truth).tobytes()).hexdigest() ==
            constants["selected_truth_float64_sha256"], "saved truth payload hash mismatch")
    require(hashlib.sha256(np.ascontiguousarray(pid).tobytes()).hexdigest() ==
            constants["selected_pid_float64_sha256"], "saved PID payload hash mismatch")
    floating = scalar_vector(floating_file["delta_b_uT"], "float prediction")
    cpu = scalar_vector(cpu_file["delta_b_uT"], "CPU prediction")
    cpu_raw = cpu_file["raw_int8"]
    sim_raw = sim_file["outputs"].reshape(ROWS)
    kit_raw = np.fromfile(kit / "hw.bin", dtype=np.int8)
    require(cpu_raw.shape == sim_raw.shape == kit_raw.shape == (ROWS,),
            "raw output row count mismatch")
    require(np.allclose(label, np.abs(truth) - pid, rtol=0, atol=1e-10),
            "residual label differs from |B_true| - B_PID")

    scale = finite_number(input_manifest["output_scale"], "output scale")
    zero = input_manifest["output_zero_point"]
    require(scale > 0 and type(zero) is int, "invalid output quantization")
    same_number(sim_file["output_scale"][0], scale, "simulator output scale", 1e-9)
    require(int(sim_file["output_zero_point"][0]) == zero, "simulator output zero point mismatch")
    sim_meta = json.loads((kit / "sim.json").read_text())
    hw_meta = json.loads((kit / "hw.json").read_text())
    require(sim_meta["status"] == "completed", "simulator did not complete")
    require(sim_meta["output"]["sha256"] == kit_manifest["files"]["sim.npz"]["sha256"],
            "simulator metadata hash mismatch")
    require(sim_meta["output"]["size_bytes"] == (kit / "sim.npz").stat().st_size,
            "simulator metadata size mismatch")
    require(hw_meta["exit_code"] == hw_meta["npu_error"] == hw_meta["poll_result"] == 0,
            "kit reported an error")
    require(hw_meta["samples"] == hw_meta["completed"] == ROWS, "kit row count mismatch")
    same_number(hw_meta["outputs"][0]["scale"], scale, "kit output scale", 1e-9)
    require(hw_meta["outputs"][0]["zero_point"] == zero, "kit output zero point mismatch")
    kit_input = np.load(kit / "input.int8.npy", allow_pickle=False)
    require(kit_input.shape == (512, 2, 1, 100) and kit_input.dtype == np.int8,
            "kit input shape or dtype mismatch")
    require(np.all(np.isfinite(kit_input)), "nonfinite kit input")

    dequantized = (cpu_raw.astype(np.float64) - zero) * scale
    require(np.allclose(cpu, dequantized, rtol=0, atol=1e-8),
            "CPU dequantized output differs from raw INT8")
    cpu_sim_lsb = int(np.max(np.abs(cpu_raw.astype(np.int16) - sim_raw.astype(np.int16))))
    sim_kit_lsb = int(np.max(np.abs(sim_raw.astype(np.int16) - kit_raw.astype(np.int16))))
    require(cpu_sim_lsb == sim_kit_lsb == 0, "raw-int8 parity mismatch")
    require(cpu_raw.tobytes() == sim_raw.tobytes() == kit_raw.tobytes(),
            "raw-int8 bytes mismatch")

    stages = {
        "float": accuracy(floating, label, pid, truth),
        "int8_cpu": accuracy(cpu, label, pid, truth),
        "simulator": accuracy((sim_raw.astype(np.float64) - zero) * scale, label, pid, truth),
        "kit": accuracy((kit_raw.astype(np.float64) - zero) * scale, label, pid, truth),
    }
    for name, stage in stages.items():
        for category in ("residual", "final_field"):
            compare_metrics(stage[category], expected["stages"][name][category],
                            f"{name}.{category}", args.atol_uT)
    pid_only = metrics(pid - np.abs(truth))
    same_number(pid_only["mae_uT"], expected["pid_only_mae_uT"],
                "PID-only MAE", args.atol_uT)
    compare_metrics(pid_only, constants["results"]["pid_proxy"], "PID-only", args.atol_uT)
    compare_metrics(stages["kit"]["final_field"],
                    constants["results"]["deployed_fcnn_int8_final_field"],
                    "constant report deployed FCNN", args.atol_uT)
    fixed = {}
    for rule in ("train_mean", "train_median"):
        published = constants["results"][rule]
        prediction = finite_number(published["prediction_uT"], rule)
        fixed[rule] = {"prediction_uT": prediction,
                       **metrics(np.full(ROWS, prediction, dtype=np.float64) - np.abs(truth))}
        compare_metrics(fixed[rule], published, rule, args.atol_uT)
    oracle = float(np.mean(np.maximum(np.abs(pid - np.abs(truth)) - CLAMP_UT, 0)))
    require(constants["oracle_bounded_residual"]["clamp_uT"] == CLAMP_UT,
            "oracle clamp mismatch")
    same_number(oracle, constants["oracle_bounded_residual"]["mae_lower_bound_uT"],
                "clairvoyant lower bound", args.atol_uT)

    gap = np.abs(floating - cpu)
    parity = {
        "cpu_vs_simulator_max_abs_lsb": cpu_sim_lsb,
        "simulator_vs_kit_max_abs_lsb": sim_kit_lsb,
        "float_vs_int8_max_abs_uT": float(np.max(gap)),
        "float_vs_int8_mae_uT": float(np.mean(gap)),
    }
    for key, value in parity.items():
        if key.endswith("lsb"):
            require(value == expected["parity"][key], f"{key} mismatch")
        else:
            same_number(value, expected["parity"][key], key, args.atol_uT)
    wall = np.asarray(hw_meta["wall_ms"], dtype=np.float64)
    require(wall.shape == (ROWS,) and np.all(np.isfinite(wall)) and np.all(wall >= 0),
            "recorded kit latency invalid")
    latency = {"median_ms": float(np.median(wall)),
               "p90_ms": float(np.percentile(wall, 90)),
               "max_ms": float(np.max(wall))}
    for key, value in latency.items():
        same_number(value, expected["kit_latency"][key], f"recorded latency {key}",
                    args.atol_uT / 1000)
    criteria = {
        "i_float_vs_int8": bool(parity["float_vs_int8_max_abs_uT"] <= 5.0
                                 and parity["float_vs_int8_mae_uT"] <= 0.5),
        "ii_cpu_vs_simulator": cpu_sim_lsb == 0,
        "iii_simulator_vs_kit": sim_kit_lsb == 0,
        "iv_kit_final_field": stages["kit"]["final_field"]["mae_uT"] <=
                              stages["float"]["final_field"]["mae_uT"] + 0.2,
    }
    for key, passed in criteria.items():
        require(passed and expected["criteria"][key]["status"] == "PASS",
                f"publication criterion failed: {key}")
    require(expected["chain_status"] == "PASS", "reference chain is not PASS")
    return {
        "status": "PASS", "samples": ROWS, "atol_uT": args.atol_uT,
        "stages": stages, "pid_only": pid_only, "parity": parity,
        "fixed_training_constants": fixed,
        "bounded_correction_oracle": {
            "description": "clairvoyant lower bound, not an estimator",
            "clamp_uT": CLAMP_UT, "mae_lower_bound_uT": oracle},
        "kit_latency_recorded_ms": latency,
        "criteria": {key: "PASS" for key in criteria},
        "source_sha256": {
            **{name: arrays_manifest["arrays"][name]["sha256"] for name in ARRAY_FILES},
            **{name: kit_manifest["files"][name]["sha256"] for name in KIT_FILES},
        },
        "scope": "Saved-array arithmetic and recorded kit evidence; no new inference or hardware run",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--hardware-evidence-dir", type=Path, required=True)
    parser.add_argument("--expected-results", type=Path, required=True)
    parser.add_argument("--expected-constants", type=Path, required=True)
    parser.add_argument("--verify-sha256", action="store_true")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--atol-uT", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        out = output_path(args.out, args.run_dir.resolve(), args.hardware_evidence_dir.resolve())
        result = verify(args)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("x") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"PASS: verified {ROWS} saved rows and all recorded references; output: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
