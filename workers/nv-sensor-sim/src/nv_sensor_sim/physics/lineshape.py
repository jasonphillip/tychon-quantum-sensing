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

Vector-readiness extension: ``generate_multi_axis_spectrum`` and
``apply_b1_gradient_multi_axis`` decompose the lab-frame B-field onto each of
the four NV crystallographic axes (Path A magnet or Path B concentrator), run
the per-axis SimOS spectrum, and ensemble-average. At total fields ≳ 0.5 mT
this resolves all 8 transitions (±1 per axis) so vector reconstruction becomes
possible; at zero bias the 4 axes degenerate into the legacy scalar lineshape.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import SimulationConfig


# Four NV crystallographic axes in the cubic diamond lattice, as unit vectors
# in the laboratory frame. Rows of the geometry matrix in the SBIR vector-
# readout writeup ("Part 1.3 — concrete repo-by-repo changes"); the 8x3 matrix
# A used by the downstream BLUE projection is built from these by stacking each
# axis once with sign +1 and once with sign -1.
NV_AXES_UNIT = np.array(
    [
        [+1.0, +1.0, +1.0],
        [+1.0, -1.0, -1.0],
        [-1.0, +1.0, -1.0],
        [-1.0, -1.0, +1.0],
    ],
    dtype=float,
) / np.sqrt(3.0)


def nv_geometry_matrix() -> np.ndarray:
    """Return the 8x3 NV-axis projection matrix used by vector readout.

    Rows are (axis_i, sign_s) for i in [0..3], s in {+1, -1}: row 2i is +n_i,
    row 2i+1 is -n_i. The frequency shift of resonance (i, s) under lab field
    B is ``s * gamma_e * (B . n_i)``, so the residual vector delta has the
    form ``A @ B`` and least-squares inversion ``B_hat = pinv(A) @ delta``
    recovers the lab vector.

    Returns
    -------
    np.ndarray
        Shape (8, 3) projection matrix in the lab frame.
    """
    A = np.zeros((8, 3), dtype=float)
    for i, n in enumerate(NV_AXES_UNIT):
        A[2 * i] = n
        A[2 * i + 1] = -n
    return A


