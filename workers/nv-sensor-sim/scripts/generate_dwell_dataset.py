#!/usr/bin/env python3
"""Generate a dwell-sweep eval dataset (identity-through-merge lineage).

The v1-inherited parameters (951-point pinned frequency grid, fixed deployment
bias vector/magnitude, per-axis contrast ladder + AR(1) drift, linewidth via
p1_ppm, T=256) are READ FROM THE ARCHIVED v1 MANIFEST, not hard-coded anew, so
the dwell lineage is provably pinned to v1. Dwell-specific controls and the
default-OFF physics cues come from the YAML config.

Usage
-----
    python scripts/generate_dwell_dataset.py \
        --config configs/sequence_dwell_v1.yaml \
        --output-dir artifacts/datasets/sequence_dwell_v1/

See docs/dataset-contract.md (optional keys -- dwell lineage) and
logs/sequence_dwell_v1_generation.md.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from nv_sensor_sim.pipelines.dwell_generate import generate_dwell_sequence_dataset


def _read_v1_pins(v1_manifest_path: Path) -> dict:
    """Extract the v1-inherited pins from the archived v1 manifest (read-only)."""
    m = json.loads(v1_manifest_path.read_text())
    if m.get("contract_version") != "v1":
        raise ValueError(f"expected contract_version v1 in {v1_manifest_path}")
    p1_lo, p1_hi = m["p1_concentration_range_ppm"]
    t_lo, t_hi = m["temperature_range_K"]
    if p1_lo != p1_hi or t_lo != t_hi:
        raise ValueError("v1 manifest has non-fixed p1/temperature ranges; unexpected")
    return {
        "freq_range_Hz": tuple(m["freq_range_Hz"]),
        "n_freq_points": int(m["n_freq_points"]),
        "bias_B0_T": float(m["bias_B0_T"]),
        "bias_direction_uvw": tuple(m["bias_direction_uvw"]),
        "p1_ppm": float(p1_lo),
        "temperature_K": float(t_lo),
        "n_timesteps": int(m["n_timesteps"]),
        "dt_s": float(m["dt_s"]),
        "collision_threshold_linewidths": float(m["collision_threshold_linewidths"]),
        "axis_contrast_scale": tuple(m["axis_contrast_scale"]),
        "axis_contrast_drift_std": float(m["axis_contrast_drift_std"]),
        "axis_contrast_drift_tau_frames": float(m["axis_contrast_drift_tau_frames"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a dwell-sweep eval dataset.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cfg = yaml.safe_load(args.config.read_text())

    v1_manifest = Path(cfg["v1_manifest"]).expanduser()
    pins = _read_v1_pins(v1_manifest)
    print(f"Read v1 pins from {v1_manifest}")
    print(f"  freq_range_Hz={pins['freq_range_Hz']} n_freq_points={pins['n_freq_points']}")
    print(f"  bias_B0_T={pins['bias_B0_T']} bias_direction_uvw={pins['bias_direction_uvw']}")

    # Optional cross-checks: any pin echoed in the config must match the manifest.
    for key in ("n_freq_points", "bias_B0_T", "n_timesteps"):
        if key in cfg and cfg[key] != pins[key]:
            raise ValueError(f"config {key}={cfg[key]!r} disagrees with v1 manifest {pins[key]!r}")
    if "freq_range_Hz" in cfg and tuple(cfg["freq_range_Hz"]) != pins["freq_range_Hz"]:
        raise ValueError("config freq_range_Hz disagrees with the v1 manifest pin")
    if (
        "bias_direction_uvw" in cfg
        and tuple(cfg["bias_direction_uvw"]) != pins["bias_direction_uvw"]
    ):
        raise ValueError("config bias_direction_uvw disagrees with the v1 manifest pin")

    dwell_kwargs = dict(
        master_seed=int(cfg["master_seed"]),
        dwell_frames_list=tuple(int(d) for d in cfg["dwell_frames_list"]),
        seqs_per_bucket=int(cfg["seqs_per_bucket"]),
        approach_linewidths=float(cfg.get("approach_linewidths", 6.0)),
        ramp_frames=int(cfg.get("ramp_frames", 4)),
        sep_min_linewidths=float(cfg.get("sep_min_linewidths", 1.5)),
        min_axis_projection_T=float(cfg.get("min_axis_projection_T", 0.4e-3)),
        jitter_frac=float(cfg.get("jitter_frac", 0.05)),
        position_jitter_frames=int(cfg.get("position_jitter_frames", 8)),
        axis_offsets_hz=(
            tuple(float(v) for v in cfg["axis_offsets_hz"]) if cfg.get("axis_offsets_hz") else None
        ),
        nv_density_ppm=float(cfg.get("nv_density_ppm", 0.0)),
    )
    generate_dwell_sequence_dataset(str(args.output_dir.resolve()), **pins, **dwell_kwargs)


if __name__ == "__main__":
    main()
