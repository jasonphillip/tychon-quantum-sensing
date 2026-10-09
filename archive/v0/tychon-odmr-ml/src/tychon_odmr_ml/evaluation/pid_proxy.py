"""Derivative zero-crossing PID proxy for ODMR dip tracking.

Simulates what an FPGA PID frequency-lock does: finds the dip minimum
via first-derivative zero-crossing, then converts to a B-field magnitude
estimate. Returns both the estimate and the lock-point bin index (used
as the CNN's spatial anchor).

Designed for weak-field regimes (20-70 uT) where Zeeman splitting is
1-4 MHz and dips may be partially or fully merged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class PidResult:
    """Result from a single PID estimation."""

    b_mag_uT: float  # Estimated |B| in micro-Tesla
    lock_bin: int  # Bin index of the PID lock point
    n_dips: int  # Number of resolved dips (1 or 2)


class DerivativeZeroCrossingPID:
    """PID proxy using first-derivative zero-crossing for dip detection.

    Parameters
    ----------
    frequencies : np.ndarray
        Frequency array in Hz, shape (n_freq,).
    """

    NV_GYROMAGNETIC_RATIO_HZ_T: float = 28.024e9  # Hz/T

    def __init__(self, frequencies: np.ndarray) -> None:
        self.frequencies = frequencies
        self.n_freq = len(frequencies)
        self.f_zfs = (frequencies[0] + frequencies[-1]) / 2.0
        self.bin_spacing_hz = frequencies[1] - frequencies[0]

    def estimate(self, spectrum: np.ndarray) -> PidResult:
        """Estimate B-field magnitude from a single raw ODMR spectrum.

        Parameters
        ----------
        spectrum : np.ndarray
            Shape (n_freq,) — raw PL signal (NOT normalized).

        Returns
        -------
        PidResult
            B-field estimate, lock-point bin, and dip count.
        """
        # First derivative
        ds = np.diff(spectrum)

        # Zero-crossings: derivative goes negative → positive (dip minima)
        zc_mask = (ds[:-1] < 0) & (ds[1:] >= 0)
        zc_indices = np.where(zc_mask)[0] + 1  # bin index of crossing

        if len(zc_indices) == 0:
            # Fallback: global minimum
            lock_bin = int(np.argmin(spectrum))
            f_dip = self.frequencies[lock_bin]
            b_uT = float(abs(f_dip - self.f_zfs)) / self.NV_GYROMAGNETIC_RATIO_HZ_T * 1e6
            return PidResult(b_mag_uT=b_uT, lock_bin=lock_bin, n_dips=0)

        if len(zc_indices) >= 2:
            # Two or more dips — pick the two deepest
            depths = np.array([-spectrum[i] for i in zc_indices])
            order = np.argsort(depths)[::-1]
            z1, z2 = sorted(zc_indices[order[:2]])

            f1, f2 = self.frequencies[z1], self.frequencies[z2]
            delta_f = float(f2 - f1)
            b_uT = delta_f / (2.0 * self.NV_GYROMAGNETIC_RATIO_HZ_T) * 1e6
            lock_bin = (z1 + z2) // 2
            return PidResult(b_mag_uT=b_uT, lock_bin=int(lock_bin), n_dips=2)

        # Single dip — estimate from offset from zero-field splitting
        lock_bin = int(zc_indices[0])
        f_dip = self.frequencies[lock_bin]
        b_uT = float(abs(f_dip - self.f_zfs)) / self.NV_GYROMAGNETIC_RATIO_HZ_T * 1e6
        return PidResult(b_mag_uT=b_uT, lock_bin=lock_bin, n_dips=1)

    def estimate_batch(self, spectra: np.ndarray) -> list[PidResult]:
        """Batch estimation.

        Parameters
        ----------
        spectra : np.ndarray
            Shape (N, n_freq).

        Returns
        -------
        list[PidResult]
            One result per spectrum.
        """
        return [self.estimate(s) for s in spectra]
