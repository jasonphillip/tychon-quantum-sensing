"""Spectrum-derived field anchors preserve the observable ODMR lines."""

import numpy as np
import pytest

from odmr_edge_ml.vector.anchors import coarse_fit_field, coarse_fit_lock_bins, oracle_lock_bins
from experiments.vector_v1_train import _prepare_channel


def _lines(fields, grid):
    return np.sort(np.stack([
        oracle_lock_bins(fields, grid, axis, sign)
        for axis in range(4) for sign in (+1, -1)
    ], axis=1), axis=1)


def test_coarse_fit_recovers_synthetic_line_sets():
    grid = np.linspace(2.70e9, 3.04e9, 800)
    n_dirs = 240
    indices = np.array([21, 86, 193])
    z = 1.0 - (indices + 0.5) / n_dirs
    theta = indices * np.pi * (3.0 - np.sqrt(5.0))
    radial = np.sqrt(1.0 - z * z)
    directions = np.stack([radial * np.cos(theta), radial * np.sin(theta), z], axis=1)
    mags = np.array([1e-3, 2.5e-3, 4e-3])
    fields = directions * mags[:, None]
    true_lines = _lines(fields, grid)
    sample_bins = np.arange(grid.size)
    spectra = 1.0 - np.sum(
        0.14 / (1.0 + ((sample_bins[None, None, :] - true_lines[:, :, None]) / 1.2) ** 2),
        axis=1,
    )

    fitted = coarse_fit_field(spectra, grid, n_dirs=n_dirs, mags_T=mags)
    assert fitted.shape == (3, 3)
    assert np.all(np.abs(_lines(fitted, grid) - true_lines) <= 3)
    for axis in range(4):
        for sign in (+1, -1):
            np.testing.assert_array_equal(
                coarse_fit_lock_bins(fitted, grid, axis, sign),
                oracle_lock_bins(fitted, grid, axis, sign),
            )


def test_coarse_fit_recovers_shallow_noisy_line_sets():
    grid = np.linspace(2.70e9, 3.04e9, 800)
    n_dirs = 120
    indices = np.array([11, 47, 96])
    z = 1.0 - (indices + 0.5) / n_dirs
    theta = indices * np.pi * (3.0 - np.sqrt(5.0))
    radial = np.sqrt(1.0 - z * z)
    directions = np.stack([radial * np.cos(theta), radial * np.sin(theta), z], axis=1)
    mags = np.array([1e-3, 2.5e-3, 4e-3])
    true_lines = _lines(directions * mags[:, None], grid)
    sample_bins = np.arange(grid.size)
    spectra = 1.0 - np.sum(
        0.005 / (1.0 + ((sample_bins[None, None, :] - true_lines[:, :, None]) / 3.0) ** 2),
        axis=1,
    )
    spectra += np.random.default_rng(20261009).normal(0.0, 0.0005, spectra.shape)

    fitted = coarse_fit_field(spectra, grid, n_dirs=n_dirs, mags_T=mags)
    assert np.all(np.abs(_lines(fitted, grid) - true_lines) <= 3)


def test_coarse_fit_marks_no_dip_fallback():
    grid = np.linspace(2.70e9, 3.04e9, 800)
    with pytest.warns(RuntimeWarning, match="No dips found"):
        fitted = coarse_fit_field(np.ones((1, 800)), grid, method="chamfer", n_dirs=10,
                                  mags_T=np.array([1e-3, 2e-3]))
    np.testing.assert_allclose(np.linalg.norm(fitted, axis=1), [1e-3])


def test_training_channel_uses_spectrum_field_for_anchor():
    grid = np.linspace(2.70e9, 3.04e9, 800)
    spectrum = np.ones((1, 800))
    label = np.zeros((1, 3))
    fitted = np.array([[0.0, 0.0, 2e-3]])
    _, bins, _, _, _ = _prepare_channel(
        spectrum, label, grid, 0, +1, 800,
        anchor_source="coarse_fit", coarse_fields_T=fitted,
    )
    np.testing.assert_array_equal(bins, oracle_lock_bins(fitted, grid, 0, +1))
