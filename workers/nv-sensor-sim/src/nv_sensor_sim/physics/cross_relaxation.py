"""NV-NV cross-relaxation PL feature (density-conditional merge marker).

When two inequivalent NV orientations ``i != j`` satisfy the resonance
condition ``|B . n_i| = |B . n_j|`` (Espinos & Budker, arXiv:2512.13835, Eq. 3)
their ms=0 -> ms=+/-1 transition energies coincide; magnetic dipole-dipole
coupling then enhances flip-flop processes between the two orientation classes,
redistributing population out of the bright ms=0 state and producing a drop in
photoluminescence (a cross-relaxation "dip"). Espinos & Budker model the PL as
a sum of Lorentzian dips centered at the degeneracy (their phenomenological
Eq. 8); the mechanism is confirmed by Wickenbrock/Budker arXiv:1505.02253
(T1 shortens at inter-orientation degeneracy).

The feature is density-conditional: Dhungel et al. (arXiv:2301.09666) report it
is visible only for NV density >~ 0.9 ppm, with two calibration points ---
3.8 ppm -> FWHM 0.78 mT, contrast ~1.79%; 16 ppm -> 1.42 mT, 3.95% --- both the
field-linewidth and the contrast growing with density. We fit a power law
through those two points and floor visibility at 0.9 ppm.

Modeling choices (documented in docs/dataset-contract.md):
- Espinos/Budker/Dhungel measure the MW-free feature as PL vs magnetic field;
  we render its manifestation in a MW-swept CW-ODMR frame as extra Lorentzian
  PL dips at the (near-)degenerate transition frequencies.
- The *field-detuning* width (0.78 mT at 3.8 ppm) gates *which frames / how
  strongly* the feature is present, via a Lorentzian in the Espinos-Eq.3
  detuning ``eta = ||B.n_i| - |B.n_j||``.
- The *spectral* width of each rendered dip is set by the ODMR linewidth Gamma
  (the dip sits on the merged transitions).
- The feature is added to the rendered spectrum ONLY; it does NOT create new
  entries in ``resonance_freqs`` (the L=8 line contract is unchanged). Its
  primary value is realism + a physics-anchored merge marker; downstream
  identity value is measured, not asserted here.
"""

from __future__ import annotations

import numpy as np

from nv_sensor_sim.physics.lineshape import NV_AXES_UNIT

# --- Dhungel (arXiv:2301.09666) two-point calibration ---
_CR_REF_PPM = 3.8  # calibration / default-cues density
_CR_CONTRAST_REF = 0.0179  # single-dip contrast at the reference density
_CR_FWHM_REF_T = 0.78e-3  # field-detuning FWHM (Tesla) at the reference density
_CR_HI_PPM = 16.0
_CR_CONTRAST_HI = 0.0395
_CR_FWHM_HI_T = 1.42e-3
_CR_VISIBILITY_FLOOR_PPM = 0.9  # below this the feature is not visible

# Power-law exponents fit through the two Dhungel calibration points.
_CR_P_CONTRAST = float(
    np.log(_CR_CONTRAST_HI / _CR_CONTRAST_REF) / np.log(_CR_HI_PPM / _CR_REF_PPM)
)
_CR_P_FWHM = float(np.log(_CR_FWHM_HI_T / _CR_FWHM_REF_T) / np.log(_CR_HI_PPM / _CR_REF_PPM))


def cr_contrast_and_width(nv_density_ppm: float) -> tuple[float, float]:
    """Cross-relaxation single-dip contrast and field-detuning FWHM at a density.

    Parameters
    ----------
    nv_density_ppm : float
        NV(-) concentration in ppm.

    Returns
    -------
    tuple[float, float]
        ``(contrast, fwhm_field_T)``: the single-dip PL contrast (fraction) and
        the field-detuning full width at half maximum in Tesla. Contrast is 0
        below the ~0.9 ppm visibility floor. Anchored to Dhungel
        (arXiv:2301.09666): 3.8 ppm -> (0.0179, 0.78 mT), 16 ppm ->
        (0.0395, 1.42 mT), power-law interpolated/extrapolated.
    """
    if nv_density_ppm <= 0.0:
        return 0.0, _CR_FWHM_REF_T
    ratio = nv_density_ppm / _CR_REF_PPM
    fwhm_field_T = _CR_FWHM_REF_T * ratio**_CR_P_FWHM
    if nv_density_ppm < _CR_VISIBILITY_FLOOR_PPM:
        return 0.0, fwhm_field_T
    contrast = _CR_CONTRAST_REF * ratio**_CR_P_CONTRAST
    return contrast, fwhm_field_T


