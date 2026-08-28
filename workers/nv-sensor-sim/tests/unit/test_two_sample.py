"""Unit tests for two-sample generator-validation statistics.

Synthetic-only: all data is drawn in-test from closed-form Gaussian
mixtures, with no dataset/adapter dependency, so this stays fast and
independent of the modules owned elsewhere (datasets/, adapters/).
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.validation.two_sample import (
    compare_spectra_sets,
    ks_max_per_bin,
    mmd_rbf,
    permutation_pvalue,
    sliced_wasserstein,
)

N_SAMPLES = 40
N_FEATURES = 16
N_PERMUTATIONS = 99
SEED = 12345


def _draw_mixture(
    n_samples: int,
    n_features: int,
    rng: np.random.Generator,
    mean_shift: float = 0.0,
) -> np.ndarray:
    """Two-component isotropic Gaussian-mixture spectra in R^n_features.

    Component means are offset +-1.5 along feature 0 (shared std 1.0);
    ``mean_shift`` (in units of the shared std) uniformly translates every
    feature of every draw, used to build a mean-shifted alternative sample.
    """
    sigma = 1.0
    component_offset = 1.5
    component = rng.integers(0, 2, size=n_samples)
    means = np.zeros((n_samples, n_features))
    means[component == 0, 0] = -component_offset
    means[component == 1, 0] = component_offset
    means += mean_shift * sigma
    return means + sigma * rng.standard_normal((n_samples, n_features))


class TestSameDistribution:
    """Two independent draws from the identical mixture should look alike."""

    def test_p_values_not_significant(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng)

        result = compare_spectra_sets(X, Y, n_permutations=N_PERMUTATIONS, rng=SEED)

        assert result["sliced_wasserstein"]["p_value"] > 0.05
        assert result["mmd_rbf"]["p_value"] > 0.05
        assert result["ks_max_per_bin"]["p_value"] > 0.05


class TestShiftedDistribution:
    """A 3-sigma mean shift should be caught by every statistic."""

    def test_p_values_significant(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=3.0)

        result = compare_spectra_sets(X, Y, n_permutations=N_PERMUTATIONS, rng=SEED)

        assert result["sliced_wasserstein"]["p_value"] <= 0.01
        assert result["mmd_rbf"]["p_value"] <= 0.01
        assert result["ks_max_per_bin"]["p_value"] <= 0.01

    def test_sliced_wasserstein_self_comparison_is_exact_zero(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        assert sliced_wasserstein(X, X, rng=0) == 0.0


class TestDeterminism:
    def test_same_seed_identical_compare_spectra_sets_output(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=1.0)

        result_a = compare_spectra_sets(X, Y, n_permutations=30, rng=999)
        result_b = compare_spectra_sets(X, Y, n_permutations=30, rng=999)

        assert result_a == result_b

    def test_same_seed_identical_sliced_wasserstein(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=0.5)

        a = sliced_wasserstein(X, Y, n_projections=32, rng=7)
        b = sliced_wasserstein(X, Y, n_projections=32, rng=7)
        assert a == b


class TestDegenerateGuard:
    """Every public entry point must reject <2-sample groups clearly."""

    def test_single_sample_raises_value_error(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(1, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng)

        with pytest.raises(ValueError, match="at least 2 samples"):
            compare_spectra_sets(X, Y, n_permutations=10, rng=0)

        with pytest.raises(ValueError, match="at least 2 samples"):
            sliced_wasserstein(X, Y)

        with pytest.raises(ValueError, match="at least 2 samples"):
            mmd_rbf(X, Y)

        with pytest.raises(ValueError, match="at least 2 samples"):
            ks_max_per_bin(X, Y)

        with pytest.raises(ValueError, match="at least 2 samples"):
            permutation_pvalue(lambda a, b: 0.0, X, Y)

    def test_mismatched_features_raises_value_error(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES + 1, rng)

        with pytest.raises(ValueError, match="frequency grid"):
            compare_spectra_sets(X, Y)


class TestLowLevelApiShapes:
    """Structural sanity checks on the individual statistics' return shapes."""

    def test_ks_max_per_bin_bounds(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=2.0)

        stat, argmax_bin = ks_max_per_bin(X, Y)
        assert isinstance(argmax_bin, int)
        assert 0 <= argmax_bin < N_FEATURES
        assert 0.0 <= stat <= 1.0

    def test_permutation_pvalue_bounds(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=2.0)

        observed, p_value = permutation_pvalue(mmd_rbf, X, Y, n_permutations=N_PERMUTATIONS, rng=1)
        assert isinstance(observed, float)
        assert 0.0 < p_value <= 1.0

    def test_mmd_rbf_explicit_bandwidth(self):
        rng = np.random.default_rng(SEED)
        X = _draw_mixture(N_SAMPLES, N_FEATURES, rng)
        Y = _draw_mixture(N_SAMPLES, N_FEATURES, rng, mean_shift=2.0)

        value = mmd_rbf(X, Y, bandwidth=2.5)
        assert np.isfinite(value)
