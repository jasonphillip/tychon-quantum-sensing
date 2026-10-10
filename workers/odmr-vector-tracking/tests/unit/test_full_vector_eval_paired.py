"""Paired field-cone comparisons retain sequence alignment."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "experiments"))
from full_vector_eval import paired_differences  # noqa: E402


def test_paired_bootstrap_contains_known_mean_difference() -> None:
    first = [
        {"seq_index": i, "rmse_T": float(i), "ae_mean_deg": float(2 * i),
         "lock_frac": 0.2 + i / 10, "lost": False}
        for i in range(5)
    ]
    second = [
        {"seq_index": row["seq_index"], "rmse_T": row["rmse_T"] + 2.0,
         "ae_mean_deg": row["ae_mean_deg"] - 1.0,
         "lock_frac": row["lock_frac"] + 0.1, "lost": row["seq_index"] < 2}
        for row in reversed(first)
    ]
    paired = paired_differences(first, second)
    for metric, expected in (("rmse_T", 2.0), ("ae_mean_deg", -1.0),
                             ("lock_frac", 0.1), ("lost", 0.4)):
        score = paired[metric]
        assert np.isclose(score["mean_diff"], expected)
        assert score["ci95"][0] - 1e-12 <= expected <= score["ci95"][1] + 1e-12
        assert score["n"] == 5
