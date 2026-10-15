"""Publication verifier tests using unchanged saved outputs and pinned kit records."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_RUN = ROOT / "docs/kit-run-2026-10-14"
KIT = Path(os.environ["KIT_EVIDENCE_DIR"]) if os.environ.get("KIT_EVIDENCE_DIR") else None
pytestmark = pytest.mark.skipif(KIT is None, reason="set KIT_EVIDENCE_DIR for pinned kit evidence")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(run: Path, kit: Path, out: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/recompute_published_kit_metrics.py"),
         "--run-dir", str(run), "--hardware-evidence-dir", str(kit),
         "--expected-results", str(run / "results.json"),
         "--expected-constants", str(ROOT / "docs/kit_constant_baselines_2026-10.json"),
         "--verify-sha256", "--no-network", "--atol-uT", "0.000001",
         "--out", str(out)],
        capture_output=True, text=True, check=False,
    )


def copy_evidence(tmp_path: Path) -> tuple[Path, Path]:
    run = tmp_path / "run"
    kit = tmp_path / "kit"
    run.mkdir()
    kit.mkdir()
    for name in ("ARRAYS.manifest.json", "labels.npz", "float_pred.npz",
                 "tflite_pred.npz", "input.manifest.json", "results.json"):
        shutil.copy2(SOURCE_RUN / name, run / name)
    for name in ("hw.bin", "hw.json", "sim.npz", "sim.json", "input.int8.npy"):
        shutil.copy2(KIT / name, kit / name)
    return run, kit


def update_manifest(run: Path, section: str, name: str, path: Path) -> None:
    manifest_path = run / "ARRAYS.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    item = manifest["arrays"][name] if section == "arrays" else manifest["external_kit_evidence"]["files"][name]
    item["sha256"] = digest(path)
    item["size_bytes"] = path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def test_real_saved_arrays_match_all_references(tmp_path: Path) -> None:
    out = tmp_path / "result.json"
    proc = invoke(SOURCE_RUN, KIT, out)
    assert proc.returncode == 0, proc.stderr
    result = json.loads(out.read_text())
    assert result["status"] == "PASS"
    assert result["samples"] == 512
    assert abs(result["stages"]["float"]["final_field"]["mae_uT"] - 14.466935546180572) < 1e-6
    assert abs(result["stages"]["kit"]["final_field"]["mae_uT"] - 14.474248643587522) < 1e-6
    assert abs(result["pid_only"]["mae_uT"] - 15.208567604032694) < 1e-6
    assert abs(result["fixed_training_constants"]["train_mean"]["mae_uT"] - 12.559596326205813) < 1e-6
    assert abs(result["fixed_training_constants"]["train_median"]["mae_uT"] - 12.561772464682381) < 1e-6
    assert abs(result["bounded_correction_oracle"]["mae_lower_bound_uT"] - 13.044395457019046) < 1e-6
    assert result["parity"]["cpu_vs_simulator_max_abs_lsb"] == 0
    assert result["parity"]["simulator_vs_kit_max_abs_lsb"] == 0
    assert result["kit_latency_recorded_ms"] == {"median_ms": 0.038, "p90_ms": 0.038, "max_ms": 0.069}


@pytest.mark.parametrize("name", ["labels.npz", "float_pred.npz", "tflite_pred.npz"])
def test_flipped_array_byte_fails_hash(tmp_path: Path, name: str) -> None:
    run, kit = copy_evidence(tmp_path)
    path = run / name
    content = bytearray(path.read_bytes())
    content[-1] ^= 1
    path.write_bytes(content)
    proc = invoke(run, kit, tmp_path / "out.json")
    assert proc.returncode != 0
    assert f"SHA256 mismatch: {name}" in proc.stderr


def test_wrong_shape_fails_even_with_updated_hash(tmp_path: Path) -> None:
    run, kit = copy_evidence(tmp_path)
    path = run / "float_pred.npz"
    with np.load(path, allow_pickle=False) as archive:
        values = archive["delta_b_uT"][:-1]
    np.savez(path, delta_b_uT=values)
    update_manifest(run, "arrays", path.name, path)
    proc = invoke(run, kit, tmp_path / "out.json")
    assert proc.returncode != 0
    assert "wrong shape" in proc.stderr


def test_missing_hardware_file_is_hard_failure(tmp_path: Path) -> None:
    run, kit = copy_evidence(tmp_path)
    (kit / "hw.bin").unlink()
    proc = invoke(run, kit, tmp_path / "out.json")
    assert proc.returncode != 0
    assert "missing evidence" in proc.stderr


def test_raw_int8_mismatch_fails_after_hash_checks(tmp_path: Path) -> None:
    run, kit = copy_evidence(tmp_path)
    sim_path = kit / "sim.npz"
    with np.load(sim_path, allow_pickle=False) as archive:
        values = {name: archive[name] for name in archive.files}
    values["outputs"][0, 0] = np.int8(int(values["outputs"][0, 0]) + 1)
    np.savez(sim_path, **values)
    update_manifest(run, "kit", "sim.npz", sim_path)
    sim_json_path = kit / "sim.json"
    sim_json = json.loads(sim_json_path.read_text())
    sim_json["output"]["sha256"] = digest(sim_path)
    sim_json["output"]["size_bytes"] = sim_path.stat().st_size
    sim_json_path.write_text(json.dumps(sim_json) + "\n")
    update_manifest(run, "kit", "sim.json", sim_json_path)
    proc = invoke(run, kit, tmp_path / "out.json")
    assert proc.returncode != 0
    assert "raw-int8 parity mismatch" in proc.stderr
