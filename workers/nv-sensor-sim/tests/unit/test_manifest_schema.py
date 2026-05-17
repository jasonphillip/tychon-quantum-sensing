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


# ---------------------------------------------------------------------------
# Bias-field (vector-readiness) fields: backward compat + validation
# ---------------------------------------------------------------------------


def test_manifest_bias_field_defaults_match_scalar_v3():
    """An unconfigured manifest has zero-bias, unit-amp, no drift = scalar regime."""
    manifest = _make_valid_manifest()
    assert manifest.bias_B0_T == 0.0
    assert tuple(manifest.bias_direction_uvw) == (0.0, 0.0, 1.0)
    assert manifest.concentrator_amplification == 1.0
    assert manifest.magnet_drift_ppm_per_K == 0.0
    assert manifest.bias_B0_range_T is None
    assert manifest.multi_axis_mode is False


def test_manifest_bias_field_roundtrip_path_a():
    """Path A (permanent magnet) bias config survives JSON roundtrip."""
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest(
        bias_B0_T=3.0e-3,
        bias_direction_uvw=(0.0, 0.0, 1.0),
        concentrator_amplification=1.0,
        magnet_drift_ppm_per_K=300.0,
        bias_B0_range_T=(0.5e-3, 5.0e-3),
        multi_axis_mode=True,
    )
    manifest.validate()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

        assert loaded.bias_B0_T == pytest.approx(3.0e-3)
        assert tuple(loaded.bias_direction_uvw) == pytest.approx((0.0, 0.0, 1.0))
        assert loaded.magnet_drift_ppm_per_K == pytest.approx(300.0)
        assert loaded.bias_B0_range_T == pytest.approx((0.5e-3, 5.0e-3))
        assert loaded.multi_axis_mode is True
        # Path A: concentrator_amplification should be unity
        assert loaded.concentrator_amplification == pytest.approx(1.0)


def test_manifest_bias_field_roundtrip_path_b():
    """Path B (flux concentrator) bias config survives JSON roundtrip."""
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest(
        bias_B0_T=1.5e-3,
        bias_direction_uvw=(1.0, 0.3, 0.1),  # off-axis lab direction
        concentrator_amplification=30.0,
        magnet_drift_ppm_per_K=0.0,
        bias_B0_range_T=(0.5e-3, 5.0e-3),
        multi_axis_mode=True,
    )
    manifest.validate()

    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

        assert loaded.concentrator_amplification == pytest.approx(30.0)
        assert tuple(loaded.bias_direction_uvw) == pytest.approx((1.0, 0.3, 0.1))
        # Path B: no magnet drift
        assert loaded.magnet_drift_ppm_per_K == pytest.approx(0.0)


def test_manifest_bias_field_backward_compat():
    """Old manifests without bias-field keys load with scalar-regime defaults."""
    import json
    import tempfile
    from pathlib import Path

    manifest = _make_valid_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)

        # Simulate a v3-era manifest: strip every bias-field key
        with open(path) as f:
            d = json.load(f)
        for key in (
            "bias_B0_T",
            "bias_direction_uvw",
            "concentrator_amplification",
            "magnet_drift_ppm_per_K",
            "bias_B0_range_T",
            "multi_axis_mode",
        ):
            d.pop(key, None)
        with open(path, "w") as f:
            json.dump(d, f)

        loaded = DatasetManifest.from_json(path)
        # All previously-tracked manifest fields must still be intact
        assert loaded.master_seed == manifest.master_seed
        assert loaded.train_seeds == manifest.train_seeds
        assert loaded.freq_range_Hz == pytest.approx(manifest.freq_range_Hz)
        # And the new fields fall back to the scalar-regime defaults
        assert loaded.bias_B0_T == 0.0
        assert tuple(loaded.bias_direction_uvw) == (0.0, 0.0, 1.0)
        assert loaded.concentrator_amplification == 1.0
        assert loaded.magnet_drift_ppm_per_K == 0.0
        assert loaded.bias_B0_range_T is None
        assert loaded.multi_axis_mode is False
        # And the manifest still validates
        loaded.validate()


def test_manifest_rejects_negative_bias_B0():
    """Negative bias magnitude must be rejected."""
    manifest = _make_valid_manifest(bias_B0_T=-1.0e-3)
    with pytest.raises(ValueError, match="bias_B0_T"):
        manifest.validate()


def test_manifest_rejects_negative_concentrator_amplification():
    """Negative concentrator amplification must be rejected."""
    manifest = _make_valid_manifest(concentrator_amplification=-2.0)
    with pytest.raises(ValueError, match="concentrator_amplification"):
        manifest.validate()


def test_manifest_rejects_wrong_length_bias_direction():
    """bias_direction_uvw must be a 3-vector."""
    manifest = _make_valid_manifest(bias_direction_uvw=(1.0, 0.0))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="bias_direction_uvw"):
        manifest.validate()


def test_manifest_rejects_inverted_bias_range():
    """Inverted bias_B0_range_T must be rejected."""
    manifest = _make_valid_manifest(bias_B0_range_T=(5.0e-3, 1.0e-3))
    with pytest.raises(ValueError, match="bias_B0_range_T"):
        manifest.validate()


def test_manifest_units_include_bias_field():
    """Units dict must expose bias-field semantics for downstream consumers."""
    manifest = _make_valid_manifest()
    assert manifest.units.get("bias_field") == "T"
    assert manifest.units.get("concentrator_amplification") == "dimensionless"
    assert manifest.units.get("magnet_drift") == "ppm/K"
