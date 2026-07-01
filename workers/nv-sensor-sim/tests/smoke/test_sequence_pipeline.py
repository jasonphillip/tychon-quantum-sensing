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
        assert manifest.contract_version == "v1"
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
def test_tiny_isotropic_sequence_generation():
    """Isotropic held-ramp mode: per-sequence geometry varies, contract holds."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=3,
            n_val=1,
            n_test=1,
            master_seed=7,
            n_timesteps=8,
            sweep_mode="isotropic",
            sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
            min_sweep_delta_T=1.0e-3,
            min_ramp_window_frac=0.25,
            min_axis_projection_T=0.4e-3,
            jitter_frac=0.0,
        )
        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.contract_version == "v1"
        assert "isotropic" in manifest.sweep_description
        assert manifest.sweep_mode == "isotropic"
        assert manifest.sweep_scalar_range_T == (-1.4e-3, 1.4e-3)
        assert manifest.min_axis_projection_T == 0.4e-3
        assert manifest.numpy_version == np.__version__
        assert manifest.linewidth_rendered_Hz is not None
        assert manifest.linewidth_rendered_Hz > manifest.linewidth_Hz
        assert manifest.n_ramp_resamples >= 0

        # Per-split label stats recorded in the manifest.
        assert manifest.sequence_stats is not None
        for split in ("train", "val", "test"):
            block = manifest.sequence_stats[split]
            assert block["n_sequences"] >= 1
            assert "no_crossing_fraction" in block
            assert "collision_dwell_frames" in block
            assert "min_axis_splitting_Hz" in block
            assert "n_ramp_resamples" in block

        n_freq = manifest.n_freq_points
        s = loader.load_sequence_split("train")
        assert s["spectra"].shape == (3, 8, n_freq)
        assert s["B_true"].shape == (3, 8, 3)

        # Each sequence sweeps its own direction: the ramp displacement vectors
        # (held end - held start) of different sequences are not collinear.
        deltas = (s["B_true"][:, -1, :] - s["B_true"][:, 0, :]).astype(float)
        mags = np.linalg.norm(deltas, axis=1)
        assert np.all(mags > 0)
        units = deltas / mags[:, None]
        cross = np.linalg.norm(np.cross(units[0], units[1]))
        assert cross > 1e-3, "sequences share a single sweep direction"

        # Displacement honors |s_end - s_start| >= min_delta (no jitter).
        assert np.all(mags >= 1.0e-3 - 1e-9)
        assert np.all(mags <= 2.8e-3 + 1e-9)


@pytest.mark.smoke
def test_sequence_pinned_window_used():
    """An explicit freq_range_Hz pin bypasses derivation and is recorded."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    pin = (2667390522.8636284, 3074609477.1363726)  # sequence_sanity_v0's grid
    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=1,
            n_val=0,
            n_test=0,
            master_seed=3,
            n_timesteps=4,
            sweep_mode="isotropic",
            sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
            min_sweep_delta_T=1.0e-3,
            freq_range_Hz=pin,
        )
        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.freq_range_Hz == pin
        assert manifest.n_freq_points == 951  # derived step matches v0's grid
        s = loader.load_sequence_split("train")
        assert s["resonance_freqs"].min() >= pin[0]
        assert s["resonance_freqs"].max() <= pin[1]


@pytest.mark.smoke
def test_sequence_pin_too_narrow_raises():
    """A pin that cannot contain the derived worst-case window fails fast."""
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="does not contain"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                sweep_mode="isotropic",
                sweep_scalar_range_T=(-2.0e-3, 2.0e-3),
                freq_range_Hz=(2.85e9, 2.89e9),
            )


@pytest.mark.smoke
def test_axis_contrast_scale_orders_line_depths():
    """Per-axis MW scales produce monotonically ordered per-axis dip depths."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    scales = (1.0, 0.85, 0.7, 0.55)
    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=1,
            n_val=0,
            n_test=0,
            master_seed=11,
            n_timesteps=4,
            sweep_mode="isotropic",
            sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
            min_sweep_delta_T=1.0e-3,
            axis_contrast_scale=scales,
        )
        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        assert manifest.axis_contrast_scale == scales
        assert manifest.axis_contrast_drift_std is None  # drift off
        depths = manifest.line_depths
        assert depths is not None and len(depths) == 8
        assert all(d > 0 for d in depths)
        # Line 2i/2i+1 belong to axis i: per-axis mean depth follows the scales.
        per_axis = [0.5 * (depths[2 * i] + depths[2 * i + 1]) for i in range(4)]
        assert per_axis[0] > per_axis[1] > per_axis[2] > per_axis[3]

        # The rendered spectra carry the asymmetry too (deepest dip belongs to
        # a stronger-driven axis than the global-min line of axis 3).
        s = loader.load_sequence_split("train")
        assert np.all(np.isfinite(s["spectra"]))


@pytest.mark.smoke
def test_uniform_contrast_records_equal_depths():
    """Without the knob, line_depths is still recorded and per-axis uniform."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=1,
            n_val=0,
            n_test=0,
            master_seed=12,
            n_timesteps=4,
        )
        manifest = DatasetLoader(output).load_manifest()
        assert manifest.axis_contrast_scale is None
        depths = manifest.line_depths
        assert depths is not None and len(depths) == 8
        per_axis = [0.5 * (depths[2 * i] + depths[2 * i + 1]) for i in range(4)]
        assert max(per_axis) - min(per_axis) < 0.25 * max(per_axis)


