"""Validation against experimental reference data.

Structural hooks for cross-validating synthetic ODMR spectra against
published laboratory CW-ODMR datasets. Required for Deliverable 1 acceptance.

Validation steps (from requirements Section 3.3):
1. Spectral MSE against Zenodo CW-ODMR datasets
2. P1/T2 cross-check against CCE study values
3. Peak position accuracy (transition frequencies vs. expected Zeeman splitting)
4. Linewidth consistency check (measured FWHM vs. predicted from P1 concentration)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.interpolate import interp1d


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


def compute_spectral_mse(
    sim_freqs: np.ndarray,
    sim_signal: np.ndarray,
    exp_freqs: np.ndarray,
    exp_signal: np.ndarray,
) -> float:
    """Compute Mean Squared Error between simulated and experimental ODMR spectra.

    Both signals are normalized to [0, 1] for pure morphological comparison,
    removing dependence on absolute PL intensity.

    Parameters
    ----------
    sim_freqs : np.ndarray
        Simulated frequency array in Hz.
    sim_signal : np.ndarray
        Simulated PL signal.
    exp_freqs : np.ndarray
        Experimental frequency array in Hz.
    exp_signal : np.ndarray
        Experimental PL signal.

    Returns
    -------
    float
        Mean squared error between normalized lineshapes.
    """
    # Normalize to [0, 1] for morphological comparison
    exp_ptp = np.ptp(exp_signal)
    sim_ptp = np.ptp(sim_signal)

    if exp_ptp == 0 or sim_ptp == 0:
        return float("inf")

    exp_norm = (exp_signal - np.min(exp_signal)) / exp_ptp
    sim_norm = (sim_signal - np.min(sim_signal)) / sim_ptp

    # Interpolate experimental data onto simulated frequency grid
    interp_func = interp1d(
        exp_freqs, exp_norm, kind="linear", bounds_error=False, fill_value=1.0
    )
    aligned_exp = interp_func(sim_freqs)

    return float(np.mean((sim_norm - aligned_exp) ** 2))


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
