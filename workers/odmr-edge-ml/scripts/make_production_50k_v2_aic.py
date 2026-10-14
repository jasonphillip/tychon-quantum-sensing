#!/usr/bin/env python3
"""Regenerate Dataset A and compare HDF5 array content with the archived set.

Run with PYTHONPATH=~/projects/nv-sensor-sim/src and the
miniconda3 Python.  --test-only retains the original full-run test seeds and
OU trajectory seed while generating only the test split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import h5py
import numpy as np

from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
from nv_sensor_sim.datasets.hashing import content_md5
from nv_sensor_sim.datasets.writer import DatasetWriter
from nv_sensor_sim.pipelines.batch_generate import (
    _generate_split_stochastic,
    generate_dataset,
)

SIM_REPO = Path("~/projects/nv-sensor-sim")
REPO = Path(__file__).resolve().parents[1]
LINK = REPO / "data/production_50k_v2_aic"
ARCHIVE = Path("~/projects/tychon-shared-data/production_50k_v2_aic")
COUNTS = {"train": 40_000, "val": 5_000, "test": 5_000}
SEED = 42
FREQ_RANGE = (2.82e9, 2.92e9)
P1_RANGE = (1.0, 300.0)
B1_RANGE = (0.05, 0.30)
B_MAG_RANGE = (20e-6, 70e-6)


def array_md5(key: str, array: np.ndarray) -> str:
    """Use the simulator's dtype, shape, and byte convention for one array."""
    value = np.ascontiguousarray(array)
    digest = hashlib.md5()
    digest.update(key.encode())
    digest.update(str(value.dtype).encode())
    digest.update(str(value.shape).encode())
    digest.update(value.tobytes())
    return digest.hexdigest()


