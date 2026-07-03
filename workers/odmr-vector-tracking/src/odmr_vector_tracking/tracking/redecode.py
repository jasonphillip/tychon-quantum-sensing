"""Zero-retrain identity re-decoders for the learned tracker (increment-2c lever A).

These operate ENTIRELY post-hoc on a trained checkpoint's inference outputs. The field
estimate ``b_est`` is never modified, so the vector/lock claim is invariant *by construction*:
``sequence_metrics_row`` reads the FIELD metrics (angular error, loss-of-lock) only from
``B_est``, and reads IDENTITY (misassoc, ID-switch/opportunity) from the per-slot claimed line
center ``tracked_hz (T, 8)``. Each decoder here re-derives that ``tracked_hz`` — the signal
that carries identity into the metric — without touching ``b_est``. Slot ``l`` always claims
axis ``LINE_AXIS_8[l]``; identity is whether slot ``l``'s decoded center stays on its physical
line through a crossing.

Non-circularity (see ``docs/design/04_identity_gap_solution_survey.md`` §scoping): ``b_est``
comes from ``state_to_proj``→BLUE and never consumes the assignment (``learned.py:543``, ``585``),
so decoding identity *from* ``b_est`` (A1/A3) is not circular.

Decoders
--------
- :func:`smoothed_exclusive_decode` (A2) — fixed-lag temporal smoothing of the saved
  ``(T, 8, K)`` association scores, then per-frame exclusive one-to-one assignment. A mean-field
  FHMM decode: the emission for each slot is averaged over a ``±lag`` window (deferring the
  commit so identity can resolve a few frames after the crossing) and per-frame exclusivity is a
  Hungarian assignment. ``lag`` is the added decision latency in frames; ``lag=0`` reduces to an
  instantaneous exclusive commit on the raw scores (the reference the deferral is measured against).
- :func:`physics_anchored_decode` (A1) — predict all 8 line centers from ``b_est`` via the known
  Zeeman forward map, then assign candidates one-to-one to those predictions; a slot with no
  candidate inside the capture radius falls back to its physics-predicted center. No scores used.
- :func:`stacked_decode` (A3) — A2's smoothed scores biased by A1's physics prior, with the same
  physics fallback. Combines the temporal smoothing with the physics anchor.

All decoders take one sequence (numpy) and return ``tracked_hz (T, 8)`` in Hz.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    LINE_AXIS_8,
    LINE_SIGN_8,
    NV_AXES_UNIT,
    ZFS_D_HZ,
    common_mode_shift,
)

N_LINES = 8


def predicted_line_positions(b_est_T3: np.ndarray) -> np.ndarray:
    """Batched Zeeman forward map: ``b_est (T, 3)`` Tesla → 8 line centers ``(T, 8)`` Hz.

    Vectorized :func:`geometry.resonance_frequencies_diagonalized` over time — the same
    first-order + common-mode geometry the BLUE decoder inverts (deliberately NOT a richer
    Hamiltonian: the prediction must be consistent with the tracker's own field model).
    """
    B = np.asarray(b_est_T3, dtype=np.float64).reshape(-1, 3)              # (T, 3)
    B_par = B @ NV_AXES_UNIT.T                                             # (T, 4) signed B·n_i
    B_perp = np.linalg.norm(
        B[:, None, :] - B_par[:, :, None] * NV_AXES_UNIT[None, :, :], axis=2
    )                                                                     # (T, 4)
    first = GAMMA_E_HZ_PER_T * LINE_SIGN_8.astype(np.float64)[None, :] * B_par[:, LINE_AXIS_8]
    cm = common_mode_shift(B_perp)[:, LINE_AXIS_8]                         # (T, 8)
    return ZFS_D_HZ + first + cm


def _boxsum_time(x: np.ndarray, lag: int) -> np.ndarray:
    """Sum ``x`` over a ``[t-lag, t+lag]`` window along axis 0 (edge-clipped). ``lag<=0`` → x."""
    if lag <= 0:
        return x
    T = x.shape[0]
    cum = np.concatenate([np.zeros((1, *x.shape[1:]), dtype=x.dtype), np.cumsum(x, axis=0)])
    lo = np.clip(np.arange(T) - lag, 0, T)
    hi = np.clip(np.arange(T) + lag + 1, 0, T)
    return cum[hi] - cum[lo]


def _assign_tracks(cost_LK: np.ndarray) -> np.ndarray:
    """Exclusive one-to-one assignment of 8 slots to K candidates minimizing cost. ``→ (8,)``.

    ``K >= 8`` so every slot gets a distinct candidate (rectangular Hungarian).
    """
    rows, cols = linear_sum_assignment(cost_LK)
    out = np.full(cost_LK.shape[0], -1, dtype=np.int64)
    out[rows] = cols
    return out


def smoothed_exclusive_decode(
    scores: np.ndarray, cand_pos_hz: np.ndarray, lag: int = 5
) -> np.ndarray:
    """A2 — fixed-lag smoothed, per-frame exclusive decode of the association scores.

    Parameters
    ----------
    scores : ``(T, 8, K)`` association logits (slot × candidate) per frame.
    cand_pos_hz : ``(T, K)`` candidate centers in Hz.
    lag : half-window; the added decision latency in frames. ``0`` = instantaneous exclusive commit.

    Returns ``tracked_hz (T, 8)`` in Hz.
    """
    S = _boxsum_time(np.asarray(scores, dtype=np.float64), lag)           # (T, 8, K)
    T = S.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        assign = _assign_tracks(-S[t])                                    # maximize score
        out[t] = cand_pos_hz[t, assign]
    return out


def physics_anchored_decode(
    b_est_T3: np.ndarray,
    cand_pos_hz: np.ndarray,
    capture_radius_hz: float,
) -> np.ndarray:
    """A1 — assign candidates to the 8 physics-predicted line centers from ``b_est``.

    A slot whose nearest assigned candidate is beyond ``capture_radius_hz`` falls back to its
    physics-predicted center (the mechanism by which a good field estimate keeps identity through
    a crossing even when the detector misses the faint line). Uses no association scores → the
    decode cannot borrow the very assignment it is meant to replace.
    """
    pred = predicted_line_positions(b_est_T3)                            # (T, 8) Hz
    T = pred.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        cost = np.abs(pred[t][:, None] - cand_pos_hz[t][None, :])        # (8, K)
        assign = _assign_tracks(cost)
        chosen = cand_pos_hz[t, assign]
        far = np.abs(chosen - pred[t]) > capture_radius_hz
        out[t] = np.where(far, pred[t], chosen)
    return out


def stacked_decode(
    scores: np.ndarray,
    b_est_T3: np.ndarray,
    cand_pos_hz: np.ndarray,
    capture_radius_hz: float,
    linewidth_hz: float,
    lag: int = 5,
    mu: float = 1.0,
) -> np.ndarray:
    """A3 — A2 smoothed scores biased toward A1's physics prediction, with physics fallback.

    Per-frame exclusive assignment on ``-S_smooth + mu·|cand − pred|/linewidth``: the physics
    prior (``mu`` in units of one score-point per linewidth of position error) breaks ties the
    scores leave ambiguous at a crossing; the temporal smoothing defers the commit. A slot whose
    assigned candidate lands beyond the capture radius falls back to its physics center.
    """
    S = _boxsum_time(np.asarray(scores, dtype=np.float64), lag)          # (T, 8, K)
    pred = predicted_line_positions(b_est_T3)                            # (T, 8) Hz
    T = S.shape[0]
    out = np.empty((T, N_LINES), dtype=np.float64)
    for t in range(T):
        pos_cost = np.abs(cand_pos_hz[t][None, :] - pred[t][:, None]) / linewidth_hz
        assign = _assign_tracks(-S[t] + mu * pos_cost)                   # (8,)
        chosen = cand_pos_hz[t, assign]
        far = np.abs(chosen - pred[t]) > capture_radius_hz
        out[t] = np.where(far, pred[t], chosen)
    return out
