"""Unit tests for BLUE (Best Linear Unbiased Estimator) vector projection.

Covers the 8x3 NV-axis projection geometry and the closed-form weighted
least-squares recovery
``B_hat = (A^T Σ^-1 A)^-1 A^T Σ^-1 δ``
used to fold 8 scalar per-resonance ΔB residuals into a single lab-frame
B-field vector.
"""

from __future__ import annotations

import numpy as np
import pytest
import pytest

from odmr_edge_ml.vector.blue_projection import (
    BluePosteriorVariance,
    blue_project,
    nv_axis_geometry_matrix,
)


# ---------------------------------------------------------------------------
# Geometry


def test_A_has_shape_8x3() -> None:
    A = nv_axis_geometry_matrix()
    assert A.shape == (8, 3)


def test_A_rows_are_unit_norm() -> None:
    A = nv_axis_geometry_matrix()
    norms = np.linalg.norm(A, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-12)


def test_A_sign_pairs_are_negatives() -> None:
    """Row 2i and row 2i+1 are ±n_i — they sum to zero."""
    A = nv_axis_geometry_matrix()
    for i in range(4):
        assert np.allclose(A[2 * i] + A[2 * i + 1], 0.0, atol=1e-12)


def test_A_rank_is_3() -> None:
    """8 rows but only 3 independent directions (4 axes × 2 signs)."""
    A = nv_axis_geometry_matrix()
    assert np.linalg.matrix_rank(A) == 3


def test_A_matches_nv_sensor_sim_canonical() -> None:
    """The geometry MUST agree with nv_sensor_sim.physics.lineshape.

    nv_sensor_sim is the canonical source for the NV-axis geometry; a
    drift between repos would silently corrupt the BLUE inversion.
    """
    import os
    import sys

    sim_src = os.environ.get(
        "NV_SENSOR_SIM_SRC",
        os.path.expanduser("~/projects/nv-sensor-sim/src"),
    )
    sys.path.insert(0, sim_src)
    try:
        from nv_sensor_sim.physics.lineshape import nv_geometry_matrix  # type: ignore
    except ImportError:
        pytest.skip("nv-sensor-sim source not available (set NV_SENSOR_SIM_SRC)")

    A_local = nv_axis_geometry_matrix()
    A_sim = nv_geometry_matrix()
    assert np.allclose(A_local, A_sim, atol=1e-12)


# ---------------------------------------------------------------------------
# BLUE inversion — noiseless


def test_blue_noiseless_identity_recovers_truth() -> None:
    """δ = A B_true, Σ = I  →  B_hat = B_true to machine precision."""
    rng = np.random.default_rng(0)
    A = nv_axis_geometry_matrix()
    for _ in range(10):
        b_true = rng.standard_normal(3) * 50e-6  # ~50 µT-scale field
        delta = A @ b_true
        b_hat = blue_project(delta, A, sigma=None).b_hat
        assert np.allclose(b_hat, b_true, atol=1e-12)


def test_blue_noiseless_diagonal_sigma_recovers_truth() -> None:
    """Σ = diag(σ_i^2) with all finite positive — same exact recovery."""
    rng = np.random.default_rng(1)
    A = nv_axis_geometry_matrix()
    sigma = rng.uniform(0.5, 2.0, size=8)
    b_true = np.array([1e-5, -2e-5, 3e-5])
    delta = A @ b_true
    b_hat = blue_project(delta, A, sigma=sigma).b_hat
    assert np.allclose(b_hat, b_true, atol=1e-12)


# ---------------------------------------------------------------------------
# BLUE inversion — noisy