def compare(reference: Path, generated: Path, splits: list[str]) -> dict:
    result = {}
    first_difference = None
    with h5py.File(reference / "dataset.h5", "r") as old, h5py.File(
        generated / "dataset.h5", "r"
    ) as new:
        for split in splits:
            old_keys = set(old[split])
            new_keys = set(new[split])
            entries = {}
            old_arrays = {}
            new_arrays = {}
            for key in sorted(old_keys | new_keys):
                if key not in old_keys or key not in new_keys:
                    entries[key] = {"existing_md5": None, "regenerated_md5": None, "match": False}
                    if first_difference is None:
                        first_difference = f"{split}/{key}: array absent from one dataset"
                    continue
                left = old[split][key][:]
                right = new[split][key][:]
                old_arrays[f"{split}/{key}"] = left
                new_arrays[f"{split}/{key}"] = right
                left_md5 = array_md5(f"{split}/{key}", left)
                right_md5 = array_md5(f"{split}/{key}", right)
                match = left_md5 == right_md5
                entries[key] = {
                    "existing_md5": left_md5,
                    "regenerated_md5": right_md5,
                    "match": match,
                }
                if not match and first_difference is None:
                    if left.shape != right.shape or left.dtype != right.dtype:
                        first_difference = (
                            f"{split}/{key}: shape/dtype {left.shape}/{left.dtype} "
                            f"versus {right.shape}/{right.dtype}"
                        )
                    else:
                        left_bytes = np.ascontiguousarray(left).view(np.uint8).ravel()
                        right_bytes = np.ascontiguousarray(right).view(np.uint8).ravel()
                        byte_offset = int(np.flatnonzero(left_bytes != right_bytes)[0])
                        idx = np.unravel_index(byte_offset // left.dtype.itemsize, left.shape)
                        first_difference = (
                            f"{split}/{key}{idx} (byte {byte_offset}): "
                            f"{left[idx]!r} versus {right[idx]!r}"
                        )
            result[split] = {
                "existing_md5": content_md5(old_arrays),
                "regenerated_md5": content_md5(new_arrays),
                "arrays": entries,
            }
    return {"splits": result, "reproduced": first_difference is None,
            "first_difference": first_difference}


def generate_test_only(output: Path, original: dict, ou: OUNoiseConfig) -> None:
    # A zero-train generate_dataset call would assign the wrong test seeds.
    seeds = np.random.default_rng(SEED).choice(
        2**31, size=sum(COUNTS.values()), replace=False
    ).tolist()
    test_seeds = seeds[COUNTS["train"] + COUNTS["val"]:]
    if test_seeds != original["test_seeds"]:
        raise ValueError("recorded test seeds differ from seed 42 sequence")
    ou_seed = int(np.random.SeedSequence(SEED + 2**30).spawn(3)[2].generate_state(1)[0])
    config = SimulationConfig(
        random_seed=SEED, use_optics=False, include_nitrogen=False,
        n_freq_points=100, mw_freq_range_Hz=FREQ_RANGE,
    )
    adapter = SimOSAdapter(config)
    spectra, labels, params, seed_arr, freqs = _generate_split_stochastic(
        adapter, config, test_seeds, ou_noise_config=ou,
        ou_trajectory_seed=ou_seed,
        p1_range_ppm=tuple(original["test_p1_concentration_range_ppm"]),
        b1_gradient_range=tuple(original["test_b1_gradient_range"]),
        b_perp_range_T=(0.0, 0.0), bz_range_T=(0.005, 0.015),
        n_freq_points=100, split_name="test", field_sampling="spherical",
        b_mag_range_T=B_MAG_RANGE,
    )
    writer = DatasetWriter(output)
    writer.write_spectra(spectra, freqs, labels, params, seed_arr, "test")
    (output / "generation.json").write_text(json.dumps({
        "mode": "test-only", "master_seed": SEED,
        "generator_git_sha": subprocess.check_output(
            ["git", "-C", str(SIM_REPO), "rev-parse", "HEAD"], text=True
        ).strip(),
    }, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--test-only", action="store_true")
    parser.add_argument("--reference", type=Path,
                        help="Existing data directory; defaults to link, then archive path")
    args = parser.parse_args()
    reference = args.reference or (LINK if LINK.is_dir() else ARCHIVE)
    if not (reference / "dataset.h5").is_file():
        parser.error(f"reference dataset absent: {reference}")
    output = args.out.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error(f"output directory is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((reference / "manifest.json").read_text())
    if original["master_seed"] != SEED or original["config_hash"] != "cfec5b0afe89":
        raise ValueError("unexpected archived seed or config hash")
    ou = OUNoiseConfig(**original["ou_params"])
    if args.test_only:
        generate_test_only(output, original, ou)
        splits = ["test"]
    else:
        prior_cwd = Path.cwd()
        try:
            # The generator's Git provenance helper inspects the cwd.
            os.chdir(SIM_REPO)
            generate_dataset(
                str(output), n_train=COUNTS["train"], n_val=COUNTS["val"],
                n_test=COUNTS["test"], master_seed=SEED, n_freq_points=100,
                freq_range_Hz=FREQ_RANGE, p1_range_ppm=P1_RANGE,
                b1_gradient_range=B1_RANGE, b_perp_range_T=(0.0, 0.0),
                noise_mode="stochastic", ou_noise_config=ou,
                field_sampling="spherical", b_mag_range_T=B_MAG_RANGE,
                shift_test_ranges=True,
                # The original run supplied this OU-derived envelope as input.
                temp_range_K=tuple(original["temperature_range_K"]),
            )
        finally:
            os.chdir(prior_cwd)
        splits = list(COUNTS)
    comparison = compare(reference, output, splits)
    comparison.update({"reference": str(reference), "output": str(output),
                       "mode": "test-only" if args.test_only else "full"})
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
    print(json.dumps({"reproduced": comparison["reproduced"],
                      "first_difference": comparison["first_difference"],
                      "comparison": str(output / "comparison.json")}))
    return 0 if comparison["reproduced"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
