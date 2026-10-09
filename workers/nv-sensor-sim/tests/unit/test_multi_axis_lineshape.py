"""Unit tests for the 4-axis bias-amplified ODMR lineshape generator.

Covers the vector-readiness extension introduced for the Phase-II
magnetometer upgrade. The single-axis (scalar) generator is exercised
elsewhere; here we verify:

1. The 8x3 geometry matrix A is fixed by the NV crystal lattice and has
   full column rank (so least-squares inversion B_hat = pinv(A) @ delta works).
2. ``project_field_onto_axes`` returns the expected per-axis decomposition,
   in particular that B_lab = sum_i (B_par_i n_i + B_perp_i_vec).
3. At zero bias the multi-axis generator reproduces the legacy single-axis
   scalar spectrum (within numerical tolerance) — backwards compat for the
   no-bias regime.
4. At ~1 mT bias along an off-symmetry direction, the multi-axis spectrum
   resolves 8 distinct resonance positions at the predicted frequencies.
"""

from __future__ import annotations

import numpy as np
import pytest

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig
from nv_sensor_sim.physics.lineshape import (
    NV_AXES_UNIT,
    generate_multi_axis_spectrum,
    nv_geometry_matrix,
    project_field_onto_axes,
)


def test_nv_axes_are_unit_vectors():
    """Each NV crystallographic axis must be normalized."""
    norms = np.linalg.norm(NV_AXES_UNIT, axis=1)
    np.testing.assert_allclose(norms, np.ones(4), atol=1e-12)


def test_nv_axes_tetrahedral_dot_products():
    """Pairwise dot products of distinct NV axes are -1/3 (tetrahedral angle)."""
    for i in range(4):
        for j in range(i + 1, 4):
            np.testing.assert_allclose(
                NV_AXES_UNIT[i] @ NV_AXES_UNIT[j], -1.0 / 3.0, atol=1e-12
            )


def test_geometry_matrix_shape_and_rank():
    """A is 8x3, full column rank (rank 3) so pinv(A) recovers vector B."""
    A = nv_geometry_matrix()
    assert A.shape == (8, 3)
    assert np.linalg.matrix_rank(A) == 3
    # Sanity: even rows are +n_i, odd rows are -n_i
    for i in range(4):
        np.testing.assert_allclose(A[2 * i], NV_AXES_UNIT[i], atol=1e-12)
        np.testing.assert_allclose(A[2 * i + 1], -NV_AXES_UNIT[i], atol=1e-12)


def test_geometry_matrix_inverts_synthetic_signal():
    """If delta = A @ B_true, then pinv(A) @ delta recovers B_true."""
    rng = np.random.default_rng(7)
    A = nv_geometry_matrix()
    for _ in range(8):
        B_true = rng.uniform(-1e-3, 1e-3, size=3)
        delta = A @ B_true
        B_hat = np.linalg.pinv(A) @ delta
        np.testing.assert_allclose(B_hat, B_true, atol=1e-12)


def test_project_field_decomposition_identity():
    """B_lab = B_par_i n_i + B_perp_i_vec exactly for each axis."""
    rng = np.random.default_rng(11)
    for _ in range(5):
        B_lab = rng.uniform(-2e-3, 2e-3, size=3)
        B_par, B_perp_mag = project_field_onto_axes(B_lab)
        for i in range(4):
            B_perp_vec = B_lab - B_par[i] * NV_AXES_UNIT[i]
            # Decomposition reconstructs B_lab
            recon = B_par[i] * NV_AXES_UNIT[i] + B_perp_vec
            np.testing.assert_allclose(recon, B_lab, atol=1e-15)
            # Reported magnitude matches the vector norm
            np.testing.assert_allclose(
                B_perp_mag[i], np.linalg.norm(B_perp_vec), atol=1e-15
            )
            # And the perpendicular component is genuinely perpendicular
            np.testing.assert_allclose(
                B_perp_vec @ NV_AXES_UNIT[i], 0.0, atol=1e-15
            )


def test_zero_bias_multi_axis_matches_single_axis():
    """At zero lab-field, all 4 axes give the same spectrum as the single-axis call.

    This pins the backward-compat property: any v3-era dataset config that uses
    B_lab = 0 (or equivalently bias_B0_T = 0) must produce the legacy lineshape.
    """
    cfg = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, 0.0]),
        n_freq_points=400,
        mw_freq_range_Hz=(2.85e9, 2.89e9),
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=10.0,
    )
    adapter = SimOSAdapter(cfg)

    freqs_single, signal_single = adapter.generate_odmr_spectrum(
        B_field=np.array([0.0, 0.0, 0.0])
    )
    freqs_multi, signal_multi = generate_multi_axis_spectrum(
        adapter, np.array([0.0, 0.0, 0.0])
    )

    np.testing.assert_allclose(freqs_multi, freqs_single, atol=1e-3)
    np.testing.assert_allclose(signal_multi, signal_single, atol=1e-6)


