#!/usr/bin/env python3
"""Generate one blind test-size holdout split with the recipe config and a NEW master seed.

Imports the recipe (make_production_50k_v2_aic.py); only the master seed differs.
With --pid-labels (default on) it also writes pid_residuals.npz (keys test_b_pid_uT,
test_lock_bins, test_delta_b_uT, test_b_mag_uT) from DerivativeZeroCrossingPID on the split.
Run with PYTHONPATH=<nv-sensor-sim>/src and the miniconda3 Python.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_production_50k_v2_aic as recipe  # noqa: E402
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter  # noqa: E402
from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig  # noqa: E402
from nv_sensor_sim.datasets.writer import DatasetWriter  # noqa: E402
from nv_sensor_sim.pipelines.batch_generate import _generate_split_stochastic  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--rows", type=int, default=5000)
    p.add_argument("--reference", type=Path, default=recipe.ARCHIVE)
    p.add_argument("--pid-labels", action=argparse.BooleanOptionalAction, default=True)
    a = p.parse_args()
    if a.seed == recipe.SEED:
        p.error("seed must differ from the recipe seed 42")
    out = a.out.resolve()
    if out.exists() and any(out.iterdir()):
        p.error(f"output directory is not empty: {out}")
    out.mkdir(parents=True, exist_ok=True)
    original = json.loads((a.reference / "manifest.json").read_text())
    if original["config_hash"] != "cfec5b0afe89":
        raise ValueError("unexpected archived config hash")
    ou = OUNoiseConfig(**original["ou_params"])
    n_prior = recipe.COUNTS["train"] + recipe.COUNTS["val"]
    # Same calls as the recipe, new seed; the first n_prior values are skipped as there.
    seeds = np.random.default_rng(a.seed).choice(2**31, size=n_prior + a.rows, replace=False).tolist()
    row_seeds = seeds[n_prior:]
    ou_seed = int(np.random.SeedSequence(a.seed + 2**30).spawn(3)[2].generate_state(1)[0])
    config = SimulationConfig(
        random_seed=a.seed, use_optics=False, include_nitrogen=False,
        n_freq_points=100, mw_freq_range_Hz=recipe.FREQ_RANGE,
    )
    adapter = SimOSAdapter(config)
    spectra, labels, params, seed_arr, freqs = _generate_split_stochastic(
        adapter, config, row_seeds, ou_noise_config=ou, ou_trajectory_seed=ou_seed,
        p1_range_ppm=tuple(original["test_p1_concentration_range_ppm"]),
        b1_gradient_range=tuple(original["test_b1_gradient_range"]),
        b_perp_range_T=(0.0, 0.0), bz_range_T=(0.005, 0.015),
        n_freq_points=100, split_name="test", field_sampling="spherical",
        b_mag_range_T=recipe.B_MAG_RANGE,
    )
    DatasetWriter(out).write_spectra(spectra, freqs, labels, params, seed_arr, "test")
    h5 = out / "dataset.h5"
    if a.pid_labels:
        from odmr_edge_ml.evaluation.pid_proxy import DerivativeZeroCrossingPID
        with h5py.File(h5, "r") as f:
            x = f["test/spectra"][:]
            b = np.linalg.norm(f["test/labels"][:] * 1e6, axis=1)
            res = DerivativeZeroCrossingPID(f["test/frequencies"][:]).estimate_batch(x)
        bp = np.array([r.b_mag_uT for r in res])
        lb = np.array([r.lock_bin for r in res])
        np.savez(out / "pid_residuals.npz", test_b_pid_uT=bp, test_lock_bins=lb,
                 test_delta_b_uT=b - bp, test_b_mag_uT=b)
    with h5py.File(h5, "r") as f:
        md5s = {f"test/{k}": recipe.array_md5(f"test/{k}", f["test"][k][:]) for k in sorted(f["test"])}
    today = datetime.date.today().isoformat()
    manifest = {
        "recipe_script": "scripts/make_production_50k_v2_aic.py",
        "recipe_script_sha256": hashlib.sha256(Path(recipe.__file__).read_bytes()).hexdigest(),
        "holdout_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "config_hash": original["config_hash"],
        "simulator_commit": subprocess.check_output(
            ["git", "-C", str(recipe.SIM_REPO), "rev-parse", "HEAD"], text=True).strip(),
        "master_seed": a.seed, "ou_trajectory_seed": ou_seed,
        "row_count": len(row_seeds), "split": "test", "per_array_md5": md5s,
        "date": today,
        "statement": "blind holdout: generated 2026-10-14, not seen by any model or person "
                     "before <date of first read>",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"rows": len(row_seeds), "md5": md5s}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
