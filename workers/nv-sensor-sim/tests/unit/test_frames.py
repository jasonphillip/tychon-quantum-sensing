"""Frame and quaternion round-trip tests."""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.orbits.frames import (
    R_to_quat,
    eci_to_ecef,
    ecef_to_eci,
    ecef_to_geodetic,
    quat_to_R,
    quat_to_rpy,
    rpy_to_quat,
)


@pytest.mark.parametrize(
    "yaw,pitch,roll",
    [
        (0.0, 0.0, 0.0),
        (0.5, 0.3, -0.2),
        (np.pi / 4, np.pi / 6, -np.pi / 5),
        (-np.pi / 3, -0.4, 0.1),
        (1.234, -1.0, 0.567),
    ],
)
def test_rpy_quaternion_round_trip(yaw, pitch, roll):
    """RPY → q → RPY is identity within 1e-12, away from gimbal-lock pole."""
    q = rpy_to_quat(roll, pitch, yaw)
    norm = np.sqrt(np.sum(q * q))
    assert abs(norm - 1.0) < 1e-15, f"q not unit-norm: ‖q‖={norm}"
    assert q[0] >= 0.0, "scalar component must be in non-negative hemisphere"
    roll_back, pitch_back, yaw_back = quat_to_rpy(q)
    assert abs(roll_back - roll) < 1e-12
    assert abs(pitch_back - pitch) < 1e-12
    assert abs(yaw_back - yaw) < 1e-12


def test_R_quaternion_round_trip_random():
    """quat_to_R(R_to_quat(R)) recovers a random rotation matrix within 1e-12."""
    rng = np.random.default_rng(42)
    for _ in range(20):
        # Random rotation via random quaternion (w >= 0)
        q = rng.normal(size=4)
        q /= np.linalg.norm(q)
        if q[0] < 0:
            q = -q
        R = quat_to_R(q)
        q_back = R_to_quat(R)
        R_back = quat_to_R(q_back)
        assert np.max(np.abs(R - R_back)) < 1e-12


def test_quaternion_unit_norm_under_round_trip():
    """rpy_to_quat output is always exactly unit norm."""
    rng = np.random.default_rng(7)
    yaws = rng.uniform(-np.pi, np.pi, size=50)
    pitches = rng.uniform(-1.4, 1.4, size=50)  # avoid ±π/2
    rolls = rng.uniform(-np.pi, np.pi, size=50)
    for y, p, r in zip(yaws, pitches, rolls):
        q = rpy_to_quat(r, p, y)
        assert abs(np.sqrt(np.sum(q * q)) - 1.0) < 1e-15


def test_eci_ecef_round_trip():
    """ECI → ECEF → ECI is identity for a fixed JD UT1."""
    rng = np.random.default_rng(0)
    jd = 2_460_000.5  # 2023-02-25 mid-day UT1
    r_eci = rng.normal(size=3) * 7000e3
    r_ecef = eci_to_ecef(r_eci, jd)
    r_back = ecef_to_eci(r_ecef, jd)
    assert np.max(np.abs(r_eci - r_back)) < 1e-6


def test_ecef_to_geodetic_known_points():
    """Closed-form Bowring geodetic conversion against known surface points."""
    a = 6378137.0
    # Equator, prime meridian, on the ellipsoid surface.
    r = np.array([a, 0.0, 0.0])
    lat, lon, alt = ecef_to_geodetic(r)
    assert abs(lat) < 1e-10
    assert abs(lon) < 1e-10
    assert abs(alt) < 1e-3

    # North pole (z = b)
    b = a * np.sqrt(1.0 - 6.69437999014e-3)
    r = np.array([0.0, 0.0, b])
    lat, lon, alt = ecef_to_geodetic(r)
    assert abs(lat - np.pi / 2) < 1e-6
    assert abs(alt) < 1e-3

    # 400 km altitude above the equator at lon = 90°
    r = np.array([0.0, a + 400e3, 0.0])
    lat, lon, alt = ecef_to_geodetic(r)
    assert abs(lat) < 1e-10
    assert abs(lon - np.pi / 2) < 1e-10
    assert abs(alt - 400e3) < 1e-3


def test_quaternion_from_identity_matrix():
    """Identity matrix maps to (1, 0, 0, 0)."""
    R = np.eye(3)
    q = R_to_quat(R)
    assert abs(q[0] - 1.0) < 1e-15
    assert np.max(np.abs(q[1:])) < 1e-15
