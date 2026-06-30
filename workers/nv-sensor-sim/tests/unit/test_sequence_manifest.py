"""Unit tests for time-series (sequence) DatasetManifest fields and validation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nv_sensor_sim.datasets.schema import DatasetManifest


def _make_sequence_manifest(**overrides) -> DatasetManifest:
    """Create a valid sequence manifest with optional overrides."""
    defaults = dict(
        generator_git_sha="abc123",
        config_hash="def456",
        simos_version="0.2.3",
        qutip_version="5.2.3",
        generated_at="2026-06-29T00:00:00Z",
        contract_version="v1",
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
        n_freq_points=951,
        freq_range_Hz=(2.66e9, 3.07e9),
        sequence_mode=True,
        n_timesteps=128,
        dt_s=1.0e-3,
        n_lines=8,
        hyperfine=False,
        linewidth_Hz=1.5e6,
        collision_threshold_linewidths=1.0,
        bias_B0_T=5.0e-3,
        bias_direction_uvw=(0.2, 0.1, 1.0),
        sweep_description="linear ramp",
    )
    defaults.update(overrides)
    return DatasetManifest(**defaults)


def test_sequence_manifest_validates():
    _make_sequence_manifest().validate()  # should not raise


def test_sequence_manifest_json_roundtrip():
    """All sequence fields survive a JSON round-trip and revalidate."""
    manifest = _make_sequence_manifest()
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        manifest.to_json(path)
        loaded = DatasetManifest.from_json(path)

    assert loaded.contract_version == "v1"
    assert loaded.sequence_mode is True
    assert loaded.n_timesteps == 128
    assert loaded.dt_s == 1.0e-3
    assert loaded.n_lines == 8
    assert loaded.hyperfine is False
    assert loaded.linewidth_Hz == 1.5e6
    assert loaded.collision_threshold_linewidths == 1.0
    assert loaded.bias_direction_uvw == (0.2, 0.1, 1.0)
    assert loaded.sweep_description == "linear ramp"
    loaded.validate()


def test_sequence_manifest_units_include_resonance_and_linewidth():
    units = _make_sequence_manifest().units
    assert units["resonance_frequency"] == "Hz"
    assert units["linewidth"] == "Hz"


def test_sequence_seed_separation_enforced():
    """Train/test seed overlap is rejected (shared validation)."""
    manifest = _make_sequence_manifest(train_seeds=[100, 101], test_seeds=[101, 102])
    with pytest.raises(ValueError, match="Train/test seed overlap"):
        manifest.validate()


def test_sequence_requires_positive_timesteps():
    with pytest.raises(ValueError, match="n_timesteps"):
        _make_sequence_manifest(n_timesteps=0).validate()


def test_sequence_requires_positive_dt():
    with pytest.raises(ValueError, match="dt_s"):
        _make_sequence_manifest(dt_s=0.0).validate()


def test_sequence_requires_positive_linewidth():
    with pytest.raises(ValueError, match="linewidth_Hz"):
        _make_sequence_manifest(linewidth_Hz=0.0).validate()


def test_n_lines_hyperfine_consistency():
    """L must be 8 (electronic) or 24 (with hyperfine)."""
    with pytest.raises(ValueError, match="n_lines"):
        _make_sequence_manifest(hyperfine=True, n_lines=8).validate()
    _make_sequence_manifest(hyperfine=True, n_lines=24).validate()  # consistent


def test_static_manifest_backward_compat():
    """An old static manifest with no sequence fields loads with safe defaults."""
    old = dict(
        master_seed=1,
        train_seeds=[1],
        val_seeds=[],
        test_seeds=[],
        n_spectra_train=1,
        n_spectra_val=0,
        n_spectra_test=0,
        train_indices=[0],
        val_indices=[],
        test_indices=[],
        n_freq_points=100,
        freq_range_Hz=[2.82e9, 2.92e9],
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps(old))
        loaded = DatasetManifest.from_json(path)

    assert loaded.sequence_mode is False
    assert loaded.contract_version == ""  # additive default on legacy manifests
    assert loaded.n_lines == 8
    loaded.validate()  # static path: sequence checks skipped
