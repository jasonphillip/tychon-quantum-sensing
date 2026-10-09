"""Format-parity guard: classical and learned output formats must score identically.

The learned tracker emits positions in normalized window units and is denormalized to Hz in
the eval path; the classical trackers emit Hz directly. Feeding the SAME underlying claimed
centers through both formats must produce the identical metric row — otherwise cross-tracker
tables are not apples-to-apples (dispatch item 3c, 2026-07-01 re-baseline).
"""

from __future__ import annotations

import numpy as np

from odmr_vector_tracking.evaluation.rows import sequence_metrics_row
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

F0, F1 = 2.7e9, 3.1e9  # window (Hz)


def _toy_sequence(T: int = 24, L: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    base = np.linspace(F0 + 40e6, F1 - 40e6, L)
    drift = np.linspace(0, 8e6, T)[:, None] * np.linspace(-1, 1, L)[None, :]
    res = base[None, :] + drift                       # (T, L) true centers
    collision = np.zeros(T, dtype=bool)
    collision[10:13] = True
    line_coll = np.zeros((T, L), dtype=bool)
    line_coll[10:13, :2] = True
    B_true = rng.normal(0, 3e-3, size=(T, 3))
    tracked_hz = res + rng.normal(0, 0.5e6, size=res.shape)  # noisy claimed centers (Hz)
    B_est = B_true + rng.normal(0, 1e-5, size=B_true.shape)
    return res, collision, line_coll, B_true, tracked_hz, B_est


def test_classical_and_learned_formats_score_identically() -> None:
    res, collision, line_coll, B_true, tracked_hz, B_est = _toy_sequence()
    T, L = tracked_hz.shape
    pred_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L))
    line_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L)).astype(np.int8)
    kw = dict(
        resonance_freqs=res, line_axis=line_axis, line_collision=line_coll,
        collision_mask=collision, B_true=B_true, dt_s=1e-3, capture_radius_hz=4.5e6,
    )

    # classical format: Hz float64, straight in
    row_classical = sequence_metrics_row(tracked_hz, pred_axis, B_est, **kw)

    # learned format: normalized float32 -> denormalized in the eval path
    tracked_norm = ((tracked_hz - F0) / (F1 - F0)).astype(np.float32)
    tracked_rt = tracked_norm.astype(np.float64) * (F1 - F0) + F0
    row_learned = sequence_metrics_row(tracked_rt, pred_axis, B_est.astype(np.float32), **kw)

    assert row_classical is not None and row_learned is not None
    for k, v in row_classical.items():
        w = row_learned[k]
        if isinstance(v, float) and np.isnan(v):
            assert np.isnan(w), k
        elif isinstance(v, float):
            # float32 round-trip of positions moves centers by O(30 Hz) << Gamma; every
            # discrete metric must be bit-identical and continuous ones equal to 1e-3.
            assert abs(v - w) < 1e-3, (k, v, w)
        else:
            assert v == w, k


def test_undefined_angular_error_counts_as_lost_not_perfect() -> None:
    res, collision, line_coll, B_true, tracked_hz, _ = _toy_sequence()
    T, L = tracked_hz.shape
    pred_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L))
    line_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L)).astype(np.int8)
    B_zero = np.zeros_like(B_true)  # angle undefined on every frame
    row = sequence_metrics_row(
        tracked_hz, pred_axis, B_zero,
        resonance_freqs=res, line_axis=line_axis, line_collision=line_coll,
        collision_mask=collision, B_true=B_true, dt_s=1e-3, capture_radius_hz=4.5e6,
    )
    assert row is not None
    assert row["lost"] is True          # undefined error = lost, never graded perfect
    assert row["ae_undefined_frac"] == 1.0
    assert np.isnan(row["ae_peak"])
