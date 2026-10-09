"""Smoke test for the hierarchical INT8 cascade end-to-end pipeline.

Runs experiments/cascade_v1_train.py main() with --quick on the golden
100/20/20 dataset (2 epochs each stage). Verifies:

  * cascade_manifest.json parses via CascadeManifest;
  * COARSE + FINE TFLite artifacts exist and the manifest's SHA256s
    match the on-disk file bytes;
  * verify_bit_exact returns ok=True on the saved 32-spectrum fixture
    using the same self-check rounding mode the orchestrator emitted;
  * cascade_eval_report.json carries the expected metric keys.

Skipped if CUDA isn't available or the golden dataset isn't on disk.
The full smoke run takes ~30-45 s on a GB10.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import torch
pytest.importorskip('tychon_shared_data', reason='needs the private tychon_shared_data package')
from tychon_shared_data.cascade import CascadeManifest, verify_bit_exact

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
EXPERIMENTS_DIR = REPO_ROOT / "experiments"
GOLDEN_DIR = REPO_ROOT / "data/golden"


def _import_cascade_v1_train():
    sys.path.insert(0, str(EXPERIMENTS_DIR))
    try:
        return importlib.import_module("cascade_v1_train")
    finally:
        # don't pollute sys.path beyond the import
        if str(EXPERIMENTS_DIR) in sys.path:
            sys.path.remove(str(EXPERIMENTS_DIR))


@pytest.fixture(scope="module")
def cascade_run(tmp_path_factory) -> Path:
    """Run the cascade orchestrator once, share results across tests."""
    if not torch.cuda.is_available():
        pytest.skip("CUDA required for cascade smoke test")
    if not (GOLDEN_DIR / "dataset.h5").exists():
        pytest.skip("golden dataset not present at data/golden/")

    out_dir = tmp_path_factory.mktemp("cascade_v1_smoke")
    cv1 = _import_cascade_v1_train()
    rc = cv1.main([
        "--dataset", str(GOLDEN_DIR),
        "--output", str(out_dir),
        "--quick",
        "--seed", "0",
    ])
    assert rc == 0, f"cascade_v1_train.main() returned {rc}"
    return out_dir


def test_cascade_manifest_exists_and_parses(cascade_run: Path) -> None:
    manifest_path = cascade_run / "cascade_manifest.json"
    assert manifest_path.exists(), f"missing {manifest_path}"
    manifest = CascadeManifest.from_json(manifest_path)
    assert manifest.coarse_model["quantization_granularity"] == "per_tensor"
    assert manifest.fine_model["quantization_granularity"] == "per_tensor"
    assert manifest.composition["mode"] == "additive_raw_x"
    # The on-disk manifest MUST keep the TBD placeholder per LOCKED CONTRACT #1.
    assert (
        manifest.composition["rounding_mode"] == "TBD_AFTER_VECTORBLOX_DOC_CHECK"
    )


def test_cascade_tflite_artifacts_match_manifest_sha256(cascade_run: Path) -> None:
    manifest = CascadeManifest.from_json(cascade_run / "cascade_manifest.json")
    for name in ("coarse_model", "fine_model"):
        block = getattr(manifest, name)
        path = cascade_run / block["tflite_path"]
        assert path.exists() and path.stat().st_size > 0, f"{name} tflite missing"
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_sha == block["tflite_sha256"], (
            f"{name} SHA256 drift: manifest={block['tflite_sha256']} "
            f"actual={actual_sha}"
        )


def test_bit_exact_fixture_self_check(cascade_run: Path) -> None:
    """verify_bit_exact must succeed on the on-disk fixture using the
    same self-check rounding mode the orchestrator wrote."""
    fixture = np.load(cascade_run / "bit_exact_fixture.npz")
    x_int8 = fixture["x_int8"]
    expected_y_int8 = fixture["expected_y_int8"]
    self_check_mode = str(fixture["self_check_rounding_mode"])

    manifest = CascadeManifest.from_json(cascade_run / "cascade_manifest.json")
    # Substitute the self-check rounding mode (on-disk has TBD placeholder)
    manifest.composition["rounding_mode"] = self_check_mode

    from odmr_edge_ml.cascade.runners import make_int8_runner
    coarse_runner = make_int8_runner(cascade_run / "coarse_int8.tflite")
    fine_runner = make_int8_runner(cascade_run / "fine_int8.tflite")
    ok, report = verify_bit_exact(
        x_int8, expected_y_int8, manifest,
        coarse_runner=coarse_runner, fine_runner=fine_runner,
    )
    assert ok, f"verify_bit_exact failed: {report}"
    assert report["n_mismatch"] == 0


def test_cascade_eval_report_has_required_keys(cascade_run: Path) -> None:
    report = json.loads((cascade_run / "cascade_eval_report.json").read_text())
    required = {
        "cascade_deployed_val_mae_uT",
        "pid_only_val_mae_uT",
        "cascade_reduction_pct_vs_pid",
        "coarse_val_mae_uT",
        "fine_val_mae_uT",
        "coarse_learned_sigma",
        "fine_learned_sigma",
    }
    missing = required - set(report.keys())
    assert not missing, f"missing keys: {missing}"
    # Sanity: PID-only MAE should be > 0 (non-degenerate signal).
    assert report["pid_only_val_mae_uT"] > 0
    # Sigmas should be positive and not collapse to the 0.1 floor.
    assert report["coarse_learned_sigma"] > 0.1
    assert report["fine_learned_sigma"] > 0.1
