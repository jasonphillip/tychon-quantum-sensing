"""Smoke tier: end-to-end first runnable result.

Generate a synthetic v1 dataset → read it through the loader → run the classical baseline →
score with the metrics, and assert the headline behavior of Increment 1: the lock-in/PID +
nearest-peak baseline holds a clean vector lock before a crossing and **loses lock at labeled
inter-axis crossings**. This is the bar the learned tracker must beat; when the real dataset
lands, the same pipeline runs on it (see tests/contract/test_real_dataset_contract.py).

Loss-of-lock is *statistical*, not universal: whether a nearest-peak swap sticks depends on the
exact crossing geometry, so some sequences recover. The assertions are therefore dataset-level
(the failure reliably occurs across the set), while pre-crossing lock is required of every
sequence.
"""

from __future__ import annotations

import numpy as np
import pytest

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.evaluation.metrics import (
    association_accuracy,
    dynamic_range,
    recovery_time,
    resolve_true_axis,
    vector_angular_error,
)
from odmr_vector_tracking.tracking.classical import ClassicalTracker
from tests.fixtures.synthetic import write_synthetic_h5


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    """Fixture → loader → classical tracker → per-sequence metric records."""
    out = tmp_path_factory.mktemp("baseline_smoke")
    write_synthetic_h5(out, {"train": 4, "val": 1, "test": 1})
    loader = SequenceDatasetLoader(out)
    gamma = loader.manifest["linewidth_Hz"]
    dt = loader.manifest["dt_s"]
    ds = loader.load_split("train")

    tracker = ClassicalTracker(ds.frequencies, linewidth_Hz=gamma)
    out_records = []
    for n in range(ds.spectra.shape[0]):
        res = tracker.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        true_axis = resolve_true_axis(res.tracked_freqs, ds.resonance_freqs[n], ds.line_axis[n])
        ang = np.nan_to_num(vector_angular_error(ds.B_true[n], res.B_est), nan=0.0)
        cf = np.where(ds.collision_mask[n])[0]
        pre, post = int(cf.min()), int(cf.max())
        out_records.append(
            {
                "pre_acc": association_accuracy(res.pred_axis[:pre], true_axis[:pre])["overall"],
                "post_acc": association_accuracy(
                    res.pred_axis[post + 1 :], true_axis[post + 1 :]
                )["overall"],
                "assoc_split": association_accuracy(
                    res.pred_axis, true_axis, line_collision=ds.line_collision[n]
                ),
                "ang": ang,
                "B_true": ds.B_true[n],
                "B_est_shape": res.B_est.shape,
                "dt": dt,
            }
        )
    return out_records


def test_pipeline_runs_for_all_sequences(records) -> None:
    assert len(records) == 4
    for r in records:
        assert r["B_est_shape"] == r["B_true"].shape


def test_every_sequence_locks_before_the_crossing(records) -> None:
    for r in records:
        assert r["pre_acc"] >= 0.99  # all 8 lines resolved and correctly identified


def test_baseline_loses_lock_on_some_crossings(records) -> None:
    # The failure reliably occurs across the set (the whole point of Increment 1).
    lost = [r for r in records if r["post_acc"] < r["pre_acc"]]
    assert len(lost) >= 1


def test_association_degrades_in_collision(records) -> None:
    for r in records:
        a = r["assoc_split"]
        assert a["in_collision"] <= a["out_collision"]


def test_vector_dynamic_range_breaks_when_lock_is_lost(records) -> None:
    # On the sequences that lose lock, the vector lock breaks at a finite |B| (not "never lost").
    drs = [dynamic_range(r["B_true"], r["ang"], threshold=2.0) for r in records]
    broke = [d for d in drs if d["never_lost"] == 0.0]
    assert len(broke) >= 1
    for d in broke:
        assert d["loss_index"] > 0
        assert d["dynamic_range_T"] > 0.0


def test_recovery_time_reflects_loss(records) -> None:
    # At least one sequence's vector error crosses the loss threshold (recovery finite>0 or inf).
    rts = [recovery_time(r["ang"], dt_s=r["dt"], threshold=2.0) for r in records]
    assert any(rt > 0.0 for rt in rts)
