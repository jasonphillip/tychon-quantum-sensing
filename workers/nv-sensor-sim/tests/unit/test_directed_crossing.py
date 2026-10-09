"""Tests for the directed merge-crossing sampler (v3 directed sub-population).

Uses a hand-built (0,2) merge template from the first-order merge helpers so the
test needs no SimOS adapter. Checks that directed trajectories reach the exact
degeneracy, satisfy the envelope guards, and produce both cross (held) and bounce
(reversal) exit behavior.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.dynamics.coverage_geometry import (
    max_line_offset_over_traj_hz,
    min_field_magnitude_T,
)
from nv_sensor_sim.dynamics.directed_crossing import sample_directed_crossing
from nv_sensor_sim.dynamics.dwell_trajectory import first_order_a_merge, merge_direction
from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
from nv_sensor_sim.dynamics.resonances import GAMMA_HZ_PER_T
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_BIAS = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
_PIN = (2667390522.8636284, 3074609477.1363726)
_D_HZ = 0.5 * (_PIN[0] + _PIN[1])
_GAMMA_FWHM = 1.501e6
_FLOOR = 3.0e-3
_T = 128


def _template_02() -> dict:
    w_hat, w_norm = merge_direction(0, 2)
    a_merge = first_order_a_merge(_BIAS, 0, 2)
    return {
        "p": 0, "q": 2, "p_mirror": 1, "q_mirror": 3,
        "w_hat": w_hat, "w_norm": w_norm, "a_merge": a_merge,
    }


def _kw() -> dict:
    return dict(
        approach_lw_range=(3.0, 5.0),
        gamma_fwhm_hz=_GAMMA_FWHM,
        jitter_frac=0.05,
        min_field_T=_FLOOR,
        window_pin_Hz=_PIN,
        D_hz=_D_HZ,
        gamma_hz_per_T=GAMMA_HZ_PER_T,
        min_axis_projection_T=0.4e-3,
        nv_axes=NV_AXES_UNIT,
    )


def test_directed_reaches_merge_and_satisfies_guards():
    tmpl = _template_02()
    a_merge = tmpl["a_merge"]
    w_hat = tmpl["w_hat"]
    allowed = min(_D_HZ - _PIN[0], _PIN[1] - _D_HZ)
    for seed in range(20):
        traj, meta = sample_directed_crossing(
            [tmpl], _BIAS, _T, seed, template_idx=0, **_kw()
        )
        a = (traj - _BIAS) @ w_hat  # scalar coordinate along the merge direction
        assert np.min(np.abs(a - a_merge)) < 5.0e-5  # reaches the degeneracy (T)
        assert min_field_magnitude_T(traj) >= _FLOOR - 1e-12
        assert (
            max_line_offset_over_traj_hz(traj, NV_AXES_UNIT, _D_HZ, GAMMA_HZ_PER_T)
            <= allowed + 1.0
        )
        assert (meta["merge_p"], meta["merge_q"]) == (0, 2)


def test_directed_produces_both_cross_and_bounce():
    tmpl = _template_02()
    a_merge = tmpl["a_merge"]
    w_hat = tmpl["w_hat"]
    w_norm = tmpl["w_norm"]
    families = set()
    for seed in range(60):
        traj, meta = sample_directed_crossing(
            [tmpl], _BIAS, _T, seed, template_idx=0, **_kw()
        )
        families.add(meta["family"])
        a = (traj - _BIAS) @ w_hat
        sep = GAMMA_HZ_PER_T * w_norm * (a - a_merge)  # first-order pair separation
        if meta["family"] == "held":
            # A cross: separation changes sign across the ramp.
            assert np.sign(sep[0]) != np.sign(sep[-1])
        else:
            # A bounce: separation returns to its entry sign.
            assert np.sign(sep[0]) == np.sign(sep[-1])
    assert families == {"held", "reversal"}


def test_directed_is_deterministic_from_seed():
    tmpl = _template_02()
    a, ma = sample_directed_crossing([tmpl], _BIAS, _T, 777, template_idx=0, **_kw())
    b, mb = sample_directed_crossing([tmpl], _BIAS, _T, 777, template_idx=0, **_kw())
    assert np.array_equal(a, b)
    assert ma == mb
