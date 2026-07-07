#!/usr/bin/env python3
"""Run the field-cone eval generator (sequence_eval_fieldcone_v1) from a YAML config.

Usage
-----
    python scripts/generate_fieldcone_dataset.py \
        --config configs/sequence_eval_fieldcone_v1.yaml \
        --output-dir artifacts/datasets/sequence_eval_fieldcone_v1/

Produces a held-out (off-bias angle x |B|) ladder eval (HDF5 + manifest), all
sequences in the ``test`` split. See docs/dataset-contract.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from nv_sensor_sim.pipelines.fieldcone_generate import generate_fieldcone_dataset

_FLOAT_TUPLE_KEYS: tuple[str, ...] = (
    "bias_direction_uvw",
    "freq_range_Hz",
    "axis_contrast_scale",
    "axis_offsets_hz",
)


def load_yaml_config(config_path: Path) -> dict:
    """Load YAML, coercing numeric list values to float tuples (bucket_spec kept as-is)."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    for key in _FLOAT_TUPLE_KEYS:
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = tuple(float(v) for v in cfg[key])
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the field-cone eval dataset.")
    parser.add_argument("--config", type=Path, required=True, help="Path to the fieldcone YAML.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Output directory.")
    args = parser.parse_args()

    cfg = load_yaml_config(args.config)
    output_dir = str(args.output_dir.resolve())
    accepted = {
        "master_seed",
        "bucket_spec",
        "seqs_per_bucket",
        "n_timesteps",
        "dt_s",
        "p1_ppm",
        "temperature_K",
        "bias_B0_T",
        "bias_direction_uvw",
        "freq_range_Hz",
        "n_freq_points",
        "axis_contrast_scale",
        "axis_contrast_drift_std",
        "axis_contrast_drift_tau_frames",
        "collision_threshold_linewidths",
        "min_axis_projection_T",
        "window_margin_frac",
        "azimuth_sweep_deg",
        "axis_offsets_hz",
        "nv_density_ppm",
        "sweep_description",
    }
    kwargs = {k: v for k, v in cfg.items() if k in accepted}
    generate_fieldcone_dataset(output_dir=output_dir, **kwargs)


if __name__ == "__main__":
    main()
