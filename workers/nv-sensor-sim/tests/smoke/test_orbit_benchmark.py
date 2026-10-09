"""Smoke test for the v1 orbit benchmark builder.

Loads ``configs/orbit_benchmark_v1.yaml``, propagates a TRUNCATED 600-sample
slice of every orbit (overriding ``duration_s`` and ``dt_s`` for speed), and
asserts that the producer-manifest + batches together pass the cross-repo
``OrbitDatasetWriter.write_manifest`` validation through to a clean parquet
shard. Also confirms TLE checksum verification fires on tampered input.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
import yaml

pytest.importorskip("sgp4")
pytest.importorskip("ppigrf")
pytest.importorskip("pyarrow")

from nv_sensor_sim.orbits.benchmark import (  # noqa: E402
    _verify_tle_checksum,
    build_orbit_benchmark,
    load_benchmark_config,
)


pytestmark = pytest.mark.smoke


def _make_truncated_v1_config(tmp: Path) -> Path:
    """Copy the real v1 config but cut duration to 60s × dt 30s for speed."""
    src = Path(__file__).resolve().parents[2] / "configs" / "orbit_benchmark_v1.yaml"
    cfg = yaml.safe_load(src.read_text())
    cfg["duration_s"] = 60.0
    cfg["dt_s"] = 30.0
    out = tmp / "orbit_benchmark_v1_truncated.yaml"
    with open(out, "w") as f:
        yaml.safe_dump(cfg, f)
    return out


def test_v1_config_loads_and_validates_tle_checksums():
    cfg = load_benchmark_config()
    assert cfg["duration_s"] == 86400.0
    assert cfg["dt_s"] == 1.0
    assert len(cfg["orbits"]) == 3
    assert {o["orbit_id"] for o in cfg["orbits"]} == {0, 1, 2}


def test_tle_checksum_verifier_rejects_bad_line():
    bad = "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  900X"
    with pytest.raises(ValueError, match="TLE checksum mismatch"):
        _verify_tle_checksum(bad)


def test_tle_checksum_verifier_rejects_wrong_length():
    with pytest.raises(ValueError, match="TLE line must be 69 chars"):
        _verify_tle_checksum("too short")


def test_build_orbit_benchmark_returns_three_batches_and_manifest():
    with tempfile.TemporaryDirectory() as td:
        cfg_path = _make_truncated_v1_config(Path(td))
        batches, manifest = build_orbit_benchmark(cfg_path)

    assert len(batches) == 3
    assert {int(b["orbit_id"][0]) for b in batches} == {0, 1, 2}

    # Manifest sub-dict shape
    assert manifest["sgp4"]["sgp4_version"]
    assert len(manifest["sgp4"]["tles"]) == 3
    assert manifest["igrf"]["model_version"] == "14"
    assert manifest["adcs"]["pointing_rule_version"] == "nadir_v1"
    assert manifest["adcs"]["quaternion_convention"] == "scalar_first_eci_to_body"
    assert manifest["units"]["t"] == "s_since_orbit_epoch"
    assert "splits" in manifest


def test_batches_round_trip_through_orbit_dataset_writer():
    """End-to-end cross-repo gate: writer accepts batches AND validates manifest."""
    tsd_writer = pytest.importorskip("tychon_shared_data.orbit_in_the_loop.writer")

    with tempfile.TemporaryDirectory() as td:
        cfg_path = _make_truncated_v1_config(Path(td))
        batches, producer_manifest = build_orbit_benchmark(cfg_path)

        writer = tsd_writer.OrbitDatasetWriter(td)
        manifest_path = writer.write_all(batches, producer_manifest)
        assert manifest_path.exists()
        # Three parquet shards plus the manifest must be on disk.
        parquets = sorted(Path(td).glob("orbit_*.parquet"))
        assert len(parquets) == 3


def test_b_payload_magnitudes_in_leo_band_across_all_orbits():
    with tempfile.TemporaryDirectory() as td:
        cfg_path = _make_truncated_v1_config(Path(td))
        batches, _ = build_orbit_benchmark(cfg_path)

    for batch in batches:
        Bx = batch["B_payload_x"]
        By = batch["B_payload_y"]
        Bz = batch["B_payload_z"]
        mags = np.sqrt(Bx * Bx + By * By + Bz * Bz)
        assert np.all(mags > 1e-5) and np.all(mags < 1e-4)
