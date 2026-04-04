"""Unit tests for DatasetManifest schema validation."""

from __future__ import annotations

import pytest

from nv_sensor_sim.datasets.schema import DatasetManifest


def _make_valid_manifest(**overrides) -> DatasetManifest:
    """Create a valid manifest with optional overrides."""
    defaults = dict(
        generator_git_sha="abc123",
        config_hash="def456",
        simos_version="0.2.3",
        qutip_version="5.2.3",
        backend="qutip",
        generated_at="2026-03-11T00:00:00Z",
        master_seed=42,
        train_seeds=[100, 101],
        val_seeds=[200],
        test_seeds=[300, 301],
        n_spectra_train=2,
        n_spectra_val=1,
        n_spectra_test=2,
        train_indices=[0, 1],
        val_indices=[0],
        test_indices=[0, 1],
        n_freq_points=100,
        freq_range_Hz=(2.82e9, 2.92e9),
    )
    defaults.update(overrides)
    return DatasetManifest(**defaults)


def test_manifest_validation_passes_good_data():
    """Valid manifest should pass validation without errors."""
    manifest = _make_valid_manifest()
    manifest.validate()  # Should not raise


def test_manifest_validation_rejects_overlapping_seeds():
    """Overlapping train/test seeds must be rejected."""
    manifest = _make_valid_manifest(
        train_seeds=[100, 101],
        test_seeds=[101, 102],  # 101 overlaps with train
    )
    with pytest.raises(ValueError, match="Train/test seed overlap"):
        manifest.validate()


def test_manifest_json_serialization():
    """Manifest should survive JSON roundtrip."""
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test_manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

        assert loaded.generator_git_sha == manifest.generator_git_sha
        assert loaded.train_seeds == manifest.train_seeds
        assert loaded.freq_range_Hz == pytest.approx(manifest.freq_range_Hz)


def test_manifest_units_all_si():
    """Manifest units should include required SI fields."""
    manifest = _make_valid_manifest()
    assert "frequency" in manifest.units
    assert manifest.units["frequency"] == "Hz"
    assert "magnetic_field" in manifest.units
    assert manifest.units["magnetic_field"] == "T"
    assert "temperature" in manifest.units
    assert manifest.units["temperature"] == "K"


def test_manifest_rejects_mismatched_seed_count():
    """Seed count must match split size."""
    manifest = _make_valid_manifest(
        train_seeds=[100],  # Only 1 seed but n_spectra_train=2
    )
    with pytest.raises(ValueError, match="train_seeds length"):
        manifest.validate()


def test_manifest_validation_rejects_train_val_overlap():
    """Overlapping train/val seeds must be rejected."""
    manifest = _make_valid_manifest(
        train_seeds=[100, 101],
        val_seeds=[101],  # 101 overlaps with train
    )
    with pytest.raises(ValueError, match="Train/val seed overlap"):
        manifest.validate()


def test_manifest_validation_rejects_val_test_overlap():
    """Overlapping val/test seeds must be rejected."""
    manifest = _make_valid_manifest(
        val_seeds=[200],
        test_seeds=[200, 301],  # 200 overlaps with val
    )
    with pytest.raises(ValueError, match="Val/test seed overlap"):
        manifest.validate()


def test_manifest_rejects_invalid_range():
    """Parameter ranges with min > max should be rejected."""
    manifest = _make_valid_manifest(
        freq_range_Hz=(2.92e9, 2.82e9),  # Reversed
    )
    with pytest.raises(ValueError, match="freq_range_Hz"):
        manifest.validate()


def test_manifest_spherical_field_roundtrip():
    """Manifest with spherical field sampling survives JSON roundtrip."""
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest(
        field_sampling="spherical",
        b_mag_range_T=(20e-6, 70e-6),
    )
    manifest.validate()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

        assert loaded.field_sampling == "spherical"
        assert loaded.b_mag_range_T == pytest.approx((20e-6, 70e-6))


