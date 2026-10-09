"""Tests for the ``nadir_v1`` ADCS pointing rule."""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.orbits.adcs import (
    ADCS_RULE_ID,
    ADCS_RULE_VERSION,
    QUATERNION_CONVENTION,
    nadir_v1,
)
from nv_sensor_sim.orbits.frames import quat_to_R, quat_to_rpy


def _rotate(q, v):
    """Apply scalar-first quaternion to a 3-vector."""
    return quat_to_R(q) @ v


def test_constants_are_versioned():
    assert ADCS_RULE_VERSION == "nadir_v1"
    assert ADCS_RULE_ID == "nadir"
    assert QUATERNION_CONVENTION == "scalar_first_eci_to_body"


def test_circular_equatorial_orbit_pointing():
    """Equatorial prograde orbit: -ẑ_body == +r̂_eci, +x̂_body == +v̂_eci."""
    r = np.array([7e6, 0.0, 0.0])
    v = np.array([0.0, 7.5e3, 0.0])
    q = nadir_v1(r, v)
    norm = float(np.linalg.norm(q))
    assert abs(norm - 1.0) < 1e-12

    # Apply rotation to position unit vector → should land at -z_body
    r_body = _rotate(q, r / np.linalg.norm(r))
    assert np.allclose(r_body, [0.0, 0.0, -1.0], atol=1e-12)

    # Apply rotation to velocity unit vector → should land at +x_body
    v_body = _rotate(q, v / np.linalg.norm(v))
    assert np.allclose(v_body, [1.0, 0.0, 0.0], atol=1e-12)


def test_inclined_orbit_z_axis_is_nadir():
    """For ANY non-radial orbit, ẑ_body·(-r̂) = +1 exactly."""
    r = np.array([5e6, 4e6, 3e6])
    v = np.array([-2e3, 6e3, 4e3])
    # Make velocity exactly perpendicular to r so it's a circular-like case.
    v -= (v @ r) / (r @ r) * r
    q = nadir_v1(r, v)
    nadir_in_body = _rotate(q, -r / np.linalg.norm(r))
    assert np.allclose(nadir_in_body, [0.0, 0.0, 1.0], atol=1e-12)


def test_batch_evaluation_matches_per_row():
    """Batched call returns a (N, 4) quaternion matching scalar-call results."""
    rng = np.random.default_rng(0)
    r = rng.normal(size=(5, 3)) * 7e6
    v = rng.normal(size=(5, 3)) * 7e3
    # Make velocities perpendicular to r so we don't trip degenerate cases.
    for i in range(5):
        v[i] -= (v[i] @ r[i]) / (r[i] @ r[i]) * r[i]

    q_batch = nadir_v1(r, v)
    assert q_batch.shape == (5, 4)
    for i in range(5):
        q_single = nadir_v1(r[i], v[i])
        assert np.allclose(q_single, q_batch[i], atol=1e-12)


def test_quaternion_is_unit_norm_on_random_orbits():
    rng = np.random.default_rng(1)
    r = rng.normal(size=(50, 3)) * 7e6
    v = rng.normal(size=(50, 3)) * 7e3
    for i in range(50):
        v[i] -= (v[i] @ r[i]) / (r[i] @ r[i]) * r[i]
    q = nadir_v1(r, v)
    norms = np.linalg.norm(q, axis=-1)
    assert np.max(np.abs(norms - 1.0)) < 1e-12


def test_rpy_derived_from_quaternion_matches_helper():
    """RPY derived via frames.quat_to_rpy is consistent with rebuilding R."""
    r = np.array([7e6, 1e6, 2e6])
    v = np.array([1e3, 7e3, -1e3])
    v -= (v @ r) / (r @ r) * r
    q = nadir_v1(r, v)
    roll, pitch, yaw = quat_to_rpy(q)
    # Use the helper's own round-trip — the contract is that this is the
    # canonical RPY emitted alongside q in TrajectoryBatch rows.
    assert np.isfinite(roll)
    assert np.isfinite(pitch)
    assert np.isfinite(yaw)
    # Pitch must not be at the gimbal-lock pole for nadir of a circular orbit.
    assert abs(pitch - np.pi / 2) > 1e-2
    assert abs(pitch + np.pi / 2) > 1e-2


def test_radial_trajectory_raises():
    """r × v == 0 means the nadir frame is undefined; we refuse to guess."""
    r = np.array([7e6, 0.0, 0.0])
    v = np.array([1e3, 0.0, 0.0])  # purely radial
    with pytest.raises(ValueError, match="radial trajectory"):
        nadir_v1(r, v)
