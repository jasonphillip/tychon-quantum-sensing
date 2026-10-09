"""Unit tests for the coverage-geometry helpers (off-bias angle, min |B|,

analytic line-offset estimate) used by the v3 widened-envelope samplers.
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.dynamics.coverage_geometry import (
    line_offset_estimate_hz,
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
    offbias_angle_deg,
)
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT


def test_offbias_angle_zero_when_parallel():
    bias = np.array([0.2, 0.1, 1.0])
    traj = (bias / np.linalg.norm(bias))[None, :] * 5.0e-3
    # arccos is ill-conditioned near parallel (derivative -> inf), so float error
    # in the normalized dot maps to ~1e-6 deg; 1e-3 deg is still far tighter than
    # any physical relevance.
    assert offbias_angle_deg(traj, bias)[0] == pytest.approx(0.0, abs=1e-3)


def test_offbias_angle_ninety_when_perpendicular():
    bias = np.array([0.0, 0.0, 1.0])
    traj = np.array([[1.0e-3, 0.0, 0.0]])
    assert offbias_angle_deg(traj, bias)[0] == pytest.approx(90.0, abs=1e-6)


def test_offbias_angle_per_frame_shape_and_known_value():
    bias = np.array([0.0, 0.0, 1.0])
    # 45 deg: equal z and x components.
    traj = np.array([[0.0, 0.0, 1.0e-3], [1.0e-3, 0.0, 1.0e-3]])
    ang = offbias_angle_deg(traj, bias)
    assert ang.shape == (2,)
    assert ang[0] == pytest.approx(0.0, abs=1e-6)
    assert ang[1] == pytest.approx(45.0, abs=1e-6)


def test_min_field_magnitude_picks_interior_min():
    # |B| along a linear scalar ramp is convex; the interior frame is the min.
    traj = np.array([[5.0e-3, 0.0, 0.0], [1.0e-3, 0.0, 0.0], [3.0e-3, 0.0, 0.0]])
    assert min_field_magnitude_T(traj) == pytest.approx(1.0e-3, abs=1e-12)


def test_line_offset_estimate_positive_and_monotone_in_projection():
    D_hz = 2.871e9
    small = line_offset_estimate_hz(
        np.array([1.0e-3, 0.0, 0.0]), NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T
    )
    large = line_offset_estimate_hz(
        np.array([4.0e-3, 0.0, 0.0]), NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T
    )
    assert small > 0.0
    assert large > small


def test_max_line_offset_over_traj_matches_single_frame_for_one_frame():
    D_hz = 2.871e9
    B = np.array([3.0e-3, 0.0, 1.0e-3])
    single = line_offset_estimate_hz(B, NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T)
    traj = max_line_offset_over_traj_hz(B[None, :], NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T)
    assert traj == pytest.approx(single, rel=1e-12)


def test_max_line_offset_over_traj_is_the_max_frame():
    D_hz = 2.871e9
    traj = np.array([[1.0e-3, 0.0, 0.0], [4.0e-3, 0.0, 0.0], [2.0e-3, 0.0, 0.0]])
    per_frame = [
        line_offset_estimate_hz(traj[t], NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T)
        for t in range(traj.shape[0])
    ]
    got = max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, D_hz, GAMMA_HZ_PER_T)
    assert got == pytest.approx(max(per_frame), rel=1e-12)
