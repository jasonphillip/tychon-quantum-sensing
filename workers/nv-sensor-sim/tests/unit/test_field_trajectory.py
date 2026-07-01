"""Unit tests for lab-frame field trajectories and the isotropic held-ramp sampler."""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.dynamics.field_trajectory import (
    held_ramp_trajectory,
    ou_field_perturbation,
    ramp_crossing_trajectory,
    reversal_trajectory,
    sample_isotropic_held_ramp,
    sample_reversal_ramp,
    static_bias_vector,
)
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

_RANGE = (-1.4e-3, 1.4e-3)
_MIN_DELTA = 1.0e-3
_T = 64
_WINDOW_FRAC = 0.25


def _sample(seed, jitter=0.0, **kwargs):
    return sample_isotropic_held_ramp(
        _RANGE, _MIN_DELTA, _T, _WINDOW_FRAC, seed=seed, jitter_frac=jitter, **kwargs
    )


class TestSampleIsotropicHeldRamp:
    def test_reproducible_from_seed(self):
        a = _sample(123, jitter=0.05)
        b = _sample(123, jitter=0.05)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)

    def test_different_seeds_differ(self):
        a = _sample(1)
        b = _sample(2)
        assert not np.allclose(a[0], b[0])

    def test_endpoints_collinear_scalars_in_range(self):
        for seed in range(60):
            start, end, _, _, _ = _sample(seed)
            # Without jitter both endpoints lie on the shared direction u.
            cross = np.linalg.norm(np.cross(start, end))
            assert cross < 1e-12
            delta = np.linalg.norm(end - start)
            assert delta >= _MIN_DELTA - 1e-12
            for v in (start, end):
                s = np.linalg.norm(v)
                assert s <= max(abs(_RANGE[0]), abs(_RANGE[1])) + 1e-12

    def test_independent_endpoints_not_antisymmetric(self):
        # With independent scalar draws, |start| == |end| is measure-zero.
        asym = 0
        for seed in range(40):
            start, end, _, _, _ = _sample(seed)
            if abs(np.linalg.norm(start) - np.linalg.norm(end)) > 1e-9:
                asym += 1
        assert asym == 40

    def test_ramp_window_bounds_and_variety(self):
        span_min = int(np.ceil(_WINDOW_FRAC * (_T - 1)))
        t0s, spans = [], []
        for seed in range(100):
            _, _, t0, t1, _ = _sample(seed)
            assert 0 <= t0 < t1 <= _T - 1
            assert t1 - t0 >= span_min
            t0s.append(t0)
            spans.append(t1 - t0)
        assert len(set(t0s)) > 10, "ramp start times do not vary"
        assert len(set(spans)) > 10, "ramp window lengths do not vary"

    def test_directions_cover_the_sphere(self):
        units = []
        for seed in range(300):
            start, end, _, _, _ = _sample(seed)
            d = end - start
            units.append(d / np.linalg.norm(d))
        units_arr = np.stack(units)
        assert np.linalg.norm(units_arr.mean(axis=0)) < 0.15
        octants = {tuple(s) for s in np.sign(units_arr).astype(int)}
        assert len(octants) == 8

    def test_jitter_perturbs_endpoints(self):
        s0, e0, t0a, t1a, _ = _sample(9, jitter=0.0)
        s1, e1, t0b, t1b, _ = _sample(9, jitter=0.05)
        # Same direction/scalar/window draws, endpoints shifted by O(jitter * delta).
        assert (t0a, t1a) == (t0b, t1b)
        delta = np.linalg.norm(e0 - s0)
        assert 0.0 < np.linalg.norm(s1 - s0) < 0.5 * delta
        assert 0.0 < np.linalg.norm(e1 - e0) < 0.5 * delta

    def test_min_projection_guard_rejects_and_respects_floor(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        min_proj = 0.4e-3
        total_rejects = 0
        for seed in range(300):
            start, end, _, _, n_rej = _sample(
                seed, bias_T=bias, min_axis_proj_T=min_proj, nv_axes=NV_AXES_UNIT
            )
            total_rejects += n_rej
            p0 = NV_AXES_UNIT @ (bias + start)
            p1 = NV_AXES_UNIT @ (bias + end)
            seg_min = np.where(p0 * p1 <= 0, 0.0, np.minimum(np.abs(p0), np.abs(p1)))
            assert seg_min.min() >= min_proj - 1e-15
        # The accepted geometry changes only for seeds that actually rejected;
        # make the guard observable at a floor high enough to trigger.
        aggressive = 0
        for seed in range(300):
            _, _, _, _, n_rej = _sample(
                seed, bias_T=bias, min_axis_proj_T=1.5e-3, nv_axes=NV_AXES_UNIT
            )
            aggressive += n_rej
        assert aggressive > 0, "guard never rejected at an aggressive floor"

    def test_guard_requires_nv_axes(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        with pytest.raises(ValueError, match="nv_axes"):
            _sample(0, bias_T=bias, min_axis_proj_T=0.4e-3)

    def test_guard_bailout_on_impossible_floor(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        with pytest.raises(RuntimeError, match="rejected"):
            _sample(
                0,
                bias_T=bias,
                min_axis_proj_T=50.0e-3,  # unreachable: bias projections are ~2-4 mT
                nv_axes=NV_AXES_UNIT,
                max_resamples=50,
            )

    def test_invalid_args_rejected(self):
        with pytest.raises(ValueError, match="lo < hi"):
            sample_isotropic_held_ramp((1.0e-3, 1.0e-3), _MIN_DELTA, _T, 0.25, seed=0)
        with pytest.raises(ValueError, match="min_delta_T"):
            sample_isotropic_held_ramp(_RANGE, 0.0, _T, 0.25, seed=0)
        with pytest.raises(ValueError, match="min_delta_T"):
            sample_isotropic_held_ramp(_RANGE, 5.0e-3, _T, 0.25, seed=0)  # > hi - lo
        with pytest.raises(ValueError, match="min_window_frac"):
            sample_isotropic_held_ramp(_RANGE, _MIN_DELTA, _T, 0.0, seed=0)
        with pytest.raises(ValueError, match="n_timesteps"):
            sample_isotropic_held_ramp(_RANGE, _MIN_DELTA, 1, 0.25, seed=0)


class TestSampleReversalRamp:
    def _sample(self, seed, jitter=0.0, **kwargs):
        return sample_reversal_ramp(
            _RANGE, _MIN_DELTA, _T, (0.2, 0.8), seed=seed, jitter_frac=jitter, **kwargs
        )

    def test_reproducible_and_reverses_direction(self):
        a = self._sample(5)
        b = self._sample(5)
        for x, y in zip(a, b):
            np.testing.assert_array_equal(x, y)
        for seed in range(60):
            start, turn, end, t_turn, _ = self._sample(seed)
            d_out = turn - start
            d_back = end - turn
            # Both legs move at least min_delta and the return leg reverses.
            assert np.linalg.norm(d_out) >= _MIN_DELTA - 1e-12
            assert np.linalg.norm(d_back) >= _MIN_DELTA - 1e-12
            cos = d_out @ d_back / (np.linalg.norm(d_out) * np.linalg.norm(d_back))
            assert cos < -0.99  # collinear, opposite direction (no jitter)

    def test_turn_frame_in_middle_window(self):
        lo = int(np.ceil(0.2 * (_T - 1)))
        hi = int(np.floor(0.8 * (_T - 1)))
        turns = set()
        for seed in range(100):
            _, _, _, t_turn, _ = self._sample(seed)
            assert lo <= t_turn <= hi
            turns.add(t_turn)
        assert len(turns) > 10, "turn frames do not vary"

    def test_min_projection_guard(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        for seed in range(150):
            start, turn, end, _, _ = self._sample(
                seed, bias_T=bias, min_axis_proj_T=0.4e-3, nv_axes=NV_AXES_UNIT
            )
            for a, b in ((start, turn), (turn, end)):
                p0 = NV_AXES_UNIT @ (bias + a)
                p1 = NV_AXES_UNIT @ (bias + b)
                seg_min = np.where(p0 * p1 <= 0, 0.0, np.minimum(np.abs(p0), np.abs(p1)))
                assert seg_min.min() >= 0.4e-3 - 1e-15

    def test_invalid_turn_range_rejected(self):
        with pytest.raises(ValueError, match="turn_frac_range"):
            sample_reversal_ramp(_RANGE, _MIN_DELTA, _T, (0.8, 0.2), seed=0)


class TestReversalTrajectory:
    def test_two_leg_structure(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        u = np.array([1.0, 0.0, 0.0])
        start, turn, end = -1.0e-3 * u, 1.2e-3 * u, -0.2e-3 * u
        t_turn = 20
        traj = reversal_trajectory(bias, start, turn, end, 64, t_turn)
        assert traj.shape == (64, 3)
        np.testing.assert_allclose(traj[0], bias + start, atol=1e-18)
        np.testing.assert_allclose(traj[t_turn], bias + turn, atol=1e-18)
        np.testing.assert_allclose(traj[-1], bias + end, atol=1e-18)
        # Velocity reverses sign at the turn (x-component here).
        v = np.diff(traj[:, 0])
        assert np.all(v[:t_turn] > 0)
        assert np.all(v[t_turn:] < 0)
        # Return rate differs from outbound (different leg length / duration).
        assert abs(v[0]) != pytest.approx(abs(v[-1]))

    def test_invalid_turn_frame_rejected(self):
        bias = np.zeros(3)
        v = np.ones(3) * 1e-3
        with pytest.raises(ValueError, match="t_turn"):
            reversal_trajectory(bias, -v, v, -v, 16, 0)
        with pytest.raises(ValueError, match="t_turn"):
            reversal_trajectory(bias, -v, v, -v, 16, 15)


class TestOUFieldPerturbation:
    def test_reproducible_and_stationary(self):
        a = ou_field_perturbation(45e-6, 16.0, 4096, seed=[7, 2, 0])
        b = ou_field_perturbation(45e-6, 16.0, 4096, seed=[7, 2, 0])
        np.testing.assert_array_equal(a, b)
        # Per-component std ~ sigma (stationary), mean ~ 0.
        assert a.shape == (4096, 3)
        assert abs(a.std() - 45e-6) < 8e-6
        assert abs(a.mean()) < 5e-6

    def test_correlation_time_scales_smoothness(self):
        fast = ou_field_perturbation(45e-6, 2.0, 2048, seed=1)
        slow = ou_field_perturbation(45e-6, 64.0, 2048, seed=1)
        # Slow OU has much smaller frame-to-frame increments.
        assert np.abs(np.diff(slow, axis=0)).mean() < 0.5 * np.abs(np.diff(fast, axis=0)).mean()

    def test_invalid_args_rejected(self):
        with pytest.raises(ValueError, match="sigma_T"):
            ou_field_perturbation(0.0, 16.0, 32, seed=0)
        with pytest.raises(ValueError, match="tau_frames"):
            ou_field_perturbation(45e-6, 0.0, 32, seed=0)


class TestHeldRampTrajectory:
    def test_hold_ramp_hold_structure(self):
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))
        start = np.array([1.0e-3, 0.0, 0.0])
        end = np.array([-0.5e-3, 0.5e-3, 0.0])
        t0, t1 = 8, 24
        traj = held_ramp_trajectory(bias, start, end, 32, t0, t1)
        assert traj.shape == (32, 3)
        # Hold segments are exactly constant.
        for t in range(t0 + 1):
            np.testing.assert_allclose(traj[t], bias + start, atol=1e-18)
        for t in range(t1, 32):
            np.testing.assert_allclose(traj[t], bias + end, atol=1e-18)
        # Ramp is linear: midpoint of the window is the endpoint average.
        mid = (t0 + t1) // 2
        np.testing.assert_allclose(traj[mid], bias + 0.5 * (start + end), atol=1e-12)
        # Motion happens only inside the window.
        deltas = np.linalg.norm(np.diff(traj, axis=0), axis=1)
        assert np.all(deltas[t0:t1] > 0)
        assert np.all(deltas[:t0] == 0)
        assert np.all(deltas[t1:] == 0)

    def test_full_span_window_matches_plain_ramp(self):
        bias = np.zeros(3)
        start = np.array([-2.0e-3, 0.0, 0.0])
        end = np.array([2.0e-3, 0.0, 0.0])
        held = held_ramp_trajectory(bias, start, end, 16, 0, 15)
        plain = ramp_crossing_trajectory(bias, start, end, 16)
        np.testing.assert_allclose(held, plain, atol=1e-18)

    def test_invalid_window_rejected(self):
        bias = np.zeros(3)
        with pytest.raises(ValueError, match="t0"):
            held_ramp_trajectory(bias, np.ones(3), -np.ones(3), 16, 8, 8)
        with pytest.raises(ValueError, match="t0"):
            held_ramp_trajectory(bias, np.ones(3), -np.ones(3), 16, -1, 8)
        with pytest.raises(ValueError, match="t0"):
            held_ramp_trajectory(bias, np.ones(3), -np.ones(3), 16, 4, 16)
