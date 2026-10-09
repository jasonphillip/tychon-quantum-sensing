"""Unit tests for evaluation metrics (hand-built known-answer inputs)."""

from __future__ import annotations

import numpy as np

from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy,
    dynamic_range,
    id_switch_rate,
    physical_line_index,
    recovery_time,
    resolve_true_axis,
    vector_angular_error,
)
from odmr_vector_tracking.evaluation.rows import sequence_metrics_row


def test_vector_angular_error_known_angles() -> None:
    B_true = np.array([[1.0, 0, 0], [0, 0, 1.0]])
    B_est = np.array([[0, 1.0, 0], [0, 0, 2.0]])
    ae = vector_angular_error(B_true, B_est)
    assert np.allclose(ae, [90.0, 0.0], atol=1e-6)


def test_vector_angular_error_near_zero_is_nan() -> None:
    ae = vector_angular_error(np.array([[0.0, 0, 0]]), np.array([[1.0, 0, 0]]))
    assert np.isnan(ae[0])


def test_association_accuracy_with_collision_mask() -> None:
    pred = np.array([[0, 1, 2, 3]])
    true = np.array([[0, 1, 9, 3]])
    lc = np.array([[False, False, True, True]])
    out = association_accuracy(pred, true, lc)
    assert out["overall"] == 0.75
    assert out["in_collision"] == 0.5
    assert out["out_collision"] == 1.0


def test_id_switch_rate() -> None:
    pa = np.array([[0, 1], [0, 1], [1, 0], [1, 0]])  # both tracks swap once at t=2
    out = id_switch_rate(pa)
    assert out["count"] == 2.0
    assert np.isclose(out["rate"], 2.0 / (2 * 3))


def test_recovery_time_recovers() -> None:
    err = np.array([0.1, 0.1, 5.0, 5.0, 0.2, 0.1])
    assert np.isclose(recovery_time(err, dt_s=1e-3, threshold=1.0), 2e-3)


def test_recovery_time_never_lost_is_zero() -> None:
    assert recovery_time(np.array([0.1, 0.2]), dt_s=1e-3, threshold=1.0) == 0.0


def test_recovery_time_never_recovers_is_inf() -> None:
    assert recovery_time(np.array([0.1, 5, 5, 5]), dt_s=1e-3, threshold=1.0) == float("inf")


def test_recovery_time_all_nan_never_recovers() -> None:
    assert recovery_time(np.full(4, np.nan), dt_s=0.1, threshold=1.0) == float("inf")


def test_recovery_time_nan_breaks_hold() -> None:
    err = np.array([9.0, 0.0, np.nan, 0.0, 0.0])
    assert np.isclose(recovery_time(err, dt_s=0.1, threshold=1.0, hold=2), 0.3)


def test_recovery_time_nan_before_explicit_onset() -> None:
    err = np.array([np.nan, 0.0, 9.0, 0.0])
    assert recovery_time(err, dt_s=0.1, threshold=1.0, onset_index=2) == 0.1


def test_dynamic_range_loss() -> None:
    B = np.array([[1, 0, 0], [2, 0, 0], [3, 0, 0], [4, 0, 0], [5, 0, 0.0]]) * 1e-3
    err = np.array([0.1, 0.1, 0.1, 9.0, 9.0])
    out = dynamic_range(B, err, threshold=1.0)
    assert np.isclose(out["dynamic_range_T"], 3e-3)
    assert out["loss_index"] == 3.0
    assert out["never_lost"] == 0.0


def test_dynamic_range_never_lost() -> None:
    B = np.array([[1, 0, 0], [5, 0, 0.0]]) * 1e-3
    out = dynamic_range(B, np.zeros(2), threshold=1.0)
    assert out["never_lost"] == 1.0
    assert np.isclose(out["dynamic_range_T"], 5e-3)


def test_dynamic_range_all_nan_lost_from_first_frame() -> None:
    B = np.array([[1.0, 0.0, 0.0], [2.0, 0.0, 0.0]]) * 1e-3
    out = dynamic_range(B, np.full(2, np.nan), threshold=1.0)
    assert out == {"dynamic_range_T": 0.0, "loss_index": 0.0, "never_lost": 0.0}


def test_dynamic_range_nan_gap_and_nonfinite_tail() -> None:
    B = np.array([[1.0, 0.0, 0.0]] * 6) * 1e-3
    err = np.array([9.0, np.nan, 0.0, np.nan, -np.inf, np.inf])
    out = dynamic_range(B, err, threshold=1.0, recovery_window=2)
    assert out["loss_index"] == 0.0
    assert out["never_lost"] == 0.0


def test_sequence_row_agrees_with_metrics_on_nan_gap() -> None:
    B_true = np.array([[1e-3, 0.0, 0.0]] * 7)
    B_est = B_true.copy()
    B_est[[1, 2]] = [0.0, 1e-3, 0.0]
    B_est[[3, 5, 6]] = 0.0
    error = vector_angular_error(B_true, B_est)
    row = sequence_metrics_row(
        tracked_hz=np.full((7, 1), 100.0),
        pred_axis=np.zeros((7, 1), dtype=np.int8),
        B_est=B_est,
        resonance_freqs=np.full((7, 1), 100.0),
        line_axis=np.zeros((7, 1), dtype=np.int8),
        line_collision=np.array([[False], [True], [False], [False], [False], [False], [False]]),
        collision_mask=np.array([False, True, False, False, False, False, False]),
        B_true=B_true,
        dt_s=0.1,
        capture_radius_hz=1.0,
        loss_deg=5.0,
        idsw_window=1,
    )
    assert row is not None
    assert np.isnan(error[3]) and np.isnan(error[5])
    assert np.isclose(row["rt"], 0.3)
    assert row["rt"] == recovery_time(error, dt_s=0.1, threshold=5.0, onset_index=1)
    assert row["lost"] is True
    assert row["loss_index"] == dynamic_range(B_true, error, threshold=5.0)["loss_index"] == 5.0


def test_physical_line_index_and_true_axis() -> None:
    # 2 locks, 3 gt lines; lock0 nearest line0, lock1 nearest line2.
    tracked = np.array([[100.0, 305.0]])
    gt = np.array([[100.0, 200.0, 300.0]])
    line_axis = np.array([[0, 1, 2]], dtype=np.int8)
    phys = physical_line_index(tracked, gt)
    assert phys.tolist() == [[0, 2]]
    true_axis = resolve_true_axis(tracked, gt, line_axis)
    assert true_axis.tolist() == [[0, 2]]
