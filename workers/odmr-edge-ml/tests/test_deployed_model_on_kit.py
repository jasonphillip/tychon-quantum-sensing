"""Original-data preparation and synthetic pfkit parity acceptance."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/deployed_model_on_kit.py"
sys.path.insert(0, str(ROOT / "experiments"))
DATASET_ROOT = Path(os.environ.get(
    "ODMR_DATASET_ROOT", "~/projects/tychon-shared-data/production_50k_v2_aic"))
ENV = {**os.environ, "TF_CPP_MIN_LOG_LEVEL": "3"}


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    if not (DATASET_ROOT / "dataset.h5").is_file():
        pytest.skip(f"live dataset absent: {DATASET_ROOT}")
    from deployed_model_on_kit import tf_python
    try:
        python = tf_python()
    except RuntimeError as error:
        pytest.skip(str(error))
    if not Path(python).exists():
        pytest.skip(f"TFLite interpreter missing: {python}")
    run = tmp_path_factory.mktemp("deployed-kit")
    subprocess.run(
        [python, str(SCRIPT), "--prepare", "--out", str(run), "--rows", "8"],
        check=True, cwd=ROOT, capture_output=True, text=True, env=ENV,
    )
    return run


def test_prepare_original_eight_rows(prepared):
    manifest = json.loads((prepared / "input.manifest.json").read_text())
    assert manifest["dataset_md5"] == "b350320066a4c6a4553f05cd1f469704"
    assert manifest["row_indices"] == list(range(8))
    inputs = np.load(prepared / "input.int8.npy")
    assert inputs.shape == (8, 1, 100, 2)
    assert inputs.dtype == np.int8
    with np.load(prepared / "labels.npz") as labels:
        assert set(labels.files) == {"delta_b_uT", "b_pid_uT", "b_true_uT"}
        assert all(labels[key].shape == (8,) for key in labels.files)
    with np.load(prepared / "float_pred.npz") as floating:
        assert floating["delta_b_uT"].shape == (8,)
    with np.load(prepared / "tflite_pred.npz") as cpu:
        assert cpu["raw_int8"].shape == (8,)
        assert cpu["raw_int8"].dtype == np.int8


def test_evaluate_synthetic_exact_kit_parity(tmp_path):
    n = 8
    run = tmp_path
    inputs = np.zeros((n, 1, 100, 2), dtype=np.int8)
    np.save(run / "input.int8.npy", inputs)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    scale, zp = 0.01, 0
    raw = np.arange(-4, 4, dtype=np.int8)
    delta = (raw.astype(np.float64) - zp) * scale
    manifest = {
        "row_indices": list(range(n)), "shape": list(inputs.shape), "dtype": "int8",
        "npy_sha256": sha(run / "input.int8.npy"),
        "output_scale": scale, "output_zero_point": zp, "dataset_md5": "synthetic",
        "model_sha256": sha(ROOT / "exports/fcnn_v2_residual_dataset_a_int8.tflite"),
        "checkpoint_sha256": sha(ROOT / "checkpoints/best_model_dataset_a.pt"),
    }
    (run / "input.manifest.json").write_text(json.dumps(manifest))
    pid = np.full(n, 50.0)
    np.savez(run / "labels.npz", delta_b_uT=delta, b_pid_uT=pid, b_true_uT=pid + delta)
    np.savez(run / "float_pred.npz", delta_b_uT=delta)
    np.savez(run / "tflite_pred.npz", raw_int8=raw, delta_b_uT=delta)
    np.savez(run / "sim.npz", outputs=raw.reshape(-1, 1))
    (run / "sim.json").write_text(json.dumps({"status": "completed"}))
    (run / "hw.bin").write_bytes(raw.tobytes())
    (run / "hw.json").write_text(json.dumps({
        "exit_code": 0, "completed": 8, "samples": 8, "wall_ms": [0.04] * 8,
    }))
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--evaluate", "--run", str(run)],
        check=True, cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "TF_CPP_MIN_LOG_LEVEL": "3"},
    )
    output = json.loads((run / "results.json").read_text())
    assert output["parity"]["simulator_vs_kit_max_abs_lsb"] == 0
    assert output["criteria"]["ii_cpu_vs_simulator"]["status"] == "PASS"
    assert output["criteria"]["iii_simulator_vs_kit"]["status"] == "PASS"
    assert "PASS: iii_simulator_vs_kit" in result.stdout
    assert (run / "results.md").is_file()
