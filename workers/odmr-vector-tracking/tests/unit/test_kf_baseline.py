"""Unit tests for the CV-KF + Hungarian baseline and the learned exclusive assignment."""

from __future__ import annotations

import numpy as np
import pytest
import torch

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.tracking.classical import auto_peak_min_depth
from odmr_vector_tracking.tracking.kf_baseline import KFHungarianTracker
from odmr_vector_tracking.tracking.learned import exclusive_greedy_assign
from tests.fixtures.synthetic import write_synthetic_h5


def test_auto_peak_min_depth_scales_with_contrast() -> None:
    # Flat baseline 1.0 with one dip of depth d per frame -> threshold = fraction * d.
    spectra = np.ones((3, 5, 50), dtype=np.float32)
    spectra[..., 20] = 1.0 - 0.004
    # tolerance bounded by float32 eps at 1.0 (~1.2e-7), not exact arithmetic
    assert abs(auto_peak_min_depth(spectra, fraction=0.35) - 0.35 * 0.004) < 1e-6
    # Works on a single (T, F) sequence too.
    assert abs(auto_peak_min_depth(spectra[0]) - 0.35 * 0.004) < 1e-6


@pytest.fixture(scope="module")
def fixture_ds(tmp_path_factory):
    out = tmp_path_factory.mktemp("kf_fixture")
    write_synthetic_h5(out, {"train": 2, "val": 1, "test": 1}, n_timesteps=80, n_freq=300)
    ld = SequenceDatasetLoader(out)
    return ld.load_split("train"), ld.manifest


def test_kf_locks_pre_crossing_and_outputs_shapes(fixture_ds) -> None:
    ds, m = fixture_ds
    n = 0
    depth = auto_peak_min_depth(ds.spectra[n])
    trk = KFHungarianTracker(
        ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
    )
    res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
    T, L = ds.resonance_freqs[n].shape
    assert res.tracked_freqs.shape == (T, L)
    assert res.B_est.shape == (T, 3)
    cf = np.where(ds.collision_mask[n])[0]
    first = int(cf.min()) if cf.size else T
    assert first > 0 and res.locked[:first].mean() > 0.9
    # Pre-crossing the KF must sit on the true lines (within a linewidth).
    err = np.abs(res.tracked_freqs[:first] - ds.resonance_freqs[n, :first])
    assert float(np.median(err)) < m["linewidth_Hz"]


def test_exclusive_greedy_assign_is_one_to_one() -> None:
    torch.manual_seed(0)
    scores = torch.randn(4, 8, 16)
    out = exclusive_greedy_assign(scores)
    assert out.shape == (4, 8)
    for b in range(4):
        assert len(set(out[b].tolist())) == 8  # no candidate claimed twice


def test_exclusive_greedy_assign_prefers_higher_scores() -> None:
    # Two slots want the same candidate; the higher score keeps it, the other takes its
    # next-best — unlike an independent argmax, which would double-claim.
    scores = torch.full((1, 2, 3), -10.0)
    scores[0, 0, 1] = 5.0   # slot 0 -> cand 1 (strongest pair overall)
    scores[0, 1, 1] = 4.0   # slot 1 also wants cand 1...
    scores[0, 1, 2] = 3.0   # ...but must settle for cand 2
    out = exclusive_greedy_assign(scores)
    assert out.tolist() == [[1, 2]]
