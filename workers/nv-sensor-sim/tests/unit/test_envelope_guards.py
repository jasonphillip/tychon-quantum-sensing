"""Tests for the v3 per-frame envelope guards (|B| floor + window containment)

added to the isotropic held-ramp and reversal samplers. The guards must (a)
enforce their constraint on every accepted geometry and (b) leave the samplers
byte-identical to the v1/v2 behavior when off (defaults).
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
)
from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    reversal_trajectory,
    sample_isotropic_held_ramp,
    sample_reversal_ramp,
    static_bias_vector,
)
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_BIAS = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
_PIN = (2667390522.8636284, 3074609477.1363726)
_D_HZ = 0.5 * (_PIN[0] + _PIN[1])
_WIDE = (-4.0e-3, 4.0e-3)
_FLOOR = 3.0e-3
_T = 64


def test_isotropic_guards_off_are_byte_identical_to_prior_call():
    # Same seed, min-proj guard active (v1/v2 regime), new guards at defaults →
    # identical to the explicit-defaults call: the new params must not perturb
    # the rng stream or the accept decision.
    kw = dict(
        scalar_range_T=(-1.4e-3, 1.4e-3),
        min_delta_T=1.0e-3,
        n_timesteps=_T,
        min_window_frac=0.25,
        seed=12345,
        jitter_frac=0.05,
        bias_T=_BIAS,
        min_axis_proj_T=0.4e-3,
        nv_axes=NV_AXES_UNIT,
    )
    a = sample_isotropic_held_ramp(**kw)
    b = sample_isotropic_held_ramp(
        **kw, min_field_T=0.0, window_pin_Hz=None, D_hz=0.0, gamma_hz_per_T=0.0
    )
    for x, y in zip(a, b):
        assert np.array_equal(np.asarray(x), np.asarray(y))


def test_isotropic_floor_guard_enforced():
    accepted_min_B = []
    for seed in range(60):
        start, end, t0, t1, _ = sample_isotropic_held_ramp(
            scalar_range_T=_WIDE,
            min_delta_T=1.0e-3,
            n_timesteps=_T,
            min_window_frac=0.25,
            seed=seed,
            jitter_frac=0.05,
            bias_T=_BIAS,
            min_axis_proj_T=0.4e-3,
            nv_axes=NV_AXES_UNIT,
            min_field_T=_FLOOR,
        )
        traj = held_ramp_trajectory(_BIAS, start, end, _T, t0, t1)
        accepted_min_B.append(min_field_magnitude_T(traj))
    assert min(accepted_min_B) >= _FLOOR - 1e-12


def test_isotropic_without_floor_some_geometries_dip_below():
    # Prove the floor guard is load-bearing: without it (min-proj only), the wide
    # scalar range yields geometries whose |B| falls below the 3.0 mT floor.
    dipped = False
    for seed in range(60):
        start, end, t0, t1, _ = sample_isotropic_held_ramp(
            scalar_range_T=_WIDE,
            min_delta_T=1.0e-3,
            n_timesteps=_T,
            min_window_frac=0.25,
            seed=seed,
            jitter_frac=0.05,
            bias_T=_BIAS,
            min_axis_proj_T=0.4e-3,
            nv_axes=NV_AXES_UNIT,
        )
        traj = held_ramp_trajectory(_BIAS, start, end, _T, t0, t1)
        if min_field_magnitude_T(traj) < _FLOOR:
            dipped = True
            break
    assert dipped


def test_isotropic_window_guard_enforced():
    allowed = min(_D_HZ - _PIN[0], _PIN[1] - _D_HZ)
    for seed in range(60):
        start, end, t0, t1, _ = sample_isotropic_held_ramp(
            scalar_range_T=_WIDE,
            min_delta_T=1.0e-3,
            n_timesteps=_T,
            min_window_frac=0.25,
            seed=seed,
            jitter_frac=0.05,
            bias_T=_BIAS,
            min_axis_proj_T=0.4e-3,
            nv_axes=NV_AXES_UNIT,
            window_pin_Hz=_PIN,
            D_hz=_D_HZ,
            gamma_hz_per_T=GAMMA_HZ_PER_T,
        )
        traj = held_ramp_trajectory(_BIAS, start, end, _T, t0, t1)
        assert max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, _D_HZ, GAMMA_HZ_PER_T) <= allowed + 1.0


def test_isotropic_without_window_some_geometries_exceed_pin():
    allowed = min(_D_HZ - _PIN[0], _PIN[1] - _D_HZ)
    exceeded = False
    for seed in range(60):
        start, end, t0, t1, _ = sample_isotropic_held_ramp(
            scalar_range_T=_WIDE,
            min_delta_T=1.0e-3,
            n_timesteps=_T,
            min_window_frac=0.25,
            seed=seed,
            jitter_frac=0.05,
            bias_T=_BIAS,
            min_axis_proj_T=0.4e-3,
            nv_axes=NV_AXES_UNIT,
        )
        traj = held_ramp_trajectory(_BIAS, start, end, _T, t0, t1)
        if max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, _D_HZ, GAMMA_HZ_PER_T) > allowed:
            exceeded = True
            break
    assert exceeded


def test_reversal_guards_enforced():
    allowed = min(_D_HZ - _PIN[0], _PIN[1] - _D_HZ)
    for seed in range(40):
        start, turn, end, t_turn, _ = sample_reversal_ramp(
            scalar_range_T=_WIDE,
            min_delta_T=1.0e-3,
            n_timesteps=_T,
            turn_frac_range=(0.2, 0.8),
            seed=seed,
            jitter_frac=0.05,
            bias_T=_BIAS,
            min_axis_proj_T=0.4e-3,
            nv_axes=NV_AXES_UNIT,
            min_field_T=_FLOOR,
            window_pin_Hz=_PIN,
            D_hz=_D_HZ,
            gamma_hz_per_T=GAMMA_HZ_PER_T,
        )
        traj = reversal_trajectory(_BIAS, start, turn, end, _T, t_turn)
        assert min_field_magnitude_T(traj) >= _FLOOR - 1e-12
        assert max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, _D_HZ, GAMMA_HZ_PER_T) <= allowed + 1.0
