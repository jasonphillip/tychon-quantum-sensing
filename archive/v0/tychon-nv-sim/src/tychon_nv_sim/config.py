"""Typed configuration dataclasses for simulation, noise, and dataset generation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


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
