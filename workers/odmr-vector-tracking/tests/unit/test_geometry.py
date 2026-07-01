"""Unit tests for the vendored NV geometry + physics constants."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_vector_tracking.vector.geometry import (
    GAMMA_E_HZ_PER_T,
    LINE_AXIS_8,
    LINE_SIGN_8,
    NV_AXES_UNIT,
    ZFS_D_HZ,
    axis_projections_from_resonances,
    common_mode_shift,
    nv_geometry_matrix,
    project_field_onto_axes,
    resonance_frequencies,
    resonance_frequencies_diagonalized,
)


def test_axes_are_unit_norm() -> None:
    assert np.allclose(np.linalg.norm(NV_AXES_UNIT, axis=1), 1.0)


def test_axes_tetrahedral_angle() -> None:
    dots = NV_AXES_UNIT @ NV_AXES_UNIT.T
    off_diag = dots[~np.eye(4, dtype=bool)]
    assert np.allclose(off_diag, -1.0 / 3.0)


def test_geometry_matrix_shape_and_rows() -> None:
    A = nv_geometry_matrix()
    assert A.shape == (8, 3)
    for i in range(4):
        assert np.allclose(A[2 * i], NV_AXES_UNIT[i])
        assert np.allclose(A[2 * i + 1], -NV_AXES_UNIT[i])


def test_geometry_matrix_rank_three() -> None:
    assert np.linalg.matrix_rank(nv_geometry_matrix()) == 3


def test_pinv_roundtrip() -> None:
    A = nv_geometry_matrix()
    rng = np.random.default_rng(0)
    for _ in range(5):
        B = rng.normal(size=3) * 1e-3
        assert np.allclose(np.linalg.pinv(A) @ (A @ B), B, atol=1e-12)


def test_axis_projections_sum_to_zero() -> None:
    # Σ n_i = 0 ⇒ Σ (n_i · B) = 0 for any B (the Σ B_i = 0 closure constraint).
    rng = np.random.default_rng(1)
    B = rng.normal(size=3) * 1e-3
    B_par, _ = project_field_onto_axes(B)
    assert abs(B_par.sum()) < 1e-15


def test_resonance_frequencies_match_linear_zeeman() -> None:
    B = np.array([3e-4, -1.2e-3, 8e-4])
    f = resonance_frequencies(B)
    B_par, _ = project_field_onto_axes(B)
    expected = ZFS_D_HZ + GAMMA_E_HZ_PER_T * LINE_SIGN_8 * B_par[LINE_AXIS_8]
    assert np.allclose(f, expected)
    assert f.shape == (8,)


def test_gamma_is_about_28_ghz_per_tesla() -> None:
    # 28 kHz/µT = 28 GHz/T, within a percent.
    assert abs(GAMMA_E_HZ_PER_T - 28.0e9) / 28.0e9 < 0.02


def test_common_mode_shift_positive_and_formula() -> None:
    b_perp = 4.33e-3  # ~axis0 transverse at 5 mT off-axis bias
    expected = 1.5 * (GAMMA_E_HZ_PER_T * b_perp) ** 2 / ZFS_D_HZ
    assert np.isclose(common_mode_shift(b_perp), expected)
    assert common_mode_shift(b_perp) > 0.0


def test_diagonalized_adds_common_mode_but_preserves_splitting() -> None:
    B = np.array([1.0e-3, 2.0e-3, 4.5e-3])  # generic off-axis few-mT field
    fo = resonance_frequencies(B)
    di = resonance_frequencies_diagonalized(B)
    # Diagonalized centers differ from first-order (common-mode is present, non-trivial).
    assert np.max(np.abs(di - fo)) > 1.0e6
    # ...but each axis's splitting is identical (common-mode cancels).
    for i in range(4):
        split_fo = (fo[2 * i] - fo[2 * i + 1]) / 2
        split_di = (di[2 * i] - di[2 * i + 1]) / 2
        assert np.isclose(split_fo, split_di)


def test_axis_projections_recovered_from_splitting() -> None:
    B = np.array([3e-4, -1.2e-3, 8e-4])
    B_par, _ = project_field_onto_axes(B)
    di = resonance_frequencies_diagonalized(B)  # diagonalized centers (with common-mode)
    proj = axis_projections_from_resonances(di)
    assert np.allclose(proj, B_par, atol=1e-9)  # splitting recovers projections exactly


def test_vendored_geometry_hash_pinned() -> None:
    """Drift guard for the vendored constants that runs on EVERY machine.

    The upstream-parity test below skips wherever ``nv_sensor_sim`` is not importable, so on
    those machines an accidental edit of the vendored geometry/constants would go unnoticed.
    This pin fails on any byte-level change; if a change is *intentional*, re-derive the digest
    and update it together with the upstream parity check.
    """
    import hashlib

    from odmr_vector_tracking.vector.geometry import (
        DD_DT_HZ_PER_K,
        LINE_TRANSITION_8,
    )

    payload = (
        NV_AXES_UNIT.tobytes() + nv_geometry_matrix().tobytes()
        + LINE_AXIS_8.tobytes() + LINE_SIGN_8.tobytes() + LINE_TRANSITION_8.tobytes()
        + np.array([GAMMA_E_HZ_PER_T, ZFS_D_HZ, DD_DT_HZ_PER_K], dtype=np.float64).tobytes()
    )
    digest = hashlib.sha256(payload).hexdigest()
    assert digest == "d9c77b7650ddbd68d6be5bc2d38b69a31caef3f25537a8975963f451d600284d"


def test_geometry_matches_nv_sensor_sim() -> None:
    """Parity guard against the upstream source of truth (skips if not importable)."""
    import sys

    sys.path.insert(0, "~/projects/nv-sensor-sim/src")
    try:
        from nv_sensor_sim.physics.lineshape import (  # type: ignore
            NV_AXES_UNIT as up_axes,
            nv_geometry_matrix as up_geo,
        )
    except Exception as exc:  # pragma: no cover - environment-dependent
        pytest.skip(f"nv_sensor_sim not importable: {exc}")

    assert np.allclose(NV_AXES_UNIT, up_axes, atol=1e-12)
    assert np.allclose(nv_geometry_matrix(), up_geo(), atol=1e-12)
