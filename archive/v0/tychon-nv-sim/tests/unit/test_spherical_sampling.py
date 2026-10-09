"""Unit tests for spherical B-field sampling helper."""

from __future__ import annotations

import numpy as np
import pytest


def test_spherical_field_magnitude_in_range():
    """Sampled field magnitude must be within b_mag_range_T."""
    from tychon_nv_sim.pipelines.batch_generate import _sample_spherical_field

    rng = np.random.default_rng(42)
    b_mag_range = (20e-6, 70e-6)

    for _ in range(100):
        B_vec = _sample_spherical_field(rng, b_mag_range)
        b_mag = np.linalg.norm(B_vec)
        assert b_mag_range[0] <= b_mag <= b_mag_range[1], (
            f"B_mag={b_mag} outside range {b_mag_range}"
        )


def test_spherical_field_is_3d_vector():
    """Returned vector must have shape (3,)."""
    from tychon_nv_sim.pipelines.batch_generate import _sample_spherical_field

    rng = np.random.default_rng(0)
    B_vec = _sample_spherical_field(rng, (30e-6, 50e-6))
    assert B_vec.shape == (3,)
    assert B_vec.dtype == np.float64


def test_spherical_field_diverse_orientations():
    """Sampling should produce diverse directions, not just z-axis."""
    from tychon_nv_sim.pipelines.batch_generate import _sample_spherical_field

    rng = np.random.default_rng(123)
    b_mag_range = (40e-6, 60e-6)
    vectors = np.array([_sample_spherical_field(rng, b_mag_range) for _ in range(200)])

    # All three components should have non-trivial variance
    for i, name in enumerate(["Bx", "By", "Bz"]):
        assert np.std(vectors[:, i]) > 1e-6, f"{name} has no variance"

    # Cosine of polar angle (Bz/|B|) should be roughly uniform in [-1, 1]
    b_mags = np.linalg.norm(vectors, axis=1)
    cos_theta = vectors[:, 2] / b_mags
    assert np.min(cos_theta) < -0.5, "No samples in southern hemisphere"
    assert np.max(cos_theta) > 0.5, "No samples in northern hemisphere"


def test_spherical_field_deterministic_with_seed():
    """Same seed must produce identical samples."""
    from tychon_nv_sim.pipelines.batch_generate import _sample_spherical_field

    rng1 = np.random.default_rng(999)
    rng2 = np.random.default_rng(999)
    b_mag_range = (20e-6, 70e-6)

    for _ in range(10):
        v1 = _sample_spherical_field(rng1, b_mag_range)
        v2 = _sample_spherical_field(rng2, b_mag_range)
        np.testing.assert_array_equal(v1, v2)


def test_spherical_field_unit_magnitude():
    """When min == max, all vectors should have the same magnitude."""
    from tychon_nv_sim.pipelines.batch_generate import _sample_spherical_field

    rng = np.random.default_rng(7)
    fixed_mag = 50e-6

    for _ in range(50):
        B_vec = _sample_spherical_field(rng, (fixed_mag, fixed_mag))
        assert np.linalg.norm(B_vec) == pytest.approx(fixed_mag, rel=1e-12)
