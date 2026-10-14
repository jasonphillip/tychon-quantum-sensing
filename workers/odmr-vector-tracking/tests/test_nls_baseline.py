"""NLS repairs: informative crossing recovery, missing width, and legacy parity."""

import numpy as np
import pytest

from odmr_vector_tracking.tracking.nls_baseline import NLSTracker


def _spectra(freq, centers, width, depths):
    lor = (width / 2) ** 2 / (
        (freq[None, :, None] - centers[:, None, :]) ** 2 + (width / 2) ** 2
    )
    return np.asarray(1 - lor @ np.asarray(depths), dtype=np.float32)


def test_multistart_recovers_after_crossing():
    freq = np.linspace(2.86e9, 2.88e9, 401)
    trajectory = np.r_[np.linspace(-4e6, 0, 11), np.zeros(5), np.arange(.4, 4.01, .4) * 1e6]
    centers = np.stack([2.87e9 + trajectory, 2.87e9 - trajectory], axis=1)
    spectra = _spectra(freq, centers, 1e6, [.04, .001])
    legacy = NLSTracker(freq, linewidth_Hz=1e6, line_depths=[.04, .001])
    repaired = NLSTracker(freq, linewidth_Hz=1e6, line_depths=[.04, .001], multi_start=True)
    old = legacy.run(spectra, centers[0])
    new = repaired.run(spectra, centers[0])
    assert np.max(np.abs(old.tracked_freqs[-1] - centers[-1])) > 1e6
    assert np.max(np.abs(new.tracked_freqs[-1] - centers[-1])) < .2e6
    assert max(repaired.diagnostics_["starts_attempted"]) == 3


def test_gamma_estimated_from_data_within_20pct():
    freq = np.linspace(2.85e9, 2.89e9, 501)
    centers = np.tile([2.86e9, 2.88e9], (14, 1))
    spectra = _spectra(freq, centers, 1.8e6, [.03, .02])
    tracker = NLSTracker(freq, linewidth_Hz=None, estimate_linewidth=True)
    tracker.run(spectra, centers[0])
    assert abs(tracker.linewidth_Hz_ / 1.8e6 - 1) < .2
    assert tracker.diagnostics_["linewidth_estimation_frames"] == 10


def test_supplied_linewidth_is_not_refit():
    freq = np.linspace(2.85e9, 2.89e9, 201)
    centers = np.tile([2.86e9, 2.88e9], (12, 1))
    tracker = NLSTracker(freq, linewidth_Hz=1e6, estimate_linewidth=True)
    tracker.run(_spectra(freq, centers, 2e6, [.03, .02]), centers[0])
    assert tracker.linewidth_Hz_ == 1e6
    assert tracker.diagnostics_["linewidth_estimation_frames"] == 0


@pytest.mark.parametrize("kwargs", [
    {"linewidth_Hz": 0}, {"linewidth_Hz": -1}, {"linewidth_Hz": float("nan")},
    {"linewidth_Hz": None}, {"linewidth_Hz": 1e6, "profile": "invalid"},
    {"linewidth_Hz": 1e6, "voigt_sigma_ratio": -1},
])
def test_invalid_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        NLSTracker(np.linspace(2.86e9, 2.88e9, 101), **kwargs)


def test_voigt_zero_gaussian_limit_matches_lorentzian():
    freq = np.linspace(2.86e9, 2.88e9, 201)
    a = NLSTracker(freq, linewidth_Hz=1e6)
    b = NLSTracker(freq, linewidth_Hz=1e6, profile="voigt", voigt_sigma_ratio=0)
    np.testing.assert_allclose(a._model(np.array([.4,.6]), np.array([.03,.02])),
                               b._model(np.array([.4,.6]), np.array([.03,.02])), atol=1e-14)


def test_missing_linewidth_without_resolved_dips_fails_explicitly():
    freq = np.linspace(2.86e9, 2.88e9, 201)
    tracker = NLSTracker(freq, linewidth_Hz=None, estimate_linewidth=True)
    with pytest.raises(ValueError, match="no isolated resolved dip"):
        tracker.run(np.ones((10,201)), np.array([2.865e9,2.875e9]))


def test_failure_accounting_preserves_all_frames():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / "experiments/nls_failure_diagnosis.py"
    spec = importlib.util.spec_from_file_location("nls_diagnosis_test",path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    bias = np.array([0,0,.005])
    truth = np.tile(bias,(10,1))
    predicted = truth.copy(); predicted[:2] = np.nan
    row = module.score(truth,predicted,bias,.001)
    assert row["n_frames"] == 10
    assert row["n_valid_frames"] == 8
    assert row["nonfinite_frames"] == 2
    assert row["lock_frac"] == .8
    assert row["lost"] is True
    assert np.isfinite(row["rmse_T"])
