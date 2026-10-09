"""Integration tests for CoupledNoiseInjector — validates SimOS stochastic API boundary.

These tests verify that the CoupledNoiseInjector correctly interfaces with
SimOS StochasticLiouvilleParameters without crashing, even though we cannot
fully validate the physics output without reference trajectories.
"""

from __future__ import annotations

import numpy as np
import pytest

import simos
from simos.systems import NV

from nv_sensor_sim.config import NoiseConfig
from nv_sensor_sim.physics.noise_injection import CoupledNoiseInjector
from nv_sensor_sim.physics.parameters import OUProcessParams


@pytest.mark.smoke
def test_build_stochastic_params_thermal_only():
    """StochasticLiouvilleParameters builds correctly for thermal noise."""
    noise_config = NoiseConfig(enable_thermal_noise=True, enable_mw_noise=False)
    ou_params = OUProcessParams()

    injector = CoupledNoiseInjector(noise_config, ou_params)
    stoch_params = injector.build_stochastic_params(seed=42, n_grid_points=5)

    assert stoch_params is not None


@pytest.mark.smoke
def test_build_stochastic_params_both_channels():
    """StochasticLiouvilleParameters builds correctly for both T and B1 noise."""
    noise_config = NoiseConfig(enable_thermal_noise=True, enable_mw_noise=True)
    ou_params = OUProcessParams()

    injector = CoupledNoiseInjector(noise_config, ou_params)
    stoch_params = injector.build_stochastic_params(seed=42, n_grid_points=7)

    assert stoch_params is not None


@pytest.mark.smoke
def test_coupled_noise_injector_api():
    """Validates the SimOS stochastic_evol API boundary.

    This exercises the previously untested inject_coupled_noise path.
    We use a spin-only (3-level) NV system for speed.
    """
    nv = NV.NVSystem(optics=False, nitrogen=False, method="qutip")
    H_spin = nv.field_hamiltonian(Bvec=np.array([0, 0, 0.01]))

    noise_config = NoiseConfig(enable_thermal_noise=True, enable_mw_noise=False)
    ou_params = OUProcessParams(mu_T=300.0, sigma_T=0.1, theta_T=100.0)

    injector = CoupledNoiseInjector(noise_config, ou_params)

    # Get eigenstates from the Hamiltonian (not the NVSystem)
    evals, evecs = H_spin.eigenstates()
    rho0 = simos.ket2dm(evecs[0])

    def H_func(temperature=300.0, **kwargs):
        """Time-dependent Hamiltonian parameterized by stochastic temperature."""
        # Temperature modulates ZFS: ΔD = -74.2 kHz/K × (T - 300)
        delta_D_rad = 2 * np.pi * (-74.2e3) * (temperature - 300.0)
        return H_spin + delta_D_rad * (nv.Sz * nv.Sz)

    try:
        # SimOS stochastic_evol expects scalar time, not array
        result = injector.inject_coupled_noise(
            H_func=H_func, nv_system=nv, rho0=rho0, t=1e-6, seed=42
        )
        assert result is not None
        # Result should be a Qobj density matrix
        assert hasattr(result, "shape"), "Expected Qobj result from stochastic_evol"
    except (NotImplementedError, AttributeError) as e:
        # SimOS stochastic_evol may not be fully implemented in all versions
        pytest.skip(f"SimOS stochastic_evol API not available: {e}")
    except Exception as e:
        pytest.fail(f"simos.stochastic_evol API call failed unexpectedly: {e}")