def project_field_onto_axes(
    B_lab_T: np.ndarray,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> tuple[np.ndarray, np.ndarray]:
    """Decompose a lab-frame B-field into per-axis parallel/perpendicular parts.

    Parameters
    ----------
    B_lab_T : np.ndarray
        Lab-frame magnetic field 3-vector in Tesla.
    nv_axes : np.ndarray
        Unit vectors for the NV axes, shape (4, 3). Defaults to NV_AXES_UNIT.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(B_par, B_perp_mag)`` arrays of length 4.
        ``B_par[i]`` is the signed scalar projection ``B_lab . n_i`` in Tesla.
        ``B_perp_mag[i]`` is the magnitude of the perpendicular component for
        axis i, in Tesla.
    """
    B_lab = np.asarray(B_lab_T, dtype=float).reshape(3)
    B_par = nv_axes @ B_lab
    B_perp_vecs = B_lab[None, :] - B_par[:, None] * nv_axes
    B_perp_mag = np.linalg.norm(B_perp_vecs, axis=1)
    return B_par, B_perp_mag


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


def generate_multi_axis_spectrum(
    adapter: SimOSAdapter,
    B_lab_T: np.ndarray,
    p1_ppm: float | None = None,
    mw_scale: float = 1.0,
    extra_b_perp_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    freq_range: tuple[float, float] | None = None,
    n_points: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Ensemble-averaged ODMR spectrum across the 4 NV crystallographic axes.

    For each NV axis ``n_i``, the lab-frame field ``B_lab`` is decomposed into
    an axial component ``B_par_i = B_lab . n_i`` and a transverse magnitude
    ``|B_perp_i| = |B_lab - B_par_i n_i|``. The adapter's single-axis spectrum
    generator is invoked with effective field ``(0, 0, |B_par_i|)`` and
    transverse field ``|B_perp_i| + extra_b_perp_T``. The 4 per-axis spectra
    are then averaged with equal weight (single-crystal diamond, four NV
    orientations equally populated).

    At total fields ≳ 0.5 mT this resolves all 8 transitions (±1 per axis); at
    zero bias the 4 axes give degenerate spectra that average to the legacy
    single-axis ODMR lineshape.

    Parameters
    ----------
    adapter : SimOSAdapter
        Adapter whose ``generate_odmr_spectrum`` is invoked four times.
    B_lab_T : np.ndarray
        Lab-frame magnetic field 3-vector (bias + signal) in Tesla.
    p1_ppm : float, optional
        P1 concentration. Defaults to adapter config value.
    mw_scale : float
        MW Rabi-amplitude scaling applied uniformly across axes (1.0 = nominal).
    extra_b_perp_T : float
        Additional lineshape-corruption transverse field in Tesla, added to the
        geometric per-axis transverse magnitude. Defaults to 0.0.
    nv_axes : np.ndarray
        Unit vectors of the 4 NV axes, shape (4, 3). Defaults to NV_AXES_UNIT.
    freq_range : tuple[float, float], optional
        MW frequency sweep range (start, stop) in Hz. Defaults to adapter
        config value.
    n_points : int, optional
        Number of frequency points. Defaults to adapter config value.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(frequencies, averaged_spectrum)``. The averaged spectrum is
        normalized so PL = 1 off-resonance, like the single-axis generator.
    """
    B_par, B_perp_mag = project_field_onto_axes(B_lab_T, nv_axes=nv_axes)

    spectra: list[np.ndarray] = []
    frequencies: np.ndarray | None = None
    original_b_perp = adapter.config.b_perp_T

    try:
        for i in range(len(nv_axes)):
            B_eff = np.array([0.0, 0.0, abs(float(B_par[i]))])
            adapter.config.b_perp_T = float(B_perp_mag[i]) + extra_b_perp_T
            freqs_i, signal_i = adapter.generate_odmr_spectrum(
                B_field=B_eff,
                freq_range=freq_range,
                n_points=n_points,
                p1_ppm=p1_ppm,
                mw_scale=mw_scale,
            )
            if frequencies is None:
                frequencies = freqs_i
            spectra.append(signal_i)
    finally:
        adapter.config.b_perp_T = original_b_perp

    assert frequencies is not None  # guaranteed by len(nv_axes) >= 1
    # Equal-weight ensemble: PL_total = 1 - mean(1 - PL_i) = mean(PL_i)
    averaged = np.mean(np.stack(spectra, axis=0), axis=0)
    return frequencies, averaged


def apply_b1_gradient_multi_axis(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    B_lab_T: np.ndarray,
    gradient_frac: float,
    p1_ppm: float | None = None,
    n_spatial_bins: int = 10,
    mw_power_scale: float = 1.0,
    extra_b_perp_T: float = 0.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    freq_range: tuple[float, float] | None = None,
    n_points: int | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Spatial-B1-gradient-averaged multi-axis ODMR spectrum.

    Combines the legacy spatial-gradient corruption with the 4-axis ensemble:
    the per-axis spectrum is computed at ``n_spatial_bins`` evenly spaced
    ``mw_scale`` values and averaged. Useful for the vector regime where the
    same B1-gradient asymmetry the scalar pipeline already models should also
    apply to each resolved resonance.
    """
    if p1_ppm is None:
        p1_ppm = config.p1_concentration_ppm

    b1_factors = mw_power_scale * np.linspace(
        1.0 - gradient_frac / 2.0,
        1.0 + gradient_frac / 2.0,
        n_spatial_bins,
    )

    spectra: list[np.ndarray] = []
    frequencies: np.ndarray | None = None
    for b1_scale in b1_factors:
        freqs, signal = generate_multi_axis_spectrum(
            adapter,
            B_lab_T,
            p1_ppm=p1_ppm,
            mw_scale=float(b1_scale),
            extra_b_perp_T=extra_b_perp_T,
            nv_axes=nv_axes,
            freq_range=freq_range,
            n_points=n_points,
        )
        if frequencies is None:
            frequencies = freqs
        spectra.append(signal)

    assert frequencies is not None
    return frequencies, np.mean(np.stack(spectra, axis=0), axis=0)


def corrupt_spectrum_multi_axis(
    adapter: SimOSAdapter,
    config: SimulationConfig,
    B_lab_T: np.ndarray,
    b1_gradient_frac: float,
    extra_b_perp_T: float = 0.0,
    p1_ppm: float | None = None,
    n_spatial_bins: int = 10,
    mw_power_scale: float = 1.0,
    nv_axes: np.ndarray = NV_AXES_UNIT,
    freq_range: tuple[float, float] | None = None,
    n_points: int | None = None,
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Multi-axis analog of ``corrupt_spectrum``: B1 gradient + transverse field.

    ``extra_b_perp_T`` is *additional* transverse field beyond the geometric
    per-axis transverse projection of ``B_lab_T``. At low bias the lab
    transverse projection already covers most of the perpendicular Zeeman
    physics; ``extra_b_perp_T`` is for residual stray-field corruption.
    """
    if p1_ppm is None:
        p1_ppm = config.p1_concentration_ppm

    frequencies, spectrum = apply_b1_gradient_multi_axis(
        adapter,
        config,
        B_lab_T,
        b1_gradient_frac,
        p1_ppm=p1_ppm,
        n_spatial_bins=n_spatial_bins,
        mw_power_scale=mw_power_scale,
        extra_b_perp_T=extra_b_perp_T,
        nv_axes=nv_axes,
        freq_range=freq_range,
        n_points=n_points,
    )

    corruption_params = {
        "b1_gradient_frac": b1_gradient_frac,
        "extra_b_perp_T": extra_b_perp_T,
        "n_spatial_bins": n_spatial_bins,
        "p1_ppm": p1_ppm,
        "mw_power_scale": mw_power_scale,
        "B_lab_T": list(np.asarray(B_lab_T, dtype=float).reshape(3)),
    }
    return frequencies, spectrum, corruption_params
