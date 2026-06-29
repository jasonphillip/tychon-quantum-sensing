"""Resonance association and collision labelling for time-series ODMR.

The per-frame ODMR spectrum is rendered by SimOS diagonalization (each NV axis
separately, then ensemble-averaged). This module turns those per-axis line
centers into the **ground-truth labels** a vector tracker needs:

- ``resonance_freqs`` — the true (diagonalized) center frequency of every line.
  These are the actual dip positions and include the second-order transverse-field
  shift, so the labels sit exactly on the dips in the rendered spectrum.
- ``line_axis`` / ``line_transition`` — which NV axis (0-3) and which transition
  (0 = ms0->-1, 1 = ms0->+1) each line belongs to. This association is the
  ground truth the tracker must preserve through a crossing; it is recovered from
  the **signed** per-axis projection ``B . n_i`` (the renderer itself only sees
  ``|B . n_i|``, so the sign — i.e. the identity — comes from here).
- ``collision_mask`` / ``line_collision`` — where lines fall within ``k * Gamma``.

Line ordering matches ``nv_geometry_matrix()`` rows: line ``2i`` is ``(axis i,
+n_i)`` (s=+1, ms0->+1); line ``2i+1`` is ``(axis i, -n_i)`` (s=-1, ms0->-1).

Why the centers are diagonalized, not analytic: a transverse field B_perp shifts
both transitions of an axis up by ~``1.5 (gamma B_perp)^2 / D`` (common mode),
which in the few-mT regime is several linewidths. The first-order projection
``D +/- gamma (B . n_i)`` would therefore miss the real dip by many Gamma. The
*split* ``(f+ - f-)/2 = gamma |B . n_i|`` is, however, exact to second order, so
the +/- transition identity is still resolved by the projection sign.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from nv_sensor_sim.physics.hamiltonian import _GAMMA_NV
from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT, project_field_onto_axes

if TYPE_CHECKING:
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter

# NV electronic gyromagnetic ratio magnitude in Hz/T (|gamma|/2pi ~ 28.035 GHz/T).
# Sourced from the same SimOS constant the renderer's Zeeman term uses, so the
# analytic split matches the diagonalized split exactly.
GAMMA_HZ_PER_T = abs(_GAMMA_NV) / (2.0 * np.pi)


def axis_transition_labels(nv_axes: np.ndarray = NV_AXES_UNIT) -> tuple[np.ndarray, np.ndarray]:
    """Return the constant per-line axis and transition id arrays.

    Parameters
    ----------
    nv_axes : np.ndarray
        Unit vectors of the NV axes, shape (n_axes, 3). Defaults to NV_AXES_UNIT.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(line_axis, line_transition)`` int8 arrays of length ``L = 2 * n_axes``.
        ``line_axis[2i] = line_axis[2i+1] = i``; ``line_transition[2i] = 1``
        (ms0->+1), ``line_transition[2i+1] = 0`` (ms0->-1), in geometry-matrix order.
    """
    n_axes = len(nv_axes)
    line_axis = np.repeat(np.arange(n_axes, dtype=np.int8), 2)
    # +n_i row (even) is the ms0->+1 transition (id 1); -n_i row (odd) is ms0->-1 (id 0)
    line_transition = np.tile(np.array([1, 0], dtype=np.int8), n_axes)
    return line_axis, line_transition


def analytic_centers(
    B_lab_T: np.ndarray,
    D_hz: float,
    gamma_hz_per_T: float = GAMMA_HZ_PER_T,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> np.ndarray:
    """First-order resonance centers ``D + s * gamma * (B . n_i)`` (Hz).

    Used for association cross-checks and tests, NOT stored as labels (the stored
    labels are the diagonalized centers, which also carry the second-order shift).

    Parameters
    ----------
    B_lab_T : np.ndarray
        Lab-frame magnetic field 3-vector in Tesla.
    D_hz : float
        Zero-field splitting in Hz.
    gamma_hz_per_T : float
        NV gyromagnetic ratio magnitude in Hz/T.
    nv_axes : np.ndarray
        Unit vectors of the NV axes, shape (n_axes, 3).

    Returns
    -------
    np.ndarray
        Length ``L = 2 * n_axes`` first-order centers, in geometry-matrix order.
    """
    B_par, _ = project_field_onto_axes(B_lab_T, nv_axes=nv_axes)
    centers = np.empty(2 * len(nv_axes), dtype=float)
    for i in range(len(nv_axes)):
        centers[2 * i] = D_hz + gamma_hz_per_T * B_par[i]  # s=+1 (ms0->+1)
        centers[2 * i + 1] = D_hz - gamma_hz_per_T * B_par[i]  # s=-1 (ms0->-1)
    return centers


def associate_axis_centers(
    per_axis_centers: list[np.ndarray],
    B_par: np.ndarray,
) -> np.ndarray:
    """Map per-axis diagonalized line centers into geometry-matrix order.

    For axis ``i`` the diagonalization yields its transitions at
    ``D' -/+ gamma |B . n_i|`` (common-mode shift D' is the same for both, so the
    *order* of the two centers is fixed). The higher center is the ``+gamma|B.n_i|``
    transition, which is the ms0->+1 (s=+1) line iff ``B . n_i >= 0`` and the
    ms0->-1 (s=-1) line otherwise. This recovers the identity the renderer dropped
    by using ``|B . n_i|``.

    Parameters
    ----------
    per_axis_centers : list[np.ndarray]
        For each NV axis, the ascending allowed transition frequencies (Hz) from
        the diagonalization. Normally length 2 per axis (ms0->+/-1).
    B_par : np.ndarray
        Signed per-axis projections ``B . n_i`` in Tesla, length ``n_axes``.

    Returns
    -------
    np.ndarray
        Length ``L = 2 * n_axes`` resonance centers in geometry-matrix order:
        index ``2i`` = (axis i, s=+1), ``2i+1`` = (axis i, s=-1).
    """
    n_axes = len(B_par)
    resonance = np.empty(2 * n_axes, dtype=float)
    for i in range(n_axes):
        c = np.sort(np.asarray(per_axis_centers[i], dtype=float))
        lo, hi = float(c[0]), float(c[-1])
        if B_par[i] >= 0.0:
            resonance[2 * i] = hi  # s=+1 is the higher line
            resonance[2 * i + 1] = lo
        else:
            resonance[2 * i] = lo  # s=+1 is the lower line (B.n_i < 0)
            resonance[2 * i + 1] = hi
    return resonance


def reference_zfs_hz(adapter: SimOSAdapter, temperature_K: float | None = None) -> float:
    """Read the zero-field splitting D (Hz) from a zero-field diagonalization.

    Ties the analytic D used for window centering / cross-checks to the exact ZFS
    SimOS produces (~2.871 GHz), including the temperature shift.

    Parameters
    ----------
    adapter : SimOSAdapter
        Adapter to diagonalize through.
    temperature_K : float, optional
        Temperature in Kelvin. Defaults to the adapter config value.

    Returns
    -------
    float
        Zero-field splitting D in Hz.
    """
    _, _, centers = adapter.generate_odmr_spectrum(
        B_field=np.zeros(3),
        temperature_K=temperature_K,
        return_line_centers=True,
    )
    return float(np.mean(centers))


def collision_labels(
    centers_TL: np.ndarray,
    gamma_fwhm_hz: float,
    k: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Label per-frame line collisions where ``|f_l - f_m| < k * Gamma``.

    Parameters
    ----------
    centers_TL : np.ndarray
        Resonance centers per frame, shape (T, L), in Hz.
    gamma_fwhm_hz : float
        Linewidth Gamma (FWHM) in Hz.
    k : float
        Collision threshold in linewidths.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(collision_mask, line_collision)``: a (T,) bool that is True where any
        two lines are within ``k * Gamma``, and a (T, L) bool flagging which lines
        are within ``k * Gamma`` of at least one other line that frame.
    """
    centers = np.asarray(centers_TL, dtype=float)
    threshold = k * gamma_fwhm_hz
    # Pairwise |f_l - f_m| per frame, self-distance masked out.
    pair = np.abs(centers[:, :, None] - centers[:, None, :])  # (T, L, L)
    n_lines = centers.shape[1]
    eye = np.eye(n_lines, dtype=bool)
    pair[:, eye] = np.inf
    nearest = pair.min(axis=2)  # (T, L) nearest other line
    line_collision = nearest < threshold
    collision_mask = line_collision.any(axis=1)
    return collision_mask, line_collision
