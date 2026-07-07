"""Smoke test for the v3 widened-envelope sequence pipeline.

A tiny isotropic_widened run must: render with the per-frame guards + directed
sub-population, write the four per-sequence coverage arrays, record coverage stats
and a reproducible data_md5, and honor the |B| floor. A second identical run must
reproduce data_md5 exactly (determinism).
"""

from __future__ import annotations

import h5py
import numpy as np

from nv_sensor_sim.datasets.schema import DatasetManifest
from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

# v1 pinned grid.
_PIN = (2667390522.8636284, 3074609477.1363726)


def _gen(out_dir: str) -> DatasetManifest:
    generate_sequence_dataset(
        output_dir=out_dir,
        n_train=6,
        n_val=2,
        n_test=2,
        master_seed=20260703,
        n_timesteps=16,
        bias_B0_T=5.0e-3,
        bias_direction_uvw=(0.2, 0.1, 1.0),
        sweep_mode="isotropic_widened",
        sweep_scalar_range_T=(-4.0e-3, 4.0e-3),
        min_sweep_delta_T=1.0e-3,
        min_ramp_window_frac=0.25,
        min_axis_projection_T=0.4e-3,
        min_field_T=3.0e-3,
        directed_fraction=0.5,
        directed_approach_lw_range=(3.0, 6.0),
        offbias_angle_target_deg=60.0,
        window_margin_frac=0.01,
        jitter_frac=0.05,
        axis_contrast_scale=(1.0, 0.85, 0.7, 0.55),
        axis_contrast_drift_std=0.05,
        axis_contrast_drift_tau_frames=64.0,
        trajectory_family_weights={"held": 0.5, "reversal": 0.25, "ou": 0.25},
        freq_range_Hz=_PIN,
        n_freq_points=951,
    )
    return DatasetManifest.from_json(f"{out_dir}/manifest.json")


def test_v3_widened_pipeline_smoke(tmp_path):
    out = str(tmp_path / "v3")
    m = _gen(out)

    assert m.sweep_mode == "isotropic_widened"
    assert m.min_field_T == 3.0e-3
    assert m.directed_fraction == 0.5
    assert m.data_md5 is not None
    # Amendment 1 condition (1): the stratification law is recorded in the manifest.
    assert m.stratification_law is not None
    assert m.stratification_law["method"] == "angle_stratified_option_A"
    assert m.stratification_law["cold_start_fraction"] == 0.5
    cov = m.sequence_stats["train"]["coverage"]
    assert cov["n_directed"] + cov["n_isotropic"] == 6
    assert cov["field_magnitude_mT"]["min"] >= 3.0 - 1e-6  # floor honored
    assert "cold_start_fraction_realized" in cov  # start-mode split recorded

    with h5py.File(f"{out}/dataset.h5", "r") as f:
        g = f["train"]
        for key in (
            "sampling_family",
            "max_offbias_angle_deg",
            "min_B_T",
            "directed_template_idx",
            "start_mode",
        ):
            assert key in g, f"missing per-sequence array {key}"
            assert g[key].shape == (6,)
        assert g["sampling_family"].dtype == np.int8
        assert g["min_B_T"].dtype == np.float32
        min_b = g["min_B_T"][:]
        assert float(min_b.min()) >= 3.0e-3 - 1e-6
        dti = g["directed_template_idx"][:]
        # directed_fraction=0.5 over 6 sequences → expect a mix.
        assert (dti >= 0).any()
        # Amendment 1 condition (2): start-mode recorded per sequence; angle-stratified
        # sequences carry 0=acquire / 1=carry, directed carry -1.
        sm = g["start_mode"][:]
        assert set(np.unique(sm)).issubset({-1, 0, 1})


def test_v3_widened_pipeline_is_deterministic(tmp_path):
    a = _gen(str(tmp_path / "a"))
    b = _gen(str(tmp_path / "b"))
    assert a.data_md5 == b.data_md5
    assert a.config_hash == b.config_hash
