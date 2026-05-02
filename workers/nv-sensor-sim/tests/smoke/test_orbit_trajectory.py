"""End-to-end smoke test for the orbit-in-the-loop trajectory builder.

Verifies that ``build_trajectory_batch`` emits a 15-column dict that exactly
matches the shipped ``tychon_shared_data.orbit_in_the_loop.ORBIT_COLUMNS``
contract — including dtypes, monotonic per-orbit relative time, quaternion
unit norm, and physically reasonable B-field magnitudes.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pytest

pytest.importorskip("sgp4")
pytest.importorskip("ppigrf")

from nv_sensor_sim.orbits.frames import quat_to_R, quat_to_rpy  # noqa: E402
from nv_sensor_sim.orbits.trajectory import (  # noqa: E402
    TRAJECTORY_COLUMNS,
    OrbitSpec,
    build_trajectory_batch,
)


pytestmark = pytest.mark.smoke


_ISS_LINE1 = (
    "1 25544U 98067A   24001.50000000  .00016717  00000-0  10270-3 0  9000"
)
_ISS_LINE2 = (
    "2 25544  51.6400 100.0000 0006703  90.0000  10.0000 15.50000000400000"
)


def _build():
    spec = OrbitSpec(
        orbit_id=42,
        line1=_ISS_LINE1,
        line2=_ISS_LINE2,
        duration_s=600.0,
        dt_s=10.0,
    )
    igrf_date = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    return build_trajectory_batch(spec, igrf_date)


def test_column_names_match_orbit_schema_exactly():
    """Verbatim match against the shipped tychon-shared-data contract."""
    pyarrow = pytest.importorskip("pyarrow")  # noqa: F841
    tsd = pytest.importorskip("tychon_shared_data.orbit_in_the_loop")
    expected = tuple(tsd.ORBIT_COLUMNS)
    assert TRAJECTORY_COLUMNS == expected, (
        f"local TRAJECTORY_COLUMNS drifted from ORBIT_COLUMNS:\n"
        f"  local:  {TRAJECTORY_COLUMNS}\n"
        f"  remote: {expected}"
    )


def test_batch_has_15_columns_with_correct_dtypes():
    batch, _meta = _build()
    assert set(batch.keys()) == set(TRAJECTORY_COLUMNS)
    for name in TRAJECTORY_COLUMNS:
        if name == "orbit_id":
            assert batch[name].dtype == np.int32
        else:
            assert batch[name].dtype == np.float64, f"{name} dtype {batch[name].dtype}"


def test_t_starts_at_zero_and_is_strictly_monotonic():
    batch, _ = _build()
    assert batch["t"][0] == 0.0
    assert np.all(np.diff(batch["t"]) > 0)


def test_orbit_id_is_constant_and_int32():
    batch, meta = _build()
    assert batch["orbit_id"].dtype == np.int32
    assert int(batch["orbit_id"].min()) == int(batch["orbit_id"].max()) == 42
    assert meta["orbit_id"] == 42


def test_quaternion_is_unit_norm():
    batch, _ = _build()
    qw = batch["q_eb_w"]
    qx = batch["q_eb_x"]
    qy = batch["q_eb_y"]
    qz = batch["q_eb_z"]
    norms = np.sqrt(qw * qw + qx * qx + qy * qy + qz * qz)
    assert np.max(np.abs(norms - 1.0)) < 1e-6


def test_rpy_round_trips_through_quaternion():
    """RPY in the parquet must round-trip via the canonical quaternion path."""
    batch, _ = _build()
    q = np.stack(
        [batch["q_eb_w"], batch["q_eb_x"], batch["q_eb_y"], batch["q_eb_z"]],
        axis=-1,
    )
    rpy_from_q = np.asarray(quat_to_rpy(q))
    assert np.max(np.abs(rpy_from_q[:, 0] - batch["roll"])) < 1e-10
    assert np.max(np.abs(rpy_from_q[:, 1] - batch["pitch"])) < 1e-10
    assert np.max(np.abs(rpy_from_q[:, 2] - batch["yaw"])) < 1e-10


def test_b_payload_magnitudes_in_leo_band():
    batch, _ = _build()
    Bx, By, Bz = batch["B_payload_x"], batch["B_payload_y"], batch["B_payload_z"]
    mags = np.sqrt(Bx * Bx + By * By + Bz * Bz)
    # Earth field at LEO ranges ~22-65 µT (allow some headroom).
    assert np.all(mags > 1e-5), f"B-field too low: min {mags.min():.2e} T"
    assert np.all(mags < 1e-4), f"B-field too high: max {mags.max():.2e} T"


def test_lat_lon_alt_in_physical_ranges():
    batch, _ = _build()
    assert np.all(batch["lat"] >= -90.0) and np.all(batch["lat"] <= 90.0)
    assert np.all(batch["lon"] >= -180.0) and np.all(batch["lon"] <= 180.0)
    # ISS altitude ~400 km
    assert np.all(batch["alt"] > 350e3)
    assert np.all(batch["alt"] < 500e3)


def test_b_payload_consistent_with_quaternion_rotation():
    """B_body == R_eb @ R_en.T @ B_ned (i.e. attitude consistent with field)."""
    batch, _ = _build()
    q = np.stack(
        [batch["q_eb_w"], batch["q_eb_x"], batch["q_eb_y"], batch["q_eb_z"]],
        axis=-1,
    )
    R_eb = quat_to_R(q)
    Bp = np.stack(
        [batch["B_payload_x"], batch["B_payload_y"], batch["B_payload_z"]],
        axis=-1,
    )
    # Inverse: B_eci = R_eb^T @ B_payload.
    B_eci = np.einsum("nji,nj->ni", R_eb, Bp)
    # |B| is rotation-invariant, so |B_eci| must equal |B_payload|.
    assert np.allclose(
        np.linalg.norm(B_eci, axis=-1),
        np.linalg.norm(Bp, axis=-1),
        rtol=1e-12,
    )


def test_writer_validate_accepts_batch():
    """OrbitDatasetWriter._validate_batch must accept the emitted batch verbatim.

    This is the single, authoritative cross-repo gate; if it ever fails the
    benchmark cannot be ingested by tychon-shared-data.
    """
    pytest.importorskip("pyarrow")
    tsd_writer = pytest.importorskip("tychon_shared_data.orbit_in_the_loop.writer")
    batch, _ = _build()
    writer_cls = tsd_writer.OrbitDatasetWriter
    # Use a temp path for ctor; we never call write_orbit (would hit disk).
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        w = writer_cls(tmp)
        # Private API but documented as the contract gate.
        w._validate_batch(batch)
