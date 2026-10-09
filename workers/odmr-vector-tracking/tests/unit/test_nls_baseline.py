"""Unit tests for the warm-started NLS baseline."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.tracking.nls_baseline import NLSTracker
from tests.fixtures.synthetic import write_synthetic_h5


def test_model_is_one_minus_lorentzian_sum() -> None:
    freqs = np.linspace(0.0, 100.0, 201)
    trk = NLSTracker(freqs, linewidth_Hz=10.0)
    centers_n = np.array([0.5])
    depths = np.array([0.2])
    model = trk._model(centers_n, depths)
    assert abs(model[100] - 0.8) < 1e-12          # exactly depth at the center
    assert abs(model[0] - 1.0) < 0.02             # ~1 off resonance
    hwhm_bins = int(round(0.05 * 200))            # HWHM = 5 units = 10 bins
    assert abs(model[100 + hwhm_bins] - 0.9) < 1e-3  # half depth at +HWHM


@pytest.fixture(scope="module")
def fixture_ds(tmp_path_factory):
    out = tmp_path_factory.mktemp("nls_fixture")
    write_synthetic_h5(out, {"train": 2, "val": 1, "test": 1}, n_timesteps=60, n_freq=300)
    ld = SequenceDatasetLoader(out)
    return ld.load_split("train"), ld.manifest


def test_nls_tracks_fixture_lines(fixture_ds) -> None:
    ds, m = fixture_ds
    n = 0
    trk = NLSTracker(ds.frequencies, linewidth_Hz=m["linewidth_Hz"])
    res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
    T, L = ds.resonance_freqs[n].shape
    assert res.tracked_freqs.shape == (T, L)
    assert res.B_est.shape == (T, 3)
    # Out-of-collision frames: fitted centers must sit on the true lines (< Gamma/2).
    ooc = ~ds.collision_mask[n]
    err = np.abs(res.tracked_freqs[ooc] - ds.resonance_freqs[n][ooc])
    assert float(np.median(err)) < 0.5 * m["linewidth_Hz"]


def test_nls_center_gate_limits_per_frame_motion(fixture_ds) -> None:
    ds, m = fixture_ds
    trk = NLSTracker(
        ds.frequencies, linewidth_Hz=m["linewidth_Hz"], max_step_lw=2.0
    )
    res = trk.run(ds.spectra[0], init_freqs=ds.resonance_freqs[0, 0])
    step = np.abs(np.diff(res.tracked_freqs.astype(np.float64), axis=0))
    assert float(step.max()) <= 2.0 * m["linewidth_Hz"] * (1 + 1e-6)
