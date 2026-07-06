"""Unit tests for the increment-4 coalescence-aware overlay decoders (D-BP/OV/UM/JV).

Every decoder rewrites only the per-slot claimed identity (``tracked_hz``); ``b_est`` is never an
output. D-BP/D-JV read only ``scores`` + ``cand_pos`` (non-circular association); D-OV/D-UM use
``b_est`` solely as a physics prior for the identity overlay.
"""

from __future__ import annotations

from itertools import product

import numpy as np

from odmr_vector_tracking.tracking.redecode import (
    N_LINES,
    association_marginals,
    bp_marginal_decode,
    identity_overlay_decode,
    joint_viterbi_decode,
    predicted_line_positions,
    sinkhorn_doubly_stochastic,
    smoothed_exclusive_decode,
    unresolved_merge_decode,
)


def _weights(scores_lk: np.ndarray, gate_m: int) -> np.ndarray:
    """Same gated exp-weights the LBP forms, for the brute-force oracle."""
    w = np.exp(scores_lk - scores_lk.max(axis=-1, keepdims=True))
    if gate_m < scores_lk.shape[-1]:
        keep = np.argsort(scores_lk, axis=-1)[:, -gate_m:]
        mask = np.zeros_like(w, dtype=bool)
        for l in range(scores_lk.shape[0]):
            mask[l, keep[l]] = True
        w = np.where(mask, w, 0.0)
    return w


def _exact_marginals(w: np.ndarray, slot_miss: float) -> np.ndarray:
    """Brute-force one-to-one association marginals (each slot -> one candidate or miss)."""
    L, K = w.shape
    tot = 0.0
    num = np.zeros((L, K))
    for assign in product(range(-1, K), repeat=L):
        used: set[int] = set()
        wt = 1.0
        ok = True
        for l, k in enumerate(assign):
            if k == -1:
                wt *= slot_miss
            elif k in used or w[l, k] == 0.0:
                ok = False
                break
            else:
                used.add(k)
                wt *= w[l, k]
        if not ok or wt == 0.0:
            continue
        tot += wt
        for l, k in enumerate(assign):
            if k >= 0:
                num[l, k] += wt
    return num / tot


# --- D-BP: association marginals ----------------------------------------------------------

def test_association_marginals_row_normalized_with_miss():
    rng = np.random.default_rng(10)
    scores = rng.normal(size=(4, N_LINES, 12))
    p = association_marginals(scores, gate_m=5)
    assert p.shape == (4, N_LINES, 12)
    row = p.sum(axis=2)                      # miss mass = 1 - row must be in [0, 1]
    assert np.all(row <= 1.0 + 1e-9)
    assert np.all(row >= -1e-12)


def test_association_marginals_permutation_invariant():
    rng = np.random.default_rng(11)
    scores = rng.normal(size=(1, N_LINES, 10))
    perm = rng.permutation(10)
    p = association_marginals(scores, gate_m=10)
    pp = association_marginals(scores[:, :, perm], gate_m=10)
    assert np.allclose(pp, p[:, :, perm], atol=1e-6)


def test_association_marginals_close_to_exact_small_graph():
    """Loopy sum-product (Williams-Lau) approximates the exact association marginals — the
    mutual-exclusion constraints make it inexact even on a bipartite tree. The exclusive read-out
    only needs the dominant candidate per slot, which must agree with exact enumeration."""
    NEG = -50.0
    scores = np.full((1, 3, 4), NEG)
    scores[0, 0, [0, 1]] = [0.3, -0.2]       # slot0 -- {c0, c1}
    scores[0, 1, [1, 2]] = [0.1, 0.4]        # slot1 -- {c1, c2}
    scores[0, 2, [2, 3]] = [-0.1, 0.2]       # slot2 -- {c2, c3}
    slot_miss = 0.05
    p = association_marginals(scores, gate_m=2, slot_miss=slot_miss)[0]
    exact = _exact_marginals(_weights(scores[0], gate_m=2), slot_miss)
    assert np.allclose(p, exact, atol=0.06)                  # loopy BP is an approximation
    assert np.array_equal(p.argmax(1), exact.argmax(1))      # same MAP candidate per slot


def test_association_marginals_split_under_competition():
    """Two slots both preferring the same candidate -> that column's mass must split."""
    scores = np.full((1, 2, 2), -10.0)
    scores[0, 0] = [2.0, 0.0]
    scores[0, 1] = [2.0, 0.0]                # both want candidate 0
    p = association_marginals(scores, gate_m=2, slot_miss=0.01)[0]
    assert p[0, 0] < 0.95 and p[1, 0] < 0.95
    assert p[:, 1].sum() > 0.1               # mass moves to the uncontested candidate


def test_bp_decode_shape_and_exclusive():
    rng = np.random.default_rng(12)
    T, K = 10, 20
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    out = bp_marginal_decode(scores, cand, lag=3)
    assert out.shape == (T, N_LINES)
    for t in range(T):
        assert len(np.unique(np.round(out[t], 3))) == N_LINES