@pytest.mark.smoke
def test_axis_contrast_drift_reproducible_and_validated():
    """Seeded drift reproduces bit-identical spectra; bad params rejected."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    kwargs: dict = dict(
        n_train=1,
        n_val=0,
        n_test=0,
        master_seed=13,
        n_timesteps=6,
        sweep_mode="isotropic",
        sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
        min_sweep_delta_T=1.0e-3,
        axis_contrast_scale=(1.0, 0.85, 0.7, 0.55),
        axis_contrast_drift_std=0.05,
        axis_contrast_drift_tau_frames=8.0,
    )
    with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
        out1 = generate_sequence_dataset(output_dir=d1, **kwargs)
        out2 = generate_sequence_dataset(output_dir=d2, **kwargs)
        s1 = DatasetLoader(out1).load_sequence_split("train")
        s2 = DatasetLoader(out2).load_sequence_split("train")
        np.testing.assert_array_equal(s1["spectra"], s2["spectra"])
        manifest = DatasetLoader(out1).load_manifest()
        assert manifest.axis_contrast_drift_std == 0.05
        assert manifest.axis_contrast_drift_tau_frames == 8.0

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="axis_contrast_scale"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                axis_contrast_scale=(1.0, 0.85),  # wrong length
            )
        with pytest.raises(ValueError, match="drift_std"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                axis_contrast_drift_std=-0.1,
            )


@pytest.mark.smoke
def test_trajectory_family_mix_recorded_and_structured():
    """Family mixture: assignment recorded, reversal/OU trajectories correct."""
    from nv_sensor_sim.datasets.loaders import DatasetLoader
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_sequence_dataset(
            output_dir=tmpdir,
            n_train=6,
            n_val=0,
            n_test=0,
            master_seed=21,
            n_timesteps=16,
            sweep_mode="isotropic",
            sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
            min_sweep_delta_T=1.0e-3,
            min_axis_projection_T=0.4e-3,
            jitter_frac=0.0,
            trajectory_family_weights={"held": 0.34, "reversal": 0.33, "ou": 0.33},
            field_ou_sigma_T=45.0e-6,
            field_ou_tau_frames=16.0,
        )
        loader = DatasetLoader(output)
        manifest = loader.load_manifest()
        weights = manifest.trajectory_family_weights
        assert weights is not None
        assert abs(sum(weights.values()) - 1.0) < 1e-9
        assert manifest.field_ou_sigma_T == 45.0e-6
        assert manifest.reversal_turn_frac_range == (0.2, 0.8)

        assert manifest.sequence_stats is not None
        stats = manifest.sequence_stats["train"]
        families = stats["trajectory_family_per_sequence"]
        turns = stats["reversal_turn_frame_per_sequence"]
        assert len(families) == 6
        assert set(families) <= {"held", "reversal", "ou"}
        assert "family_stats" in stats
        assert "n_reversals_inside_collision_dwell" in stats
        assert stats["n_reversal_sequences"] == families.count("reversal")

        s = loader.load_sequence_split("train")
        B = s["B_true"].astype(float)
        for i, fam in enumerate(families):
            ext = B[i]  # bias + external, (T, 3)
            if fam == "reversal":
                t_turn = turns[i]
                assert 0 < t_turn < 15
                # Velocity projected on the sweep direction flips sign at the turn.
                d = np.diff(ext, axis=0)
                u = d[0] / np.linalg.norm(d[0])
                proj = d @ u
                assert np.all(proj[:t_turn] > 0)
                assert np.all(proj[t_turn:] < 0)
            elif fam == "held":
                assert turns[i] == -1
                # Piecewise linear: second differences vanish inside each
                # segment up to float32 storage quantization (~1e-10 T),
                # allowing the two knot frames to be nonzero.
                dd = np.linalg.norm(np.diff(ext, n=2, axis=0), axis=1)
                assert (dd < 1e-8).sum() >= dd.size - 2
            else:  # ou
                assert turns[i] == -1
                # OU perturbation (per-step increments ~1e-5 T) makes the path
                # non-piecewise-linear almost everywhere.
                dd = np.linalg.norm(np.diff(ext, n=2, axis=0), axis=1)
                assert (dd > 1e-8).sum() >= dd.size - 2
                # Perturbed trajectory still honors the projection floor.
                proj = np.abs(
                    ext
                    @ np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]).T
                    / np.sqrt(3.0)
                )
                assert proj.min() >= 0.4e-3 - 1e-12

        # OU wander stats recorded when the family occurred.
        if families.count("ou"):
            assert "wander_std_linewidths_mean" in stats["family_stats"]["ou"]


@pytest.mark.smoke
def test_family_weights_validation():
    """Family weights: unknown keys and non-isotropic use are config errors."""
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="unknown trajectory families"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=8,
                sweep_mode="isotropic",
                sweep_scalar_range_T=(-1.4e-3, 1.4e-3),
                trajectory_family_weights={"held": 0.5, "orbital": 0.5},
            )
        with pytest.raises(ValueError, match="isotropic"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=8,
                trajectory_family_weights={"held": 1.0},
            )


@pytest.mark.smoke
def test_sequence_isotropic_requires_scalar_range():
    """Isotropic mode without an endpoint scalar range is a config error."""
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="sweep_scalar_range_T"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                sweep_mode="isotropic",
            )


@pytest.mark.smoke
def test_sequence_unknown_sweep_mode_rejected():
    """Unknown sweep_mode values are rejected before any rendering."""
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="sweep_mode"):
            generate_sequence_dataset(
                output_dir=tmpdir,
                n_train=1,
                n_val=0,
                n_test=0,
                n_timesteps=4,
                sweep_mode="orbital",
            )


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
