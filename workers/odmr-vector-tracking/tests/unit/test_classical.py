"""Unit test: the classical baseline locks pre-crossing and loses lock at the crossing."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy,
    id_switch_rate,
    physical_line_index,
    resolve_true_axis,
    vector_angular_error,
)
from odmr_vector_tracking.tracking.classical import ClassicalTracker
from tests.fixtures.synthetic import make_synthetic_dataset


@pytest.fixture(scope="module")
def seq():
    """One deterministic sequence with a labeled inter-axis crossing + its linewidth."""
    splits, mani = make_synthetic_dataset({"train": 1, "val": 1, "test": 1})
    s = splits["train"]
    return {
        "spectra": s["spectra"][0],
        "frequencies": s["frequencies"],
        "resonance_freqs": s["resonance_freqs"][0],
        "B_true": s["B_true"][0],
        "collision_mask": s["collision_mask"][0],
        "line_axis": s["line_axis"][0],
        "linewidth_Hz": mani["linewidth_Hz"],
    }


def _run(seq) -> dict:
    trk = ClassicalTracker(seq["frequencies"], linewidth_Hz=seq["linewidth_Hz"])
    res = trk.run(seq["spectra"], init_freqs=seq["resonance_freqs"][0])
    true_axis = resolve_true_axis(
        res.tracked_freqs, seq["resonance_freqs"], seq["line_axis"]
    )
    return {"res": res, "true_axis": true_axis}


def test_locks_perfectly_before_crossing(seq) -> None:
    out = _run(seq)
    cf = np.where(seq["collision_mask"])[0]
    pre = int(cf.min())
    acc = association_accuracy(out["res"].pred_axis[:pre], out["true_axis"][:pre])
    assert acc["overall"] >= 0.99  # all 8 lines resolved and correctly identified


def test_loses_lock_after_crossing(seq) -> None:
    out = _run(seq)
    cf = np.where(seq["collision_mask"])[0]
    pre, post = int(cf.min()), int(cf.max())
    pre_acc = association_accuracy(out["res"].pred_axis[:pre], out["true_axis"][:pre])["overall"]
    post_acc = association_accuracy(
        out["res"].pred_axis[post + 1 :], out["true_axis"][post + 1 :]
    )["overall"]
    assert post_acc < pre_acc          # association degrades through the crossing
    assert post_acc <= 0.9             # at least one line-lock swapped identity


def test_identity_switch_occurs(seq) -> None:
    out = _run(seq)
    phys = physical_line_index(out["res"].tracked_freqs, seq["resonance_freqs"])
    assert id_switch_rate(phys)["count"] >= 1


def test_vector_error_grows_after_crossing(seq) -> None:
    out = _run(seq)
    cf = np.where(seq["collision_mask"])[0]
    pre, post = int(cf.min()), int(cf.max())
    ae = vector_angular_error(seq["B_true"], out["res"].B_est)
    pre_err = np.nanmean(ae[:pre])
    post_err = np.nanmean(ae[post + 1 :])
    assert pre_err < 1.0               # near-perfect vector lock before the crossing
    assert post_err > 1.0              # identity swap corrupts the BLUE vector
    assert post_err > pre_err
