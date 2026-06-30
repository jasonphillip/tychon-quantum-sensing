"""BLUE inversion: per-resonance frequency shifts → 3D lab-frame B vector + covariance.

Once the per-resonance shifts ``δ`` (relative to the zero-field splitting) are associated to
their canonical ``(axis, sign)`` rows, they satisfy

    δ ≈ γ_e · (A · B)

where ``A`` is the 8×3 NV-axis projection matrix fixed by diamond geometry
(:func:`odmr_vector_tracking.vector.geometry.nv_geometry_matrix`). The Best Linear Unbiased
Estimator of ``B`` under additive zero-mean noise with covariance ``Σ`` is

    B_hat = (Aᵀ Σ⁻¹ A)⁻¹ Aᵀ Σ⁻¹ δ           posterior cov = (Aᵀ Σ⁻¹ A)⁻¹

reducing to the Moore–Penrose pseudo-inverse when ``Σ = σ² I``. Mirrors
``odmr_edge_ml.vector.blue_projection``; the estimator is generic over the row count, so it
serves both the 8-line classical path and the learned tracker's 4-projection path
(``Σ projection_i = 0``, pass the 4×3 :data:`~odmr_vector_tracking.vector.geometry.NV_AXES_UNIT`).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    NV_AXES_UNIT,
    axis_projections_from_resonances,
)


@dataclass(frozen=True)
class BluePosteriorVariance:
    """Result of a BLUE inversion.

    Attributes
    ----------
    b_hat
        Recovered lab-frame B-field, shape ``(3,)``, Tesla.
    posterior_covariance
        ``(Aᵀ Σ⁻¹ A)⁻¹`` scaled to field units, shape ``(3, 3)``. The square root of the
        diagonal gives per-axis 1-σ uncertainty.
    """

    b_hat: np.ndarray
    posterior_covariance: np.ndarray


def blue_project(
    delta: np.ndarray,
    A: np.ndarray,
    sigma: np.ndarray | None = None,
) -> BluePosteriorVariance:
    """Recover ``B_hat`` from per-row residuals via weighted least-squares.

    Solves ``delta ≈ A @ B`` for ``B``. Units follow ``delta``/``A``: pass ``delta`` in the
    same units as ``A @ B`` (e.g. ``delta = (f − D) / γ_e`` with ``A`` unitless gives ``B``
    in Tesla).

    Parameters
    ----------
    delta
        Length-``m`` residual vector (``m`` = ``A``'s row count: 8 lines or 4 projections).
    A
        ``m × 3`` projection matrix.
    sigma
        Length-``m`` per-row standard deviations (same units as ``delta``). ``None`` ⇒
        ``Σ = I`` (ordinary least squares = Moore–Penrose pseudo-inverse).

    Raises
    ------
    ValueError
        If ``delta``/``sigma`` have the wrong length or any ``sigma_i`` is non-positive.
    """
    A = np.asarray(A, dtype=np.float64)
    delta = np.asarray(delta, dtype=np.float64).reshape(-1)
    n_rows = A.shape[0]
    if delta.shape != (n_rows,):
        raise ValueError(f"delta must have shape ({n_rows},), got {delta.shape}")

    if sigma is None:
        Aw, dw = A, delta
    else:
        sigma = np.asarray(sigma, dtype=np.float64).reshape(-1)
        if sigma.shape != (n_rows,):
            raise ValueError(f"sigma must have shape ({n_rows},), got {sigma.shape}")
        if not np.all(sigma > 0.0):
            raise ValueError("sigma entries must be strictly positive (Σ must be PD)")
        w = 1.0 / sigma
        Aw = A * w[:, None]
        dw = delta * w

    # Whitened least-squares via lstsq — stable even when Aw is ill-conditioned (e.g. one
    # σ_i ≪ the others). Equivalent to the closed-form (AᵀΣ⁻¹A)⁻¹AᵀΣ⁻¹δ when invertible.
    b_hat, *_ = np.linalg.lstsq(Aw, dw, rcond=None)
    cov = np.linalg.pinv(Aw.T @ Aw)
    return BluePosteriorVariance(b_hat=b_hat, posterior_covariance=cov)


def blue_invert_field(
    resonance_freqs_canonical: np.ndarray,
    gamma_hz_per_t: float = GAMMA_E_HZ_PER_T,
    sigma_hz: np.ndarray | float | None = None,
) -> BluePosteriorVariance:
    """Invert 8 canonically-ordered resonance frequencies to a lab-frame B vector.

    Convenience wrapper for the classical 8-line path. The upstream ``resonance_freqs`` are
    *diagonalized* centers carrying a second-order common-mode shift (3–16·Γ in the few-mT
    regime), so this recovers each axis projection from the **splitting**
    ``(f_+ − f_-)/2 = γ_e·(B·n_i)`` — exact and common-mode-invariant — then inverts the 4
    projections against the 4×3 NV-axis matrix, yielding ``B`` in Tesla. It deliberately does
    **not** use ``f − D`` of single lines (which carries the common-mode shift).

    The caller must have placed the frequencies in canonical ``(axis, sign)`` row order — i.e.
    done the data association. A mis-association (a swapped line landing in the wrong axis pair)
    corrupts that pair's splitting, which is how loss-of-lock at a crossing reaches the vector.

    Parameters
    ----------
    resonance_freqs_canonical
        Length-8 resonance centers (Hz) in canonical row order.
    gamma_hz_per_t
        Gyromagnetic ratio (Hz/T).
    sigma_hz
        Per-line (8,) or scalar frequency 1-σ in Hz; propagated to the per-axis projection
        uncertainty ``σ_proj = √(σ_{2i}² + σ_{2i+1}²) / (2 γ_e)``.

    Returns
    -------
    BluePosteriorVariance
        ``b_hat`` (Tesla) and posterior covariance (Tesla²).
    """
    proj = axis_projections_from_resonances(resonance_freqs_canonical, gamma_hz_per_t)  # (4,)

    sigma = None
    if sigma_hz is not None:
        s = np.broadcast_to(np.asarray(sigma_hz, dtype=np.float64), (8,))
        sigma = np.sqrt(s[0::2] ** 2 + s[1::2] ** 2) / (2.0 * gamma_hz_per_t)
    return blue_project(proj, NV_AXES_UNIT, sigma=sigma)
