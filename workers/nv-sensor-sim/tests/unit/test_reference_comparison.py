import numpy as np
import pytest

from nv_sensor_sim.validation.reference_comparison import (
    SpectralComparison,
    compare_spectra,
    compute_spectral_mse,
)


def _lorentzian_dip(freqs_hz, center_hz, fwhm_hz, contrast, baseline=1.0):
    hw = fwhm_hz / 2.0
    return baseline * (1.0 - contrast * hw**2 / ((freqs_hz - center_hz) ** 2 + hw**2))


def test_disjoint_ranges_fail():
    f_sim = np.linspace(2.80e9, 2.95e9, 300)
    f_exp = np.linspace(3.10e9, 3.30e9, 300)
    s = _lorentzian_dip(f_sim, 2.87e9, 8e6, 0.2)
    e = _lorentzian_dip(f_exp, 3.20e9, 8e6, 0.2)
    r = compare_spectra(f_sim, s, f_exp, e)
    assert isinstance(r, SpectralComparison)
    assert r.overlap_ok is False and r.overlap_fraction == 0.0 and np.isnan(r.shape_mse)
    with pytest.raises(ValueError):
        compute_spectral_mse(f_sim, s, f_exp, e)


def test_wrong_contrast_fails_despite_same_shape():
    f = np.linspace(2.80e9, 2.95e9, 400)
    sim = _lorentzian_dip(f, 2.87e9, 8e6, 0.30)
    exp = _lorentzian_dip(f, 2.87e9, 8e6, 0.10)
    r = compare_spectra(f, sim, f, exp)
    assert r.overlap_ok and r.shape_mse < 1e-6          # identical normalized shape
    assert r.contrast_ratio == pytest.approx(3.0, rel=0.05)  # contrast disagreement is visible
    assert abs(r.linewidth_sim_hz - 8e6) < 1e6 and abs(r.linewidth_exp_hz - 8e6) < 1e6


def test_unit_mismatch_rejected():
    f_hz = np.linspace(2.80e9, 2.95e9, 300)
    s = _lorentzian_dip(f_hz, 2.87e9, 8e6, 0.2)
    f_mhz = f_hz / 1e6
    # MHz data declared as Hz: ranges are disjoint by six orders of magnitude -> must not return a number
    r = compare_spectra(f_hz, s, f_mhz, s, exp_freq_unit="Hz")
    assert r.overlap_ok is False
    # MHz data declared as MHz: identical result to the Hz call
    r_ok = compare_spectra(f_hz, s, f_mhz, s, exp_freq_unit="MHz")
    assert r_ok.overlap_ok and r_ok.shape_mse < 1e-12
    with pytest.raises(ValueError):
        compare_spectra(f_hz, s, f_hz, s, exp_freq_unit="GHz")


def test_peak_offsets_and_noise():
    f = np.linspace(2.80e9, 2.95e9, 600)
    sim = _lorentzian_dip(f, 2.870e9, 8e6, 0.2)
    rng = np.random.default_rng(0)
    exp = _lorentzian_dip(f, 2.872e9, 8e6, 0.2) + rng.normal(0, 0.002, f.size)
    r = compare_spectra(f, sim, f, exp)
    assert len(r.peak_offsets_hz) == 1 and abs(r.peak_offsets_hz[0] - 2e6) < 1e6
    assert 0.001 < r.noise_exp < 0.004


def test_backcompat_mse_unchanged_on_overlap():
    f = np.linspace(2.80e9, 2.95e9, 300)
    s = _lorentzian_dip(f, 2.87e9, 8e6, 0.2)
    assert compute_spectral_mse(f, s, f, s) == pytest.approx(0.0, abs=1e-12)
