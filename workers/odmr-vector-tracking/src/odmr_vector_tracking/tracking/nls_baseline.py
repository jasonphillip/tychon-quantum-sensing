"""Published NLS baseline and opt-in repairs with shared cold acquisition.

The legacy path accepts explicit initial centers and fits every frame against an 8-line model:

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

Historical runs supplied true t=0 centers. Explicit seeds with all repairs off preserve that
published fitting loop. Omitting seeds instead invokes the shared frame-zero detector, using
the supplied calibrated bias; development comparisons never supply truth centers.
Missing-width estimation uses a first-ten-frame calibration buffer, not an immediate streaming
estimate. Manifest-width evaluations do not use that lookahead. Repair flags default off.
Physics constants stay upstream: Gamma comes from the ``nv-sensor-sim`` manifest, geometry
from the parity-tested vendored module.
"""

from __future__ import annotations

import numpy as np
import time
from scipy.optimize import least_squares, linear_sum_assignment
from scipy.signal import find_peaks, peak_widths
from scipy.special import voigt_profile

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
    multi_start
        Try three fits around the closest merged pair; canonicalize by continuity and
        select by residual. Equal unresolved line identities remain ambiguous.
    profile
        ``lorentzian`` (default) or ``voigt`` with fixed ``voigt_sigma_ratio``.
    estimate_linewidth
        Estimate an absent linewidth from isolated dips in the first ten frames.
        A supplied manifest linewidth is never refit by this option.
    bias_field_t
        Calibrated bias for shared cold acquisition when ``run`` receives no initial centers.
    """

    def __init__(
        self,
        frequencies: np.ndarray,
        *,
        linewidth_Hz: float | None = None,
        line_depths: np.ndarray | list[float] | None = None,
        max_nfev: int = 200,
        max_step_lw: float = 6.0,
        depth_floor_frac: float = 0.25,
        multi_start: bool = False,
        profile: str = "lorentzian",
        estimate_linewidth: bool = False,
        voigt_sigma_ratio: float = 0.15,
        bias_field_t: np.ndarray | None = None,
    ) -> None:
        self.freqs = np.asarray(frequencies, dtype=np.float64).reshape(-1)
        if (len(self.freqs) < 3 or not np.isfinite(self.freqs).all()
                or np.any(np.diff(self.freqs) <= 0)):
            raise ValueError("frequencies must be finite, strictly increasing, and have >=3 bins")
        if linewidth_Hz is None and not estimate_linewidth:
            raise ValueError("missing linewidth requires estimate_linewidth=True")
        if linewidth_Hz is not None and (not np.isfinite(linewidth_Hz) or linewidth_Hz <= 0):
            raise ValueError("linewidth_Hz must be finite and positive")
        if profile not in {"lorentzian", "voigt"}:
            raise ValueError("profile must be lorentzian or voigt")
        if not np.isfinite(voigt_sigma_ratio) or voigt_sigma_ratio < 0:
            raise ValueError("voigt_sigma_ratio must be finite and nonnegative")
        if max_nfev <= 0 or max_step_lw <= 0 or not 0 <= depth_floor_frac < 1:
            raise ValueError("invalid optimizer bound or depth floor")
        self._missing_linewidth = linewidth_Hz is None
        self.multi_start = bool(multi_start)
        self.profile = profile
        self.estimate_linewidth = bool(estimate_linewidth)
        self.voigt_sigma_ratio = float(voigt_sigma_ratio)
        self.bias_field_t = bias_field_t
        self.max_step_lw = float(max_step_lw)
        self.linewidth_Hz_ = (float(linewidth_Hz) if linewidth_Hz is not None
                              else 4 * float(np.median(np.diff(self.freqs))))
        self.diagnostics_: dict = {}
        self.f0 = float(self.freqs[0])
        self.span = float(self.freqs[-1] - self.freqs[0])
        self.hwhm_n = 0.5 * self.linewidth_Hz_ / self.span   # HWHM in window units
        self.line_depths = (
            np.asarray(line_depths, dtype=np.float64) if line_depths is not None else None
        )
        self.max_nfev = int(max_nfev)
        self.max_step_n = float(max_step_lw) * self.linewidth_Hz_ / self.span
        self.depth_floor_frac = float(depth_floor_frac)
        self._grid_n = (self.freqs - self.f0) / self.span      # (F,) in [0, 1]

    # --- model -------------------------------------------------------------------------

    def _model(self, centers_n: np.ndarray, depths: np.ndarray) -> np.ndarray:
        """``PL(f)`` for centers (window units) + depths. Vectorized over the F grid."""
        d2 = (self._grid_n[:, None] - centers_n[None, :]) ** 2          # (F, L)
        if self.profile == "lorentzian" or self.voigt_sigma_ratio == 0:
            lor = self.hwhm_n**2 / (d2 + self.hwhm_n**2)                # (F, L)
        else:
            sigma = self.voigt_sigma_ratio * 2 * self.hwhm_n
            lor = voigt_profile(self._grid_n[:, None] - centers_n[None, :],
                                sigma, self.hwhm_n)
            lor /= voigt_profile(0, sigma, self.hwhm_n)
        return 1.0 - lor @ depths

    def _residual(self, x: np.ndarray, spectrum: np.ndarray, L: int) -> np.ndarray:
        return self._model(x[:L], x[L:]) - spectrum

    # --- main loop ---------------------------------------------------------------------

    def _run_legacy(self, spectra: np.ndarray, init_freqs: np.ndarray) -> ClassicalTrackResult:
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

    def _estimate_width(self, spectra: np.ndarray) -> float:
        """Median isolated-dip FWHM from at most ten initial frames; no label access."""
        widths = []
        for spectrum in spectra[:10]:
            dip = np.percentile(spectrum, 95) - spectrum
            prominence = max(float(np.ptp(dip)) * .05, 1e-8)
            peaks, props = find_peaks(dip, prominence=prominence, distance=3)
            if not len(peaks):
                continue
            estimates, _, left, right = peak_widths(dip, peaks, rel_height=.5)
            for i, (peak, bins, lo, hi) in enumerate(zip(peaks, estimates, left, right)):
                others = np.delete(peaks, i)
                isolated = not len(others) or np.min(np.abs(others - peak)) > 2 * bins
                if isolated and bins >= 1.5 and lo > 0 and hi < len(self.freqs) - 1:
                    width = np.interp(hi, np.arange(len(self.freqs)), self.freqs)
                    width -= np.interp(lo, np.arange(len(self.freqs)), self.freqs)
                    widths.append(float(width))
        if not widths:
            raise ValueError("cannot estimate linewidth: no isolated resolved dip in first ten frames")
        self.diagnostics_["linewidth_width_samples"] = len(widths)
        return float(np.median(widths))

    def run(self, spectra: np.ndarray, init_freqs: np.ndarray | None = None) -> ClassicalTrackResult:
        """Run with explicit legacy seeds, or shared cold acquisition when seeds are omitted.

        All repairs default OFF. Explicit seeds then use the unchanged published loop.
        Multistart explores both orderings of the closest merged pair. The lowest spectrum
        residual wins; numerical ties use the retained velocity and nominal-depth history.
        Equal-depth unresolved identities remain unidentifiable, even with multistart.
        """
        started = time.perf_counter()
        spectra = np.asarray(spectra, dtype=np.float64)
        if spectra.ndim != 2 or spectra.shape[1] != len(self.freqs) or not len(spectra):
            raise ValueError("spectra must have shape (T,F), T>0")
        if not np.isfinite(spectra).all():
            raise ValueError("spectra must be finite")
        self.diagnostics_ = {"linewidth_estimation_frames": 0}
        if self._missing_linewidth:
            self.linewidth_Hz_ = self._estimate_width(spectra)
            self.hwhm_n = .5 * self.linewidth_Hz_ / self.span
            self.max_step_n = self.max_step_lw * self.linewidth_Hz_ / self.span
            self.diagnostics_["linewidth_estimation_frames"] = min(10, len(spectra))
        if init_freqs is None:
            from odmr_vector_tracking.tracking.acquisition import acquire_centers_with_diagnostics
            init_freqs, acquisition = acquire_centers_with_diagnostics(
                spectra[0], self.freqs, linewidth_Hz=self.linewidth_Hz_,
                bias_field_t=self.bias_field_t)
            self.diagnostics_["acquisition"] = acquisition
        if not self.multi_start and self.profile == "lorentzian" and not self.estimate_linewidth:
            return self._run_legacy(spectra, init_freqs)
        init = np.asarray(init_freqs, dtype=float).reshape(-1)
        if not np.isfinite(init).all() or not len(init):
            raise ValueError("initial centers must be finite and nonempty")
        L, T = len(init), len(spectra)
        centers = (init - self.f0) / self.span
        if self.line_depths is not None and self.line_depths.shape == (L,):
            depths = self.line_depths.copy()
            d_lo = self.depth_floor_frac * self.line_depths
        else:
            idx = np.clip(np.round(centers * (len(self.freqs)-1)).astype(int), 0, len(self.freqs)-1)
            depths = np.clip(1 - spectra[0, idx], 1e-5, None)
            d_lo = np.zeros(L)
        d_hi = max(5 * float(depths.max()), 1e-3)
        nominal_depths = depths.copy()
        x = np.r_[centers, depths]
        previous = centers.copy()
        retained_velocity = np.zeros(L)
        tracked = np.empty((T,L))
        fields = np.full((T,3), np.nan)
        residuals, starts_used, selected, elapsed, converged = [], [], [], [], []
        previous_close = False
        for t, spectrum in enumerate(spectra):
            frame_start = time.perf_counter()
            velocity = x[:L] - previous
            distance = np.abs(x[:L,None] - x[None,:L])
            np.fill_diagonal(distance, np.inf)
            close = bool(np.min(distance) < 2 * self.linewidth_Hz_ / self.span) if L > 1 else False
            if not close:
                retained_velocity = velocity.copy()
            previous = x[:L].copy()
            x0 = np.r_[x[:L] + velocity, x[L:]]
            lo = np.r_[x0[:L] - self.max_step_n, d_lo]
            hi = np.r_[x0[:L] + self.max_step_n, np.full(L,d_hi)]
            candidates = [x0.copy()]
            if self.multi_start and L > 1 and (close or previous_close):
                a,b = np.unravel_index(np.argmin(distance), distance.shape)
                midpoint = (x0[a]+x0[b])/2
                separation = max(self.linewidth_Hz_ / self.span, abs(x0[a]-x0[b]))
                direction = np.sign(retained_velocity[a]-retained_velocity[b]) or 1
                for sign in (direction, -direction):
                    candidate = x0.copy()
                    candidate[a] = midpoint + sign * separation/2
                    candidate[b] = midpoint - sign * separation/2
                    candidates.append(candidate)
            solutions = [least_squares(self._residual, np.clip(candidate, lo, hi),
                         args=(spectrum,L), bounds=(lo,hi), method="trf", x_scale="jac",
                         max_nfev=self.max_nfev) for candidate in candidates]
            # A sum of line profiles is invariant to a joint center/depth permutation.
            # Residual alone therefore cannot identify slots. Canonicalize every candidate
            # against the same velocity/depth history before comparing its residual.
            prediction = previous + (retained_velocity if close else velocity)
            if self.multi_start and len(candidates) > 1:
                for solution in solutions:
                    motion = ((prediction[:,None] - solution.x[None,:L]) / (2*self.hwhm_n))**2
                    depth_cost = np.log(np.maximum(x[L:,None],1e-8)
                                        / np.maximum(solution.x[None,L:],1e-8))**2
                    _,order = linear_sum_assignment(motion + .1*depth_cost)
                    reordered = np.r_[solution.x[:L][order],solution.x[L:][order]]
                    if np.all(reordered[L:] >= d_lo):
                        solution.x = reordered
            costs = np.array([float(np.dot(sol.fun,sol.fun)) for sol in solutions])
            minimum = costs.min()
            ties = np.flatnonzero(costs <= minimum + max(1e-16, minimum * 1e-6))
            def continuity(i):
                sol = solutions[i]
                motion = np.sum(((sol.x[:L] - prediction) / (2*self.hwhm_n))**2)
                depth = np.sum(((sol.x[L:] - nominal_depths) / np.maximum(nominal_depths,1e-5))**2)
                return motion + depth
            chosen = min(ties, key=continuity)
            solution = solutions[chosen]
            x = solution.x
            tracked[t] = self.f0 + x[:L] * self.span
            if L == N_LINES_ELECTRONIC:
                fields[t] = blue_invert_field(tracked[t]).b_hat
            residuals.append(float(np.sqrt(costs[chosen]/len(spectrum))))
            starts_used.append(len(candidates)); selected.append(int(chosen))
            converged.append(bool(solution.success))
            elapsed.append(time.perf_counter()-frame_start)
            previous_close = close
        elapsed[0] += max(0, time.perf_counter()-started-sum(elapsed))
        self.diagnostics_.update({"residual_rms":residuals, "starts_attempted":starts_used,
            "selected_start":selected, "optimizer_converged":converged,
            "frame_seconds":elapsed, "linewidth_Hz":self.linewidth_Hz_, "profile":self.profile})
        return ClassicalTrackResult(
            tracked_freqs=tracked.astype(np.float32),
            pred_axis=np.broadcast_to(LINE_AXIS_8[:L], (T,L)).astype(np.int8).copy(),
            pred_transition=np.broadcast_to(LINE_TRANSITION_8[:L], (T,L)).astype(np.int8).copy(),
            locked=np.ones((T,L),dtype=bool), B_est=fields.astype(np.float32))
