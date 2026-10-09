"""Unit tests for the parameterized merged-dwell trajectory builder.

The dwell family drives one chosen cross-axis line pair together along a single
field direction ``w_hat``: hold (separated) -> ramp in -> merged dwell of D
frames at ``a_merge`` (where the pair is degenerate) -> ramp out -> hold. The
exit topology is set by which side of ``a_merge`` the ramp-out lands on:
``cross`` (opposite side -> the lines swap) vs ``bounce`` (same side -> the
field reverses and the lines return to their entry sides).
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.dynamics.dwell_trajectory import (
    build_dwell_trajectory,
    dwell_scalars,
    merge_direction,
)
from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT


def test_merge_direction_is_unit_and_matches_first_order_slope():
    """merge_direction(p, q) returns the unit vector along sp*n_i - sq*n_j."""
    p, q = 1, 4  # axis0 (s=-1), axis2 (s=+1)
    w_hat, w_norm = merge_direction(p, q)
    expected = -1.0 * NV_AXES_UNIT[0] - 1.0 * NV_AXES_UNIT[2]
    np.testing.assert_allclose(w_hat * w_norm, expected, atol=1e-12)
    np.testing.assert_allclose(np.linalg.norm(w_hat), 1.0, atol=1e-12)


def test_dwell_scalars_cross_and_bounce():
    """cross -> a_out on the opposite side of a_merge; bounce -> same side."""
    a_merge, delta_a = 0.5e-3, 0.3e-3
    a_in_c, a_out_c = dwell_scalars(a_merge, delta_a, "cross", approach_sign=+1)
    a_in_b, a_out_b = dwell_scalars(a_merge, delta_a, "bounce", approach_sign=+1)
    # Same entry side for both.
    assert a_in_c == a_in_b == a_merge + delta_a
    # Cross exits on the far side; bounce returns to the entry side.
    assert a_out_c == a_merge - delta_a
    assert a_out_b == a_merge + delta_a


def test_build_dwell_trajectory_layout_and_holds():
    """Trajectory has the right length and constant hold/dwell segments."""
    bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
    w_hat, _ = merge_direction(1, 4)
    a_in, a_merge, a_out = 1.0e-3, 0.4e-3, -0.2e-3
    pre, ramp, dwell, post = 20, 6, 32, 40
    traj = build_dwell_trajectory(bias, w_hat, a_in, a_merge, a_out, pre, ramp, dwell, post)

    T = pre + ramp + dwell + ramp + post
    assert traj.shape == (T, 3)

    # Recover the scalar coordinate a(t) = w_hat . (B - bias).
    a = (traj - bias[None, :]) @ w_hat
    np.testing.assert_allclose(a[:pre], a_in, atol=1e-12)  # pre-hold
    t1 = pre + ramp
    t2 = t1 + dwell
    np.testing.assert_allclose(a[t1:t2], a_merge, atol=1e-12)  # merged dwell held exactly
    np.testing.assert_allclose(a[t2 + ramp :], a_out, atol=1e-12)  # post-hold


def test_build_dwell_trajectory_ramp_is_monotone_between_knots():
    """The scalar coordinate ramps monotonically in and out of the dwell."""
    bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
    w_hat, _ = merge_direction(1, 4)
    a_in, a_merge, a_out = 1.0e-3, 0.4e-3, -0.2e-3
    pre, ramp, dwell, post = 10, 6, 16, 10
    traj = build_dwell_trajectory(bias, w_hat, a_in, a_merge, a_out, pre, ramp, dwell, post)
    a = (traj - bias[None, :]) @ w_hat

    t1 = pre + ramp
    t2 = t1 + dwell
    ramp_in = a[pre - 1 : t1 + 1]  # a_in ... a_merge
    ramp_out = a[t2 - 1 : t2 + ramp + 1]  # a_merge ... a_out
    assert np.all(np.diff(ramp_in) <= 1e-15)  # decreasing in (a_in > a_merge)
    assert np.all(np.diff(ramp_out) <= 1e-15)  # decreasing out (a_merge > a_out)
