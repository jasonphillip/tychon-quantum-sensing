"""Unit tests for DatasetManifest schema validation."""

from __future__ import annotations

import pytest

from tychon_nv_sim.datasets.schema import DatasetManifest


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
