"""BLUE projection: 8 per-resonance scalar ΔB residuals → 3D lab-frame vector.

The vector readout pattern recommended by the SBIR Vector Capability writeup
(``~/projects/tychon-sbir/ToDo/Vector_Capability_Implementation_and_Research_Prompt_2026-05-04.md``
§1.3): once 8 FCNN-v2 instances each predict a scalar ΔB residual on their
own resonance window, the 8-vector ``δ`` of residuals satisfies

    δ ≈ A · B

where ``A`` is the 8×3 NV-axis projection matrix fixed by diamond crystal
geometry (four NV axes × ±B sign pair). The Best Linear Unbiased Estimator
of ``B`` under additive zero-mean noise with covariance ``Σ`` is

    B_hat = (Aᵀ Σ⁻¹ A)⁻¹ Aᵀ Σ⁻¹ δ

with posterior covariance ``(Aᵀ Σ⁻¹ A)⁻¹``. With Σ = σ² I this reduces to
the Moore-Penrose pseudo-inverse ``A⁺ δ``.

The 8×3 ``A`` matrix is sourced from
``nv_sensor_sim.physics.lineshape.nv_geometry_matrix`` to keep one canonical
geometry across the repos. A test guards that the local copy used here
matches that source.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Four NV crystallographic axes in the cubic-diamond lattice, as unit
# vectors in the lab frame. Matches ``nv_sensor_sim.physics.lineshape``;
# the test ``test_A_matches_nv_sensor_sim_canonical`` enforces parity.
_NV_AXES_UNIT = np.array(
    [
        [+1.0, +1.0, +1.0],
        [+1.0, -1.0, -1.0],
        [-1.0, +1.0, -1.0],
        [-1.0, -1.0, +1.0],
    ],
    dtype=np.float64,
) / np.sqrt(3.0)


def nv_axis_geometry_matrix() -> np.ndarray:
    """Return the 8×3 ``A`` projection matrix used by the BLUE inversion.

    Row 2i is ``+n_i`` and row 2i+1 is ``-n_i`` for the four NV axes ``n_i``
    above. The resonance frequency shift on axis ``(i, s)`` under lab
    field ``B`` is ``s · γ_e · (B · n_i)``, so stacking the 8 shifts gives
    ``δ = A · B``.
    """
    A = np.zeros((8, 3), dtype=np.float64)
    for i, n in enumerate(_NV_AXES_UNIT):
        A[2 * i] = n
        A[2 * i + 1] = -n
    return A


@dataclass(frozen=True)
class BluePosteriorVariance:
    """Result of a BLUE projection.

    Attributes
    ----------
    b_hat
        Recovered lab-frame B-field, shape (3,).
    posterior_covariance
        ``(Aᵀ Σ⁻¹ A)⁻¹``, shape (3, 3). Square root of the diagonal gives
        per-axis 1-σ uncertainty.
    """

    b_hat: np.ndarray
    posterior_covariance: np.ndarray


def blue_project(
    delta: np.ndarray,
    A: np.ndarray,
    sigma: np.ndarray | None = None,
) -> BluePosteriorVariance:
    """Recover ``B_hat`` from 8 per-resonance residuals via weighted least-squares.

    Parameters
    ----------
    delta
        Length-8 vector of per-resonance residuals. Same length as ``A``'s row
        count.
    A
        8×3 NV-axis projection matrix (from :func:`nv_axis_geometry_matrix`).
    sigma
        Length-8 per-resonance standard deviations. If ``None``, treats Σ = I
        (ordinary least squares); equivalent to the Moore-Penrose pseudo-inverse.

    Raises
    ------
    ValueError
        If ``delta`` or ``sigma`` have the wrong length, or if any ``sigma_i``
        is non-positive (Σ must be strictly positive-definite).
    """
    A = np.asarray(A, dtype=np.float64)
    delta = np.asarray(delta, dtype=np.float64).reshape(-1)
    n_rows = A.shape[0]
    if delta.shape != (n_rows,):
        raise ValueError(f"delta must have shape ({n_rows},), got {delta.shape}")

    if sigma is None:
        Aw = A
        dw = delta
    else:
        sigma = np.asarray(sigma, dtype=np.float64).reshape(-1)
        if sigma.shape != (n_rows,):
            raise ValueError(f"sigma must have shape ({n_rows},), got {sigma.shape}")
        if not np.all(sigma > 0.0):
            raise ValueError("sigma entries must be strictly positive (Σ must be PD)")
        w = 1.0 / sigma
        Aw = A * w[:, None]
        dw = delta * w

    # Solve the whitened least-squares system via lstsq, which gracefully
    # handles ill-conditioned ``Aw`` (e.g. one σ_i much smaller than the
    # others). This is equivalent to the closed-form
    # ``(AᵀΣ⁻¹A)⁻¹AᵀΣ⁻¹δ`` when ``AᵀΣ⁻¹A`` is invertible, but stable when
    # it isn't.
    b_hat, *_ = np.linalg.lstsq(Aw, dw, rcond=None)

    # Posterior covariance via the pseudo-inverse of ``AᵀΣ⁻¹A``. We use
    # ``pinv`` (not ``inv``) so the answer is well-defined even when one
    # whitened row dominates the spectrum of ``AᵀΣ⁻¹A``.
    AtSinvA = Aw.T @ Aw
    cov = np.linalg.pinv(AtSinvA)

    return BluePosteriorVariance(b_hat=b_hat, posterior_covariance=cov)
