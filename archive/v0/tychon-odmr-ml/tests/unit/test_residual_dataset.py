"""Tests for the residual dataset construction."""

import numpy as np
import torch

from tychon_odmr_ml.evaluation.residual_dataset import (
    _make_anchor,
    _normalize_symmetric,
)


def test_normalize_symmetric_range():
    """Output should be in [-1, 1]."""
    spectra = np.random.rand(10, 100) * 0.03 + 0.97  # ODMR-like range
    normed = _normalize_symmetric(spectra)
    assert normed.min() >= -1.0 - 1e-7
    assert normed.max() <= 1.0 + 1e-7


def test_normalize_symmetric_endpoints():
    """Min maps to -1, max maps to +1 per spectrum."""
    spectra = np.array([[0.97, 0.98, 0.99, 1.0, 0.975]])
    normed = _normalize_symmetric(spectra)
    assert abs(normed[0, 0] - (-1.0)) < 1e-6  # min → -1
    assert abs(normed[0, 3] - 1.0) < 1e-6  # max → +1


def test_normalize_flat_spectrum():
    """Flat spectrum doesn't produce NaN."""
    spectra = np.ones((2, 100))
    normed = _normalize_symmetric(spectra)
    assert np.isfinite(normed).all()


def test_anchor_shape():
    """Anchor output shape matches (N, n_freq)."""
    lock_bins = np.array([30, 50, 70])
    anchor = _make_anchor(lock_bins, n_freq=100, sigma=1.5)
    assert anchor.shape == (3, 100)


def test_anchor_peak_at_lock_bin():
    """Gaussian peak should be at the lock bin."""
    lock_bins = np.array([50])
    anchor = _make_anchor(lock_bins, n_freq=100, sigma=1.5)
    assert anchor[0].argmax() == 50


def test_anchor_peak_value():
    """Peak should be 1.0 (Gaussian at center = 1)."""
    lock_bins = np.array([50])
    anchor = _make_anchor(lock_bins, n_freq=100, sigma=1.5)
    assert abs(anchor[0, 50] - 1.0) < 1e-6


def test_anchor_decays():
    """Values should decay away from the peak."""
    lock_bins = np.array([50])
    anchor = _make_anchor(lock_bins, n_freq=100, sigma=1.5)
    assert anchor[0, 50] > anchor[0, 52] > anchor[0, 55]
