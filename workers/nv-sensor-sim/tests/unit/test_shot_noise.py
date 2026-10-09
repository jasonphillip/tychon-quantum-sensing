"""Unit tests for the consumer-side photon shot-noise model."""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.physics.shot_noise import (
    apply_shot_noise,
    photons_for_dip_snr,
    shot_noise_sigma,
)


class TestShotNoiseSigma:
    def test_baseline_scaling(self):
        # S = 1 -> sigma = 1/sqrt(N)
        sigma = shot_noise_sigma(np.ones(8), 1.0e6)
        np.testing.assert_allclose(sigma, 1.0e-3)

    def test_signal_dependence_and_shape(self):
        spec = np.array([[1.0, 0.25], [0.0, 4.0]])
        sigma = shot_noise_sigma(spec, 100.0)
        np.testing.assert_allclose(sigma, np.sqrt(spec / 100.0))
        assert sigma.shape == spec.shape

    def test_negative_values_clipped(self):
        sigma = shot_noise_sigma(np.array([-0.5, 1.0]), 100.0)
        assert sigma[0] == 0.0

    def test_invalid_budget_rejected(self):
        with pytest.raises(ValueError, match="photons_per_point"):
            shot_noise_sigma(np.ones(4), 0.0)


class TestApplyShotNoise:
    def test_seeded_reproducibility(self):
        spec = 1.0 - 0.03 * np.exp(-(np.linspace(-3, 3, 101) ** 2))
        a = apply_shot_noise(spec, 1e5, seed=42)
        b = apply_shot_noise(spec, 1e5, seed=42)
        np.testing.assert_array_equal(a, b)
        c = apply_shot_noise(spec, 1e5, seed=43)
        assert not np.allclose(a, c)

    def test_gaussian_residual_statistics(self):
        spec = np.ones(200_000)
        noisy = apply_shot_noise(spec, 1e4, seed=0)
        resid = noisy - spec
        assert abs(resid.mean()) < 5e-5
        np.testing.assert_allclose(resid.std(), 1.0 / np.sqrt(1e4), rtol=0.02)

    def test_poisson_mode_statistics_and_quantization(self):
        n = 1000.0
        spec = np.full(200_000, 0.97)
        noisy = apply_shot_noise(spec, n, seed=1, exact_poisson=True)
        # Counts / N: quantized to multiples of 1/N, unbiased, std ~ sqrt(S/N).
        np.testing.assert_allclose(noisy * n, np.round(noisy * n), atol=1e-9)
        np.testing.assert_allclose(noisy.mean(), 0.97, rtol=1e-3)
        np.testing.assert_allclose(noisy.std(), np.sqrt(0.97 / n), rtol=0.02)

    def test_generator_instance_accepted(self):
        rng = np.random.default_rng(7)
        spec = np.ones((4, 16))
        out = apply_shot_noise(spec, 1e4, seed=rng)
        assert out.shape == spec.shape

    def test_invalid_budget_rejected(self):
        with pytest.raises(ValueError, match="photons_per_point"):
            apply_shot_noise(np.ones(4), -1.0, seed=0)


class TestPhotonsForDipSnr:
    def test_roundtrip_snr(self):
        depth, snr = 0.0012, 5.0  # faintest v1 axis depth, target SNR 5
        n = photons_for_dip_snr(depth, snr)
        sigma_baseline = shot_noise_sigma(np.ones(1), n)[0]
        np.testing.assert_allclose(depth / sigma_baseline, snr, rtol=1e-12)

    def test_scaling(self):
        # Halving the depth requires 4x the photons.
        assert photons_for_dip_snr(0.001, 5.0) == pytest.approx(
            4.0 * photons_for_dip_snr(0.002, 5.0)
        )

    def test_invalid_args_rejected(self):
        with pytest.raises(ValueError, match="dip_depth"):
            photons_for_dip_snr(0.0, 5.0)
        with pytest.raises(ValueError, match="snr"):
            photons_for_dip_snr(0.001, 0.0)
