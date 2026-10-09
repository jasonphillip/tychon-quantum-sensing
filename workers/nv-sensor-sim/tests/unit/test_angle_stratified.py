"""Tests for angle-stratified widened sampling (v3 Amendment 1 Option A).

The key behavioral requirement: reach the >=60 deg off-bias cone at the |B|>=3.0 mT
floor (where uniform isotropic sampling gives 0/1500), keep every geometry inside
the pinned grid, and produce both cold-acquire and carry start modes.
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.dynamics.angle_stratified import (
    START_MODE_ACQUIRE,
    START_MODE_CARRY,
    field_at_angle,
    sample_angle_stratified_ramp,
)
from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
    offbias_angle_deg,
)
from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_BIAS = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
_PIN = (2667390522.8636284, 3074609477.1363726)
_D_HZ = 0.5 * (_PIN[0] + _PIN[1])
_FLOOR = 3.0e-3
_T = 128


def _kw(shape: str) -> dict:
    return dict(
        shape=shape,
        angle_max_deg=62.0,
        field_range_T=(3.0e-3, 6.0e-3),
        cold_start_fraction=0.5,
        carry_start_max_deg=15.0,
        carry_field_range_T=(4.0e-3, 5.6e-3),
        min_sweep_delta_T=1.0e-3,
        jitter_frac=0.05,
        min_field_T=_FLOOR,
        window_pin_Hz=_PIN,
        D_hz=_D_HZ,
        gamma_hz_per_T=GAMMA_HZ_PER_T,
        window_margin_hz=0.02 * 0.5 * (_PIN[1] - _PIN[0]),
        min_axis_projection_T=0.4e-3,
        nv_axes=NV_AXES_UNIT,
    )


def test_field_at_angle_exact_angle_and_magnitude():
    for theta in (0.0, 30.0, 53.2, 60.0):
        for phi in (0.0, 1.3, 4.7):
            B = field_at_angle(_BIAS, theta, 3.3e-3, phi)
            assert offbias_angle_deg(B[None, :], _BIAS)[0] == pytest.approx(theta, abs=1e-4)
            assert np.linalg.norm(B) == pytest.approx(3.3e-3, rel=1e-9)


def test_reaches_60_degree_cone_at_floor():
    allowed = min(_D_HZ - _PIN[0], _PIN[1] - _D_HZ)
    max_angles = []
    for seed in range(400):
        traj, _ = sample_angle_stratified_ramp(_BIAS, _T, seed, **_kw("held"))
        max_angles.append(float(offbias_angle_deg(traj, _BIAS).max()))
        assert min_field_magnitude_T(traj) >= _FLOOR - 1e-9
        assert max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, _D_HZ, GAMMA_HZ_PER_T) <= allowed + 1.0
    a = np.array(max_angles)
    # The whole point of Option A: reach >=60 deg where isotropic gave 0/1500, with
    # 53.2 deg in the interior (meaningful density beyond it), not on the rim.
    assert a.max() >= 60.0
    assert np.mean(a >= 53.2) > 0.05
    assert np.mean(a >= 60.0) > 0.01


def test_both_start_modes_appear_and_carry_starts_near_bias():
    modes = {START_MODE_ACQUIRE: 0, START_MODE_CARRY: 0}
    for seed in range(120):
        _, meta = sample_angle_stratified_ramp(_BIAS, _T, seed, **_kw("held"))
        modes[meta["start_mode"]] += 1
        if meta["start_mode"] == START_MODE_CARRY:
            assert meta["start_angle_deg"] <= 15.0 + 1e-9
    assert modes[START_MODE_ACQUIRE] > 0
    assert modes[START_MODE_CARRY] > 0


def test_reversal_shape_and_determinism():
    a, ma = sample_angle_stratified_ramp(_BIAS, _T, 99, **_kw("reversal"))
    b, mb = sample_angle_stratified_ramp(_BIAS, _T, 99, **_kw("reversal"))
    assert np.array_equal(a, b)
    assert ma == mb
    assert a.shape == (_T, 3)
