#!/usr/bin/env python3
"""Run the bias-amplified vector-regime batch generator from a YAML config.

Usage
-----
    # Sanity slice
    python scripts/generate_vector_dataset.py \
        --config configs/production_50k_v3_vector_sanity1k.yaml \
        --output-dir artifacts/datasets/production_50k_v3_vector_sanity1k/

    # Full production cut
    python scripts/generate_vector_dataset.py \
        --config configs/production_50k_v3_vector.yaml \
        --output-dir artifacts/datasets/production_50k_v3_vector/
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from nv_sensor_sim.pipelines.batch_generate import generate_dataset


_FLOAT_RANGE_KEYS: tuple[str, ...] = (
    "freq_range_Hz",
    "p1_range_ppm",
    "temp_range_K",
    "b1_gradient_range",
    "b_perp_range_T",
    "bz_range_T",
    "b_mag_range_T",
    "bias_B0_range_T",
    "test_p1_range_ppm",
    "test_temp_range_K",
    "test_b1_gradient_range",
    "test_b_perp_range_T",
)
_FLOAT_VECTOR_KEYS: tuple[str, ...] = ("bias_direction_uvw",)


def load_yaml_config(config_path: Path) -> dict:
    """Load YAML, coercing range tuples + direction vectors to typed Python."""
    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    for key in _FLOAT_RANGE_KEYS:
        if key in cfg and isinstance(cfg[key], list) and cfg[key] is not None:
            cfg[key] = tuple(float(v) for v in cfg[key])
    for key in _FLOAT_VECTOR_KEYS:
        if key in cfg and isinstance(cfg[key], list):
            cfg[key] = tuple(float(v) for v in cfg[key])
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a vector-regime ODMR dataset from a YAML config."
    )
    parser.add_argument(
        "--config", type=Path, required=True,
        help="Path to vector dataset YAML config.",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Output directory for HDF5 + manifest.",
    )
    args = parser.parse_args()

    cfg = load_yaml_config(args.config)
    output_dir = str(args.output_dir.resolve())

    # generate_dataset accepts a subset of the keys in the YAML; pass only the
    # ones it knows about, ignore everything else (e.g. metadata-only keys).
    accepted = {
        "n_train", "n_val", "n_test", "master_seed",
        "n_freq_points", "freq_range_Hz",
        "p1_range_ppm", "temp_range_K", "b1_gradient_range", "b_perp_range_T",
        "bz_range_T", "noise_mode",
        "field_sampling", "b_mag_range_T",
        "shift_test_ranges",
        "test_p1_range_ppm", "test_temp_range_K",
        "test_b1_gradient_range", "test_b_perp_range_T",
        "multi_axis_mode", "bias_B0_T", "bias_direction_uvw",
        "concentrator_amplification", "magnet_drift_ppm_per_K",
        "bias_B0_range_T",
        "inhomogeneous_fwhm_hz", "base_contrast",
    }
    kwargs = {k: v for k, v in cfg.items() if k in accepted}
    generate_dataset(output_dir=output_dir, **kwargs)


if __name__ == "__main__":
    main()
