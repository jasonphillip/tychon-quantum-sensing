"""Unit tests for the 8-resonance window-slicing utility."""

from __future__ import annotations

import numpy as np
import pytest

from odmr_edge_ml.vector.blue_projection import nv_axis_geometry_matrix
from odmr_edge_ml.vector.windowing import (
    NV_AXES_UNIT,
    NV_GYROMAGNETIC_RATIO_HZ_T,
    NV_ZERO_FIELD_SPLITTING_HZ,
    build_windows_for_axis_sign,
    compute_axis_projections,
    dip_frequency_hz,
    slice_resonance_window,
)


# ---------------------------------------------------------------------------
# Geometry agreement with the BLUE matrix


def test_nv_axes_match_blue_top_half() -> None:
    """The 4 NV axes used for windowing must match rows 0, 2, 4, 6 of the
    BLUE 8x3 matrix (the +n_i rows). Otherwise per-channel projections won't
    line up with the BLUE inversion's row ordering."""
    A = nv_axis_geometry_matrix()
    assert np.allclose(NV_AXES_UNIT, A[::2], atol=1e-12)


# ---------------------------------------------------------------------------
# Projection


def test_axis_projection_shape() -> None:
    B = np.random.default_rng(0).standard_normal((10, 3)) * 1e-3
    proj = compute_axis_projections(B)
    assert proj.shape == (10, 4)


def test_axis_projection_aligned_with_axis_zero() -> None:
    """B parallel to axis 0 gives projection (|B|, 0_ish, 0_ish, 0_ish)."""
    # Axis 0 = (1,1,1)/√3; build B along that direction
    B = np.array([[1e-3, 1e-3, 1e-3]]) / np.sqrt(3)
    proj = compute_axis_projections(B)
    assert np.isclose(proj[0, 0], 1e-3, atol=1e-12)
    # Other axes pick up smaller projections (they're not orthogonal)
    other = proj[0, 1:]
    assert np.all(np.abs(other) < 1e-3 - 1e-9)


def test_axis_projection_rejects_bad_shape() -> None:
    with pytest.raises(ValueError, match="must be"):
        compute_axis_projections(np.zeros((4,)))


# ---------------------------------------------------------------------------
# Dip frequency


def test_dip_frequency_zero_field_returns_D() -> None:
    f = dip_frequency_hz(np.zeros(5), sign=+1)
    assert np.allclose(f, NV_ZERO_FIELD_SPLITTING_HZ, atol=1e-3)


def test_dip_frequency_plus_one_mT_along_axis() -> None:
    """At B·n = 1 mT, sign=+1 dip is at D + 28.024 MHz."""
    f = dip_frequency_hz(np.array([1e-3]), sign=+1)
    assert np.isclose(f[0], NV_ZERO_FIELD_SPLITTING_HZ + NV_GYROMAGNETIC_RATIO_HZ_T * 1e-3)


def test_dip_frequency_sign_minus_one_flips() -> None:
    fp = dip_frequency_hz(np.array([1e-3]), sign=+1)
    fm = dip_frequency_hz(np.array([1e-3]), sign=-1)
    assert np.isclose(
        (fp[0] - NV_ZERO_FIELD_SPLITTING_HZ),
        -(fm[0] - NV_ZERO_FIELD_SPLITTING_HZ),
        atol=1.0,
    )


def test_dip_frequency_rejects_invalid_sign() -> None:
    with pytest.raises(ValueError, match="sign"):
        dip_frequency_hz(np.zeros(1), sign=0)


# ---------------------------------------------------------------------------
# Window slicing


def _toy_grid_and_spectra() -> tuple[np.ndarray, np.ndarray]:
    """8-row toy: 800-bin grid 2.83–2.91 GHz, each row = `np.arange(800)` so
    we can verify exactly which slice came out."""
    freq = np.linspace(2.83e9, 2.91e9, 800)
    sp = np.tile(np.arange(800, dtype=np.float64), (8, 1))
    return freq, sp


def test_slice_centres_window_on_target() -> None:
    freq, sp = _toy_grid_and_spectra()
    # Target the centre of the grid → window covers bins [350, 450)
    target_freqs = np.full(8, 0.5 * (freq[0] + freq[-1]))
    out = slice_resonance_window(sp, freq, target_freqs, window_size=100)
    assert out.windows.shape == (8, 100)
    assert out.valid_mask.all()
    # Every row should be np.arange from 350 to 450 (give or take 1 for
    # round-off in the linspace-vs-bin centre lookup)
    row0 = out.windows[0]
    assert row0[0] in {349.0, 350.0}
    assert row0[-1] in {448.0, 449.0}


