"""Inverse-θ importance sampler (P3-12, fix-list Limitation 2).

The current upstream sampler draws B-vectors uniformly on the sphere,
which gives a ``sin(θ)`` prior in the polar angle θ. That under-samples
the poles (θ near 0 or π) where the v2 monolithic FCNN is empirically
observed to over-correct. This sampler reweights training samples by
``1 / sin(θ)`` (with a stability floor) so that drawing from the
weighted distribution yields a θ-marginal that is uniform on [0, π].

Returns weights normalized to mean=1 so ``WeightedRandomSampler``'s
``num_samples`` = dataset length keeps the per-epoch sample count
unchanged.
"""

from __future__ import annotations

import numpy as np

from odmr_edge_ml.sampling.theta_utils import polar_theta_from_labels


def inverse_theta_weights(
    labels: np.ndarray, eps: float = 1e-2,
) -> np.ndarray:
    """Compute per-sample importance weights ∝ 1 / max(sin(θ), eps).

    Parameters
    ----------
    labels
        ``(N, 3)`` array of B-field vectors (units irrelevant).
    eps
        Stability floor. ``sin(θ)`` → 0 at the poles; without a floor a
        single near-pole sample would dominate the entire epoch. The
        default ``eps=1e-2`` caps the per-sample weight at ~100× the
        median.

    Returns
    -------
    np.ndarray
        ``(N,)`` non-negative float64 weights, normalized to mean=1.
    """
    if eps <= 0:
        raise ValueError(f"eps must be > 0, got {eps}")
    theta = polar_theta_from_labels(labels)
    sin_theta = np.maximum(np.sin(theta), eps)
    w = 1.0 / sin_theta
    # Normalize so mean=1; keeps WeightedRandomSampler's num_samples
    # interpretation stable across configurations.
    w *= len(w) / w.sum()
    return w.astype(np.float64)
