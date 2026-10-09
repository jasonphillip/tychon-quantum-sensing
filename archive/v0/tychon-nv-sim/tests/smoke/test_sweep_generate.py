"""Smoke test for the sweep generation script."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest
import yaml

# Suppress grid aliasing warnings from low-resolution test grids
pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")

# Add scripts/ to path so we can import generate_sweep
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))


@pytest.mark.smoke
def test_sweep_single_combination():
    """Run sweep with 1 P1, 1 temp, 1 replicate — minimal config."""
    from generate_sweep import run_sweep

    with tempfile.TemporaryDirectory() as tmpdir:
        # Write minimal config
        config = {
            "n_freq_points": 20,
            "freq_range_Hz": [2.82e9, 2.92e9],
            "B_field_T": [0.0, 0.0, 50.0e-6],
            "p1_sweep_ppm": [10],
            "temperature_sweep_K": [300],
            "b1_gradient_range": [0.05, 0.30],
            "b_perp_range_T": [0.0, 50.0e-6],
            "n_replicates": 1,
            "master_seed": 42,
            "output_format": "h5",
            "include_nitrogen": False,
            "use_optics": False,
        }
        config_path = Path(tmpdir) / "test_sweep.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config, f)

        output_dir = Path(tmpdir) / "output"
        run_sweep(config_path, output_dir)

        # Verify outputs exist
        assert (output_dir / "dataset.h5").exists()
        assert (output_dir / "manifest.json").exists()
        # Progress file should be cleaned up
        assert not (output_dir / ".progress").exists()

        # Verify HDF5 content
        import h5py
        with h5py.File(output_dir / "dataset.h5", "r") as f:
            assert "train" in f
            assert f["train"]["spectra"].shape == (1, 20)
            assert np.all(np.isfinite(f["train"]["spectra"][:]))
            assert f["train"]["corruption_params"].shape == (1, 4)
