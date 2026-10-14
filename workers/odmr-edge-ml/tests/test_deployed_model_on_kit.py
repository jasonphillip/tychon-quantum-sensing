"""Original-data preparation and synthetic pfkit parity acceptance."""

import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments/deployed_model_on_kit.py"
PREPARE_PYTHON = Path("~/miniconda3/envs/tfc2/bin/python3")


@pytest.fixture(scope="module")
def prepared(tmp_path_factory):
    run = tmp_path_factory.mktemp("deployed-kit")
    subprocess.run(
        [str(PREPARE_PYTHON), str(SCRIPT), "--prepare", "--out", str(run), "--rows", "8"],
        check=True, cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "TF_CPP_MIN_LOG_LEVEL": "3"},
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


def test_evaluate_synthetic_exact_kit_parity(prepared):
    with np.load(prepared / "tflite_pred.npz") as cpu:
        raw = cpu["raw_int8"].copy()
    np.savez(prepared / "sim.npz", outputs=raw.reshape(-1, 1))
    (prepared / "sim.json").write_text(json.dumps({"status": "completed"}))
    (prepared / "hw.bin").write_bytes(raw.tobytes())
    (prepared / "hw.json").write_text(json.dumps({
        "exit_code": 0, "completed": 8, "samples": 8, "wall_ms": [0.04] * 8,
    }))
    result = subprocess.run(
        [str(PREPARE_PYTHON), str(SCRIPT), "--evaluate", "--run", str(prepared)],
        check=True, cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "TF_CPP_MIN_LOG_LEVEL": "3"},
    )
    output = json.loads((prepared / "results.json").read_text())
    assert output["parity"]["simulator_vs_kit_max_abs_lsb"] == 0
    assert output["criteria"]["ii_cpu_vs_simulator"]["status"] == "PASS"
    assert output["criteria"]["iii_simulator_vs_kit"]["status"] == "PASS"
    assert "PASS: iii_simulator_vs_kit" in result.stdout
    assert (prepared / "results.md").is_file()
