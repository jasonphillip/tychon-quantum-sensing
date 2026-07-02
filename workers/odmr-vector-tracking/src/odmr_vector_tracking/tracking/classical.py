"""Classical lock-in + per-line PID baseline with nearest-peak association.

This is the Γ/2-limited baseline the learned tracker must beat. It is the standard closed-loop
approach: each of the L resonances is locked by a per-line PID driven by a dispersive lock-in
discriminator, and lines are re-associated each frame to the nearest detected peak.

It tracks a **frequency, not an identity**: at an inter-axis crossing, two lines merge within a
linewidth and the nearest-peak association swaps which physical line each lock follows. The lock
keeps its *claimed* (axis, sign) identity from acquisition, so after the crossing that claim is
wrong — the loss-of-lock that corrupts the per-axis vector estimate. This is exactly the failure
documented classically (MIT-LL Clevenson 2018) and never fixed with learning.

Pure numpy (no scipy) to keep the package dependency-light, mirroring the sibling. The output
feeds the vendored BLUE inversion in canonical line order: a swapped association places the wrong
line's frequency in a BLUE row, propagating the identity error into the 3D vector.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    LINE_AXIS_8,
    LINE_TRANSITION_8,
    N_LINES_ELECTRONIC,
    ZFS_D_HZ,
)


def auto_peak_min_depth(
    spectra: np.ndarray,
    fraction: float = 0.35,
    line_depths: np.ndarray | list[float] | None = None,
) -> float:
    """Detection threshold scaled from the data's own dip contrast.

    ``fraction`` x a reference dip depth: the **shallowest nominal line depth** when the
    dataset manifest provides ``line_depths`` (v1+ carries per-line depths; per-axis contrast
    scaling makes the weakest line ~4x shallower than the deepest, and a max-depth-derived
    threshold silently drops it), else the median per-frame maximum depth
    (``1 - min(PL)`` over the frequency axis; ``spectra`` may be ``(T, F)`` or ``(N, T, F)``).

    Why this exists: the default absolute ``peak_min_depth=0.03`` exceeds the real
    ``sequence_sanity_v0`` dip depth (~0.4% of baseline, measured 0.0037-0.0077 per-frame max),
    so the detector returned **zero peaks on every real frame** and the tracker never left its
    initialization — the originally published Increment-1 numbers scored that frozen tracker
    and were retracted (2026-07-01). Every evaluation must scale the threshold from the data.

    ``fraction`` must sit below the reference line's residual depth under contrast drift
    (v1 AR(1) drift plus overlap can halve the shallowest dip) and above overlap ripple
    between neighboring Lorentzians; 0.35 satisfies both on v0 and v1.
    """
    if line_depths is not None and len(line_depths):
        return float(fraction * float(np.min(np.asarray(line_depths, dtype=np.float64))))
    s = np.asarray(spectra, dtype=np.float64)
    depth = 1.0 - s.min(axis=-1)
    return float(fraction * np.median(depth))


@dataclass(frozen=True)
class ClassicalTrackResult:
    """Output of :meth:`ClassicalTracker.run` over one (T, F) sequence.

    Attributes
    ----------
    tracked_freqs
        ``(T, L)`` locked center frequency per line-lock (canonical / claimed-identity order).
    pred_axis
        ``(T, L)`` NV axis the tracker *claims* each lock is on (constant from acquisition).
    pred_transition
        ``(T, L)`` transition id claimed per lock (constant from acquisition).
    locked
        ``(T, L)`` bool — whether each lock found a peak within capture range that frame.
    B_est
        ``(T, 3)`` lab-frame B estimate from the BLUE inversion of ``tracked_freqs``.
    """

    tracked_freqs: np.ndarray
    pred_axis: np.ndarray
    pred_transition: np.ndarray
    locked: np.ndarray
    B_est: np.ndarray


class ClassicalTracker:
    """Lock-in + per-line PID tracker with greedy nearest-peak association.

    Parameters
    ----------
    frequencies
        ``(F,)`` MW frequency axis (Hz) — the spectrum's sweep grid.
    linewidth_Hz
        Resonance FWHM (Hz); sets the discriminator/capture scales.
    kp, ki, kd
        Per-line PID gains acting on the (assigned-peak − center) error, in fraction-of-error
        units (kp ≈ 1 → near-deadbeat follow; lower → more lag, the regime where a fast field
        sweep alone can break lock).
    capture_range_Hz
        Max |center − peak| for a peak to be associated to a lock. ``None`` → ``8 × linewidth``.
    peak_min_depth
        Minimum dip depth (in normalized PL units) for a local minimum to count as a peak.
    peak_min_distance_bins
        Minimum separation between detected peaks, in frequency bins (non-max suppression).
    """

    def __init__(
        self,
        frequencies: np.ndarray,
        *,
        linewidth_Hz: float,
        kp: float = 0.7,
        ki: float = 0.05,
        kd: float = 0.0,
        capture_range_Hz: float | None = None,
        peak_min_depth: float = 0.03,
        peak_min_distance_bins: int = 3,
        zfs_Hz: float = ZFS_D_HZ,
        gamma_Hz_per_T: float = GAMMA_E_HZ_PER_T,
    ) -> None:
        self.freqs = np.asarray(frequencies, dtype=np.float64).reshape(-1)
        self.df = float(self.freqs[1] - self.freqs[0])
        self.linewidth = float(linewidth_Hz)
        self.kp, self.ki, self.kd = float(kp), float(ki), float(kd)
        self.capture_range = (
            float(capture_range_Hz) if capture_range_Hz is not None else 8.0 * self.linewidth
        )
        self.peak_min_depth = float(peak_min_depth)
        self.peak_min_distance_bins = int(peak_min_distance_bins)
        self.zfs = float(zfs_Hz)
        self.gamma = float(gamma_Hz_per_T)

    # --- peak detection -----------------------------------------------------------------

    def _find_peaks(self, spectrum: np.ndarray) -> np.ndarray:
        """Detect resonance dips → array of sub-bin-refined peak frequencies (Hz), sorted.

        Dips are local minima of PL below a depth threshold; the center is refined by a 3-point
        parabolic interpolation (the dispersive-discriminator zero crossing). Non-max
        suppression enforces a minimum peak separation.
        """
        s = np.asarray(spectrum, dtype=np.float64)
        baseline = float(np.median(s))
        # Local minima (strict left, non-strict right) interior to the grid.
        is_min = (s[1:-1] < s[:-2]) & (s[1:-1] <= s[2:])
        idx = np.where(is_min)[0] + 1
        depth = baseline - s[idx]
        idx = idx[depth >= self.peak_min_depth]
        if idx.size == 0:
            return np.empty(0, dtype=np.float64)

        # Non-max suppression by depth, enforcing min distance.
        order = idx[np.argsort(baseline - s[idx])[::-1]]  # deepest first
        kept: list[int] = []
        for k in order:
            if all(abs(k - j) >= self.peak_min_distance_bins for j in kept):
                kept.append(int(k))
        kept_idx = np.array(sorted(kept))

        # Sub-bin parabolic refinement of each kept minimum.
        centers = []
        for k in kept_idx:
            if 1 <= k < len(s) - 1:
                y0, y1, y2 = s[k - 1], s[k], s[k + 1]
                denom = y0 - 2.0 * y1 + y2
                offset = 0.5 * (y0 - y2) / denom if denom != 0 else 0.0
                offset = float(np.clip(offset, -1.0, 1.0))
            else:
                offset = 0.0
            centers.append(self.freqs[k] + offset * self.df)
        return np.array(sorted(centers), dtype=np.float64)

    # --- association --------------------------------------------------------------------

    def _associate(
        self, predicted: np.ndarray, peaks: np.ndarray
    ) -> np.ndarray:
        """Greedy nearest-peak association.

        Returns an array ``assign`` of length L: ``assign[i]`` is the peak frequency claimed by
        lock ``i``, or ``nan`` if no peak fell within ``capture_range``. Greedy global
        smallest-distance-first assignment with each peak claimed once — the step that swaps
        identities when two lines merge.
        """
        n_locks = predicted.shape[0]
        assign = np.full(n_locks, np.nan, dtype=np.float64)
        if peaks.size == 0:
            return assign

        dist = np.abs(predicted[:, None] - peaks[None, :])  # (L, M)
        dist[dist > self.capture_range] = np.inf
        avail_lock = np.ones(n_locks, dtype=bool)
        avail_peak = np.ones(peaks.shape[0], dtype=bool)

        while np.isfinite(dist).any():
            flat = int(np.argmin(dist))
            i, j = divmod(flat, peaks.shape[0])
            if not np.isfinite(dist[i, j]):
                break
            assign[i] = peaks[j]
            avail_lock[i] = False
            avail_peak[j] = False
            dist[i, :] = np.inf
            dist[:, j] = np.inf
        return assign

    # --- main loop ----------------------------------------------------------------------

    def run(self, spectra: np.ndarray, init_freqs: np.ndarray) -> ClassicalTrackResult:
        """Track all L resonances through a ``(T, F)`` spectrum series.

        Parameters
        ----------
        spectra
            ``(T, F)`` PL time-series.
        init_freqs
            ``(L,)`` initial line centers (Hz) in canonical ``(axis, sign)`` order, used to
            acquire lock at frame 0 (the well-resolved-acquisition assumption). Each lock keeps
            the canonical identity of its slot for the whole run.
        """
        spectra = np.asarray(spectra, dtype=np.float64)
        T = spectra.shape[0]
        centers = np.asarray(init_freqs, dtype=np.float64).reshape(-1).copy()
        L = centers.shape[0]

        tracked = np.empty((T, L), dtype=np.float64)
        locked = np.zeros((T, L), dtype=bool)
        integral = np.zeros(L, dtype=np.float64)
        prev_err = np.zeros(L, dtype=np.float64)
        velocity = np.zeros(L, dtype=np.float64)

        for t in range(T):
            peaks = self._find_peaks(spectra[t])
            predicted = centers + velocity  # constant-velocity prediction
            assign = self._associate(predicted, peaks)

            new_centers = centers.copy()
            for i in range(L):
                if np.isfinite(assign[i]):
                    err = assign[i] - centers[i]
                    integral[i] += err
                    deriv = err - prev_err[i]
                    step = self.kp * err + self.ki * integral[i] + self.kd * deriv
                    new_centers[i] = centers[i] + step
                    prev_err[i] = err
                    locked[t, i] = True
                else:
                    # Lost lock: coast on last velocity, decay the integrator.
                    new_centers[i] = centers[i] + velocity[i]
                    integral[i] *= 0.5
                    locked[t, i] = False

            velocity = new_centers - centers
            centers = new_centers
            tracked[t] = centers

        pred_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L)).astype(np.int8).copy()
        pred_transition = np.broadcast_to(LINE_TRANSITION_8[:L], (T, L)).astype(np.int8).copy()

        B_est = np.empty((T, 3), dtype=np.float64)
        if L == N_LINES_ELECTRONIC:
            for t in range(T):
                # Splitting-based BLUE (common-mode-robust): a swapped line in the wrong axis
                # pair corrupts that pair's splitting → vector error.
                B_est[t] = blue_invert_field(tracked[t], gamma_hz_per_t=self.gamma).b_hat
        else:
            B_est[:] = np.nan  # BLUE convenience path is defined for the 8-line electronic set

        return ClassicalTrackResult(
            tracked_freqs=tracked.astype(np.float32),
            pred_axis=pred_axis,
            pred_transition=pred_transition,
            locked=locked,
            B_est=B_est.astype(np.float32),
        )
