"""Coupled stochastic noise injection via Ornstein-Uhlenbeck processes.

Implements the critical v4 change: noise is injected AT THE HAMILTONIAN LEVEL,
not as post-processing. Temperature T(t) and MW amplitude B1(t) are modeled as
Ornstein-Uhlenbeck stochastic processes and injected into the SimOS
time-dependent Hamiltonian via StochasticLiouvilleParameters.

References
----------
- SimOS stochastic framework: fokker module
- OU process: dX = θ(μ - X)dt + σdW
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

import simos

if TYPE_CHECKING:
    from tychon_nv_sim.config import NoiseConfig
    from tychon_nv_sim.physics.parameters import OUProcessParams


def ou_process(
    theta: float,
    mu: float,
    sigma: float,
    dt: float,
    n_steps: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a single Ornstein-Uhlenbeck trajectory.

    Implements the Euler-Maruyama discretization:
        X[n+1] = X[n] + θ(μ - X[n])dt + σ√(dt)·Z[n]

    where Z[n] ~ N(0, 1).

    Parameters
    ----------
    theta : float
        Mean reversion rate (1/s). Higher = faster reversion to μ.
    mu : float
        Long-term mean value.
    sigma : float
        Volatility (diffusion coefficient).
    dt : float
        Time step in seconds.
    n_steps : int
        Number of time steps.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    np.ndarray
        OU trajectory of shape (n_steps,).
    """
    rng = np.random.default_rng(seed)
    X = np.zeros(n_steps)
    X[0] = mu  # Start at the mean

    sqrt_dt = np.sqrt(dt)
    noise = rng.standard_normal(n_steps - 1)

    for i in range(n_steps - 1):
        X[i + 1] = X[i] + theta * (mu - X[i]) * dt + sigma * sqrt_dt * noise[i]

    return X


def generate_temperature_trajectory(
    params: OUProcessParams,
    dt: float,
    n_steps: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a temperature T(t) trajectory using OU process.

    Parameters
    ----------
    params : OUProcessParams
        OU process parameters (theta_T, mu_T, sigma_T).
    dt : float
        Time step in seconds.
    n_steps : int
        Number of time steps.
    seed : int, optional
        Random seed.

    Returns
    -------
    np.ndarray
        Temperature trajectory in Kelvin, shape (n_steps,).
    """
    return ou_process(params.theta_T, params.mu_T, params.sigma_T, dt, n_steps, seed)


def generate_b1_trajectory(
    params: OUProcessParams,
    dt: float,
    n_steps: int,
    seed: int | None = None,
) -> np.ndarray:
    """Generate a MW amplitude B1(t) trajectory using OU process.

    Parameters
    ----------
    params : OUProcessParams
        OU process parameters (theta_B1, mu_B1, sigma_B1).
    dt : float
        Time step in seconds.
    n_steps : int
        Number of time steps.
    seed : int, optional
        Random seed.

    Returns
    -------
    np.ndarray
        B1 amplitude trajectory (normalized), shape (n_steps,).
    """
    return ou_process(params.theta_B1, params.mu_B1, params.sigma_B1, dt, n_steps, seed)


class CoupledNoiseInjector:
    """Injects coupled OU noise into SimOS Hamiltonian via Fokker-Planck space.

    Uses SimOS StochasticLiouvilleParameters to define discretized T and B1
    values from OU process distributions, then evolves via stochastic_evol.

    Parameters
    ----------
    noise_config : NoiseConfig
        Noise injection configuration.
    ou_params : OUProcessParams
        OU process parameters for T and B1.
    """

    def __init__(self, noise_config: NoiseConfig, ou_params: OUProcessParams) -> None:
        self.noise_config = noise_config
        self.ou_params = ou_params

    def build_stochastic_params(
        self,
        seed: int = 42,
        n_grid_points: int = 11,
    ) -> simos.StochasticLiouvilleParameters:
        """Build SimOS StochasticLiouvilleParameters from OU process distributions.

        Creates a parameter grid for temperature and B1 with OU dynamics
        (mean-reversion rates) encoded as first-order dynamics matrices.

        Parameters
        ----------
        seed : int
            Random seed for trajectory generation.
        n_grid_points : int
            Number of discrete grid points per parameter.

        Returns
        -------
        simos.StochasticLiouvilleParameters
            Configured stochastic parameters for SimOS.
        """
        params = simos.StochasticLiouvilleParameters()

        if self.noise_config.enable_thermal_noise:
            # Temperature grid centered on mu_T with 3-sigma spread
            T_spread = 3 * self.ou_params.sigma_T / np.sqrt(2 * self.ou_params.theta_T)
            T_values = np.linspace(
                self.ou_params.mu_T - T_spread,
                self.ou_params.mu_T + T_spread,
                n_grid_points,
            )
            # Stationary distribution weights (Gaussian)
            T_var = self.ou_params.sigma_T**2 / (2 * self.ou_params.theta_T)
            weights = np.exp(-0.5 * (T_values - self.ou_params.mu_T) ** 2 / T_var)
            weights /= weights.sum()

            params["temperature"].values = T_values.tolist()
            params["temperature"].weights = weights.tolist()
            params["temperature"].dynamics = {1: self.ou_params.theta_T}

        if self.noise_config.enable_mw_noise:
            # B1 grid centered on mu_B1
            B1_spread = 3 * self.ou_params.sigma_B1 / np.sqrt(2 * self.ou_params.theta_B1)
            B1_values = np.linspace(
                self.ou_params.mu_B1 - B1_spread,
                self.ou_params.mu_B1 + B1_spread,
                n_grid_points,
            )
            B1_var = self.ou_params.sigma_B1**2 / (2 * self.ou_params.theta_B1)
            weights = np.exp(-0.5 * (B1_values - self.ou_params.mu_B1) ** 2 / B1_var)
            weights /= weights.sum()

            params["b1_amplitude"].values = B1_values.tolist()
            params["b1_amplitude"].weights = weights.tolist()
            params["b1_amplitude"].dynamics = {1: self.ou_params.theta_B1}

        return params

    def inject_coupled_noise(
        self,
        H_func,
        nv_system,
        rho0,
        t: float,
        c_ops: list | None = None,
        e_ops: list | None = None,
        seed: int = 42,
    ):
        """Evolve the system under stochastic Hamiltonian with coupled noise.

        Parameters
        ----------
        H_func : callable
            Function ``H_func(temperature=T, b1_amplitude=B1) -> Qobj`` that
            returns the Hamiltonian for given stochastic parameter values.
        nv_system : NVSystem
            SimOS NV system (for operator dimensions).
        rho0 : Qobj
            Initial density matrix.
        t : float
            Evolution time in seconds.
        c_ops : list, optional
            Collapse operators.
        e_ops : list, optional
            Expectation value operators.
        seed : int
            Random seed.

        Returns
        -------
        Qobj or tuple
            Averaged density matrix, or (rho, expectations) if e_ops given.
        """
        stoch_params = self.build_stochastic_params(seed=seed)

        kwargs = {}
        if c_ops is not None:
            kwargs["c_ops"] = c_ops
        if e_ops is not None:
            kwargs["e_ops"] = e_ops

        # rho0 is a positional arg in simos.stochastic_evol (via *rho)
        return simos.stochastic_evol(H_func, stoch_params, t, rho0, **kwargs)
