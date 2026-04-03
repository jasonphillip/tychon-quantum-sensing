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
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=2,
            n_val=1,
            n_test=1,
            master_seed=99,
            n_freq_points=20,
            field_sampling="z_only",
        )

        out = Path(output)
        assert (out / "dataset.h5").exists(), "HDF5 file not created"
        assert (out / "manifest.json").exists(), "Manifest not created"

        # Verify via loader
        from nv_sensor_sim.datasets.loaders import DatasetLoader

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
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=5,
            n_val=0,
            n_test=0,
            master_seed=123,
            n_freq_points=20,
            field_sampling="z_only",
        )

        from nv_sensor_sim.datasets.loaders import DatasetLoader

        loader = DatasetLoader(output)
        _, _, _, params, _ = loader.load_split("train")

        # Each column (p1, T, b1_grad, b_perp) should have variation
        for col_idx, name in enumerate(["p1_ppm", "T_K", "b1_grad", "b_perp"]):
            col = params[:, col_idx]
            assert np.std(col) > 0, f"Column {name} has zero variance — not being sampled"


@pytest.mark.smoke
def test_stochastic_batch_generation():
    """Generate a stochastic dataset via OU noise trajectories."""
    from nv_sensor_sim.config import OUNoiseConfig
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    ou_config = OUNoiseConfig(
        theta_T=0.1, mu_T=300.0, sigma_T=0.5,
        theta_B1=1.0, mu_B1=1.0, sigma_B1=0.05,
        trajectory_dt_s=1.0,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=5,
            n_val=2,
            n_test=2,
            master_seed=77,
            n_freq_points=20,
            noise_mode="stochastic",
            ou_noise_config=ou_config,
            field_sampling="z_only",
        )

        out = Path(output)
        assert (out / "dataset.h5").exists()
        assert (out / "manifest.json").exists()

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.noise_mode == "stochastic"
        assert manifest.ou_params is not None
        assert manifest.ou_params["theta_T"] == 0.1
        assert manifest.ou_params["mu_T"] == 300.0

        # Train split: 5 spectra, 5 columns (p1, T_K, b1_grad, b_perp, mw_power_scale)
        spectra, freqs, labels, params, seeds = loader.load_split("train")
        assert spectra.shape == (5, 20)
        assert labels.shape == (5, 3)
        assert params.shape == (5, 5), f"Expected 5 columns, got {params.shape[1]}"
        assert len(seeds) == 5

        # Spectra should be finite and have ODMR features
        assert np.all(np.isfinite(spectra))
        for i in range(spectra.shape[0]):
            signal_range = np.max(spectra[i]) - np.min(spectra[i])
            assert signal_range > 0, f"Spectrum {i} has no ODMR features"

        # mw_power_scale (column 4) should be near 1.0 but not all identical
        mw_scales = params[:, 4]
        assert np.all(mw_scales > 0), "MW power scale must be positive"


@pytest.mark.smoke
def test_cascaded_stochastic_batch_generation():
    """Generate a stochastic dataset via cascaded causal SDE model."""
    from nv_sensor_sim.config import OUNoiseConfig
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    ou_config = OUNoiseConfig(
        theta_T=1.0e-3, sigma_T=0.05,
        theta_B1=10.0, sigma_B1=0.006,
        trajectory_dt_s=1.0,
        alpha_B1=-0.0035,
        T_mean_C=20.0,
        delta_T_orb_C=15.0,
        tau_orb_s=5400.0,
        B1_nominal=1.0,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=5,
            n_val=2,
            n_test=2,
            master_seed=88,
            n_freq_points=20,
            noise_mode="stochastic",
            ou_noise_config=ou_config,
            field_sampling="z_only",
        )

        out = Path(output)
        assert (out / "dataset.h5").exists()
        assert (out / "manifest.json").exists()

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.noise_mode == "stochastic"
        assert manifest.ou_params is not None
        assert manifest.ou_params["alpha_B1"] == pytest.approx(-0.0035)

        spectra, freqs, labels, params, seeds = loader.load_split("train")
        assert spectra.shape == (5, 20)
        assert params.shape == (5, 5)
        assert np.all(np.isfinite(spectra))

        # T values should be near 293.15 K (20°C), within orbital + OU range
        T_vals = params[:, 1]
        assert np.all(T_vals > 250.0), "Temperature unreasonably low"
        assert np.all(T_vals < 340.0), "Temperature unreasonably high"

        # MW power scale should be near 1.0
        mw_scales = params[:, 4]
        assert np.all(mw_scales > 0.5)
        assert np.all(mw_scales < 1.5)


