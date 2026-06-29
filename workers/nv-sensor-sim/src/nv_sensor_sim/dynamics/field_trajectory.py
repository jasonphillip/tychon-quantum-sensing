"""Lab-frame magnetic field trajectories B(t) for time-series ODMR.

A trajectory is a static bias plus a swept external field. The sweep is designed
to drag resonances from different NV axes across each other in frequency space so
a tracker can be trained/evaluated on holding per-axis identity through the
crossing. Fields are kept in the honest regime (a few mT to ~tens of mT, below
ESLAC ~51 mT) where the 8 lines are resolved and the first-order Zeeman geometry
holds.

The static bias is set from the path-agnostic bias config (``bias_B0_T``,
``bias_direction_uvw``) shared with the static vector pipeline; the lab-frame
bias vector is ``bias_B0_T * normalize(bias_direction_uvw)`` (the repo convention
aligns the diamond crystal [uvw] axes with lab xyz).
"""

from __future__ import annotations

import numpy as np


def static_bias_vector(
    bias_B0_T: float,
    bias_direction_uvw: tuple[float, float, float] | np.ndarray,
) -> np.ndarray:
    """Lab-frame static bias vector ``bias_B0_T * normalize(uvw)`` in Tesla.

    Parameters
    ----------
    bias_B0_T : float
        Bias-field magnitude in Tesla.
    bias_direction_uvw : tuple[float, float, float] or np.ndarray
        Bias direction in crystal [uvw] (== lab xyz under the repo convention).
        Need not be normalized.

    Returns
    -------
    np.ndarray
        Lab-frame bias 3-vector in Tesla. Zero vector if ``bias_B0_T == 0``.
    """
    direction = np.asarray(bias_direction_uvw, dtype=float).reshape(3)
    norm = np.linalg.norm(direction)
    if norm == 0.0 or bias_B0_T == 0.0:
        return np.zeros(3)
    return bias_B0_T * direction / norm


def ramp_crossing_trajectory(
    bias_T: np.ndarray,
    ramp_start_T: tuple[float, float, float] | np.ndarray,
    ramp_end_T: tuple[float, float, float] | np.ndarray,
    n_timesteps: int,
    *,
    seed: int | None = None,
    jitter_frac: float = 0.0,
) -> np.ndarray:
    """Linear ramp of an external field added to a static bias.

    ``B(t) = bias + lerp(ramp_start, ramp_end, t / (T - 1))``. With ``jitter_frac``
    > 0 the ramp endpoints are perturbed per-sequence (seeded) so a dataset of
    sequences varies while still sweeping through a crossing. Choose
    ``ramp_start``/``ramp_end`` so a target axis pair's lines move toward and
    through each other near mid-sequence (see ``configs/sequence_sanity_v0.yaml``).

    Parameters
    ----------
    bias_T : np.ndarray
        Static bias 3-vector in Tesla (lab frame).
    ramp_start_T, ramp_end_T : tuple[float, float, float] or np.ndarray
        External-field 3-vectors (Tesla) at the first and last frame.
    n_timesteps : int
        Number of frames T (>= 2).
    seed : int, optional
        Seed for per-sequence endpoint jitter. None disables jitter.
    jitter_frac : float
        Fractional Gaussian perturbation of each endpoint (relative to its norm).
        Default 0.0 (deterministic nominal trajectory).

    Returns
    -------
    np.ndarray
        Field trajectory of shape (n_timesteps, 3) in Tesla.
    """
    if n_timesteps < 2:
        raise ValueError(f"n_timesteps must be >= 2, got {n_timesteps}")

    bias = np.asarray(bias_T, dtype=float).reshape(3)
    start = np.asarray(ramp_start_T, dtype=float).reshape(3)
    end = np.asarray(ramp_end_T, dtype=float).reshape(3)

    if jitter_frac > 0.0 and seed is not None:
        rng = np.random.default_rng(seed)
        start = start + jitter_frac * np.linalg.norm(start) * rng.standard_normal(3)
        end = end + jitter_frac * np.linalg.norm(end) * rng.standard_normal(3)

    frac = np.linspace(0.0, 1.0, n_timesteps)[:, None]  # (T, 1)
    external = start[None, :] * (1.0 - frac) + end[None, :] * frac  # (T, 3)
    return bias[None, :] + external


def orbit_trajectory(*args, **kwargs) -> np.ndarray:
    """Orbit-driven B(t) from ``orbits.trajectory`` (planned).

    The ``orbits`` package already produces a per-step lab/payload-frame B(t) on a
    uniform dt grid (``build_trajectory_batch`` -> ``B_payload_{x,y,z}``); wiring
    those columns in as a field trajectory is a future increment.
    """
    raise NotImplementedError(
        "Orbit-driven field trajectories are not yet wired in. Use "
        "ramp_crossing_trajectory; orbits.trajectory.build_trajectory_batch "
        "provides B(t) columns to adapt here later."
    )
