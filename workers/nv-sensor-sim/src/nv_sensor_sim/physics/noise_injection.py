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

import warnings
from typing import TYPE_CHECKING

import numpy as np

import simos

if TYPE_CHECKING:
    from nv_sensor_sim.config import NoiseConfig, OUNoiseConfig
    from nv_sensor_sim.physics.parameters import OUProcessParams


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


def _orbital_thermal_baseline(
    t_array_s: np.ndarray,
    T_mean_K: float,
    delta_T_orb_K: float,
    tau_orb_s: float,
) -> np.ndarray:
    """Compute deterministic orbital thermal baseline T_env(t).

    Parameters
    ----------
    t_array_s : np.ndarray
        Time array in seconds.
    T_mean_K : float
        Mean temperature in Kelvin.
    delta_T_orb_K : float
        Orbital temperature half-amplitude in Kelvin.
    tau_orb_s : float
        Orbital period in seconds.

    Returns
    -------
    np.ndarray
        T_env(t) = T_mean + delta_T_orb * sin(2*pi*t / tau_orb), in Kelvin.
    """
    return T_mean_K + delta_T_orb_K * np.sin(2.0 * np.pi * t_array_s / tau_orb_s)


def _cascaded_sde_pair(
    ou_config: OUNoiseConfig,
    n_samples: int,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate cascaded T(t) -> B1(t) trajectories via exact OU kernel.

    SDE system (integrated with exact OU transition kernel for stability):

        T_env(t) = T_mean + dT_orb * sin(2*pi*t / tau_orb)
        dT  = -theta_T * (T - T_env(t)) * dt + sigma_T * dW_T
        B1_target(t) = B1_nom * [1 + alpha_B1 * (T(t) - T_mean)]
        dB1 = -theta_B1 * (B1 - B1_target(t)) * dt + sigma_B1 * dW_B1

    Causal ordering: T is computed first, then drives B1_target.
    Independent Wiener processes; correlation arises through the coupling.

    Parameters
    ----------
    ou_config : OUNoiseConfig
        Configuration with cascaded SDE fields (alpha_B1 != 0).
    n_samples : int
        Number of trajectory samples.
    seed : int, optional
        Random seed for reproducibility.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (T_trajectory_K, B1_trajectory) each of shape (n_samples,).
    """
    T_mean_K = ou_config.T_mean_C + 273.15
    dt = ou_config.trajectory_dt_s

    # Orbital baseline
    t_array = np.arange(n_samples) * dt
    T_env = _orbital_thermal_baseline(
        t_array, T_mean_K, ou_config.delta_T_orb_C, ou_config.tau_orb_s
    )

    # Two independent RNG streams
    ss = np.random.SeedSequence(seed)
    seed_T, seed_B1 = ss.spawn(2)
    rng_T = np.random.default_rng(seed_T)
    rng_B1 = np.random.default_rng(seed_B1)

    noise_T = rng_T.standard_normal(n_samples - 1)
    noise_B1 = rng_B1.standard_normal(n_samples - 1)

    # Precompute exact OU kernel coefficients
    decay_T = np.exp(-ou_config.theta_T * dt)
    noise_scale_T = ou_config.sigma_T * np.sqrt(
        (1.0 - decay_T**2) / (2.0 * ou_config.theta_T)
    )

    decay_B1 = np.exp(-ou_config.theta_B1 * dt)
    noise_scale_B1 = ou_config.sigma_B1 * np.sqrt(
        (1.0 - decay_B1**2) / (2.0 * ou_config.theta_B1)
    )

    T_traj = np.zeros(n_samples)
    B1_traj = np.zeros(n_samples)

    # Initial conditions
    T_traj[0] = T_env[0]
    B1_traj[0] = ou_config.B1_nominal

    for i in range(n_samples - 1):
        # --- Temperature step: revert to T_env[i] ---
        T_traj[i + 1] = (
            T_env[i] + (T_traj[i] - T_env[i]) * decay_T
            + noise_scale_T * noise_T[i]
        )

        # --- B1 step: target depends causally on just-computed T ---
        B1_target = ou_config.B1_nominal * (
            1.0 + ou_config.alpha_B1 * (T_traj[i + 1] - T_mean_K)
        )
        B1_traj[i + 1] = (
            B1_target + (B1_traj[i] - B1_target) * decay_B1
            + noise_scale_B1 * noise_B1[i]
        )

    return T_traj, B1_traj


def sample_ou_trajectory_pair(
    ou_config: OUNoiseConfig,
    n_samples: int,
    seed: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate paired OU trajectories for T(t) and B1(t).

    Produces temporally correlated samples for use in the batch generation
    pipeline. Each element represents the quasi-static (T, B1) value for
    one CW ODMR sweep.

    Parameters
    ----------
    ou_config : OUNoiseConfig
        OU trajectory configuration (theta, mu, sigma for each channel).
    n_samples : int
        Number of samples (one per spectrum in the split).
    seed : int, optional
        Random seed. Split into independent sub-seeds for T and B1.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (T_trajectory, B1_trajectory) each of shape (n_samples,).
        Disabled channels return constant mu values.
    """
    # --- Cascaded causal SDE mode (alpha_B1 != 0) ---
    if ou_config.alpha_B1 != 0.0:
        T_traj, B1_traj = _cascaded_sde_pair(ou_config, n_samples, seed)

        if not ou_config.enable_thermal_noise:
            T_mean_K = ou_config.T_mean_C + 273.15
            T_traj = np.full(n_samples, T_mean_K)
        else:
            n_clipped = int(np.sum(T_traj <= 0))
            if n_clipped > 0:
                warnings.warn(
                    f"Cascaded T trajectory: {n_clipped} samples clipped to >0 K",
                    UserWarning,
                )
                T_traj = np.clip(T_traj, 1e-3, None)

        if not ou_config.enable_mw_noise:
            B1_traj = np.full(n_samples, ou_config.B1_nominal)
        else:
            n_clipped = int(np.sum(B1_traj <= 0))
            if n_clipped > 0:
                warnings.warn(
                    f"Cascaded B1 trajectory: {n_clipped} samples clipped to >0",
                    UserWarning,
                )
                B1_traj = np.clip(B1_traj, 1e-6, None)

        return T_traj, B1_traj

    # --- Legacy independent OU mode (alpha_B1 == 0) ---
    # Split seed into independent sub-seeds for T and B1
    ss = np.random.SeedSequence(seed)
    seed_T, seed_B1 = ss.spawn(2)

    if ou_config.enable_thermal_noise:
        T_traj = ou_process(
            theta=ou_config.theta_T,
            mu=ou_config.mu_T,
            sigma=ou_config.sigma_T,
            dt=ou_config.trajectory_dt_s,
            n_steps=n_samples,
            seed=seed_T.generate_state(1)[0],
        )
        # Clip to physical bounds (temperature must be positive)
        n_clipped = np.sum(T_traj <= 0)
        if n_clipped > 0:
            warnings.warn(
                f"OU temperature trajectory: {n_clipped} samples clipped to >0 K",
                UserWarning,
            )
            T_traj = np.clip(T_traj, 1e-3, None)
    else:
        T_traj = np.full(n_samples, ou_config.mu_T)

    if ou_config.enable_mw_noise:
        B1_traj = ou_process(
            theta=ou_config.theta_B1,
            mu=ou_config.mu_B1,
            sigma=ou_config.sigma_B1,
            dt=ou_config.trajectory_dt_s,
            n_steps=n_samples,
            seed=seed_B1.generate_state(1)[0],
        )
        # Clip to physical bounds (MW power must be positive)
        n_clipped = np.sum(B1_traj <= 0)
        if n_clipped > 0:
            warnings.warn(
                f"OU B1 trajectory: {n_clipped} samples clipped to >0",
                UserWarning,
            )
            B1_traj = np.clip(B1_traj, 1e-6, None)
    else:
        B1_traj = np.full(n_samples, ou_config.mu_B1)

    return T_traj, B1_traj


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