@pytest.mark.smoke
def test_both_mode_batch_generation():
    """Generate paired deterministic + stochastic datasets."""
    import h5py

    from nv_sensor_sim.config import OUNoiseConfig
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    ou_config = OUNoiseConfig(
        theta_T=0.1, mu_T=300.0, sigma_T=0.5,
        theta_B1=1.0, mu_B1=1.0, sigma_B1=0.05,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=3,
            n_val=1,
            n_test=1,
            master_seed=55,
            n_freq_points=20,
            noise_mode="both",
            ou_noise_config=ou_config,
            field_sampling="z_only",
        )

        out = Path(output)
        assert (out / "dataset.h5").exists()

        # Both group types should exist in HDF5
        with h5py.File(out / "dataset.h5", "r") as f:
            assert "train_deterministic" in f
            assert "train_stochastic" in f
            assert "val_deterministic" in f
            assert "val_stochastic" in f

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.noise_mode == "both"

        # Deterministic: 4-column params
        _, _, _, det_params, det_seeds = loader.load_split("train_deterministic")
        assert det_params.shape == (3, 4)

        # Stochastic: 5-column params
        _, _, _, sto_params, sto_seeds = loader.load_split("train_stochastic")
        assert sto_params.shape == (3, 5)

        # Same seeds → paired spectra
        np.testing.assert_array_equal(det_seeds, sto_seeds)

        # Paired: p1 (col 0), b1_grad (col 2), b_perp (col 3) should match
        np.testing.assert_array_almost_equal(det_params[:, 0], sto_params[:, 0])  # p1
        np.testing.assert_array_almost_equal(det_params[:, 2], sto_params[:, 2])  # b1_grad
        np.testing.assert_array_almost_equal(det_params[:, 3], sto_params[:, 3])  # b_perp


@pytest.mark.smoke
def test_spherical_field_sampling():
    """Generate dataset with spherical B-field sampling and verify diverse orientations."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.batch_generate import generate_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_dataset(
            output_dir=tmpdir,
            n_train=10,
            n_val=0,
            n_test=0,
            master_seed=42,
            n_freq_points=20,
            field_sampling="spherical",
            b_mag_range_T=(30e-6, 60e-6),
        )

        out = Path(output)
        assert (out / "dataset.h5").exists()
        assert (out / "manifest.json").exists()

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.field_sampling == "spherical"
        assert manifest.b_mag_range_T == pytest.approx((30e-6, 60e-6))
        assert manifest.b_perp_range_T == pytest.approx((0.0, 0.0))

        spectra, freqs, labels, params, seeds = loader.load_split("train")
        assert spectra.shape == (10, 20)
        assert labels.shape == (10, 3)

        # Labels should have diverse Bx, By, Bz (not all z-only)
        assert np.std(labels[:, 0]) > 1e-6, "Bx has no variance"
        assert np.std(labels[:, 1]) > 1e-6, "By has no variance"
        assert np.std(labels[:, 2]) > 1e-6, "Bz has no variance"

        # Field magnitudes should be within range
        b_mags = np.linalg.norm(labels, axis=1)
        assert np.all(b_mags >= 30e-6 - 1e-12)
        assert np.all(b_mags <= 60e-6 + 1e-12)

        # b_perp column (col 3) should be all zeros in spherical mode
        assert np.all(params[:, 3] == 0.0), "b_perp should be 0 in spherical mode"

        # Spectra should be finite and have ODMR features
        assert np.all(np.isfinite(spectra))
        for i in range(spectra.shape[0]):
            signal_range = np.max(spectra[i]) - np.min(spectra[i])
            assert signal_range > 0, f"Spectrum {i} has no ODMR features"