def test_slice_zero_fills_out_of_bounds_left() -> None:
    freq, sp = _toy_grid_and_spectra()
    # Target near the lower edge: window of 100 around bin 10 → starts at -40
    target_freqs = np.full(8, freq[10])
    out = slice_resonance_window(sp, freq, target_freqs, window_size=100)
    assert (~out.valid_mask).all()
    assert (out.windows == 0).all()
    assert (out.centre_bins == -1).all()


def test_slice_zero_fills_out_of_bounds_right() -> None:
    freq, sp = _toy_grid_and_spectra()
    target_freqs = np.full(8, freq[795])  # window would end at 845, > 800
    out = slice_resonance_window(sp, freq, target_freqs, window_size=100)
    assert (~out.valid_mask).all()


def test_slice_mixed_valid_and_invalid() -> None:
    freq, sp = _toy_grid_and_spectra()
    targets = freq[[400, 5, 400, 795, 600, 400, 5, 600]]
    out = slice_resonance_window(sp, freq, targets, window_size=100)
    # Rows 0,2,4,5,7 are valid; rows 1,3,6 are not
    expected = np.array([True, False, True, False, True, True, False, True])
    assert np.array_equal(out.valid_mask, expected)


def test_slice_rejects_odd_window_size() -> None:
    freq, sp = _toy_grid_and_spectra()
    with pytest.raises(ValueError, match="window_size"):
        slice_resonance_window(sp, freq, np.full(8, freq[400]), window_size=101)


def test_slice_rejects_grid_mismatch() -> None:
    freq, sp = _toy_grid_and_spectra()
    with pytest.raises(ValueError, match="freq_grid"):
        slice_resonance_window(sp, freq[:799], np.full(8, freq[400]), window_size=100)


# ---------------------------------------------------------------------------
# End-to-end axis-sign window builder


def test_build_window_zero_field_centres_on_D() -> None:
    freq = np.linspace(2.83e9, 2.91e9, 800)
    sp = np.zeros((4, 800))
    labels = np.zeros((4, 3))
    out = build_windows_for_axis_sign(
        sp, labels, freq, axis_idx=0, sign=+1, window_size=100,
    )
    # At B=0, both signs collapse on D = 2.87 GHz → bin index around 500
    assert out.valid_mask.all()
    # Per axis label is signed projection in µT — at B=0 it's all zero
    assert np.allclose(out.b_proj_uT, 0.0)


def test_build_window_axis_aligned_field() -> None:
    """B = 1 mT along NV axis 0 → for (axis=0, sign=+1), label = +1000 µT.

    Dip is at D + 28 MHz; with 800-pt grid over 80 MHz spanning ±40 MHz from
    D, that bin is at ~350+700 = sample-dependent; check the label and
    valid_mask only."""
    freq = np.linspace(2.83e9, 2.91e9, 800)
    sp = np.zeros((1, 800))
    labels = (1e-3 * NV_AXES_UNIT[0]).reshape(1, 3)  # 1 mT along axis 0
    out_plus = build_windows_for_axis_sign(sp, labels, freq, axis_idx=0, sign=+1)
    out_minus = build_windows_for_axis_sign(sp, labels, freq, axis_idx=0, sign=-1)
    assert np.isclose(out_plus.b_proj_uT[0], 1000.0, atol=1e-6)
    assert np.isclose(out_minus.b_proj_uT[0], -1000.0, atol=1e-6)
    # +1 dip at D + 28 MHz → bin near (28/100)*800 above centre = ~280 bins
    # right of bin 400 → bin ~680, window [630..730) in bounds
    assert out_plus.valid_mask[0]
    # -1 dip at D - 28 MHz → bin ~120, window [70..170) in bounds
    assert out_minus.valid_mask[0]


def test_build_window_label_matches_axis_sign_pair_for_blue() -> None:
    """Concatenating the 8 b_proj_uT values for one spectrum gives the
    δ-vector that BLUE consumes. Sanity-check that A·B reconstructs δ to
    high precision under noiseless conditions."""
    rng = np.random.default_rng(0)
    B = rng.standard_normal((1, 3)) * 1e-3  # 1 mT-scale field
    labels = B
    freq = np.linspace(2.83e9, 2.91e9, 800)
    sp = np.zeros((1, 800))
    delta = []
    for axis_idx in range(4):
        for sign in (+1, -1):
            out = build_windows_for_axis_sign(
                sp, labels, freq, axis_idx=axis_idx, sign=sign,
            )
            delta.append(out.b_proj_uT[0])
    delta = np.array(delta)  # (8,) in µT
    # The BLUE A matrix is unit-norm rows; A @ B (in µT) should equal δ
    A = nv_axis_geometry_matrix()
    expected = (A @ B[0]) * 1e6  # T → µT
    assert np.allclose(delta, expected, atol=1e-6)
