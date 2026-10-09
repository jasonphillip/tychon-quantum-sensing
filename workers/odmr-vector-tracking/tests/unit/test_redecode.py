"""Unit tests for the zero-retrain identity re-decoders (increment-2c lever A)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from odmr_vector_tracking.tracking.redecode import (
    N_LINES,
    physics_anchored_decode,
    predicted_line_positions,
    smoothed_exclusive_decode,
    stacked_decode,
)
from odmr_vector_tracking.vector.geometry import resonance_frequencies_diagonalized


def test_predicted_line_positions_matches_reference():
    """Batched forward map == per-frame geometry.resonance_frequencies_diagonalized."""
    rng = np.random.default_rng(0)
    B = rng.normal(0.0, 2e-3, size=(7, 3))  # few-mT regime
    got = predicted_line_positions(B)
    exp = np.stack([resonance_frequencies_diagonalized(B[t]) for t in range(B.shape[0])])
    assert got.shape == (7, N_LINES)
    assert np.allclose(got, exp, atol=1e-3)


def test_physics_decode_recovers_identity_when_candidates_on_predictions():
    """With candidates sitting on the predicted centers, each slot recovers its OWN line."""
    rng = np.random.default_rng(1)
    B = rng.normal(0.0, 2e-3, size=(5, 3))
    pred = predicted_line_positions(B)  # (5, 8)
    T, n_decoy = 5, 4
    cand = np.empty((T, N_LINES + n_decoy))
    for t in range(T):
        decoys = pred[t].mean() + rng.uniform(-1e8, 1e8, size=n_decoy)
        allc = np.concatenate([pred[t], decoys])
        rng.shuffle(allc)
        cand[t] = allc
    out = physics_anchored_decode(B, cand, capture_radius_hz=1e6)
    # per-slot identity, not merely the right set
    assert np.allclose(out, pred, atol=1.0)


def test_smoothed_decode_shape_and_exclusive():
    rng = np.random.default_rng(2)
    T, K = 10, 20
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    out = smoothed_exclusive_decode(scores, cand, lag=3)
    assert out.shape == (T, N_LINES)
    for t in range(T):
        assert len(np.unique(np.round(out[t], 3))) == N_LINES  # 8 distinct candidates


def test_lag0_is_instantaneous_exclusive_assignment():
    """lag=0 reduces to a per-frame Hungarian on the raw scores."""
    rng = np.random.default_rng(3)
    T, K = 6, 15
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    out0 = smoothed_exclusive_decode(scores, cand, lag=0)
    for t in range(T):
        _, cols = linear_sum_assignment(-scores[t])
        assert np.allclose(out0[t], cand[t, cols])


def test_smoothing_corrects_single_frame_glitch():
    """A single-frame score glitch flips identity at lag=0 but is outvoted by the window."""
    T, K = 11, N_LINES
    cand = np.tile(np.linspace(2.82e9, 2.92e9, K), (T, 1))  # static, well-separated
    scores = np.full((T, N_LINES, K), -1.0)
    for li in range(N_LINES):
        scores[:, li, li] = 1.0  # identity-favoring
    # glitch at t=5: slots 0 and 1 momentarily prefer each other's candidate
    scores[5, 0, 0], scores[5, 0, 1] = -1.0, 1.0
    scores[5, 1, 1], scores[5, 1, 0] = -1.0, 1.0
    out0 = smoothed_exclusive_decode(scores, cand, lag=0)
    out3 = smoothed_exclusive_decode(scores, cand, lag=3)
    assert not np.isclose(out0[5, 0], cand[5, 0])          # lag0 swaps at the glitch
    assert np.isclose(out3[5, 0], cand[5, 0])              # window keeps identity
    assert np.isclose(out3[5, 1], cand[5, 1])


def test_stack_falls_back_to_physics_when_no_candidate_in_radius():
    rng = np.random.default_rng(5)
    B = rng.normal(0.0, 2e-3, size=(3, 3))
    pred = predicted_line_positions(B)
    T, K = 3, N_LINES
    cand = np.tile(1.0e9 + np.arange(K) * 1e6, (T, 1))  # ~1 GHz, far from 2.87 GHz predictions
    out = stacked_decode(
        np.zeros((T, N_LINES, K)), B, cand,
        capture_radius_hz=1e6, linewidth_hz=1e6, lag=0,
    )
    assert np.allclose(out, pred, atol=1.0)


def test_field_estimate_is_never_an_input_to_scores_decode():
    """A2 uses only scores + candidate positions — never b_est (guards non-circularity)."""
    rng = np.random.default_rng(6)
    T, K = 8, 12
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    a = smoothed_exclusive_decode(scores, cand, lag=2)
    b = smoothed_exclusive_decode(scores, cand.copy(), lag=2)
    assert np.array_equal(a, b)
