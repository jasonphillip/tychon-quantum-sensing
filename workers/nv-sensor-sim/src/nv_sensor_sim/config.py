"""Typed configuration dataclasses for simulation, noise, and dataset generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class NoiseMode(str, Enum):
    """Noise injection mode for batch generation pipeline."""

    DETERMINISTIC = "deterministic"
    STOCHASTIC = "stochastic"
    BOTH = "both"


class FieldSampling(str, Enum):
    """B-field sampling strategy for batch generation."""

    Z_ONLY = "z_only"
    SPHERICAL = "spherical"
    BIAS_PLUS_AMBIENT = "bias_plus_ambient"


@dataclass
class OUNoiseConfig:
    """Ornstein-Uhlenbeck trajectory configuration for stochastic noise mode.

    Controls how T(t) and B1(t) trajectories are sampled. Each spectrum
    in a split gets one (T, B1) sample from the OU trajectory, producing
    temporally correlated parameter drift across the dataset.

    Two modes controlled by ``alpha_B1``:

    - **Independent** (``alpha_B1 == 0.0``, default): T and B1 are independent
      OU processes reverting to ``mu_T`` and ``mu_B1`` respectively.
    - **Cascaded causal** (``alpha_B1 != 0.0``): orbital thermal baseline
      drives sensor T(t), which causally modulates B1 target. Uses exact
      OU transition kernel (stable for any dt). ``mu_T`` / ``mu_B1`` are
      overridden by ``T_mean_C + 273.15`` and ``B1_nominal``.

    Parameters
    ----------
    theta_T : float
        Temperature mean reversion rate (1/s).
    mu_T : float
        Temperature long-term mean (K). Used in independent mode only.
    sigma_T : float
        Temperature volatility (K/sqrt(s)).
    theta_B1 : float
        MW power mean reversion rate (1/s).
    mu_B1 : float
        MW power long-term mean (normalized). Used in independent mode only.
    sigma_B1 : float
        MW power volatility (fractional/sqrt(s)).
    trajectory_dt_s : float
        Time step between successive spectra in the trajectory (seconds).
    enable_thermal_noise : bool
        Enable OU noise on the temperature channel.
    enable_mw_noise : bool
        Enable OU noise on the MW power channel.
    alpha_B1 : float
        T->B1 coupling coefficient (1/K). Negative means gain drops with
        heat. Set to 0.0 for independent mode (legacy). Reference:
        SBQuantum arXiv:2509.19179, ~-0.03 dB/°C for COTS amplifiers.
    T_mean_C : float
        Mean sensor temperature in Celsius. Cascaded mode only.
    delta_T_orb_C : float
        Orbital thermal half-amplitude in Celsius (or Kelvin, it's a delta).
    tau_orb_s : float
        Orbital period in seconds. 5400 = 90-min LEO.
    B1_nominal : float
        Nominal MW amplitude (dimensionless, 1.0 = full power).
    """

    theta_T: float = 0.1
    mu_T: float = 300.0
    sigma_T: float = 0.5
    theta_B1: float = 1.0
    mu_B1: float = 1.0
    sigma_B1: float = 0.05
    trajectory_dt_s: float = 1.0
    enable_thermal_noise: bool = True
    enable_mw_noise: bool = True
    # Cascaded SDE fields (alpha_B1 != 0.0 activates cascaded mode)
    alpha_B1: float = 0.0
    T_mean_C: float = 20.0
    delta_T_orb_C: float = 15.0
    tau_orb_s: float = 5400.0
    B1_nominal: float = 1.0


@dataclass
class SimulationConfig:
    """Core NV-diamond ODMR simulation parameters.

    Parameters
    ----------
    B_field_T : np.ndarray
        3-vector magnetic field [Bx, By, Bz] in Tesla.
    temperature_K : float
        Sample temperature in Kelvin.
    mw_freq_range_Hz : tuple[float, float]
        MW frequency sweep range (start, stop) in Hz.
    n_freq_points : int
        Number of frequency points in the ODMR sweep.
    p1_concentration_ppm : float
        P1 (substitutional nitrogen) concentration in ppm.
    b1_gradient_frac : float
        Spatial B1 gradient magnitude as fraction (0.05 to 0.30).
    b_perp_T : float
        Transverse magnetic field component in Tesla (0 to 50e-6).
    random_seed : int
        Master random seed for reproducibility.
    include_nitrogen : bool
        Include nitrogen nuclear spin in the Hamiltonian.
    use_optics : bool
        Include optical (electronic) levels for PL readout.
    inhomogeneous_fwhm_hz : float
        Sample-specific inhomogeneous broadening from lattice strain and
        magnetic gradients. Default 0.0 for pure homogeneous limit.
    base_saturation_s0 : float
        Baseline MW saturation parameter for power broadening at mw_scale=1.0.
    base_contrast : float
        Nominal ODMR contrast at mw_scale=1.0.
    """

    B_field_T: np.ndarray = field(default_factory=lambda: np.array([0.0, 0.0, 0.01]))
    temperature_K: float = 300.0
    mw_freq_range_Hz: tuple[float, float] = (2.82e9, 2.92e9)
    n_freq_points: int = 100
    p1_concentration_ppm: float = 10.0
    b1_gradient_frac: float = 0.10
    b_perp_T: float = 0.0
    random_seed: int = 42
    include_nitrogen: bool = True
    use_optics: bool = True
    inhomogeneous_fwhm_hz: float = 0.0
    base_saturation_s0: float = 0.1
    base_contrast: float = 0.03


@dataclass
class NoiseConfig:
    """Ornstein-Uhlenbeck stochastic noise parameters.

    Parameters
    ----------
    enable_thermal_noise : bool
        Enable temperature OU process noise injection.
    enable_mw_noise : bool
        Enable MW amplitude B1 OU process noise injection.
    ou_theta_T : float
        Temperature OU mean reversion rate (1/s).
    ou_sigma_T : float
        Temperature OU volatility (K/sqrt(s)).
    ou_theta_B1 : float
        B1 amplitude OU mean reversion rate (1/s).
    ou_sigma_B1 : float
        B1 amplitude OU volatility (fractional/sqrt(s)).
    n_time_steps : int
        Number of discrete time steps for OU trajectories.
    """

    enable_thermal_noise: bool = True
    enable_mw_noise: bool = True
    ou_theta_T: float = 0.1
    ou_sigma_T: float = 0.5
    ou_theta_B1: float = 1.0
    ou_sigma_B1: float = 0.05
    n_time_steps: int = 100


@dataclass
class DatasetConfig:
    """Dataset generation configuration.

    Parameters
    ----------
    n_spectra_train : int
        Number of spectra in the training split.
    n_spectra_val : int
        Number of spectra in the validation split.
    n_spectra_test : int
        Number of spectra in the test split.
    output_dir : str
        Directory for output files.
    output_format : str
        Output format: "h5" (HDF5) or "npz" (numpy compressed).
    """

    n_spectra_train: int = 1000
    n_spectra_val: int = 200
    n_spectra_test: int = 200
    output_dir: str = "artifacts/datasets"
    output_format: str = "h5"