def test_blue_noisy_unbiased_in_the_mean() -> None:
    """Averaging many noisy estimates converges to truth — the definition of
    'unbiased' in BLUE."""
    rng = np.random.default_rng(42)
    A = nv_axis_geometry_matrix()
    b_true = np.array([2.5e-5, -1.0e-5, 0.8e-5])  # ~28 µT magnitude
    noise_std = 1e-7  # 100 nT per-resonance noise — small vs signal
    n_runs = 5000

    estimates = np.zeros((n_runs, 3))
    for i in range(n_runs):
        delta = A @ b_true + rng.normal(0.0, noise_std, size=8)
        estimates[i] = blue_project(delta, A, sigma=None).b_hat

    mean = estimates.mean(axis=0)
    # standard error of mean ~ noise_std / sqrt(n_runs) * sensitivity
    assert np.allclose(mean, b_true, atol=1e-8)


def test_blue_weights_inverse_variance() -> None:
    """A single resonance with much smaller σ should dominate the answer.

    Heuristic: as σ_i → 0 on a single index, that row becomes a hard
    constraint and the recovered B should satisfy that row exactly.
    """
    A = nv_axis_geometry_matrix()
    b_true = np.array([1e-5, 1e-5, 1e-5])
    delta = A @ b_true
    # Corrupt all rows by a big amount, except row 0 which is exact
    delta_bad = delta + 1e-3  # 1 mT-scale corruption everywhere
    delta_bad[0] = delta[0]
    sigma = np.full(8, 1.0)
    sigma[0] = 1e-12  # row 0 is the gospel
    out = blue_project(delta_bad, A, sigma=sigma)
    # Row 0 constraint should be satisfied to high precision
    assert np.isclose(A[0] @ out.b_hat, delta[0], atol=1e-9)


# ---------------------------------------------------------------------------
# BLUE posterior variance


def test_blue_posterior_variance_shape_and_psd() -> None:
    """(A^T Σ^-1 A)^-1 is a 3x3 PSD matrix."""
    A = nv_axis_geometry_matrix()
    sigma = np.full(8, 1.0)
    delta = np.zeros(8)
    out = blue_project(delta, A, sigma=sigma)
    cov = out.posterior_covariance
    assert cov.shape == (3, 3)
    # PSD: symmetric and all eigenvalues >= 0
    assert np.allclose(cov, cov.T, atol=1e-12)
    eigs = np.linalg.eigvalsh(cov)
    assert (eigs >= -1e-12).all()


def test_blue_posterior_variance_decreases_with_lower_noise() -> None:
    """Smaller per-resonance σ → smaller posterior covariance trace."""
    A = nv_axis_geometry_matrix()
    delta = np.zeros(8)
    out_loose = blue_project(delta, A, sigma=np.full(8, 1.0))
    out_tight = blue_project(delta, A, sigma=np.full(8, 0.1))
    assert np.trace(out_tight.posterior_covariance) < np.trace(out_loose.posterior_covariance)


# ---------------------------------------------------------------------------
# Input validation


def test_blue_rejects_wrong_delta_length() -> None:
    A = nv_axis_geometry_matrix()
    with pytest.raises(ValueError, match="delta"):
        blue_project(np.zeros(7), A, sigma=None)


def test_blue_rejects_wrong_sigma_length() -> None:
    A = nv_axis_geometry_matrix()
    with pytest.raises(ValueError, match="sigma"):
        blue_project(np.zeros(8), A, sigma=np.zeros(7))


def test_blue_rejects_nonpositive_sigma() -> None:
    A = nv_axis_geometry_matrix()
    bad = np.ones(8)
    bad[3] = 0.0
    with pytest.raises(ValueError, match="positive"):
        blue_project(np.zeros(8), A, sigma=bad)


def test_blue_result_dataclass_carries_arrays() -> None:
    """Quick smoke that BluePosteriorVariance can be unpacked normally."""
    A = nv_axis_geometry_matrix()
    out = blue_project(np.zeros(8), A, sigma=None)
    assert isinstance(out, BluePosteriorVariance)
    assert out.b_hat.shape == (3,)
    assert out.posterior_covariance.shape == (3, 3)
