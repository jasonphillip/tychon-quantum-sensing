"""E3: free Lorentzian centers, exact spin-one inversion, and BLUE vector decode.

The axis inversion adapts the E=0 formulas in nvtools 1.0.0
``nvtools/solver.py::Solver.field_from_resonances`` (MIT), using trace and
determinant invariants for numerical stability and this repository's constants.
No dependency installation or change to nvtools global constants is needed.
Nonzero E with unknown azimuth is explicitly unsupported: two frequencies do
not identify polar angle in that Hamiltonian. No hyperfine model is claimed.

Copyright (c) 2024 Dennis Lönard

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

from itertools import permutations, product
import numpy as np
from scipy.optimize import least_squares

from odmr_vector_tracking.tracking.acquisition import (
    TrackState, acquire_centers_with_diagnostics, axis_transitions_hz,
)
from odmr_vector_tracking.vector.blue import blue_project
from odmr_vector_tracking.vector.geometry import GAMMA_E_HZ_PER_T, NV_AXES_UNIT, ZFS_D_HZ


def invert_axis(f_plus: float, f_minus: float, D: float = ZFS_D_HZ,
                E: float = 0., gamma: float = GAMMA_E_HZ_PER_T) -> tuple[float, float]:
    """Return (magnitude in T, absolute polar cosine) for E=0, Hz inputs.

    The two transitions originate at the lowest eigenvalue. This is valid in
    the registered millitesla regime, not beyond the ground-state crossing.
    A nonzero transverse strain needs azimuth information absent from this API.
    Unphysical pairs raise ValueError; they are not silently projected to valid data.
    """
    if not np.isfinite([f_plus, f_minus, D, E, gamma]).all():
        raise ValueError("finite frequencies and constants required")
    if min(f_plus, f_minus, D, gamma) <= 0:
        raise ValueError("positive frequencies, D, and gamma required")
    if E != 0:
        raise ValueError("nonzero E requires transverse azimuth information; unsupported")
    # Long double protects the small invariant relative to the GHz zero-field scale.
    lo, hi = sorted([np.longdouble(f_plus) / D, np.longdouble(f_minus) / D])
    e0 = (2 - lo - hi) / 3
    eigenvalues = np.array([e0, e0 + lo, e0 + hi], dtype=np.longdouble)
    b2 = (np.sum(eigenvalues**2) - 2) / 2
    if b2 <= 0:
        raise ValueError("frequency pair has nonpositive inferred field magnitude")
    # det(H)/D^3 = -(gamma*B_perp/D)^2 when E=0.
    cosine2 = 1 + np.prod(eigenvalues) / b2
    if cosine2 < -1e-8 or cosine2 > 1 + 1e-8:
        raise ValueError("frequency pair is inconsistent with the E=0 Hamiltonian")
    return float(np.sqrt(b2) * D / gamma), float(np.sqrt(np.clip(cosine2, 0, 1)))


class ExactInversionTracker:
    """Cold-acquired eight-line fit with continuity and explicit sign ambiguity.

    A calibrated bias selects one branch, while ``ambiguous`` continues to
    disclose spectrally indistinguishable candidates. Without that prior,
    step_from_frequencies returns candidates but no guessed field estimate.
    ``locked`` means a fit/physics-consistent estimate, not truth-based vector lock.
    """
    def __init__(self, frequencies, *, linewidth_Hz, bias_field_t=None,
                 D=ZFS_D_HZ, E=0., gamma=GAMMA_E_HZ_PER_T,
                 max_nfev=100, max_step_lw=6.):
        self.freqs = np.asarray(frequencies, dtype=float).reshape(-1)
        if self.freqs.size < 5 or not np.isfinite(self.freqs).all() or np.any(np.diff(self.freqs) <= 0):
            raise ValueError("finite increasing frequency grid required")
        if linewidth_Hz <= 0 or E != 0:
            raise ValueError("positive linewidth and E=0 required; nonzero E needs azimuth")
        self.linewidth_Hz = float(linewidth_Hz)
        self.D, self.gamma = float(D), float(gamma)
        self.bias = None if bias_field_t is None else np.asarray(bias_field_t, dtype=float).reshape(3).copy()
        if self.bias is not None and (not np.isfinite(self.bias).all() or np.linalg.norm(self.bias) == 0):
            raise ValueError("bias_field_t must be finite and nonzero")
        self.max_nfev = int(max_nfev)
        self.max_step = float(max_step_lw) * self.linewidth_Hz / 1e6
        self.grid = (self.freqs - self.D) / 1e6
        self.halfwidth = self.linewidth_Hz / 2e6
        self.slope_grid = (self.grid - self.grid.mean()) / np.ptp(self.grid)
        self._parameters = None
        self._previous_centers = None
        self._previous_field = None
        self.acquisition_diagnostics = None

    def _associate_fitted_centers(self, centers):
        """Resolve spectral pairs/axis permutation using invariants and the public prior.

        The four lower and four upper lines are paired by agreement of the
        independently inverted field magnitude. For the best valid pairing,
        enumerate all 24 axis assignments and 16 projection signs. Retain
        candidates reproducing every line within one linewidth, then use the
        last estimate (or bias) to choose a branch. The sign ambiguity remains
        disclosed. This is association after a free line fit, not a rigid-B fit.
        """
        prior = self._previous_field if self._previous_field is not None else self.bias
        if prior is None:
            return None
        ordered = np.sort(centers)
        best = None
        for upper_order in permutations(range(4)):
            pairs = np.column_stack([ordered[:4], ordered[4:][list(upper_order)]])
            try:
                values = np.array([invert_axis(hi, lo, self.D, 0., self.gamma) for lo, hi in pairs])
            except ValueError:
                continue
            spread = float(np.std(values[:, 0]))
            if best is None or spread < best[0]:
                best = spread, pairs, values[:, 0] * values[:, 1]
        if best is None:
            return None
        _, pairs, absolute_projections = best
        winner, winner_distance = None, float("inf")
        for axis_order in permutations(range(4)):
            assigned_pairs = pairs[list(axis_order)]
            for signs in product((-1., 1.), repeat=4):
                field = blue_project(absolute_projections[list(axis_order)] * signs, NV_AXES_UNIT).b_hat
                if np.max(np.abs(axis_transitions_hz(field, D=self.D, gamma=self.gamma)-assigned_pairs)) > self.linewidth_Hz:
                    continue
                distance = float(np.linalg.norm(field-prior))
                if distance < winner_distance:
                    winner_distance = distance
                    positive = NV_AXES_UNIT @ field >= 0
                    winner = np.where(positive[:, None], assigned_pairs[:, ::-1], assigned_pairs).reshape(8)
        return winner

    def _failure(self, centers=None, residual=float("nan"), fit_success=False):
        return TrackState(np.full(3, np.nan), np.full(8, np.nan) if centers is None else centers,
                          False, False, residual, fit_success=fit_success)

    def step_from_frequencies(self, f_plus, f_minus):
        plus = np.asarray(f_plus, dtype=float).reshape(4)
        minus = np.asarray(f_minus, dtype=float).reshape(4)
        centers = np.column_stack([plus, minus]).reshape(8)
        try:
            magnitudes, cosines = np.array([invert_axis(p, m, self.D, 0., self.gamma)
                                            for p, m in zip(plus, minus)]).T
        except ValueError:
            return self._failure(centers, fit_success=True)
        projections = magnitudes * cosines
        observed = np.sort(np.column_stack([plus, minus]), axis=1)
        candidates, errors = [], []
        for signs in product((-1., 1.), repeat=4):
            field = blue_project(projections * signs, NV_AXES_UNIT).b_hat
            predicted = axis_transitions_hz(field, D=self.D, gamma=self.gamma)
            error = float(np.max(np.abs(predicted - observed)))
            if error <= self.linewidth_Hz:
                if not any(np.linalg.norm(field - previous) < 1e-10 for previous in candidates):
                    candidates.append(field)
                    errors.append(error)
        candidates = np.asarray(candidates).reshape(-1, 3)
        if len(candidates) == 0:
            return self._failure(centers, fit_success=True)
        ambiguous = len(candidates) > 1
        prior = self._previous_field if self._previous_field is not None else self.bias
        if prior is None and ambiguous:
            return TrackState(np.full(3, np.nan), centers, False, True,
                              min(errors), candidates)
        chosen = 0 if prior is None else int(np.argmin(np.linalg.norm(candidates - prior, axis=1)))
        field = candidates[chosen].copy()
        self._previous_field = field
        return TrackState(field, centers, True, ambiguous, errors[chosen], candidates)

    def _model_and_jacobian(self, parameters):
        centers, depths = parameters[:8], parameters[8:16]
        delta = self.grid[:, None] - centers
        denominator = delta**2 + self.halfwidth**2
        lorentzian = self.halfwidth**2 / denominator
        model = parameters[16] + parameters[17] * self.slope_grid - lorentzian @ depths
        jacobian = np.empty((self.grid.size, 18))
        jacobian[:, :8] = -2 * depths * self.halfwidth**2 * delta / denominator**2
        jacobian[:, 8:16] = -lorentzian
        jacobian[:, 16] = 1
        jacobian[:, 17] = self.slope_grid
        return model, jacobian

    def step(self, frame):
        frame = np.asarray(frame, dtype=float).reshape(-1)
        if frame.shape != self.freqs.shape or not np.isfinite(frame).all():
            return self._failure()
        if self._parameters is None:
            try:
                centers, self.acquisition_diagnostics = acquire_centers_with_diagnostics(
                    frame, self.freqs, linewidth_Hz=self.linewidth_Hz,
                    bias_field_t=self.bias, D=self.D, gamma=self.gamma)
            except ValueError:
                return self._failure()
            indices = np.argmin(abs(self.freqs[:, None] - centers), axis=0)
            baseline = float(np.percentile(frame, 95))
            depths = np.maximum(baseline - frame[indices], 1e-5)
            initial = np.r_[(centers - self.D) / 1e6, depths, baseline, 0.]
        else:
            initial = self._parameters.copy()
            initial[:8] += self._parameters[:8] - self._previous_centers
        depth_max = max(10 * float(np.ptp(frame)), .1)
        low = np.r_[np.maximum(initial[:8] - self.max_step, self.grid[0]),
                    np.zeros(8), np.min(frame) - .1, -.2]
        high = np.r_[np.minimum(initial[:8] + self.max_step, self.grid[-1]),
                     np.full(8, depth_max), np.max(frame) + .1, .2]
        if np.any(low >= high):
            self._parameters = None
            return self._failure()
        initial = np.clip(initial, low + 1e-12, high - 1e-12)
        solution = least_squares(lambda p: self._model_and_jacobian(p)[0] - frame,
                                 initial, jac=lambda p: self._model_and_jacobian(p)[1],
                                 bounds=(low, high), x_scale="jac", max_nfev=self.max_nfev,
                                 ftol=1e-9, xtol=1e-9, gtol=1e-9)
        self._previous_centers = initial[:8].copy() if self._parameters is None else self._parameters[:8].copy()
        self._parameters = solution.x
        centers = self.D + solution.x[:8] * 1e6
        if not solution.success:
            return self._failure(centers, float(np.sqrt(np.mean(solution.fun**2))))
        # Acquisition returns seeds, not guaranteed canonical identities. Repair
        # association at the first fit, or if the maintained pairing becomes invalid.
        initial_association = self._previous_field is None
        prior_before_decode = self._previous_field
        state = self.step_from_frequencies(centers[::2], centers[1::2])
        if initial_association or not state.locked:
            self._previous_field = prior_before_decode
            associated = self._associate_fitted_centers(centers)
            if associated is not None:
                # Reorder fit centers/depths together; reset velocity after reassociation.
                from scipy.optimize import linear_sum_assignment
                rows, columns = linear_sum_assignment(abs(associated[:, None]-centers[None, :]))
                order = columns[np.argsort(rows)]
                self._parameters[:8] = self._parameters[:8][order]
                self._parameters[8:16] = self._parameters[8:16][order]
                self._previous_centers = self._parameters[:8].copy()
                centers = associated
                state = self.step_from_frequencies(centers[::2], centers[1::2])
            elif state.locked:
                self._previous_field = state.B_est.copy()
        return TrackState(state.B_est, centers, state.locked, state.ambiguous,
                          float(np.sqrt(np.mean(solution.fun**2))), state.candidates, True)
