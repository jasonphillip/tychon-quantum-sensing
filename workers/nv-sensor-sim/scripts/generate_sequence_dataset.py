#!/usr/bin/env python3
"""Run the time-series ("dynamic") ODMR sequence generator from a YAML config.

Usage
-----
    python scripts/generate_sequence_dataset.py \
        --config configs/sequence_sanity_v0.yaml \
        --output-dir artifacts/datasets/sequence_sanity_v0/

Produces a time-series dataset (HDF5 + manifest) where the magnetic field sweeps
and the NV-axis resonances move and cross, with per-frame collision labels. See
docs/dataset-contract.md (time-series layout).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

# Numeric YAML lists (field 3-vectors, scalar/frequency ranges) coerced to float tuples.
_FLOAT_TUPLE_KEYS: tuple[str, ...] = (
    "bias_direction_uvw",
    "ramp_start_T",
    "ramp_end_T",
    "sweep_scalar_range_T",
    "freq_range_Hz",
    "axis_contrast_scale",
    "reversal_turn_frac_range",
    "directed_approach_lw_range",
    "field_range_T",
    "carry_field_range_T",
    "axis_offsets_hz",
)


def load_yaml_config(config_path: Path) -> dict:
    """Load YAML, coercing numeric list values to float tuples."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    for key in _FLOAT_TUPLE_KEYS:
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = tuple(float(v) for v in cfg[key])
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a time-series ODMR sequence dataset from a YAML config."
    )
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to sequence dataset YAML config.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for HDF5 + manifest.",
    )
    args = parser.parse_args()

    cfg = load_yaml_config(args.config)
    output_dir = str(args.output_dir.resolve())

    # Pass only the keys generate_sequence_dataset knows about; ignore metadata keys.
    accepted = {
        "n_train",
        "n_val",
        "n_test",
        "master_seed",
        "n_timesteps",
        "dt_s",
        "p1_ppm",
        "temperature_K",
        "bias_B0_T",
        "bias_direction_uvw",
        "ramp_start_T",
        "ramp_end_T",
        "sweep_mode",
        "sweep_scalar_range_T",
        "min_sweep_delta_T",
        "min_ramp_window_frac",
        "min_axis_projection_T",
        "min_field_T",
        "directed_fraction",
        "directed_approach_lw_range",
        "window_margin_frac",
        "offbias_angle_target_deg",
        "field_range_T",
        "cold_start_fraction",
        "carry_start_max_deg",
        "carry_field_range_T",
        "jitter_frac",
        "axis_contrast_scale",
        "axis_contrast_drift_std",
        "axis_contrast_drift_tau_frames",
        "trajectory_family_weights",
        "reversal_turn_frac_range",
        "field_ou_sigma_T",
        "field_ou_tau_frames",
        "collision_threshold_linewidths",
        "extra_b_perp_T",
        "hyperfine",
        "axis_offsets_hz",
        "nv_density_ppm",
        "freq_range_Hz",
        "n_freq_points",
        "freq_margin_factor",
        "aliasing_safety",
        "sweep_description",
    }
    kwargs = {k: v for k, v in cfg.items() if k in accepted}
    generate_sequence_dataset(output_dir=output_dir, **kwargs)


if __name__ == "__main__":
    main()
