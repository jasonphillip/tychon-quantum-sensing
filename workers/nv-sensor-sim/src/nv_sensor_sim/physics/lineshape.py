"""Asymmetric lineshape generation via B1 gradient and transverse field injection.

Two corruption channels are applied to generate realistic, asymmetric,
Fano-like ODMR lineshapes (rather than idealized symmetric Voigt profiles):

1. Spatial B1 gradient: Averages spectra across spatially varying MW drive
   amplitude (mw_scale), producing inhomogeneous power broadening and asymmetry.
2. Transverse field injection: Adds B_perp as off-diagonal Zeeman terms,
   mixing spin states and shifting/distorting resonance profiles.

Parameters are drawn from published ranges (Section 3.2):
- b1_gradient_frac: [0.05, 0.30] (5-30% variation)
- b_perp_T: [0, 50e-6] T (0 to 50 µT)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import SimulationConfig


def apply_b1_gradient(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    gradient_frac: float,
    p1_ppm: float | None = None,
    n_spatial_bins: int = 10,
    mw_power_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate ODMR spectrum with spatial B1 gradient averaging.

    Simulates inhomogeneous MW drive by generating spectra at multiple
    spatial positions with linearly varying MW Rabi frequency (mw_scale),
    then averaging. This produces realistic power-broadened, asymmetric
    lineshapes.

    Parameters
    ----------
    adapter : SimOSAdapter
        SimOS adapter instance for spectrum generation.
    config : SimulationConfig
        Simulation configuration.
    gradient_frac : float
        Fractional B1 gradient magnitude (e.g. 0.10 = 10% variation).
    p1_ppm : float, optional
        P1 concentration in ppm. Defaults to config value.
    n_spatial_bins : int
        Number of spatial positions to average over.
    mw_power_scale : float
        Temporal MW power scaling from OU B1(t) drift (1.0 = nominal).
        Composes multiplicatively with the spatial gradient.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (frequencies, averaged_spectrum).
    """
    if p1_ppm is None:
        p1_ppm = config.p1_concentration_ppm

    # B1 scaling factors: spatial gradient × temporal power drift
    b1_factors = mw_power_scale * np.linspace(
        1 - gradient_frac / 2, 1 + gradient_frac / 2, n_spatial_bins
    )

    spectra = []
    frequencies = None

    for b1_scale in b1_factors:
        # Vary mw_scale (MW Rabi frequency), NOT optical pumping beta
        freqs, signal = adapter.generate_odmr_spectrum(
            temperature_K=config.temperature_K,
            p1_ppm=p1_ppm,
            mw_scale=b1_scale,
        )
        if frequencies is None:
            frequencies = freqs
        spectra.append(signal)

    # Average across spatial positions
    averaged = np.mean(spectra, axis=0)
    return frequencies, averaged


def apply_transverse_field(
    adapter: SimOSAdapter,
    b_perp_T: float,
    p1_ppm: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate ODMR spectrum with transverse field injection.

    The transverse field enters the Hamiltonian directly as off-diagonal
    Zeeman terms via the adapter's configuration.

    Parameters
    ----------
    adapter : SimOSAdapter
        SimOS adapter with b_perp_T set in config.
    b_perp_T : float
        Transverse field magnitude in Tesla.
    p1_ppm : float, optional
        P1 concentration in ppm. Defaults to config value.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (frequencies, spectrum_with_b_perp).
    """
    # Temporarily set b_perp in the adapter config
    original_b_perp = adapter.config.b_perp_T
    adapter.config.b_perp_T = b_perp_T
    try:
        kwargs = {}
        if p1_ppm is not None:
            kwargs["p1_ppm"] = p1_ppm
        freqs, signal = adapter.generate_odmr_spectrum(**kwargs)
    finally:
        adapter.config.b_perp_T = original_b_perp
    return freqs, signal


def corrupt_spectrum(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    b1_gradient_frac: float,
    b_perp_T: float,
    p1_ppm: float | None = None,
    n_spatial_bins: int = 10,
    mw_power_scale: float = 1.0,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Apply both corruption channels to produce asymmetric ODMR spectrum.

    Parameters
    ----------
    adapter : SimOSAdapter
        SimOS adapter instance.
    config : SimulationConfig
        Simulation configuration.
    b1_gradient_frac : float
        B1 gradient fractional magnitude (0.05 to 0.30).
    b_perp_T : float
        Transverse field in Tesla (0 to 50e-6).
    p1_ppm : float, optional
        P1 concentration in ppm. Defaults to config value.
    n_spatial_bins : int
        Number of spatial bins for B1 gradient averaging.
    mw_power_scale : float
        Temporal MW power scaling from OU B1(t) drift (1.0 = nominal).

    Returns
    -------
    tuple[np.ndarray, np.ndarray, dict]
        (frequencies, corrupted_spectrum, corruption_params) where
        corruption_params records the applied corruption values.
    """
    if p1_ppm is None:
        p1_ppm = config.p1_concentration_ppm

    # Set transverse field in adapter
    original_b_perp = adapter.config.b_perp_T
    adapter.config.b_perp_T = b_perp_T

    try:
        frequencies, spectrum = apply_b1_gradient(
            adapter, config, b1_gradient_frac, p1_ppm=p1_ppm,
            n_spatial_bins=n_spatial_bins, mw_power_scale=mw_power_scale,
        )
    finally:
        adapter.config.b_perp_T = original_b_perp

    corruption_params = {
        "b1_gradient_frac": b1_gradient_frac,
        "b_perp_T": b_perp_T,
        "n_spatial_bins": n_spatial_bins,
        "p1_ppm": p1_ppm,
        "mw_power_scale": mw_power_scale,
    }

    return frequencies, spectrum, corruption_params
