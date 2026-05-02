"""Polar angle θ utilities — single source of truth.

Consolidates the ``polar_theta`` definition from
``experiments/orientation_binned_comparison.py:79`` so the bias-aware
samplers (inverse-θ, ephemeris) and the polar-bias regression test
agree on the angle convention.

Convention: θ = arccos(B_z / ||B||), in [0, π]. θ=0 is +z (north pole),
θ=π is -z (south pole), θ=π/2 is the equator.
"""

from __future__ import annotations

import numpy as np


def polar_theta_from_labels(labels: np.ndarray) -> np.ndarray:
    """Compute polar angle θ from a batch of B-vector labels.

    Parameters
    ----------
    labels
        ``(N, 3)`` array of B-field vectors. Units don't matter — only
        the direction is used.

    Returns
    -------
    np.ndarray
        ``(N,)`` array of θ values in radians, in ``[0, π]``.
    """
    if labels.ndim != 2 or labels.shape[1] != 3:
        raise ValueError(
            f"labels must be (N, 3); got shape {labels.shape}"
        )
    bmag = np.linalg.norm(labels, axis=1)
    bz = labels[:, 2]
    cos_theta = bz / np.where(bmag == 0, 1.0, bmag)
    return np.arccos(np.clip(cos_theta, -1.0, 1.0))
