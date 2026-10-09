#!/usr/bin/env python3
"""Small, seeded, CPU-only synthetic ODMR training benchmark."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from pathlib import Path

# Set before importing NumPy/SciPy/PyTorch. Keep CPU reductions single threaded.
for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[variable] = "1"
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())

import numpy as np
import torch

from nv_sensor_sim.pipelines.batch_generate import generate_dataset
from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
from odmr_edge_ml.models.mlp import OdmrMLP


ROOT = Path(__file__).resolve().parents[1]
BENCH = Path(__file__).resolve().parent
DATA_SEED = 12345
MODEL_SEED = 20261009
SPLITS = {"train": 1000, "val": 200, "test": 200}
EPOCHS = 1000
MIN_MEAN_GAIN_UT = 1.0


def check_metrics(metrics: dict[str, float], expected: dict) -> list[str]:
    if set(expected["metrics"]) != set(metrics):
        raise RuntimeError("Expected metrics must match measured metrics")
    failed = []
    for name, spec in expected["metrics"].items():
        delta = abs(metrics[name] - spec["value"])
        if delta > spec["absolute_tolerance"]:
            failed.append(f"{name}: {metrics[name]:.6f} vs {spec['value']:.6f} +/- {spec['absolute_tolerance']}")
    mean_gain = metrics["mean_baseline_mae_uT"] - metrics["test_mae_uT"]
    if mean_gain < MIN_MEAN_GAIN_UT:
        failed.append(f"mean gain {mean_gain:.6f} uT < required {MIN_MEAN_GAIN_UT:.6f} uT")
    if metrics["test_mae_uT"] >= metrics["pid_proxy_mae_uT"]:
        failed.append("model test MAE must be lower than PID-proxy MAE")
    return failed


def main() -> int:
    started = time.perf_counter()
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(MODEL_SEED)

    with tempfile.TemporaryDirectory(prefix="odmr-bench-") as directory:
        generate_dataset(
            output_dir=directory,
            n_train=SPLITS["train"],
            n_val=SPLITS["val"],
            n_test=SPLITS["test"],
            master_seed=DATA_SEED,
            n_freq_points=100,
            freq_range_Hz=(2.866e9, 2.874e9),
            noise_mode="deterministic",
            field_sampling="spherical",
            shift_test_ranges=False,
        )
        loader = DatasetLoader(directory, normalize=True)
        data = {name: loader.load_split(name) for name in SPLITS}
        raw = DatasetLoader(directory, normalize=False).load_split("test")

    digest = hashlib.sha256()
    for name, split in data.items():
        assert split.spectra.shape == (SPLITS[name], 100)
        for array in (split.spectra, split.labels, split.seeds):
            digest.update(np.ascontiguousarray(array).tobytes())

    def tensors(name: str) -> tuple[torch.Tensor, torch.Tensor]:
        split = data[name]
        x = torch.from_numpy(np.asarray(split.spectra, dtype=np.float32))
        y = torch.from_numpy(np.linalg.norm(split.labels, axis=1).astype(np.float32)) * 1e6
        return x, y

    train_x, train_y = tensors("train")
    val_x, val_y = tensors("val")
    test_x, test_y = tensors("test")
    model = OdmrMLP(input_dim=100, output_dim=1, hidden_dims=[64, 64])
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    model.train()
    for _ in range(EPOCHS):
        optimizer.zero_grad(set_to_none=True)
        prediction = model(train_x).squeeze(1)
        loss = torch.mean((prediction - train_y / 50.0) ** 2)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        val_pred = model(val_x).squeeze(1) * 50.0
        test_pred = model(test_x).squeeze(1) * 50.0
        metrics = {
            "val_mae_uT": float(torch.mean(torch.abs(val_pred - val_y)).item()),
            "test_mae_uT": float(torch.mean(torch.abs(test_pred - test_y)).item()),
            "test_rmse_uT": float(torch.sqrt(torch.mean((test_pred - test_y) ** 2)).item()),
            "mean_baseline_mae_uT": float(torch.mean(torch.abs(train_y.mean() - test_y)).item()),
        }
    pid = DerivativeZeroCrossingPID(raw.frequencies)
    pid_pred = np.array([result.b_mag_uT for result in pid.estimate_batch(raw.spectra)])
    metrics["pid_proxy_mae_uT"] = float(np.mean(np.abs(pid_pred - test_y.numpy())))

    if not all(math.isfinite(value) for value in metrics.values()):
        raise RuntimeError("Non-finite benchmark metric")
    result = {
        "dataset": "nv-sensor-sim deterministic spherical, disjoint seeds",
        "data_seed": DATA_SEED,
        "split_sizes": SPLITS,
        "data_sha256": digest.hexdigest(),
        "model": "OdmrMLP(input_dim=100, output_dim=1, hidden_dims=[64, 64]); trained here",
        "model_seed": MODEL_SEED,
        "epochs": EPOCHS,
        "required_mean_gain_uT": MIN_MEAN_GAIN_UT,
        "metrics": metrics,
    }
    output = BENCH / "results.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")

    print("Metric                         Value (uT)")
    print("------------------------------------------")
    for name, value in metrics.items():
        print(f"{name:<30} {value:10.4f}")
    print(f"Mean gain: {metrics['mean_baseline_mae_uT'] - metrics['test_mae_uT']:.4f} uT (minimum {MIN_MEAN_GAIN_UT:.4f})")
    print(f"PID-proxy gain: {metrics['pid_proxy_mae_uT'] - metrics['test_mae_uT']:.4f} uT")
    print(f"Runtime: {time.perf_counter() - started:.2f} s")
    print(f"Results: {output.relative_to(ROOT)}")

    expected = json.loads((BENCH / "expected.json").read_text())
    failed = check_metrics(metrics, expected)
    if failed:
        print("Outside tolerance: " + "; ".join(failed))
        return 1
    print("All metrics within expected tolerances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
