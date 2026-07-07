"""Unit tests for the increment-5 cue-aware decode extensions (strain offsets + CR marker).

Strain: per-axis static ZFS offsets shift BOTH transitions of an axis by the same delta
(split-invisible, center-shifting) — the physics forward map must reproduce that so the decode
prior can exploit it. CR: the cross-relaxation PL dip is a merge marker readable from the raw
spectrum; the gated decode holds physics identity for the marked (unresolved) lines only.
"""

from __future__ import annotations

import numpy as np

from odmr_vector_tracking.tracking.redecode import (
    N_LINES,
    cr_dwell_marker,
    cr_gated_decode,
    physics_anchored_decode,
    predicted_line_positions,
    stacked_decode,
)
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8


def test_predicted_line_positions_axis_offsets_shift_both_transitions():
    rng = np.random.default_rng(20)
    B = rng.normal(0.0, 2e-3, size=(6, 3))
    offsets = np.array([19600.0, -4200.0, -3500.0, -11900.0])
    base = predicted_line_positions(B)
    shifted = predicted_line_positions(B, axis_offsets_hz=offsets)
    assert np.allclose(shifted - base, offsets[LINE_AXIS_8][None, :], atol=1e-6)


def test_predicted_line_positions_offsets_none_is_unchanged():
    rng = np.random.default_rng(21)
    B = rng.normal(0.0, 2e-3, size=(4, 3))
    assert np.array_equal(predicted_line_positions(B),
                          predicted_line_positions(B, axis_offsets_hz=None))


def test_physics_decode_uses_offset_aware_predictions():
    """Candidates sit at the OFFSET positions; with offsets the decode recovers them, without
    offsets (and a capture radius smaller than the offset) it falls back to physics centers."""
    rng = np.random.default_rng(22)
    B = rng.normal(0.0, 2e-3, size=(5, 3))
    offsets = np.array([5e6, -4e6, 3e6, -2e6])            # exaggerated for a mechanism test
    pred_off = predicted_line_positions(B, axis_offsets_hz=offsets)
    out_aware = physics_anchored_decode(B, pred_off.copy(), capture_radius_hz=1e6,
                                        axis_offsets_hz=offsets)
    assert np.allclose(out_aware, pred_off, atol=1.0)      # recovers the offset candidates
    out_blind = physics_anchored_decode(B, pred_off.copy(), capture_radius_hz=1e6)
    assert not np.allclose(out_blind, pred_off, atol=1.0)  # blind decode can't reach them


def test_stacked_decode_accepts_offsets_and_reduces_when_zero():
    rng = np.random.default_rng(23)
    T, K = 6, 12
    B = rng.normal(0.0, 2e-3, size=(T, 3))
    scores = rng.normal(size=(T, N_LINES, K))
    cand = np.sort(rng.uniform(2.80e9, 2.94e9, size=(T, K)), axis=1)
    a = stacked_decode(scores, B, cand, 4.5e6, 1.5e6, lag=2)
    b = stacked_decode(scores, B, cand, 4.5e6, 1.5e6, lag=2, axis_offsets_hz=np.zeros(4))
    assert np.array_equal(a, b)


def _lorentzian(f, f0, gamma, depth):
    return 1.0 - depth / (1.0 + ((f - f0) / (gamma / 2)) ** 2)


def test_cr_dwell_marker_finds_dip_window_and_frequency():
    F = np.linspace(2.80e9, 2.94e9, 951)
    T, gamma = 20, 1.5e6
    spectra = np.ones((T, F.size))
    for t in range(T):                                     # ordinary lines everywhere (0.35%)
        spectra[t] *= _lorentzian(F, 2.83e9, gamma, 0.0035)
        spectra[t] *= _lorentzian(F, 2.91e9, gamma, 0.0030)
    f_cr = 2.87e9
    for t in range(6, 12):                                 # CR dip only in the dwell window
        spectra[t] *= _lorentzian(F, f_cr, gamma, 0.02)
    marked, freqs = cr_dwell_marker(spectra, F, depth_thresh=0.011)
    assert marked.tolist() == [6 <= t < 12 for t in range(T)]
    for t in range(6, 12):
        assert any(abs(fd - f_cr) < 2 * gamma for fd in freqs[t])
    assert all(len(freqs[t]) == 0 for t in range(T) if not marked[t])


def test_cr_gated_decode_holds_marked_pair_and_assigns_rest():
    """During marked frames the pair nearest the dip holds physics identity even though their
    candidates collapsed to one blob; unmarked lines get exclusive nearest assignment."""
    rng = np.random.default_rng(24)
    B = rng.normal(0.0, 2e-3, size=(8, 3))
    pred = predicted_line_positions(B)
    T, K = 8, N_LINES
    F = np.linspace(pred.min() - 5e7, pred.max() + 5e7, 951)
    gamma = 1.5e6
    # target pair = the two globally closest predicted lines (stable across frames here)
    i, j = np.unravel_index(
        np.argmin(np.abs(pred[0][:, None] - pred[0][None, :]) + np.eye(N_LINES) * 1e18),
        (N_LINES, N_LINES))
    spectra = np.ones((T, F.size))
    blob = 0.5 * (pred[:, i] + pred[:, j])                 # (T,)
    cand = pred.copy()
    for t in range(3, 6):                                  # dwell: CR dip + collapsed candidates
        spectra[t] *= _lorentzian(F, blob[t], gamma, 0.02)
        cand[t, i] = cand[t, j] = blob[t]
    # In a real dwell the pair's predictions are degenerate (within ~a linewidth of the dip).
    # The synthetic B has no true degeneracy, so scale the decode's linewidth to the constructed
    # pair separation — the gate must capture both members at sep/2 from the dip.
    lw_eff = 1.2 * float(np.abs(pred[:, i] - pred[:, j]).max()) / 2
    out = cr_gated_decode(spectra, F, B, cand, capture_radius_hz=1e9, linewidth_hz=lw_eff,
                          depth_thresh=0.011)
    for t in range(3, 6):                                  # marked: pair holds physics identity
        assert np.isclose(out[t, i], pred[t, i], atol=1.0)
        assert np.isclose(out[t, j], pred[t, j], atol=1.0)
    for t in list(range(0, 3)) + list(range(6, T)):        # unmarked: candidates recovered
        assert np.allclose(out[t], pred[t], atol=1.0)
