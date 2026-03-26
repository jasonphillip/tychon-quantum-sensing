"""Smoke tests for the batch generation pipeline."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

# Suppress grid aliasing warnings from low-resolution test grids
pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")


@pytest.mark.smoke
def test_tiny_batch_generation():
    """Generate a tiny dataset (2+1+1) via the batch pipeline."""
    from tychon_nv_sim.pipelines.batch_generate import generate_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=2,
            n_val=1,
            n_test=1,
            master_seed=99,
            n_freq_points=20,
        )

        out = Path(output)
        assert (out / "dataset.h5").exists(), "HDF5 file not created"
        assert (out / "manifest.json").exists(), "Manifest not created"

        # Verify via loader
        from tychon_nv_sim.datasets.loaders import DatasetLoader

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()

        assert manifest.n_spectra_train == 2
        assert manifest.n_spectra_val == 1
        assert manifest.n_spectra_test == 1

        # Verify train/test seed separation
        assert set(manifest.train_seeds) & set(manifest.test_seeds) == set()

        # Load and verify train split
        spectra, freqs, labels, params, seeds = loader.load_split("train")
        assert spectra.shape == (2, 20)
        assert labels.shape == (2, 3)
        assert params.shape == (2, 4)
        assert len(seeds) == 2

        # Spectra should be finite and have ODMR features
        assert np.all(np.isfinite(spectra))
        for i in range(spectra.shape[0]):
            signal_range = np.max(spectra[i]) - np.min(spectra[i])
            assert signal_range > 0, f"Spectrum {i} has no ODMR features"


@pytest.mark.smoke
def test_batch_corruption_params_vary():
    """Verify that corruption parameters actually differ across spectra."""
    from tychon_nv_sim.pipelines.batch_generate import generate_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=5,
            n_val=0,
            n_test=0,
            master_seed=123,
            n_freq_points=20,
        )

        from tychon_nv_sim.datasets.loaders import DatasetLoader

        loader = DatasetLoader(output)
        _, _, _, params, _ = loader.load_split("train")

        # Each column (p1, T, b1_grad, b_perp) should have variation
        for col_idx, name in enumerate(["p1_ppm", "T_K", "b1_grad", "b_perp"]):
            col = params[:, col_idx]
            assert np.std(col) > 0, f"Column {name} has zero variance — not being sampled"
