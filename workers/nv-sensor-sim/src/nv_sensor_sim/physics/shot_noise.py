"""Photon shot-noise model for normalized ODMR spectra (consumer-side).

The stored dataset spectra are deliberately noiseless (deterministic renders);
measurement noise is applied by the consumer — as train-time augmentation and
as fixed-seed evaluation realizations. This module owns the physics of that
noise so downstream repos do not re-derive it.

Model: CW photon counting. With ``N`` detected photons per frequency point at
the off-resonance baseline, the count at normalized PL level ``S(f)`` is
Poisson with mean ``N * S(f)``, so the normalized-PL noise is

    sigma(f) = sqrt(S(f) / N)

(~ ``1/sqrt(N)`` at the baseline ``S ~ 1``). A dip of depth ``C`` therefore
has amplitude SNR ``C * sqrt(N)`` — use ``photons_for_dip_snr`` with the
manifest's ``line_depths`` to size a photon budget for the faintest line.
"""

from __future__ import annotations

import numpy as np


def shot_noise_sigma(spectrum: np.ndarray, photons_per_point: float) -> np.ndarray:
    """Per-point shot-noise standard deviation in normalized-PL units.

    Parameters
    ----------
    spectrum : np.ndarray
        Normalized PL spectrum (any shape; ~1 off-resonance). Negative values
        are clipped to 0 before the square root.
    photons_per_point : float
        Detected photons per frequency point at the off-resonance baseline
        (> 0).

    Returns
    -------
    np.ndarray
        ``sqrt(S / N)``, same shape as ``spectrum``.
    """
    if photons_per_point <= 0.0:
        raise ValueError(f"photons_per_point must be > 0, got {photons_per_point}")
    s = np.clip(np.asarray(spectrum, dtype=float), 0.0, None)
    return np.sqrt(s / photons_per_point)


def apply_shot_noise(
    spectrum: np.ndarray,
    photons_per_point: float,
    seed: int | np.random.Generator,
    exact_poisson: bool = False,
) -> np.ndarray:
    """Return a seeded shot-noise realization of a normalized PL spectrum.

    Parameters
    ----------
    spectrum : np.ndarray
        Normalized PL spectrum (any shape; ~1 off-resonance).
    photons_per_point : float
        Detected photons per frequency point at the off-resonance baseline
        (> 0).
    seed : int or np.random.Generator
        Seed (or generator) for the realization. Fixed seeds give bit-stable
        evaluation sets; per-epoch seeds give train-time augmentation.
    exact_poisson : bool
        If True, draw counts ~ Poisson(N * S) and return ``counts / N``
        (correct in the few-photon regime). Default False: Gaussian
        approximation ``S + sigma(S) * eps``, accurate for ``N * S >> 1``.

    Returns
    -------
    np.ndarray
        Noisy spectrum, same shape as ``spectrum``, dtype float64.
    """
    if photons_per_point <= 0.0:
        raise ValueError(f"photons_per_point must be > 0, got {photons_per_point}")
    rng = seed if isinstance(seed, np.random.Generator) else np.random.default_rng(seed)
    s = np.clip(np.asarray(spectrum, dtype=float), 0.0, None)
    if exact_poisson:
        return rng.poisson(photons_per_point * s) / photons_per_point
    return s + np.sqrt(s / photons_per_point) * rng.standard_normal(s.shape)


def photons_for_dip_snr(dip_depth: float, snr: float) -> float:
    """Photon budget for a target amplitude SNR on a dip of given depth.

    Inverts ``SNR = dip_depth * sqrt(N)`` (baseline-noise approximation):
    ``N = (snr / dip_depth)**2``. Size against the faintest line — e.g.
    ``min(manifest['line_depths'])`` — so every line meets the target.

    Parameters
    ----------
    dip_depth : float
        Dip depth in normalized-PL units (> 0), e.g. from the manifest's
        ``line_depths``.
    snr : float
        Target amplitude signal-to-noise ratio (> 0).

    Returns
    -------
    float
        Required detected photons per frequency point at the baseline.
    """
    if dip_depth <= 0.0:
        raise ValueError(f"dip_depth must be > 0, got {dip_depth}")
    if snr <= 0.0:
        raise ValueError(f"snr must be > 0, got {snr}")
    return (snr / dip_depth) ** 2
