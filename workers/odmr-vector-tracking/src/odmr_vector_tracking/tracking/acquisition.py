"""Shared spectrum-only cold acquisition for the registered classical comparators.

The bias is a public calibration prior, not a true per-frame field. Missing detected
minima are filled from that prior and counted. A seed is not an acquired measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.optimize import linear_sum_assignment
from scipy.signal import find_peaks

from odmr_vector_tracking.vector.geometry import GAMMA_E_HZ_PER_T, NV_AXES_UNIT, ZFS_D_HZ


@dataclass(frozen=True)
class TrackState:
    B_est: np.ndarray
    tracked_freqs: np.ndarray
    locked: bool
    ambiguous: bool = False
    residual: float = float("nan")
    candidates: np.ndarray = field(default_factory=lambda: np.empty((0, 3)))
    fit_success: bool = True


def axis_transitions_hz(field_t, *, D=ZFS_D_HZ, gamma=GAMMA_E_HZ_PER_T):
    """Exact E=0 transition pairs (lower, upper); no first-order approximation."""
    field_t = np.asarray(field_t, dtype=float).reshape(3)
    parallel = NV_AXES_UNIT @ field_t
    transverse = np.sqrt(np.maximum(0., field_t @ field_t - parallel**2))
    h = np.zeros((4, 3, 3))
    h[:, 0, 0] = D + gamma * parallel
    h[:, 2, 2] = D - gamma * parallel
    coupling = gamma * transverse / np.sqrt(2)
    h[:, 0, 1] = h[:, 1, 0] = coupling
    h[:, 1, 2] = h[:, 2, 1] = coupling
    eigenvalues = np.linalg.eigvalsh(h)
    return eigenvalues[:, 1:] - eigenvalues[:, :1]


def acquire_centers_with_diagnostics(frame, frequencies, *, linewidth_Hz,
                                     bias_field_t=None, D=ZFS_D_HZ,
                                     gamma=GAMMA_E_HZ_PER_T):
    """Eight canonical (+,-) seeds from minima, assigned using the calibrated bias.

    Detector: Gaussian width 0.15 linewidth; prominence max(3 noise sigma,
    3% observed depth, 1e-8); minimum separation 0.5 linewidth. Noise sigma
    uses the median absolute second difference divided by sqrt(6).
    Hungarian distance to the bias's exact resonances assigns detected minima.
    Unresolved lines retain bias seeds and are explicitly counted.
    """
    frequencies = np.asarray(frequencies, dtype=float).reshape(-1)
    frame = np.asarray(frame, dtype=float).reshape(-1)
    if frame.shape != frequencies.shape or frequencies.size < 5:
        raise ValueError("frame and frequencies must have the same length >=5")
    if not np.all(np.isfinite(frame)) or not np.all(np.isfinite(frequencies)):
        raise ValueError("frame and frequency grid must be finite")
    if linewidth_Hz <= 0 or np.any(np.diff(frequencies) <= 0):
        raise ValueError("positive linewidth and increasing frequency grid required")
    if bias_field_t is None:
        raise ValueError("axis assignment requires a calibrated bias_field_t")
    bias = np.asarray(bias_field_t, dtype=float).reshape(3)
    if not np.isfinite(bias).all() or np.linalg.norm(bias) == 0:
        raise ValueError("bias_field_t must be finite and nonzero")
    pairs = axis_transitions_hz(bias, D=D, gamma=gamma)
    signs = NV_AXES_UNIT @ bias >= 0
    seeds = np.where(signs[:, None], pairs[:, ::-1], pairs).reshape(8)
    spacing = float(np.median(np.diff(frequencies)))
    smooth = gaussian_filter1d(frame, max(.5, .15 * linewidth_Hz / spacing))
    second = np.diff(frame, n=2)
    sigma = float(np.median(np.abs(second - np.median(second))) / (.67448975 * np.sqrt(6)))
    prominence = max(3 * sigma, .03 * float(np.ptp(smooth)), 1e-8)
    indices, props = find_peaks(-smooth, prominence=prominence,
                               distance=max(1, int(.5 * linewidth_Hz / spacing)))
    n_detected = len(indices)
    if len(indices) > 8:
        indices = indices[np.argsort(props['prominences'])[-8:]]
    if len(indices):
        observed = frequencies[indices]
        rows, columns = linear_sum_assignment(abs(seeds[:, None] - observed[None, :]))
        seeds[rows] = observed[columns]
    else:
        rows = []
    return seeds, dict(n_detected=n_detected, n_assigned=len(rows),
                       n_bias_fills=8-len(rows), noise_sigma=sigma,
                       prominence=prominence, assignment="nearest calibrated-bias resonances")


def acquire_centers(frame, frequencies, **kwargs):
    return acquire_centers_with_diagnostics(frame, frequencies, **kwargs)[0]