def test_manifest_z_only_backward_compat():
    """Manifests without field_sampling field default to z_only."""
    import json
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)

        # Simulate old manifest: strip field_sampling and b_mag_range_T
        with open(path) as f:
            d = json.load(f)
        d.pop("field_sampling", None)
        d.pop("b_mag_range_T", None)
        with open(path, "w") as f:
            json.dump(d, f)

        loaded = DatasetManifest.from_json(path)
        assert loaded.field_sampling == "z_only"
        assert loaded.b_mag_range_T is None


def test_manifest_spherical_validates_b_mag_range():
    """Spherical mode with inverted b_mag_range should fail validation."""
    manifest = _make_valid_manifest(
        field_sampling="spherical",
        b_mag_range_T=(70e-6, 20e-6),  # Inverted
    )
    with pytest.raises(ValueError, match="b_mag_range_T"):
        manifest.validate()


def test_manifest_inverse_crime_fields_roundtrip():
    """Manifest with shifted test ranges survives JSON roundtrip."""
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest(
        inverse_crime_shift=True,
        test_p1_concentration_range_ppm=(50.0, 400.0),
        test_temperature_range_K=(285.0, 340.0),
        test_b1_gradient_range=(0.06, 0.36),
        test_b_perp_range_T=(0.0, 60e-6),
    )
    manifest.validate()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

        assert loaded.inverse_crime_shift is True
        assert loaded.test_p1_concentration_range_ppm == pytest.approx((50.0, 400.0))
        assert loaded.test_temperature_range_K == pytest.approx((285.0, 340.0))
        assert loaded.test_b1_gradient_range == pytest.approx((0.06, 0.36))
        assert loaded.test_b_perp_range_T == pytest.approx((0.0, 60e-6))


def test_manifest_inverse_crime_backward_compat():
    """Old manifests without inverse-crime fields load with defaults."""
    import json
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)

        # Simulate old manifest: strip inverse-crime fields
        with open(path) as f:
            d = json.load(f)
        for key in (
            "inverse_crime_shift",
            "test_p1_concentration_range_ppm",
            "test_temperature_range_K",
            "test_b1_gradient_range",
            "test_b_perp_range_T",
        ):
            d.pop(key, None)
        with open(path, "w") as f:
            json.dump(d, f)

        loaded = DatasetManifest.from_json(path)
        assert loaded.inverse_crime_shift is False
        assert loaded.test_p1_concentration_range_ppm is None
        assert loaded.test_temperature_range_K is None


def test_manifest_rejects_invalid_test_range():
    """Inverted test ranges should fail validation."""
    manifest = _make_valid_manifest(
        inverse_crime_shift=True,
        test_p1_concentration_range_ppm=(400.0, 50.0),  # Inverted
    )
    with pytest.raises(ValueError, match="test_p1_concentration_range_ppm"):
        manifest.validate()


def test_shift_range_moves_mean_and_widens():
    """_shift_range should shift midpoint up and widen the interval."""
    from nv_sensor_sim.pipelines.batch_generate import _shift_range

    lo, hi = 10.0, 20.0
    new_lo, new_hi = _shift_range(lo, hi)

    orig_mean = (lo + hi) / 2.0
    orig_width = hi - lo
    new_mean = (new_lo + new_hi) / 2.0
    new_width = new_hi - new_lo

    # Mean shifted up by 12.5%
    assert new_mean == pytest.approx(orig_mean * 1.125)
    # Width expanded by 20%
    assert new_width == pytest.approx(orig_width * 1.2)


def test_shift_range_respects_floor():
    """_shift_range should clamp the lower bound at the floor."""
    from nv_sensor_sim.pipelines.batch_generate import _shift_range

    # A range near zero: shifting could produce negative lower bound
    lo, hi = 0.0, 10.0
    new_lo, new_hi = _shift_range(lo, hi, floor=0.0)
    assert new_lo >= 0.0
