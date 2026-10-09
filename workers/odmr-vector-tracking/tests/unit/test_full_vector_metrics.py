import numpy as np

from odmr_vector_tracking.evaluation.metrics import (
    full_vector_lock,
    full_vector_lock_stats,
    magnitude_error,
    vector_bias,
    vector_rmse,
)
from odmr_vector_tracking.evaluation.rows import fieldcone_metrics_row


def test_rmse_bias_magnitude_known_values() -> None:
    B_true = np.array([[0, 0, 1e-3], [0, 0, 1e-3], [0, 0, 1e-3]])
    B_est = B_true + np.array([[1e-4, 0, 0], [1e-4, 0, 0], [1e-4, 0, 0]])
    assert np.isclose(vector_rmse(B_true, B_est), 1e-4)
    assert np.allclose(vector_bias(B_true, B_est), [1e-4, 0, 0])
    me = magnitude_error(B_true, B_est)
    assert np.allclose(me, np.sqrt(1e-6 + 1e-8) - 1e-3)


def test_full_vector_lock_requires_both_tolerances() -> None:
    B_true = np.tile([0, 0, 1e-3], (3, 1))
    B_est = np.array([
        [0, 0, 1.02e-3],                      # 2 % magnitude, 0 deg -> locked
        [0, 0, 1.10e-3],                      # 10 % magnitude, 0 deg -> not locked
        [1e-3 * np.sin(np.radians(8)), 0, 1e-3 * np.cos(np.radians(8))],  # 8 deg -> not locked
    ])
    assert full_vector_lock(B_true, B_est).tolist() == [True, False, False]


def test_full_vector_lock_nan_is_false() -> None:
    B_true = np.tile([0, 0, 1e-3], (2, 1))
    B_est = np.array([[np.nan, np.nan, np.nan], [0, 0, 0]])
    assert full_vector_lock(B_true, B_est).tolist() == [False, False]


def test_lock_stats_loss_convention() -> None:
    lock = np.array([False, True, True, False, True, False, False])
    s = full_vector_lock_stats(lock)
    assert s["acq_index"] == 1 and s["lost"] is True and s["loss_index"] == 5
    assert np.isclose(s["lock_frac"], 3 / 7)
    never = full_vector_lock_stats(np.zeros(4, dtype=bool))
    assert never["acq_index"] == -1 and never["lost"] is True


def test_fieldcone_row_keys() -> None:
    B_true = np.tile([0, 0, 1e-3], (10, 1))
    row = fieldcone_metrics_row(B_true, B_true.copy(), dt_s=1e-3)
    for k in ("rmse_T", "mag_err_mean_T", "mag_err_p90_T", "bias_x_T", "bias_y_T", "bias_z_T",
              "ae_mean_deg", "ae_p90_deg", "lock_frac", "acq_index", "lost", "loss_index", "n_frames"):
        assert k in row
    assert row["lock_frac"] == 1.0 and row["lost"] is False and row["n_frames"] == 10


def test_magnitude_error_is_signed() -> None:
    B_true = np.tile([0, 0, 1e-3], (2, 1))
    B_est = np.array([[0, 0, 0.9e-3], [0, 0, 1.1e-3]])
    assert np.allclose(magnitude_error(B_true, B_est), [-1e-4, 1e-4])
    row = fieldcone_metrics_row(B_true, B_est, dt_s=1e-3)
    assert np.isclose(row["mag_err_mean_T"], 0.0, atol=1e-12)   # signed mean = magnitude bias
    assert np.isclose(row["mag_err_p90_T"], 1e-4)               # p90 of |error|
