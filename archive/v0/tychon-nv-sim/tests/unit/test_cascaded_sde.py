"""Unit tests for cascaded causal SDE T(t) -> B1(t) model."""

from __future__ import annotations

import numpy as np
import pytest

from tychon_nv_sim.config import OUNoiseConfig
from tychon_nv_sim.physics.noise_injection import sample_ou_trajectory_pair


@pytest.fixture()
def cascaded_config():
    """SBQuantum-derived cascaded SDE configuration."""
    return OUNoiseConfig(
        theta_T=1.0e-3,
        sigma_T=0.05,
        theta_B1=10.0,
        sigma_B1=0.006,
        trajectory_dt_s=1.0,
        alpha_B1=-0.0035,
        T_mean_C=20.0,
        delta_T_orb_C=15.0,
        tau_orb_s=5400.0,
        B1_nominal=1.0,
    )


class TestCascadedSDEStatistics:
    """Statistical tests for cascaded SDE trajectories."""

    def test_negative_cross_correlation(self, cascaded_config):
        """T and B1 should be negatively correlated (alpha_B1 < 0)."""
        T_traj, B1_traj = sample_ou_trajectory_pair(
            cascaded_config, n_samples=50_000, seed=42
        )
        corr = np.corrcoef(T_traj, B1_traj)[0, 1]
        assert corr < -0.1, f"Expected negative T-B1 correlation, got {corr:.4f}"

    def test_temperature_mean_near_T_mean(self, cascaded_config):
        """Long-run T mean should be near T_mean_K = 293.15 K."""
        T_traj, _ = sample_ou_trajectory_pair(
            cascaded_config, n_samples=50_000, seed=42
        )
        T_mean_K = cascaded_config.T_mean_C + 273.15
        assert abs(np.mean(T_traj) - T_mean_K) < 5.0

    def test_b1_mean_near_nominal(self, cascaded_config):
        """Long-run B1 mean should be near B1_nominal = 1.0."""
        _, B1_traj = sample_ou_trajectory_pair(
            cascaded_config, n_samples=50_000, seed=42
        )
        assert abs(np.mean(B1_traj) - cascaded_config.B1_nominal) < 0.05

    def test_temperature_tracks_orbital_baseline(self, cascaded_config):
        """T(t) should oscillate with period tau_orb (dominant FFT peak)."""
        n_samples = 10800  # 2 full orbits at dt=1s
        T_traj, _ = sample_ou_trajectory_pair(
            cascaded_config, n_samples=n_samples, seed=42
        )
        freqs = np.fft.rfftfreq(n_samples, d=cascaded_config.trajectory_dt_s)
        spectrum = np.abs(np.fft.rfft(T_traj - np.mean(T_traj)))
        peak_idx = np.argmax(spectrum[1:]) + 1  # skip DC
        peak_freq = freqs[peak_idx]
        expected_freq = 1.0 / cascaded_config.tau_orb_s
        # Allow ±2 frequency bins of tolerance
        assert abs(peak_freq - expected_freq) < 2 * (freqs[1] - freqs[0])

    def test_all_values_positive(self, cascaded_config):
        """Both T and B1 should remain positive after clipping."""
        T_traj, B1_traj = sample_ou_trajectory_pair(
            cascaded_config, n_samples=10_000, seed=42
        )
        assert np.all(T_traj > 0)
        assert np.all(B1_traj > 0)

    def test_legacy_mode_independent(self):
        """alpha_B1=0.0 should produce independent trajectories (~0 correlation)."""
        config = OUNoiseConfig(
            theta_T=0.1, mu_T=300.0, sigma_T=0.5,
            theta_B1=1.0, mu_B1=1.0, sigma_B1=0.05,
            alpha_B1=0.0,
        )
        T_traj, B1_traj = sample_ou_trajectory_pair(
            config, n_samples=50_000, seed=42
        )
        corr = np.corrcoef(T_traj, B1_traj)[0, 1]
        assert abs(corr) < 0.05, (
            f"Expected ~0 correlation in legacy mode, got {corr:.4f}"
        )

    def test_reproducibility(self, cascaded_config):
        """Same seed should produce identical trajectories."""
        T1, B1_1 = sample_ou_trajectory_pair(cascaded_config, 100, seed=999)
        T2, B1_2 = sample_ou_trajectory_pair(cascaded_config, 100, seed=999)
        np.testing.assert_array_equal(T1, T2)
        np.testing.assert_array_equal(B1_1, B1_2)
