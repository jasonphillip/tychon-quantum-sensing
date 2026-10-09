"""Unit tests for the BLUE inversion."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_vector_tracking.vector.blue import blue_invert_field, blue_project
from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    NV_AXES_UNIT,
    ZFS_D_HZ,
    nv_geometry_matrix,
    resonance_frequencies,
    resonance_frequencies_diagonalized,
)


def test_blue_project_roundtrip_8_lines() -> None:
    A = nv_geometry_matrix()
    rng = np.random.default_rng(0)
    B = rng.normal(size=3) * 1e-3
    delta = A @ B
    res = blue_project(delta, A)
    assert np.allclose(res.b_hat, B, atol=1e-12)
    assert res.posterior_covariance.shape == (3, 3)


def test_blue_project_roundtrip_4_projections() -> None:
    # The learned-tracker path: 4 signed axis-projections, 4×3 geometry.
    N = NV_AXES_UNIT
    rng = np.random.default_rng(2)
    B = rng.normal(size=3) * 1e-3
    proj = N @ B
    res = blue_project(proj, N)
    assert np.allclose(res.b_hat, B, atol=1e-12)


def test_blue_invert_field_recovers_B() -> None:
    B = np.array([2e-4, -9e-4, 1.3e-3])
    f = resonance_frequencies(B, zfs_hz=ZFS_D_HZ, gamma_hz_per_t=GAMMA_E_HZ_PER_T)
    res = blue_invert_field(f)
    assert np.allclose(res.b_hat, B, atol=1e-9)


def test_blue_invert_field_is_common_mode_robust() -> None:
    """On diagonalized centers (with the second-order common-mode shift), the splitting-based
    inversion recovers B exactly: the splitting cancels the common-mode."""
    B = np.array([1.0e-3, 2.0e-3, 4.5e-3])
    di = resonance_frequencies_diagonalized(B)
    res = blue_invert_field(di)
    assert np.allclose(res.b_hat, B, atol=1e-9)


def test_single_line_inversion_is_biased_by_common_mode() -> None:
    """The genuinely-wrong path the contract warns against: using a single transition per axis
    (absolute center ``f − D``, no ± pairing) carries the common-mode shift and biases B.

    Note the full 8-line ``(f − D)`` lstsq is *also* robust, because the symmetric common-mode
    cancels in the antisymmetric ± pairing — equivalent to the splitting. The bias appears only
    when the pairing is dropped.
    """
    B = np.array([1.0e-3, 2.0e-3, 4.5e-3])
    di = resonance_frequencies_diagonalized(B)
    plus_lines = di[0::2]  # only the + transition of each axis (rows 2i)
    proj_naive = (plus_lines - ZFS_D_HZ) / GAMMA_E_HZ_PER_T  # = proj_i + cm_i/γ (biased)
    b_naive, *_ = np.linalg.lstsq(NV_AXES_UNIT, proj_naive, rcond=None)
    assert np.linalg.norm(b_naive - B) > 1e-4  # off by many µT — the common-mode error


def test_blue_covariance_symmetric_psd() -> None:
    res = blue_project(np.zeros(8), nv_geometry_matrix())
    cov = res.posterior_covariance
    assert np.allclose(cov, cov.T)
    assert np.all(np.linalg.eigvalsh(cov) >= -1e-12)


def test_blue_weighted_runs() -> None:
    A = nv_geometry_matrix()
    B = np.array([1e-3, 0.0, 0.0])
    delta = A @ B
    sigma = np.ones(8)
    sigma[0] = 10.0  # downweight one line
    res = blue_project(delta, A, sigma=sigma)
    assert res.b_hat.shape == (3,)
    assert np.linalg.norm(res.b_hat - B) < 1e-9


def test_blue_project_bad_length_raises() -> None:
    with pytest.raises(ValueError):
        blue_project(np.zeros(7), nv_geometry_matrix())


def test_blue_invert_field_bad_length_raises() -> None:
    with pytest.raises(ValueError):
        blue_invert_field(np.zeros(6))
