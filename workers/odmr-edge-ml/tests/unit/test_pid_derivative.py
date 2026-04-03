"""Tests for the derivative zero-crossing PID proxy."""

import numpy as np

from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID, PidResult


def _make_frequencies(n: int = 100) -> np.ndarray:
    return np.linspace(2.82e9, 2.92e9, n)


def _make_single_dip_spectrum(
    frequencies: np.ndarray, dip_freq: float, depth: float = 0.03, width: float = 2e6
) -> np.ndarray:
    """Synthetic Gaussian dip centered at dip_freq."""
    return 1.0 - depth * np.exp(-0.5 * ((frequencies - dip_freq) / width) ** 2)


def _make_two_dip_spectrum(
    frequencies: np.ndarray, f1: float, f2: float, depth: float = 0.03, width: float = 2e6
) -> np.ndarray:
    """Synthetic double-Gaussian dip spectrum."""
    dip1 = depth * np.exp(-0.5 * ((frequencies - f1) / width) ** 2)
    dip2 = depth * np.exp(-0.5 * ((frequencies - f2) / width) ** 2)
    return 1.0 - dip1 - dip2


def test_pid_result_fields():
    result = PidResult(b_mag_uT=45.0, lock_bin=50, n_dips=1)
    assert result.b_mag_uT == 45.0
    assert result.lock_bin == 50
    assert result.n_dips == 1


def test_single_dip_at_center():
    """Single dip at ZFS center → B near zero (within 1-bin discretization)."""
    freqs = _make_frequencies()
    f_zfs = (freqs[0] + freqs[-1]) / 2
    spectrum = _make_single_dip_spectrum(freqs, dip_freq=f_zfs)

    pid = DerivativeZeroCrossingPID(freqs)
    result = pid.estimate(spectrum)
    # 1 bin = 1.01 MHz → ~18 uT resolution limit
    assert result.b_mag_uT < 25.0
    assert result.n_dips == 1


def test_single_dip_offset():
    """Single dip offset from center → B proportional to offset."""
    freqs = _make_frequencies()
    f_zfs = (freqs[0] + freqs[-1]) / 2
    offset_hz = 5e6  # 5 MHz offset
    spectrum = _make_single_dip_spectrum(freqs, dip_freq=f_zfs + offset_hz)

    pid = DerivativeZeroCrossingPID(freqs)
    result = pid.estimate(spectrum)
    expected_uT = offset_hz / pid.NV_GYROMAGNETIC_RATIO_HZ_T * 1e6
    # Within ~1 bin discretization (~18 uT)
    assert abs(result.b_mag_uT - expected_uT) < 25.0


def test_two_resolved_dips():
    """Two well-separated dips → B from splitting."""
    freqs = _make_frequencies()
    f_zfs = (freqs[0] + freqs[-1]) / 2
    splitting_hz = 10e6
    f1 = f_zfs - splitting_hz / 2
    f2 = f_zfs + splitting_hz / 2
    spectrum = _make_two_dip_spectrum(freqs, f1, f2, width=1.5e6)

    pid = DerivativeZeroCrossingPID(freqs)
    result = pid.estimate(spectrum)
    expected_uT = splitting_hz / (2 * pid.NV_GYROMAGNETIC_RATIO_HZ_T) * 1e6
    assert result.n_dips == 2
    # Within ~1 bin discretization per dip (~18 uT)
    assert abs(result.b_mag_uT - expected_uT) < 25.0


def test_batch_returns_list():
    freqs = _make_frequencies()
    f_zfs = (freqs[0] + freqs[-1]) / 2
    spectra = np.stack([
        _make_single_dip_spectrum(freqs, f_zfs),
        _make_single_dip_spectrum(freqs, f_zfs + 3e6),
    ])

    pid = DerivativeZeroCrossingPID(freqs)
    results = pid.estimate_batch(spectra)
    assert len(results) == 2
    assert all(isinstance(r, PidResult) for r in results)


def test_lock_bin_in_range():
    """Lock bin must be a valid index."""
    freqs = _make_frequencies()
    f_zfs = (freqs[0] + freqs[-1]) / 2
    spectrum = _make_single_dip_spectrum(freqs, f_zfs + 2e6)

    pid = DerivativeZeroCrossingPID(freqs)
    result = pid.estimate(spectrum)
    assert 0 <= result.lock_bin < len(freqs)


def test_flat_spectrum_fallback():
    """Near-flat spectrum triggers argmin fallback."""
    freqs = _make_frequencies()
    spectrum = np.ones(len(freqs)) * 0.99
    spectrum[50] = 0.989  # tiny dip

    pid = DerivativeZeroCrossingPID(freqs)
    result = pid.estimate(spectrum)
    assert result.lock_bin == 50
