"""PID baseline proxy for evaluation comparison.

Estimates B-field from ODMR spectrum using symmetric peak-finding,
replicating what a classical PID frequency-lock would achieve.
This is NOT a real-time controller — it's a Python proxy for
offline evaluation against the neural network models.

Deliberately embodies three limitations the NN must beat:
1. Assumes symmetric lineshape (biased on skewed spectra)
2. Single-axis extraction (no MIMO degeneracy handling)
3. No heading error correction (ignores second-order perturbation)
"""

from __future__ import annotations

import numpy as np


class PidProxy:
    """PID-style baseline for ODMR → B-field estimation.

    Parameters
    ----------
    n_freq_points : int
        Number of frequency points per spectrum.
    freq_range_hz : tuple[float, float]
        Frequency sweep range in Hz (start, stop).
    """

    # NV center ground-state gyromagnetic ratio
    NV_GYROMAGNETIC_RATIO_HZ_T: float = 28.024e9  # Hz/T

    def __init__(
        self,
        n_freq_points: int = 100,
        freq_range_hz: tuple[float, float] = (2.82e9, 2.92e9),
    ) -> None:
        self.n_freq_points = n_freq_points
        self.freq_range_hz = freq_range_hz
        self.frequencies = np.linspace(
            freq_range_hz[0], freq_range_hz[1], n_freq_points
        )
        # Zero-field splitting frequency (center of ODMR)
        self.f_zfs = (freq_range_hz[0] + freq_range_hz[1]) / 2.0

    def estimate_bfield(self, spectrum: np.ndarray) -> np.ndarray:
        """Estimate B-field from a single ODMR spectrum.

        Finds the two deepest dips, computes their frequency splitting,
        and converts to Bz via the gyromagnetic ratio. Bx = By = 0
        (PID is single-axis SISO).

        Parameters
        ----------
        spectrum : np.ndarray
            Shape (n_freq_points,) — PL signal (raw or normalized).

        Returns
        -------
        np.ndarray
            Shape (3,) — [Bx, By, Bz] estimate in Tesla.
        """
        result = np.zeros(3)

        # Find dip positions: ODMR dips are minima in PL signal
        # Use a simple approach: find the two lowest points that are
        # separated by at least 10% of the sweep range
        min_separation = self.n_freq_points // 10

        # First dip: global minimum
        idx1 = int(np.argmin(spectrum))

        # Second dip: minimum outside exclusion zone around first dip
        mask = np.ones(self.n_freq_points, dtype=bool)
        lo = max(0, idx1 - min_separation)
        hi = min(self.n_freq_points, idx1 + min_separation + 1)
        mask[lo:hi] = False

        if mask.any():
            masked_spectrum = spectrum.copy()
            masked_spectrum[~mask] = np.max(spectrum)
            idx2 = int(np.argmin(masked_spectrum))

            # Frequency splitting
            f1 = self.frequencies[min(idx1, idx2)]
            f2 = self.frequencies[max(idx1, idx2)]
            delta_f = f2 - f1

            # Bz = delta_f / (2 * gamma_NV)
            result[2] = delta_f / (2.0 * self.NV_GYROMAGNETIC_RATIO_HZ_T)
        else:
            # Only one dip found — estimate from offset from ZFS
            f_dip = self.frequencies[idx1]
            delta_f = abs(f_dip - self.f_zfs)
            result[2] = delta_f / self.NV_GYROMAGNETIC_RATIO_HZ_T

        return result

    def estimate_batch(self, spectra: np.ndarray) -> np.ndarray:
        """Batch B-field estimation.

        Parameters
        ----------
        spectra : np.ndarray
            Shape (N, n_freq_points).

        Returns
        -------
        np.ndarray
            Shape (N, 3) — [Bx, By, Bz] per spectrum.
        """
        return np.array([self.estimate_bfield(s) for s in spectra])
