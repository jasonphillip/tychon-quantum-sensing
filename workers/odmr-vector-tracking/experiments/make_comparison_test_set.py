#!/usr/bin/env python3
"""Generate and verify the sealed, paired comparison set (master seed 20261014).

Run with PYTHONPATH=~/projects/nv-sensor-sim/src and the
miniconda Python. Refuses a shared/symlinked data root and existing output.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import signal
import shutil
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import yaml

from nv_sensor_sim.physics.parameters import compute_linewidth
from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
from nv_sensor_sim.pipelines.fieldcone_generate import generate_fieldcone_dataset
from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

ROOT = Path(__file__).resolve().parent.parent
SIM = Path("~/projects/nv-sensor-sim")
DATA = ROOT / "data" / "comparison_test_v1"
MANIFEST = ROOT / "docs" / "comparison_test_v1.manifest.json"
MASTER_SEED = 20261014
MAX_SEQUENCES = 2000
MAX_SECONDS = 3600
REPLICATES = 3
REQUESTED_PER_REPLICATE = 40
FALLBACK_PER_REPLICATE = 20
ARRAY_NAME = "dataset.h5"


def cells() -> list[dict]:
    # One realistic anchor uses the +/+ signs. The - signs are explicit OFAT cells.
    base = dict(linewidth_MHz=5.0, contrast_pct=1.5, snr=10,
                baseline_slope_pct=2.0, frequency_offset_MHz=0.3)
    out = [("clean", "clean", dict(linewidth_MHz=1.5, contrast_pct=3.0,
                                    snr=None, baseline_slope_pct=0.0,
                                    frequency_offset_MHz=0.0)),
           ("realistic", "realistic", base.copy())]
    for key, values, tags in (
        ("linewidth_MHz", (1.5, 3.0, 7.0), ("1p5", "3", "7")),
        ("contrast_pct", (3.0,), ("3",)),
        ("snr", (None, 30, 3), ("inf", "30", "3")),
        ("baseline_slope_pct", (0.0, -2.0), ("0", "minus2")),
        ("frequency_offset_MHz", (0.0, -0.3), ("0", "minus0p3")),
    ):
        for value, tag in zip(values, tags):
            cfg = base.copy()
            cfg[key] = value
            out.append((f"realistic_{key}_{tag}", "realistic", cfg))
    out.append(("extrapolation", "extrapolation", base.copy()))
    return [dict(name=name, rung=rung, config=cfg) for name, rung, cfg in out]


def _seed(name: str, replicate: int) -> int:
    # Common random numbers pair all in-envelope trajectories across OFAT cells.
    # The extrapolation generator uses its own geometry and seed stream.
    family = "extrapolation" if name == "extrapolation" else "in_envelope"
    digest = hashlib.sha256(f"{MASTER_SEED}:{family}:{replicate}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31 - 1) + 1


def _p1_for_linewidth(mhz: float) -> float:
    floor = compute_linewidth(0.0)
    target = mhz * 1e6
    if target < floor:
        raise ValueError(f"linewidth {mhz} MHz is below the physical floor")
    return (math.pi * target - 1 / 1.48e-6) * 9.9e-6


def _read_config(path: Path) -> dict:
    cfg = yaml.safe_load(path.read_text())
    return {key: tuple(value) if isinstance(value, list) and key in {
        "bias_direction_uvw", "sweep_scalar_range_T", "freq_range_Hz",
        "axis_contrast_scale", "reversal_turn_frac_range",
    } else value for key, value in cfg.items()}


def _call_generator(output: Path, cell: dict, seed: int, n_seq: int) -> dict:
    if cell["rung"] == "extrapolation":
        source = SIM / "configs" / "sequence_eval_fieldcone_v1.yaml"
        cfg = _read_config(source)
        cfg["bucket_spec"] = [b for b in cfg["bucket_spec"] if b["class"] == "beyond"
                              and b["angle_deg"] == 40.0 and b["B_mT"] == 2.5]
        cfg["seqs_per_bucket"] = n_seq
        generator = generate_fieldcone_dataset
    else:
        source = SIM / "configs" / "sequence_train_v2.yaml"
        cfg = _read_config(source)
        cfg.update(n_train=0, n_val=0, n_test=n_seq)
        # At 5/7 MHz the source's 1.15x worst-case window margin rejects the
        # pinned 951-point grid before rendering. This is a guard only; 0.90
        # leaves the generated field/spectra unchanged. The generator still
        # asserts every realized resonance label lies inside the pinned grid.
        cfg["freq_margin_factor"] = 0.90
        generator = generate_sequence_dataset
    cfg["master_seed"] = seed
    cfg["p1_ppm"] = _p1_for_linewidth(cell["config"]["linewidth_MHz"])
    accepted = set(inspect.signature(generator).parameters) - {"output_dir"}
    kwargs = {key: value for key, value in cfg.items() if key in accepted}
    generator(output_dir=str(output), **kwargs)
    return {"source_config": str(source), "generator": f"{generator.__module__}.{generator.__name__}",
            "generator_config": kwargs}


def _augment(dataset: Path, cell: dict, noise_seed: int) -> dict:
    c = cell["config"]
    with h5py.File(dataset, "r+") as h5:
        split = h5["test"]
        freq = split["frequencies"][:].astype(np.float64)
        spectra = split["spectra"]
        # The generator's absolute contrast is under 1%. Define requested contrast
        # as the deepest pre-noise dip in each sequence, preserving relative line depths.
        factors = []
        budgets = []
        x = (freq - 0.5 * (freq[0] + freq[-1])) / (freq[-1] - freq[0])
        offset = c["frequency_offset_MHz"] * 1e6
        for i in range(spectra.shape[0]):
            s = spectra[i].astype(np.float64)
            depth = float(np.max(1.0 - s))
            if depth <= 0:
                raise RuntimeError("nonpositive ODMR dip depth")
            factor = (c["contrast_pct"] / 100.0) / depth
            s = 1.0 - factor * (1.0 - s)
            if offset:
                s = np.stack([np.interp(freq - offset, freq, row,
                                        left=float(row[0]), right=float(row[-1]))
                              for row in s])
            s += (c["baseline_slope_pct"] / 100.0) * x[None, :]
            if c["snr"] is not None:
                # Faintest per-axis dip inherits the source manifest's depth ratio.
                # The global scale is already applied, so derive the faintest ratio
                # from the source's line-depth ladder recorded in its manifest.
                src = json.loads((dataset.parent / "manifest.json").read_text())
                depths = np.asarray(src.get("line_depths") or [], dtype=float)
                ratio = float(depths.min() / depths.max()) if depths.size else 0.30
                faintest = c["contrast_pct"] / 100.0 * ratio
                photons = photons_for_dip_snr(faintest, c["snr"])
                s = apply_shot_noise(s, photons, seed=noise_seed + i)
                budgets.append(photons)
            spectra[i] = s.astype(spectra.dtype)
            factors.append(factor)
    return {"contrast_scale_min": min(factors), "contrast_scale_max": max(factors),
            "photons_per_point": budgets[0] if budgets else None}


def data_md5(cell_dir: Path) -> str:
    files = sorted(cell_dir.rglob(ARRAY_NAME), key=lambda p: p.relative_to(cell_dir).as_posix())
    if not files:
        raise RuntimeError(f"no array files under {cell_dir}")
    digest = hashlib.md5()
    for path in files:
        rel = path.relative_to(cell_dir).as_posix().encode()
        digest.update(len(rel).to_bytes(4, "big"))
        digest.update(rel)
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
    return digest.hexdigest()


def verify() -> int:
    m = json.loads(MANIFEST.read_text())
    if len(m["cells"]) != len(cells()):
        raise RuntimeError("cell count differs from registered grid")
    for cell in m["cells"]:
        got = data_md5(DATA / cell["name"])
        if got != cell["data_md5"]:
            raise RuntimeError(f"{cell['name']}: {got} != {cell['data_md5']}")
        for rep in cell["replicates"]:
            p = DATA / cell["name"] / f"seed_{rep['index']}" / ARRAY_NAME
            with h5py.File(p, "r") as h5:
                if h5["test/spectra"].shape[:2] != (rep["n_sequences"], rep["n_frames"]):
                    raise RuntimeError(f"wrong shape: {p}")
    print(f"verified {len(m['cells'])} cells, {m['total_sequences']} sequences")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="replace existing local test set")
    ap.add_argument("--verify", action="store_true", help="recompute every sealed cell MD5")
    args = ap.parse_args()
    if args.verify:
        return verify()
    if (ROOT / "data").is_symlink():
        raise RuntimeError("data/ is a shared symlink; make a worktree-local data/ directory first")
    if DATA.is_symlink():
        raise RuntimeError("test output may not be a symlink")
    if DATA.exists():
        if not args.force:
            raise FileExistsError(f"refusing to overwrite {DATA}; pass --force")
        shutil.rmtree(DATA)
    planned = len(cells()) * REPLICATES * REQUESTED_PER_REPLICATE
    # Field-cone lineage measured 47 s / 120 sequences in the source generation log.
    # Use a conservative 4x projection, then enforce an absolute wall-clock alarm.
    projected_seconds = planned * (47.0 / 120.0) * 4.0
    n_seq = (REQUESTED_PER_REPLICATE if planned <= MAX_SEQUENCES
             and projected_seconds <= MAX_SECONDS else FALLBACK_PER_REPLICATE)
    if len(cells()) * REPLICATES * n_seq > MAX_SEQUENCES:
        raise RuntimeError("sequence cap exceeded even at fallback")
    DATA.mkdir(parents=True)
    start = time.perf_counter()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(
        TimeoutError("60-minute generation cap reached; no manifest written")))
    signal.alarm(MAX_SECONDS)
    records = []
    for cell in cells():
        cell_dir = DATA / cell["name"]
        reps = []
        cell_seeds = set()
        for index in range(REPLICATES):
            elapsed = time.perf_counter() - start
            if elapsed >= MAX_SECONDS:
                raise TimeoutError("60-minute cap reached; partial set is not sealed")
            seed = _seed(cell["name"], index)
            if seed in cell_seeds:
                raise RuntimeError("derived seed collision")
            cell_seeds.add(seed)
            target = cell_dir / f"seed_{index}"
            lineage = _call_generator(target, cell, seed, n_seq)
            aug = _augment(target / ARRAY_NAME, cell, seed + MASTER_SEED)
            reps.append({"index": index, "seed": seed, "n_sequences": n_seq,
                         "n_frames": 256, "lineage": lineage, "augmentation": aug})
            print(f"{cell['name']} seed_{index}: {n_seq} sequences; {time.perf_counter()-start:.1f}s", flush=True)
        records.append({**cell, "seed": [r["seed"] for r in reps],
                        "n_sequences": n_seq * REPLICATES, "n_frames": 256,
                        "replicates": reps, "data_md5": data_md5(cell_dir)})
    elapsed = time.perf_counter() - start
    if elapsed > MAX_SECONDS:
        raise TimeoutError("generation exceeded 60 minutes; no manifest written")
    payload = {"schema": 1, "master_seed": MASTER_SEED, "cell_count": len(records),
               "sequences_per_cell_seed": n_seq, "total_sequences": len(records)*REPLICATES*n_seq,
               "generation_wall_s": elapsed, "array_hash_rule": "MD5 of sorted relative dataset.h5 paths (4-byte big-endian length + path UTF-8 + raw file bytes)",
               "source_fieldcone_manifest_data_md5": "92dc06692d1975f6fcd101e70cc02d99",
               "cells": records}
    MANIFEST.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    signal.alarm(0)
    return verify()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"comparison set error: {exc}", file=sys.stderr)
        raise
