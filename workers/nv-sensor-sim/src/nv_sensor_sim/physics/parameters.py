"""Published noise parameter catalog for NV-diamond ODMR simulation.

All parameters are from peer-reviewed literature. Do NOT derive from first principles.

References
----------
- P1 bath: CCE study, arXiv:2503.05404
- Thermal drift: dD/dT textbook value; SBQuantum arXiv:2509.19179
- OU process: Standard parameterization for stochastic noise injection
- Asymmetry: B1 gradient and transverse B_perp injection (see docs/architecture.md)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class P1BathParams:
    """P1 bath noise parameters from CCE study (arXiv:2503.05404).

    Parameters
    ----------
    delta_range_Hz : tuple[float, float]
        P1 bath coupling strength range in Hz.
    tau_c_range_s : tuple[float, float]
        P1 bath correlation time range in seconds.
    """

    delta_range_Hz: tuple[float, float] = (1e6, 7e6)  # 1-7 MHz
    tau_c_range_s: tuple[float, float] = (5e-6, 50e-6)  # 5-50 µs


@dataclass(frozen=True)
class ThermalDriftParams:
    """Thermal drift parameters.

    Parameters
    ----------
    dD_dT_Hz_per_K : float
        Temperature coefficient of ZFS in Hz/K.
    temp_range_K : tuple[float, float]
        Operating temperature range in Kelvin.
    sensitivity_pT_per_rtHz : float
        Magnetometer sensitivity in pT/sqrt(Hz).
    heading_error_nT : float
        Heading error upper bound in nT.
    """

    dD_dT_Hz_per_K: float = -74.2e3  # dD/dT ≈ -74.2 kHz/K
    # SBQuantum space qualification (arXiv:2509.19179):
    temp_range_K: tuple[float, float] = (208.15, 398.15)  # -65°C to +125°C
    sensitivity_pT_per_rtHz: float = 400.0  # ~400 pT/√Hz
    heading_error_nT: float = 5.0  # below 5 nT


@dataclass(frozen=True)
class OUProcessParams:
    """Ornstein-Uhlenbeck process parameters for stochastic noise.

    Parameters
    ----------
    theta_T : float
        Temperature OU mean reversion rate (1/s).
    mu_T : float
        Temperature OU mean value (K).
    sigma_T : float
        Temperature OU volatility (K/sqrt(s)).
    theta_B1 : float
        B1 amplitude OU mean reversion rate (1/s).
    mu_B1 : float
        B1 amplitude OU mean value (normalized).
    sigma_B1 : float
        B1 amplitude OU volatility (fractional/sqrt(s)).
    """

    theta_T: float = 0.1  # mean reversion rate (1/s)
    mu_T: float = 300.0  # mean temperature (K)
    sigma_T: float = 0.5  # volatility (K/√s)
    theta_B1: float = 1.0  # mean reversion rate (1/s)
    mu_B1: float = 1.0  # mean B1 (normalized)
    sigma_B1: float = 0.05  # volatility (fractional)


@dataclass(frozen=True)
class AsymmetryParams:
    """Asymmetric lineshape corruption parameters.

    Two corruption channels applied to every generated spectrum:
    1. Spatial B1 gradient: linear spatial gradient to MW drive amplitude.
    2. Transverse field injection: random B_perp as off-diagonal Zeeman terms.

    Parameters
    ----------
    b1_gradient_range : tuple[float, float]
        B1 gradient fractional variation range.
    b_perp_range_T : tuple[float, float]
        Transverse field range in Tesla.
    """

    b1_gradient_range: tuple[float, float] = (0.05, 0.30)  # 5-30% variation
    b_perp_range_T: tuple[float, float] = (0.0, 50e-6)  # Range in Tesla (0 to 50 µT = 0 to 50e-6 T)


def compute_linewidth(p1_ppm: float, inhomogeneous_fwhm_hz: float = 0.0) -> float:
    """Compute total FWHM linewidth in Hz using literature scaling laws.

    Combines two dephasing channels and an optional inhomogeneous contribution:
    1. 13C natural-abundance spin bath: T2*(13C) ~ 1.48 µs (floor for ultra-pure diamond)
    2. P1 (nitrogen) spin bath: inverse coefficient of 9.9 µs·ppm (CCE study arXiv:2503.05404)
    3. Inhomogeneous broadening from lattice strain / magnetic gradients (Voigt approx.)

    The total homogeneous rate is: 1/T2* = 1/T2*(13C) + [P1] / T2*_N
    FWHM_hom = 1 / (π · T2*)
    Total FWHM = √(FWHM_hom² + FWHM_inhom²) [Voigt quadrature approximation]

    Parameters
    ----------
    p1_ppm : float
        P1 concentration in ppm.
    inhomogeneous_fwhm_hz : float
        Sample-specific inhomogeneous broadening FWHM in Hz. Default 0.0.

    Returns
    -------
    float
        Total linewidth (FWHM) in Hz.
    """
    # Protect against zero/negative P1 for ultra-pure samples
    p1_eff = max(p1_ppm, 1e-6)

    # Calculate dephasing rates (1/T2*)
    rate_13c = 1.0 / 1.48e-6  # 13C natural abundance floor
    rate_n = p1_eff / 9.9e-6  # P1 nitrogen spin bath

    total_rate = rate_13c + rate_n
    t2_star_s = 1.0 / total_rate

    # Homogeneous FWHM = 1 / (pi * T2*)
    homogeneous_fwhm = 1.0 / (np.pi * t2_star_s)

    # Return Voigt-approximated total FWHM (quadrature sum)
    return float(np.sqrt(homogeneous_fwhm**2 + inhomogeneous_fwhm_hz**2))
