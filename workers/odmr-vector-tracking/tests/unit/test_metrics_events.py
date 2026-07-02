"""Unit tests for the re-baseline metric extensions — hand-built inputs, known answers."""

from __future__ import annotations

import numpy as np

from odmr_vector_tracking.evaluation.metrics import (
    crossing_events,
    id_switch_rate,
    id_switches_per_opportunity,
    physical_line_index,
    resolve_true_axis,
    wilson_ci,
)


def test_capture_radius_marks_far_locks_unassigned() -> None:
    gt = np.array([[100.0, 200.0]])          # (T=1, Lgt=2)
    tracked = np.array([[101.0, 250.0]])     # lock 1 is 50 away from everything
    idx = physical_line_index(tracked, gt, capture_radius_hz=10.0)
    assert idx.tolist() == [[0, -1]]
    # without a radius: legacy nearest-line behavior
    assert physical_line_index(tracked, gt).tolist() == [[0, 1]]


def test_resolve_true_axis_unassigned_is_minus_one() -> None:
    gt = np.array([[100.0, 200.0]])
    axes = np.array([[2, 3]], dtype=np.int8)
    tracked = np.array([[99.0, 500.0]])
    ta = resolve_true_axis(tracked, gt, axes, capture_radius_hz=20.0)
    assert ta.tolist() == [[2, -1]]  # -1 never matches a claimed axis -> misassociated


def test_id_switch_rate_ignores_unassigned_transitions() -> None:
    # lock 0: 0 -> -1 -> 0 (fragmentation, no switch); lock 1: 1 -> 2 -> 2 (one switch)
    pa = np.array([[0, 1], [-1, 2], [0, 2]])
    out = id_switch_rate(pa)
    assert out["count"] == 1.0
    assert abs(out["unassigned_frac"] - 1.0 / 6.0) < 1e-12


def test_crossing_events_finds_contiguous_runs() -> None:
    cm = np.array([0, 1, 1, 0, 0, 1, 0, 1], dtype=bool)
    assert crossing_events(cm) == [(1, 2), (5, 5), (7, 7)]
    assert crossing_events(np.zeros(4, dtype=bool)) == []


def test_id_switches_per_opportunity_counts_permanent_swaps_only() -> None:
    # One event frames 4..5, window 2. Lock 0 flickers INSIDE the event but exits on its own
    # line (no switch); lock 1 exits on a different line (one switch).
    T, L = 10, 2
    pa = np.zeros((T, L), dtype=int)
    pa[:, 0] = [0, 0, 0, 0, 9, 0, 0, 0, 0, 0]   # in-event flicker only
    pa[:, 1] = [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]   # permanent swap 1 -> 2
    out = id_switches_per_opportunity(pa, [(4, 5)], window=2)
    assert out["opportunities"] == 2.0
    assert out["switches"] == 1.0
    assert out["rate"] == 0.5


def test_id_switches_per_opportunity_skips_edge_events() -> None:
    pa = np.zeros((6, 1), dtype=int)
    out = id_switches_per_opportunity(pa, [(0, 1)], window=3)  # no pre-window exists
    assert out["opportunities"] == 0.0
    assert np.isnan(out["rate"])


def test_id_switches_per_opportunity_undefined_when_unassigned() -> None:
    pa = np.full((10, 1), -1, dtype=int)
    out = id_switches_per_opportunity(pa, [(4, 5)], window=2)
    assert out["opportunities"] == 0.0
    assert out["undefined"] == 1.0


def test_wilson_ci_known_values() -> None:
    lo, hi = wilson_ci(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60   # 50/100 -> (0.404, 0.596)
    lo0, hi0 = wilson_ci(0, 20)
    assert lo0 == 0.0 or lo0 < 1e-12
    assert 0.15 < hi0 < 0.17                        # rule-of-thumb upper bound
    assert np.isnan(wilson_ci(0, 0)[0])
