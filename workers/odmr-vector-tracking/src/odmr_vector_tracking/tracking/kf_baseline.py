"""Competent classical baseline: per-line constant-velocity Kalman + Hungarian assignment.

Textbook global-nearest-neighbor tracking — CV state ``[f, fdot]`` per line, gated one-to-one
assignment of detected peaks by ``scipy.optimize.linear_sum_assignment``, predict-coast when a
line's peak is missing (merged peaks at a crossing). This is the baseline a competent
classical implementation would actually field, and the one the learned tracker must be
compared against (the original Increment-1 PID bar was retracted 2026-07-01: its detector
threshold exceeded the real dip depth, so it scored a tracker that never received a
measurement — see ``auto_peak_min_depth``).

Adapted from the TVW design-review reference implementation
(``tvw/audits/evidence-2026-07-01/kf_hungarian_baseline.py``); untuned defaults from the
review: ``sigma_accel = 0.05 Γ/frame²``, ``R = (Γ/5)²``, gate ``8 Γ``. Reuses
:class:`ClassicalTracker`'s peak detector so PID/KF comparisons share detection; callers must
pass a data-scaled ``peak_min_depth`` (use :func:`auto_peak_min_depth`).

Output mirrors :class:`ClassicalTrackResult`, so it drops into the shared evaluation rows.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from odmr_vector_tracking.tracking.classical import ClassicalTracker, ClassicalTrackResult
from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.vector.geometry import (
    LINE_AXIS_8,
    LINE_TRANSITION_8,
    N_LINES_ELECTRONIC,
)

_BIG = 1e18


class KFHungarianTracker:
    """Per-line CV Kalman filter + global Hungarian peak assignment (GNN tracking).

    Parameters
    ----------
    frequencies
        ``(F,)`` MW frequency axis (Hz).
    linewidth_Hz
        Resonance FWHM Γ (Hz) — sets the noise/gate scales.
    peak_min_depth
        Detection threshold in normalized-PL depth units. **Required** — pass
        :func:`~odmr_vector_tracking.tracking.classical.auto_peak_min_depth` of the sequence
        being tracked; an absolute default is exactly the retracted-bar failure mode.
    q_accel_frac
        Process-noise acceleration σ as a fraction of Γ per frame².
    gate_lw
        Assignment gate in linewidths (innovation beyond this is not assignable).
    """

    def __init__(
        self,
        frequencies: np.ndarray,
        *,
        linewidth_Hz: float,
        peak_min_depth: float,
        q_accel_frac: float = 0.05,
        gate_lw: float = 8.0,
    ) -> None:
        self.lw = float(linewidth_Hz)
        self._detector = ClassicalTracker(
            frequencies, linewidth_Hz=linewidth_Hz, peak_min_depth=peak_min_depth
        )
        self.F = np.array([[1.0, 1.0], [0.0, 1.0]])
        sa = q_accel_frac * self.lw
        self.Q = sa**2 * np.array([[0.25, 0.5], [0.5, 1.0]])
        self.R = (self.lw / 5.0) ** 2
        self.gate = gate_lw * self.lw
        self.H = np.array([[1.0, 0.0]])

    def run(self, spectra: np.ndarray, init_freqs: np.ndarray) -> ClassicalTrackResult:
        """Track all L lines through a ``(T, F)`` series from ``(L,)`` initial centers."""
        spectra = np.asarray(spectra, dtype=np.float64)
        T = spectra.shape[0]
        init = np.asarray(init_freqs, dtype=np.float64).reshape(-1)
        L = init.shape[0]

        x = np.zeros((L, 2))
        x[:, 0] = init
        P = np.tile(np.diag([self.R, (0.5 * self.lw) ** 2]), (L, 1, 1))
        tracked = np.empty((T, L))
        locked = np.zeros((T, L), dtype=bool)

        for t in range(T):
            for i in range(L):  # predict
                x[i] = self.F @ x[i]
                P[i] = self.F @ P[i] @ self.F.T + self.Q
            peaks = self._detector._find_peaks(spectra[t])
            M = peaks.shape[0]
            if M:
                cost = np.abs(x[:, 0][:, None] - peaks[None, :])
                cost_g = np.where(cost <= self.gate, cost, _BIG)
                n = max(L, M)
                sq = np.full((n, n), _BIG * 10.0)
                sq[:L, :M] = cost_g
                ri, ci = linear_sum_assignment(sq)
                for i, j in zip(ri, ci):
                    if i < L and j < M and sq[i, j] < _BIG:
                        z = peaks[j]  # KF update
                        S = P[i][0, 0] + self.R
                        K = P[i] @ self.H.T / S  # (2, 1)
                        x[i] = x[i] + K[:, 0] * (z - x[i][0])
                        P[i] = (np.eye(2) - K @ self.H) @ P[i]
                        locked[t, i] = True
            tracked[t] = x[:, 0]

        pred_axis = np.broadcast_to(LINE_AXIS_8[:L], (T, L)).astype(np.int8).copy()
        pred_transition = np.broadcast_to(LINE_TRANSITION_8[:L], (T, L)).astype(np.int8).copy()
        B_est = np.empty((T, 3))
        if L == N_LINES_ELECTRONIC:
            for t in range(T):
                B_est[t] = blue_invert_field(tracked[t]).b_hat
        else:
            B_est[:] = np.nan

        return ClassicalTrackResult(
            tracked_freqs=tracked.astype(np.float32),
            pred_axis=pred_axis,
            pred_transition=pred_transition,
            locked=locked,
            B_est=B_est.astype(np.float32),
        )
