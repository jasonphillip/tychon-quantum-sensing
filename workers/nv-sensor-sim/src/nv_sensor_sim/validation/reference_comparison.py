"""Compare simulated and experimental CW-ODMR spectra.

``compare_spectra`` accepts one-dimensional, finite, paired frequency and signal
arrays. Frequencies may be in Hz or MHz independently and are converted to Hz.
Frequency axes are sorted before comparison; duplicate frequencies are invalid.

Overlap is the experimental span's intersection with the simulated span, divided
by the simulated span. The shape MSE uses only simulated samples inside the
experimental range. Both sampled signals are independently min-max normalized
over those samples after interpolating the experimental signal onto that grid.
The MSE is NaN when overlap is below ``min_overlap`` or has no sampled points;
it is infinite if either sampled signal is constant. An overlap at the threshold passes.

For each full spectrum, the baseline is the median of its highest 20 percent of
samples (rounded up). Contrast is (baseline - minimum) / baseline. Dip peaks
come from ``scipy.signal.find_peaks`` on (baseline - signal) / baseline using
``peak_prominence``. Each simulated peak's offset is its nearest experimental
peak frequency minus its own frequency, in Hz. An unmatched peak has a NaN
offset. Linewidth is the deepest dip's full width at half depth relative to
the measured baseline, with linear interpolation at both crossings; it is NaN
when either crossing is outside the sampled span. Experimental noise is the
standard deviation of the residual after a Savitzky-Golay filter (11, 3),
divided by its baseline; it is NaN for fewer than 11 samples. Ratios needing
a zero baseline or zero experimental contrast are NaN.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.signal import find_peaks, savgol_filter


@dataclass(frozen=True)
class SpectralComparison:
    """Measured agreement and dip properties for two spectra."""

    overlap_fraction: float
    overlap_ok: bool
    shape_mse: float
    contrast_sim: float
    contrast_exp: float
    contrast_ratio: float
    peak_offsets_hz: list[float]
    linewidth_sim_hz: float
    linewidth_exp_hz: float
    noise_exp: float
    n_points_overlap: int


def load_experimental_odmr(filepath: str) -> tuple[np.ndarray, np.ndarray]:
    """Load experimental CW ODMR data from a CSV file.

    Uses flexible column name matching: the frequency column is identified by
    containing 'freq' (case-insensitive) and the PL signal column by containing
    'pl' or 'signal'. Falls back to first two columns if no match is found.

    Parameters
    ----------
    filepath : str
        Path to CSV file with frequency and PL signal columns.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (frequencies_Hz, pl_signal) arrays.

    Raises
    ------
    ValueError
        If file has fewer than 2 columns or no data rows.
    """
    df = pd.read_csv(filepath)

    if df.shape[1] < 2:
        raise ValueError(f"Expected at least 2 columns, got {df.shape[1]}")
    if len(df) == 0:
        raise ValueError("CSV file contains no data rows")

    cols_lower = {c: c.lower() for c in df.columns}

    # Find frequency column
    freq_col = None
    for c, cl in cols_lower.items():
        if "freq" in cl:
            freq_col = c
            break

    # Find PL / signal column
    signal_col = None
    for c, cl in cols_lower.items():
        if c == freq_col:
            continue
        if "pl" in cl or "signal" in cl:
            signal_col = c
            break

    # Fallback: first two columns
    if freq_col is None:
        freq_col = df.columns[0]
    if signal_col is None:
        signal_col = df.columns[1] if df.columns[1] != freq_col else df.columns[0]

    return df[freq_col].to_numpy(dtype=np.float64), df[signal_col].to_numpy(dtype=np.float64)


def _prepared_spectrum(
    freqs: np.ndarray, signal: np.ndarray, unit: str
) -> tuple[np.ndarray, np.ndarray]:
    if unit not in ("Hz", "MHz"):
        raise ValueError(f"Frequency unit must be 'Hz' or 'MHz', got {unit!r}")
    freqs = np.asarray(freqs, dtype=np.float64)
    signal = np.asarray(signal, dtype=np.float64)
    if freqs.ndim != 1 or signal.ndim != 1 or len(freqs) != len(signal) or len(freqs) < 2:
        raise ValueError("Frequency and signal must be paired one-dimensional arrays of length >= 2")
    freqs = freqs * (1e6 if unit == "MHz" else 1.0)
    if not np.all(np.isfinite(freqs)) or not np.all(np.isfinite(signal)):
        raise ValueError("Frequency and signal must contain only finite values")
    order = np.argsort(freqs)
    freqs, signal = freqs[order], signal[order]
    if np.any(np.diff(freqs) <= 0):
        raise ValueError("Frequency samples must be distinct")
    return freqs, signal


def _baseline(signal: np.ndarray) -> float:
    top_count = max(1, int(np.ceil(len(signal) * 0.2)))
    return float(np.median(np.partition(signal, -top_count)[-top_count:]))


def _linewidth(freqs: np.ndarray, signal: np.ndarray, baseline: float) -> float:
    minimum = int(np.argmin(signal))
    half_depth = (baseline + signal[minimum]) / 2
    if minimum == 0 or minimum == len(signal) - 1:
        return float("nan")

    left = minimum
    while left > 0 and signal[left] < half_depth:
        left -= 1
    right = minimum
    while right < len(signal) - 1 and signal[right] < half_depth:
        right += 1
    if left == 0 and signal[left] < half_depth:
        return float("nan")
    if right == len(signal) - 1 and signal[right] < half_depth:
        return float("nan")
    if left == minimum or right == minimum:
        return float("nan")

    left_freq = np.interp(half_depth, signal[left : left + 2][::-1], freqs[left : left + 2][::-1])
    right_freq = np.interp(half_depth, signal[right - 1 : right + 1], freqs[right - 1 : right + 1])
    return float(right_freq - left_freq)


def compare_spectra(
    sim_freqs: np.ndarray,
    sim_signal: np.ndarray,
    exp_freqs: np.ndarray,
    exp_signal: np.ndarray,
    *,
    exp_freq_unit: str = "Hz",
    sim_freq_unit: str = "Hz",
    min_overlap: float = 0.8,
    peak_prominence: float = 0.02,
) -> SpectralComparison:
    """Return shape agreement and physical dip metrics as documented above."""
    sim_freqs, sim_signal = _prepared_spectrum(sim_freqs, sim_signal, sim_freq_unit)
    exp_freqs, exp_signal = _prepared_spectrum(exp_freqs, exp_signal, exp_freq_unit)
    if not 0 <= min_overlap <= 1:
        raise ValueError("min_overlap must be between 0 and 1")
    if peak_prominence < 0:
        raise ValueError("peak_prominence must be nonnegative")

    overlap_span = max(
        0.0,
        min(sim_freqs[-1], exp_freqs[-1]) - max(sim_freqs[0], exp_freqs[0]),
    )
    overlap_fraction = float(overlap_span / (sim_freqs[-1] - sim_freqs[0]))
    overlap_ok = bool(overlap_fraction >= min_overlap)
    inside = (sim_freqs >= exp_freqs[0]) & (sim_freqs <= exp_freqs[-1])
    n_points_overlap = int(np.count_nonzero(inside))
    shape_mse = float("nan")
    if overlap_ok and n_points_overlap:
        sampled_sim = sim_signal[inside]
        sampled_exp = np.interp(sim_freqs[inside], exp_freqs, exp_signal)
        sim_range = np.ptp(sampled_sim)
        exp_range = np.ptp(sampled_exp)
        if sim_range == 0 or exp_range == 0:
            shape_mse = float("inf")
        else:
            sim_norm = (sampled_sim - np.min(sampled_sim)) / sim_range
            exp_norm = (sampled_exp - np.min(sampled_exp)) / exp_range
            shape_mse = float(np.mean((sim_norm - exp_norm) ** 2))

    sim_baseline = _baseline(sim_signal)
    exp_baseline = _baseline(exp_signal)
    contrast_sim = (
        float((sim_baseline - np.min(sim_signal)) / sim_baseline)
        if sim_baseline != 0 else float("nan")
    )
    contrast_exp = (
        float((exp_baseline - np.min(exp_signal)) / exp_baseline)
        if exp_baseline != 0 else float("nan")
    )
    contrast_ratio = float(contrast_sim / contrast_exp) if contrast_exp != 0 else float("nan")

    sim_peaks = (
        find_peaks((sim_baseline - sim_signal) / sim_baseline, prominence=peak_prominence)[0]
        if sim_baseline != 0 else np.array([], dtype=int)
    )
    exp_peaks = (
        find_peaks((exp_baseline - exp_signal) / exp_baseline, prominence=peak_prominence)[0]
        if exp_baseline != 0 else np.array([], dtype=int)
    )
    peak_offsets_hz = []
    for peak in sim_peaks:
        if len(exp_peaks):
            nearest = exp_peaks[np.argmin(abs(exp_freqs[exp_peaks] - sim_freqs[peak]))]
            peak_offsets_hz.append(float(exp_freqs[nearest] - sim_freqs[peak]))
        else:
            peak_offsets_hz.append(float("nan"))
    noise_exp = (
        float(np.std(exp_signal - savgol_filter(exp_signal, 11, 3)) / exp_baseline)
        if len(exp_signal) >= 11 and exp_baseline != 0 else float("nan")
    )
    return SpectralComparison(
        overlap_fraction=overlap_fraction,
        overlap_ok=overlap_ok,
        shape_mse=shape_mse,
        contrast_sim=contrast_sim,
        contrast_exp=contrast_exp,
        contrast_ratio=contrast_ratio,
        peak_offsets_hz=peak_offsets_hz,
        linewidth_sim_hz=_linewidth(sim_freqs, sim_signal, sim_baseline),
        linewidth_exp_hz=_linewidth(exp_freqs, exp_signal, exp_baseline),
        noise_exp=noise_exp,
        n_points_overlap=n_points_overlap,
    )


def compute_spectral_mse(
    sim_freqs: np.ndarray,
    sim_signal: np.ndarray,
    exp_freqs: np.ndarray,
    exp_signal: np.ndarray,
) -> float:
    """Return the normalized shape MSE, raising for insufficient overlap."""
    comparison = compare_spectra(sim_freqs, sim_signal, exp_freqs, exp_signal)
    if not comparison.overlap_ok:
        raise ValueError("Experimental spectrum covers less than the required simulated span")
    return comparison.shape_mse


def check_peak_positions(
    frequencies: np.ndarray,
    pl_signal: np.ndarray,
    expected_freqs_Hz: list[float],
    tolerance_Hz: float = 5e6,
) -> dict[str, list]:
    """Check that ODMR dip positions match expected transition frequencies.

    Parameters
    ----------
    frequencies : np.ndarray
        Frequency array in Hz.
    pl_signal : np.ndarray
        PL signal (dips are minima).
    expected_freqs_Hz : list[float]
        Expected transition frequencies from Hamiltonian eigenvalues.
    tolerance_Hz : float
        Acceptable deviation in Hz.

    Returns
    -------
    dict
        {"matched": [...], "unmatched": [...]} with frequency pairs.
    """
    from scipy.signal import find_peaks

    # Find dip positions (invert signal to find peaks)
    inverted = -pl_signal
    peaks, _ = find_peaks(inverted, height=np.mean(inverted))

    found_freqs = frequencies[peaks]
    matched = []
    unmatched = []

    for exp_f in expected_freqs_Hz:
        diffs = np.abs(found_freqs - exp_f)
        if len(diffs) > 0 and np.min(diffs) < tolerance_Hz:
            best_idx = np.argmin(diffs)
            matched.append((exp_f, found_freqs[best_idx], diffs[best_idx]))
        else:
            unmatched.append(exp_f)

    return {"matched": matched, "unmatched": unmatched}


def check_linewidth_consistency(
    frequencies: np.ndarray,
    pl_signal: np.ndarray,
    expected_fwhm_Hz: float,
    tolerance_frac: float = 0.5,
) -> dict[str, float]:
    """Check measured FWHM against predicted linewidth from P1 concentration.

    Parameters
    ----------
    frequencies : np.ndarray
        Frequency array in Hz.
    pl_signal : np.ndarray
        PL signal.
    expected_fwhm_Hz : float
        Expected FWHM from compute_linewidth(p1_ppm).
    tolerance_frac : float
        Acceptable fractional deviation (0.5 = 50%).

    Returns
    -------
    dict
        {"measured_fwhm_Hz": float, "expected_fwhm_Hz": float,
         "deviation_frac": float, "pass": bool}
    """
    # Estimate FWHM from the deepest dip
    min_idx = np.argmin(pl_signal)
    min_val = pl_signal[min_idx]
    half_depth = (1.0 + min_val) / 2.0  # Halfway between off-resonance and dip

    # Find half-max crossings around the dip
    above_half = pl_signal > half_depth
    # Walk left from minimum
    left_idx = min_idx
    while left_idx > 0 and not above_half[left_idx]:
        left_idx -= 1
    # Walk right from minimum
    right_idx = min_idx
    while right_idx < len(pl_signal) - 1 and not above_half[right_idx]:
        right_idx += 1

    measured_fwhm = frequencies[right_idx] - frequencies[left_idx]
    deviation = abs(measured_fwhm - expected_fwhm_Hz) / expected_fwhm_Hz if expected_fwhm_Hz > 0 else float("inf")

    return {
        "measured_fwhm_Hz": float(measured_fwhm),
        "expected_fwhm_Hz": float(expected_fwhm_Hz),
        "deviation_frac": float(deviation),
        "pass": deviation < tolerance_frac,
    }
