"""Unit tests for published noise parameters and OU process statistics."""

from __future__ import annotations

import numpy as np
import pytest


def test_thermal_drift_coefficient():
    """dD/dT should be -74.2 kHz/K."""
    from tychon_nv_sim.physics.parameters import ThermalDriftParams

    params = ThermalDriftParams()
    assert params.dD_dT_Hz_per_K == pytest.approx(-74.2e3)


def test_p1_bath_ranges():
    """P1 bath delta should be 1-7 MHz, tau_c 5-50 µs."""
    from tychon_nv_sim.physics.parameters import P1BathParams

    params = P1BathParams()
    assert params.delta_range_Hz == (1e6, 7e6)
    assert params.tau_c_range_s == (5e-6, 50e-6)


def test_ou_process_statistics():
    """OU trajectory should have correct mean and bounded variance."""
    from tychon_nv_sim.physics.noise_injection import ou_process

    theta, mu, sigma = 1.0, 5.0, 0.5
    dt = 0.001
    n_steps = 100_000

    traj = ou_process(theta, mu, sigma, dt, n_steps, seed=42)

    # Mean should converge to mu
    assert np.abs(np.mean(traj) - mu) < 0.1

    # Stationary variance = sigma^2 / (2*theta)
    expected_var = sigma**2 / (2 * theta)
    actual_var = np.var(traj)
    assert np.abs(actual_var - expected_var) < 0.05


def test_asymmetry_param_ranges():
    """B1 gradient should be 5-30%, B_perp 0-50 µT."""
    from tychon_nv_sim.physics.parameters import AsymmetryParams

    params = AsymmetryParams()
    assert params.b1_gradient_range == (0.05, 0.30)
    assert params.b_perp_range_T == (0.0, 50e-6)


def test_temperature_zfs_shift():
    """ZFS shift function should match dD/dT coefficient."""
    from tychon_nv_sim.physics.hamiltonian import temperature_zfs_shift

    # At 301K (1K above reference), shift should be dD/dT * 1K in rad/s
    shift = temperature_zfs_shift(301.0, reference_T=300.0)
    expected = 2 * np.pi * (-74.2e3) * 1.0  # rad/s
    assert shift == pytest.approx(expected, rel=1e-10)

    # At reference temperature, shift should be zero
    assert temperature_zfs_shift(300.0) == pytest.approx(0.0)
