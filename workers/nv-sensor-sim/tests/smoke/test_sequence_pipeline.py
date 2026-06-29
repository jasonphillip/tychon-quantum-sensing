"""Smoke tests for the time-series (sequence) generation pipeline (CPU-only)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

# Coarse test grids can trip the grid-aliasing guard; not relevant to shape checks.
pytestmark = pytest.mark.filterwarnings("ignore:Grid aliasing risk:UserWarning")


@pytest.mark.smoke
def test_tiny_sequence_generation():
    """Generate a tiny sequence dataset and verify the full HDF5 contract."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=2,
            n_val=1,
            n_test=1,
            master_seed=99,
            n_timesteps=6,
        )

        out = Path(output)
        assert (out / "dataset.h5").exists(), "HDF5 file not created"
        assert (out / "manifest.json").exists(), "Manifest not created"

        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.sequence_mode is True
        assert manifest.n_timesteps == 6
        assert manifest.n_lines == 8
        assert manifest.linewidth_Hz > 0.0
        assert manifest.dt_s > 0.0
        # Train/test seed separation
        assert set(manifest.train_seeds) & set(manifest.test_seeds) == set()

        n_freq = manifest.n_freq_points
        s = loader.load_sequence_split("train")
        assert s["spectra"].shape == (2, 6, n_freq)
        assert s["spectra"].dtype == np.float32
        assert s["frequencies"].shape == (n_freq,)
        assert s["B_true"].shape == (2, 6, 3)
        assert s["resonance_freqs"].shape == (2, 6, 8)
        assert s["line_axis"].shape == (2, 6, 8)
        assert s["line_axis"].dtype == np.int8
        assert s["line_transition"].dtype == np.int8
        assert s["collision_mask"].shape == (2, 6)
        assert s["collision_mask"].dtype == np.bool_
        assert s["line_collision"].shape == (2, 6, 8)
        assert s["line_collision"].dtype == np.bool_
        assert s["seeds"].shape == (2,)
        assert s["bias"].shape == (3,)

        # Spectra are finite, normalized (<= 1 off-resonance), and have ODMR dips.
        assert np.all(np.isfinite(s["spectra"]))
        assert s["spectra"].max() <= 1.0 + 1e-4
        assert s["spectra"].max() - s["spectra"].min() > 0.0, "No ODMR features"

        # Resonance labels lie inside the MW window.
        f = s["frequencies"]
        assert s["resonance_freqs"].min() >= f.min() - 1e6
        assert s["resonance_freqs"].max() <= f.max() + 1e6

        # Axis/transition ids span the expected sets.
        assert set(np.unique(s["line_axis"]).tolist()) == {0, 1, 2, 3}
        assert set(np.unique(s["line_transition"]).tolist()) <= {0, 1}


@pytest.mark.smoke
def test_sequence_B_true_tracks_swept_field():
    """B_true equals bias + ramp, so the field moves along the swept axis."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.dynamics.field_trajectory import static_bias_vector
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=1,
            n_val=0,
            n_test=0,
            master_seed=5,
            n_timesteps=8,
            jitter_frac=0.0,  # nominal trajectory: frame 0 == bias + ramp_start
            bias_B0_T=5.0e-3,
            bias_direction_uvw=(0.2, 0.1, 1.0),
            ramp_start_T=(-2.0e-3, 0.0, 0.0),
            ramp_end_T=(2.0e-3, 0.0, 0.0),
        )
        loader = DatasetLoader(output)
        s = loader.load_sequence_split("train")
        B = s["B_true"][0].astype(float)  # (T, 3)
        bias = static_bias_vector(5.0e-3, (0.2, 0.1, 1.0))

        # Frame 0 is bias + ramp_start; last frame is bias + ramp_end.
        np.testing.assert_allclose(B[0], bias + np.array([-2.0e-3, 0.0, 0.0]), atol=1e-9)
        np.testing.assert_allclose(B[-1], bias + np.array([2.0e-3, 0.0, 0.0]), atol=1e-9)
        # Field sweeps monotonically along x.
        assert np.all(np.diff(B[:, 0]) > 0)


@pytest.mark.smoke
def test_sequence_hyperfine_not_implemented():
    """L=24 hyperfine sequences are explicitly unsupported for v0."""
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(NotImplementedError, match="hyperfine"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                n_freq_points=80,
                hyperfine=True,
            )