def test_bp_decode_smoothing_corrects_single_frame_glitch():
    """A single-frame score glitch flips identity at lag 0 but is outvoted by the window."""
    T, K = 11, N_LINES
    cand = np.tile(np.linspace(2.82e9, 2.92e9, K), (T, 1))
    scores = np.full((T, N_LINES, K), -6.0)
    for li in range(N_LINES):
        scores[:, li, li] = 4.0
    scores[5, 0, 0], scores[5, 0, 1] = -6.0, 4.0
    scores[5, 1, 1], scores[5, 1, 0] = -6.0, 4.0
    out0 = bp_marginal_decode(scores, cand, lag=0)
    out3 = bp_marginal_decode(scores, cand, lag=3)
    assert not np.isclose(out0[5, 0], cand[5, 0])
    assert np.isclose(out3[5, 0], cand[5, 0])
    assert np.isclose(out3[5, 1], cand[5, 1])


# --- D-OV: Set-JPDA identity overlay ------------------------------------------------------

def test_sinkhorn_doubly_stochastic():
    rng = np.random.default_rng(13)
    M = rng.uniform(0.1, 1.0, size=(8, 8))
    Q = sinkhorn_doubly_stochastic(M, iters=200)
    assert np.allclose(Q.sum(axis=0), 1.0, atol=1e-4)
    assert np.allclose(Q.sum(axis=1), 1.0, atol=1e-4)
    assert np.all(Q >= 0.0)


def test_identity_overlay_shape_and_reduces_to_baseline_when_unambiguous():
    rng = np.random.default_rng(14)
    T, K = 12, N_LINES
    B = rng.normal(0.0, 2e-3, size=(T, 3))
    pred = predicted_line_positions(B)
    cand = pred.copy()                        # candidates on predictions, well separated
    track = pred.copy()                       # baseline positions = predictions
    scores = np.full((T, N_LINES, K), -6.0)
    for li in range(N_LINES):
        scores[:, li, li] = 5.0
    out = identity_overlay_decode(scores, B, cand, track, linewidth_hz=1e6, lag=5)
    assert out.shape == (T, N_LINES)
    assert np.allclose(out, track, atol=1.0)  # unambiguous => overlay == baseline


def test_identity_overlay_is_a_permutation_of_baseline_positions():
    """The overlay only re-labels which slot carries which line; it never invents positions."""
    rng = np.random.default_rng(140)
    T, K = 15, N_LINES
    B = rng.normal(0.0, 2e-3, size=(T, 3))
    cand = predicted_line_positions(B)
    track = cand + rng.normal(0, 1e5, size=cand.shape)
    scores = rng.normal(size=(T, N_LINES, K))
    out = identity_overlay_decode(scores, B, cand, track, linewidth_hz=1e6, lag=5)
    for t in range(T):
        assert sorted(np.round(out[t], 3)) == sorted(np.round(track[t], 3))


# --- D-UM: unresolved-measurement hypotheses ----------------------------------------------

def test_unresolved_merge_all_unresolved_holds_physics_identity():
    """With everything unresolved, merged hypotheses keep each slot on its physics line even
    though the detections have collapsed to one blob (no forced exclusive pick)."""
    rng = np.random.default_rng(16)
    B = rng.normal(0.0, 2e-3, size=(4, 3))
    pred = predicted_line_positions(B)
    T, K = 4, N_LINES
    blob = pred.mean(axis=1, keepdims=True)   # all candidates collapsed to one location
    cand = np.tile(blob, (1, K))
    out = unresolved_merge_decode(np.zeros((T, N_LINES, K)), B, cand,
                                  capture_radius_hz=1e9, linewidth_hz=1e6, r_cells=1e9)
    assert np.allclose(out, pred, atol=1.0)


def test_unresolved_merge_none_unresolved_is_exclusive_physics():
    """With nothing unresolved and candidates on the predictions, each slot recovers its line."""
    rng = np.random.default_rng(17)
    B = rng.normal(0.0, 2e-3, size=(4, 3))
    pred = predicted_line_positions(B)
    out = unresolved_merge_decode(np.zeros((4, N_LINES, N_LINES)), B, pred.copy(),
                                  capture_radius_hz=1e6, linewidth_hz=1e6, r_cells=1e-6)
    assert np.allclose(out, pred, atol=1.0)


# --- D-JV: joint fixed-lag Viterbi --------------------------------------------------------

def test_joint_viterbi_lag0_nopenalty_equals_greedy():
    """D-JV at lag 0 with no transition penalty must reproduce greedy (per-frame Hungarian)."""
    rng = np.random.default_rng(18)
    T, K = 8, 14
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    out_jv = joint_viterbi_decode(scores, cand, lag=0, penalty=0.0)
    out_greedy = smoothed_exclusive_decode(scores, cand, lag=0)
    assert np.array_equal(out_jv, out_greedy)


def test_joint_viterbi_smoothing_corrects_glitch():
    T, K = 11, N_LINES
    cand = np.tile(np.linspace(2.82e9, 2.92e9, K), (T, 1))
    lw = (2.92e9 - 2.82e9) / (N_LINES - 1)
    scores = np.full((T, N_LINES, K), -1.0)
    for li in range(N_LINES):
        scores[:, li, li] = 1.0
    scores[5, 0, 0], scores[5, 0, 1] = -1.0, 1.0
    scores[5, 1, 1], scores[5, 1, 0] = -1.0, 1.0
    out = joint_viterbi_decode(scores, cand, lag=3, penalty=3.0, linewidth_hz=lw)
    assert np.isclose(out[5, 0], cand[5, 0])
    assert np.isclose(out[5, 1], cand[5, 1])
