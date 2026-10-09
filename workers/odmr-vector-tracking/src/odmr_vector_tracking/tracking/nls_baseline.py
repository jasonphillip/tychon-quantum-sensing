"""Strongest classical baseline: per-frame warm-started nonlinear least-squares fitting.

Fits every raw spectrum frame against a parametric 8-line model — no detection stage at all:

    PL(f) = 1 - sum_i  d_i * L(f; c_i, Gamma),   L = (G/2)^2 / ((f - c_i)^2 + (G/2)^2)

with the 8 centers ``c_i`` and 8 depths ``d_i`` free per frame and Gamma fixed from the
dataset manifest (``linewidth_rendered_Hz`` when present). The fit is **warm-started from a
constant-velocity extrapolation of the previous solutions** — that continuity IS the data
association (each parameter slot keeps its canonical identity), and merged blobs are handled
natively by lineshape overlap instead of a peak detector. The CV extrapolation matters at
crossing exits: with a static warm start the two merged centers are exchange-degenerate and
the exit assignment is a coin flip (measured on v0: swaps at ~0.67/opportunity, every
sequence eventually lost); velocity memory resolves the exit exactly as it does for the KF.
B̂ decodes from the fitted splittings through the same BLUE path as the other classical
baselines, so the estimation front-end is the only difference in any comparison.

Model choice (vs a direct 3-parameter B-fit through the physics forward model): the fitted
model is deliberately the standard Lorentzian approximation, not a re-run of the upstream
SimOS generator — fitting simulated data with its own exact generator would be an inverse
crime, and a rigid B-parameterization would additionally inherit the first-order/common-mode
model residual (≲0.4 Γ asymmetric) as bias. Free centers keep the front-end assumption-light;
lineshape mismatch (saturation detail) lands in the fit residual exactly as it would on a
real instrument. The rigid-B variant remains a possible follow-up.

GT t=0 initialization (centers = true t=0 lines), like the other classical baselines.
Physics constants stay upstream: Gamma comes from the ``nv-sensor-sim`` manifest, geometry
from the parity-tested vendored module.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from odmr_vector_tracking.tracking.classical import ClassicalTrackResult
from odmr_vector_tracking.vector.blue import blue_invert_field
from odmr_vector_tracking.vector.geometry import (
    LINE_AXIS_8,
    LINE_TRANSITION_8,
    N_LINES_ELECTRONIC,
)


class NLSTracker:
    """Per-frame 8-Lorentzian NLS fit with warm-started continuity association.

    Parameters
    ----------
    frequencies
        ``(F,)`` MW frequency axis (Hz).
    linewidth_Hz
        Lorentzian FWHM used by the model — pass the manifest's ``linewidth_rendered_Hz``
        when present (saturation-broadened), else ``linewidth_Hz``.
    line_depths
        Nominal per-line dip depths for t=0 depth initialization (manifest ``line_depths``);
        if ``None``, depths initialize from the spectrum value at each initial center.
    max_nfev
        Cap on model evaluations per frame (bounds worst-case runtime; warm-started fits
        typically converge in a handful of iterations).
    max_step_lw
        Per-frame center gate: each fitted center may move at most this many linewidths from
        its warm start. Honest tracker tuning, not a fudge — the manifest's measured maximum
        line speed is ~1.4 Γ/frame, so a 6 Γ gate is generous headroom while preventing the
        wandering-center failure (an unconstrained shallow line can otherwise fit to depth≈0
        and drift arbitrarily).
    depth_floor_frac
        Per-line depth lower bound as a fraction of the nominal depth (lines physically
        never vanish; the v1 AR(1) contrast drift stays well above 0.25x nominal). Prevents
        the depth-collapse mode that makes a center meaningless. Only active when
        ``line_depths`` is provided.
    """

    def __init__(
        self,
        frequencies: np.ndarray,
        *,
        linewidth_Hz: float,
        line_depths: np.ndarray | list[float] | None = None,
        max_nfev: int = 200,
        max_step_lw: float = 6.0,
        depth_floor_frac: float = 0.25,
    ) -> None:
        self.freqs = np.asarray(frequencies, dtype=np.float64).reshape(-1)
        self.f0 = float(self.freqs[0])
        self.span = float(self.freqs[-1] - self.freqs[0])
        self.hwhm_n = 0.5 * float(linewidth_Hz) / self.span   # HWHM in window units
        self.line_depths = (
            np.asarray(line_depths, dtype=np.float64) if line_depths is not None else None
        )
        self.max_nfev = int(max_nfev)
        self.max_step_n = float(max_step_lw) * float(linewidth_Hz) / self.span
        self.depth_floor_frac = float(depth_floor_frac)
        self._grid_n = (self.freqs - self.f0) / self.span      # (F,) in [0, 1]

    # --- model -------------------------------------------------------------------------

    def _model(self, centers_n: np.ndarray, depths: np.ndarray) -> np.ndarray:
        """``PL(f)`` for centers (window units) + depths. Vectorized over the F grid."""
        d2 = (self._grid_n[:, None] - centers_n[None, :]) ** 2          # (F, L)
        lor = self.hwhm_n**2 / (d2 + self.hwhm_n**2)                    # (F, L)
        return 1.0 - lor @ depths

    def _residual(self, x: np.ndarray, spectrum: np.ndarray, L: int) -> np.ndarray:
        return self._model(x[:L], x[L:]) - spectrum

    # --- main loop ---------------------------------------------------------------------

    def run(self, spectra: np.ndarray, init_freqs: np.ndarray) -> ClassicalTrackResult:
        """Fit all frames of a ``(T, F)`` series from ``(L,)`` initial centers (Hz)."""
        spectra = np.asarray(spectra, dtype=np.float64)
        T = spectra.shape[0]
        init = np.asarray(init_freqs, dtype=np.float64).reshape(-1)
        L = init.shape[0]

        centers_n = (init - self.f0) / self.span
        if self.line_depths is not None and self.line_depths.shape[0] == L:
            depths = self.line_depths.copy()
        else:
            idx = np.clip(
                np.round(centers_n * (len(self.freqs) - 1)).astype(int), 0, len(self.freqs) - 1
            )
            depths = np.clip(1.0 - spectra[0, idx], 1e-5, None)

        d_hi = max(5.0 * float(depths.max()), 1e-3)
        if self.line_depths is not None and self.line_depths.shape[0] == L:
            d_lo = self.depth_floor_frac * self.line_depths
        else:
            d_lo = np.zeros(L)

        tracked = np.empty((T, L), dtype=np.float64)
        locked = np.ones((T, L), dtype=bool)  # no detection stage; the fit always updates

        x = np.concatenate([centers_n, depths])
        prev_centers = x[:L].copy()
        for t in range(T):
            # Constant-velocity warm start (kinematic memory across merges), gated to
            # +/- max_step around the extrapolation; depths bounded globally.
            vel = x[:L] - prev_centers
            prev_centers = x[:L].copy()
            x0 = np.concatenate([x[:L] + vel, x[L:]])
            lo = np.concatenate([x0[:L] - self.max_step_n, d_lo])
            hi = np.concatenate([x0[:L] + self.max_step_n, np.full(L, d_hi)])
            x0 = np.clip(x0, lo, hi)
            sol = least_squares(
                self._residual,
                x0,
                args=(spectra[t], L),
                bounds=(lo, hi),
                method="trf",
                x_scale="jac",
                max_nfev=self.max_nfev,
            )
            x = sol.x  # solution carries to the next frame = continuity association
            tracked[t] = self.f0 + x[:L] * self.span

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
