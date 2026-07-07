"""Geometry helpers for the v3 widened field-coverage envelope.

These are pure, render-free functions used by the widened-isotropic and directed
merge-crossing samplers to reason about a candidate trajectory's angular reach,
its field-magnitude floor, and whether its resonances stay inside the pinned MW
window — the three quantities the per-frame envelope guards act on.

The off-bias angle is the angle between the total lab field ``B(t)`` and the
static bias direction; widening it is the whole point of v3 (increment-5 found a
deterministic acquisition failure beyond the ~18 deg v1/v2 cone). ``min |B|`` is
enforced as a hard floor so the widened scalar range does not bleed below the
3.0 mT regime the field-cone eval probes below. ``line_offset_estimate_hz``
reproduces the analytic first + second-order half-window model the pipeline uses
to size the MW window (``pipelines/sequence_generate.py``), applied to a single
field vector so a guard can accept/reject a geometry without a full render.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.physics.lineshape import project_field_onto_axes


def offbias_angle_deg(B_traj: np.ndarray, bias_dir: np.ndarray) -> np.ndarray:
    """Per-frame angle (degrees) between ``B_traj[t]`` and the bias direction.

    Parameters
    ----------
    B_traj : np.ndarray
        Lab-frame field trajectory, shape ``(T, 3)`` in Tesla.
    bias_dir : np.ndarray
        Bias direction 3-vector (need not be normalized).

    Returns
    -------
    np.ndarray
        Off-bias angle per frame, shape ``(T,)``, in degrees. Frames with a
        numerically zero field return 0.0 (undefined direction).
    """
    B = np.asarray(B_traj, dtype=float).reshape(-1, 3)
    b_hat = np.asarray(bias_dir, dtype=float).reshape(3)
    b_norm = np.linalg.norm(b_hat)
    if b_norm == 0.0:
        raise ValueError("bias_dir must be non-zero")
    b_hat = b_hat / b_norm
    mags = np.linalg.norm(B, axis=1)
    safe = mags > 0.0
    cos = np.zeros(B.shape[0])
    cos[safe] = np.clip((B[safe] @ b_hat) / mags[safe], -1.0, 1.0)
    ang = np.zeros(B.shape[0])
    ang[safe] = np.degrees(np.arccos(cos[safe]))
    return ang


def min_field_magnitude_T(B_traj: np.ndarray) -> float:
    """Minimum ``|B(t)|`` over a trajectory, in Tesla.

    Parameters
    ----------
    B_traj : np.ndarray
        Lab-frame field trajectory, shape ``(T, 3)`` in Tesla.

    Returns
    -------
    float
        ``min_t |B_traj[t]|``.
    """
    B = np.asarray(B_traj, dtype=float).reshape(-1, 3)
    return float(np.linalg.norm(B, axis=1).min())


def line_offset_estimate_hz(
    B_lab_T: np.ndarray,
    nv_axes: np.ndarray,
    D_hz: float,
    gamma_hz_per_T: float,
) -> float:
    """Analytic max ``|line_center - D|`` (Hz) at a single field vector.

    First-order Zeeman split plus the second-order transverse common-mode shift,
    matching the half-window model in ``pipelines/sequence_generate.py`` (there
    ``first_order = gamma * max|B.n_i|`` and ``second_order =
    1.5 * (gamma * max B_perp)^2 / D``). Applied per field vector so a guard can
    decide window containment without diagonalizing.

    Parameters
    ----------
    B_lab_T : np.ndarray
        Lab-frame field 3-vector in Tesla.
    nv_axes : np.ndarray
        NV-axis unit vectors, shape ``(4, 3)``.
    D_hz : float
        Zero-field splitting (Hz), the window center.
    gamma_hz_per_T : float
        Electron gyromagnetic ratio in Hz/T.

    Returns
    -------
    float
        Estimated maximum absolute line-center offset from ``D`` in Hz.
    """
    b_par, b_perp = project_field_onto_axes(np.asarray(B_lab_T, dtype=float), nv_axes=nv_axes)
    first_order = gamma_hz_per_T * float(np.max(np.abs(b_par)))
    second_order = 1.5 * (gamma_hz_per_T * float(np.max(b_perp))) ** 2 / D_hz
    return first_order + second_order


__all__ = ["offbias_angle_deg", "min_field_magnitude_T", "line_offset_estimate_hz"]