def test_zero_signal_with_bias_along_111_gives_partial_degeneracy():
    """Bias along [1,1,1]/sqrt(3) projects equally onto only ONE NV axis (the [111]
    one); the other three axes share a common smaller projection.

    Result: 4 dip pairs, but with 3 pairs degenerate -> 2 distinct dip positions
    on each side of D = 2.87 GHz, i.e. 4 unique resonance positions, not 8.
    """
    B_bias = 1.0e-3 * np.array([1.0, 1.0, 1.0]) / np.sqrt(3.0)
    B_par, _ = project_field_onto_axes(B_bias)
    # Axis 0 ([1,1,1]/sqrt(3)) gets full projection 1 mT; the rest get -1/3 mT
    np.testing.assert_allclose(B_par[0], 1.0e-3, atol=1e-12)
    np.testing.assert_allclose(B_par[1:], [-1.0e-3 / 3.0] * 3, atol=1e-12)


def _detect_dips(spectrum: np.ndarray, prominence: float = 5e-5) -> np.ndarray:
    """Local-minima detection via scipy.signal.find_peaks on (1 - spectrum)."""
    from scipy.signal import find_peaks

    dip_indices, _ = find_peaks(1.0 - spectrum, prominence=prominence)
    return dip_indices


def test_off_axis_bias_at_1mT_resolves_eight_resonances():
    """At ~1 mT bias along an off-symmetry direction, all 8 NV resonances resolve.

    Predicted positions (linear Zeeman): f_{i,±} = D ± gamma_e * |B_par_i|.
    The SimOS eigenvalue generator includes off-diagonal transverse mixing, so
    detected dips can shift by a few MHz from the linear prediction; the test
    requires that 8 distinct dips are detected and that they cluster around
    the predicted positions to within ~3 MHz tolerance.
    """
    # Off-symmetry direction so all 4 |B_par_i| are distinct
    direction = np.array([1.0, 0.3, 0.1])
    direction = direction / np.linalg.norm(direction)
    B_lab = 1.0e-3 * direction  # 1 mT total

    cfg = SimulationConfig(
        B_field_T=B_lab,
        n_freq_points=600,
        mw_freq_range_Hz=(2.83e9, 2.91e9),
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=10.0,
    )
    adapter = SimOSAdapter(cfg)
    freqs, spectrum = generate_multi_axis_spectrum(adapter, B_lab)

    dip_idx = _detect_dips(spectrum, prominence=5e-5)
    assert len(dip_idx) == 8, (
        f"Expected 8 resolved resonances at 1 mT off-axis, got {len(dip_idx)}"
    )

    # Linear-Zeeman prediction per axis
    from simos.systems import NV

    gamma_e_hz = abs(NV.yNV) / (2.0 * np.pi)
    B_par, _ = project_field_onto_axes(B_lab)
    D = 2.87e9
    predicted = sorted(
        [D + s * gamma_e_hz * abs(bp) for bp in B_par for s in (+1, -1)]
    )
    detected = sorted(float(freqs[i]) for i in dip_idx)

    for f_pred, f_obs in zip(predicted, detected):
        assert abs(f_pred - f_obs) < 3.0e6, (
            f"Detected dip at {f_obs / 1e6:.2f} MHz is > 3 MHz from "
            f"predicted {f_pred / 1e6:.2f} MHz"
        )


def test_multi_axis_spectrum_normalized_off_resonance():
    """PL signal should equal 1.0 (within tolerance) far from any resonance."""
    direction = np.array([1.0, 0.3, 0.1])
    direction = direction / np.linalg.norm(direction)
    B_lab = 1.0e-3 * direction

    # Pick a frequency window above the highest predicted dip
    cfg = SimulationConfig(
        B_field_T=B_lab,
        n_freq_points=20,
        mw_freq_range_Hz=(3.05e9, 3.10e9),
        use_optics=False,
        include_nitrogen=False,
        p1_concentration_ppm=10.0,
    )
    adapter = SimOSAdapter(cfg)
    with pytest.warns(UserWarning, match="Grid aliasing"):
        _, spectrum = generate_multi_axis_spectrum(adapter, B_lab)
    np.testing.assert_allclose(spectrum, 1.0, atol=1e-3)