def add_cross_relaxation(
    frequencies: np.ndarray,
    spectrum: np.ndarray,
    resonance_freqs: np.ndarray,
    B_par: np.ndarray,
    nv_density_ppm: float,
    gamma_fwhm_hz: float,
    nv_axes: np.ndarray = NV_AXES_UNIT,
) -> np.ndarray:
    """Add NV-NV cross-relaxation PL dips at inter-orientation degeneracies.

    For each orientation pair ``(i, j)`` the Espinos-Eq.3 field detuning
    ``eta = ||B.n_i| - |B.n_j||`` sets a Lorentzian-in-field weight (peak 1 at
    degeneracy, HWHM = half the density-dependent field width). At (near-)
    degeneracy the two orientations' transitions coincide at two frequencies; a
    Lorentzian PL dip of depth ``contrast * weight`` and spectral HWHM
    ``gamma_fwhm_hz / 2`` is placed at each. The feature modifies the spectrum
    only (resonance_freqs / line labels are untouched).

    Parameters
    ----------
    frequencies : np.ndarray
        MW frequency axis (Hz), shape (F,).
    spectrum : np.ndarray
        Normalized PL spectrum (1 off-resonance), shape (F,).
    resonance_freqs : np.ndarray
        Line centers (Hz) in geometry-matrix order, shape (L = 2 * n_axes,).
    B_par : np.ndarray
        Signed per-axis projections ``B . n_i`` (Tesla), shape (n_axes,).
    nv_density_ppm : float
        NV concentration in ppm. 0 (default in callers) returns the spectrum
        unchanged (byte-identical); below ~0.9 ppm produces no feature.
    gamma_fwhm_hz : float
        ODMR linewidth (FWHM, Hz) setting the spectral width of each CR dip.
    nv_axes : np.ndarray
        Unit vectors of the NV axes, shape (n_axes, 3). Defaults to NV_AXES_UNIT.

    Returns
    -------
    np.ndarray
        The spectrum with cross-relaxation dips subtracted. The input array is
        returned unchanged (same object) when the feature is off.
    """
    if nv_density_ppm <= 0.0:
        return spectrum
    contrast, fwhm_field_T = cr_contrast_and_width(nv_density_ppm)
    if contrast <= 0.0:
        return spectrum

    freqs = np.asarray(frequencies, dtype=float)
    res = np.asarray(resonance_freqs, dtype=float)
    proj = np.abs(np.asarray(B_par, dtype=float))
    n_axes = proj.shape[0]
    hwhm_field = 0.5 * fwhm_field_T
    gamma_hwhm = 0.5 * gamma_fwhm_hz

    out = np.array(spectrum, dtype=float, copy=True)
    for i in range(n_axes):
        for j in range(i + 1, n_axes):
            eta = abs(proj[i] - proj[j])
            weight = hwhm_field**2 / (eta**2 + hwhm_field**2)  # Lorentzian in field detuning
            if weight < 1e-6:
                continue
            depth = contrast * weight
            # The two orientations' transitions coincide at two frequencies:
            # match axis-i lines to the nearest axis-j line, one CR dip each.
            ci0, ci1 = res[2 * i], res[2 * i + 1]
            cj0, cj1 = res[2 * j], res[2 * j + 1]
            straight = abs(ci0 - cj0) + abs(ci1 - cj1)
            crossed = abs(ci0 - cj1) + abs(ci1 - cj0)
            matched = ((ci0, cj0), (ci1, cj1)) if straight <= crossed else ((ci0, cj1), (ci1, cj0))
            for a, b in matched:
                f_center = 0.5 * (a + b)
                lorentz = gamma_hwhm**2 / ((freqs - f_center) ** 2 + gamma_hwhm**2)
                out -= depth * lorentz
    return out
