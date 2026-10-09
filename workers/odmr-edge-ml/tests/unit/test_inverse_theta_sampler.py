"""Unit tests for the inverse-θ importance sampler."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_edge_ml.sampling import inverse_theta_weights
from odmr_edge_ml.sampling.theta_utils import polar_theta_from_labels


def _spherical_uniform_sample(n: int, seed: int) -> np.ndarray:
    """Sample n unit vectors uniform on S^2; gives the sin(θ) prior in θ."""
    rng = np.random.default_rng(seed)
    cos_theta = rng.uniform(-1.0, 1.0, n)
    phi = rng.uniform(0.0, 2.0 * np.pi, n)
    sin_theta = np.sqrt(1.0 - cos_theta * cos_theta)
    return np.stack(
        [sin_theta * np.cos(phi), sin_theta * np.sin(phi), cos_theta], axis=1,
    )


def test_inverse_theta_shape_and_normalization():
    labels = _spherical_uniform_sample(500, seed=0)
    w = inverse_theta_weights(labels)
    assert w.shape == (500,)
    assert (w > 0).all(), "weights must be strictly positive"
    assert np.isclose(w.mean(), 1.0, atol=1e-9), "weights must be mean=1"


def test_inverse_theta_makes_polar_distribution_uniform():
    """Bin θ in [0, π] and check that the *weighted* histogram is more
    uniform than the uniform-prior unweighted histogram. Concretely:
    weighted-bin-density variance < unweighted-bin-density variance."""
    labels = _spherical_uniform_sample(20000, seed=1)
    theta = polar_theta_from_labels(labels)
    w = inverse_theta_weights(labels)

    edges = np.linspace(0.0, np.pi, 11)
    unweighted, _ = np.histogram(theta, bins=edges)
    weighted, _ = np.histogram(theta, bins=edges, weights=w)
    unweighted = unweighted.astype(float) / unweighted.sum()
    weighted = weighted / weighted.sum()
    assert weighted.std() < unweighted.std() * 0.5, (
        f"weighted distribution should be flatter; "
        f"unweighted std={unweighted.std():.4f}, weighted std={weighted.std():.4f}"
    )


def test_inverse_theta_weights_concentrate_near_poles():
    """Pole samples (small sin θ) get larger weights than equator samples."""
    pole_labels = np.array([[1e-3, 0, 1.0], [-1e-3, 0, -1.0]])
    equator_labels = np.array([[1.0, 0, 0], [0, 1.0, 0]])
    labels = np.vstack([pole_labels, equator_labels])
    w = inverse_theta_weights(labels)
    assert (w[:2] > w[2:]).all(), "near-pole samples must outweigh equator"


def test_inverse_theta_eps_floor_prevents_blowup():
    """Exact-pole samples get the eps floor, not infinity."""
    labels = np.array([[0.0, 0.0, 1.0]])  # exact north pole, sin(θ)=0
    w = inverse_theta_weights(labels, eps=1e-2)
    # Single sample, normalized → exactly 1.0; the test is that no NaN/inf arises.
    assert np.isfinite(w).all()
    assert w.shape == (1,)


def test_inverse_theta_rejects_invalid_eps():
    labels = np.array([[1.0, 0, 0]])
    with pytest.raises(ValueError, match="eps"):
        inverse_theta_weights(labels, eps=0)
    with pytest.raises(ValueError, match="eps"):
        inverse_theta_weights(labels, eps=-1.0)


def test_inverse_theta_rejects_bad_label_shape():
    with pytest.raises(ValueError, match="N, 3"):
        inverse_theta_weights(np.zeros((10, 2)))
