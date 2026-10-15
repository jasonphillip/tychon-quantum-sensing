#!/usr/bin/env python3
"""Generate one sealed scalar repair partition from the fixed stress protocol."""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import os
import resource
import stat
import subprocess
import sys
import time
import warnings
from pathlib import Path

for variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ[variable] = "1"

import numpy as np

REPO = Path(__file__).resolve().parents[1]
SIM_REPO = Path("~/projects/nv-sensor-sim")
ARCHIVE = Path("~/projects/tychon-shared-data")
STRESS = Path("~/projects/portfolio-publication/work/scalar-stress-test")
VECTOR_DOCS = Path("~/projects/portfolio-publication/wt/odmr-vector-tracking-s1-comparison/docs")
COORDINATION = Path("~/projects/portfolio-publication/work/scalar-repair-cycle")
ORIGINAL = ARCHIVE / "production_50k_v2_aic/manifest.json"
PROTOCOL = REPO / "experiments/scalar_stress_test/PROTOCOL.md"
PARTITIONS = {"dev": (256, 202610160), "val": (512, 202610161), "final": (1024, 202610162)}
EXCLUDED = {20261014, 20261114, 20261214, 20270114, 202610140, 202610141,
            202610142, 20261015}

# Imported definitions are the fixed seven stress cells, including their order.
sys.path.insert(0, str(REPO / "experiments/scalar_stress_test"))
from generate_stress_data import CELLS  # noqa: E402


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def _seed_values(value: object, key: str = "") -> set[int]:
    """Read numeric seed fields only; never treat counts or hashes as seeds."""
    found: set[int] = set()
    if isinstance(value, dict):
        for child_key, child in value.items():
            found.update(_seed_values(child, child_key.lower()))
    elif "seed" in key and isinstance(value, int) and not isinstance(value, bool):
        found.add(value)
    elif "seed" in key and isinstance(value, list):
        found.update(int(item) for item in value if isinstance(item, int) and not isinstance(item, bool))
    elif isinstance(value, list):
        for item in value:
            found.update(_seed_values(item, key))
    return found


def manifest_paths() -> list[Path]:
    paths = []
    for base in (REPO / "docs", REPO / "experiments", ARCHIVE, STRESS / "data",
                 STRESS / "sealing", VECTOR_DOCS):
        if base.is_dir():
            paths.extend(p for p in base.rglob("*manifest*.json") if p.is_file())
    return sorted(set(paths))


def scan_used_seeds() -> tuple[set[int], list[dict]]:
    used = set(EXCLUDED)
    records = []
    for path in manifest_paths():
        data = json.loads(path.read_text())
        seeds = _seed_values(data)
        # The target repair holdout omits row seeds, but its public recipe
        # reconstructs them exactly from this manifest's master seed and count.
        if path == ARCHIVE / "production_50k_v2_aic_holdout_2026-10/manifest.json":
            n = 45000 + int(data["row_count"])
            seeds.update(map(int, np.random.default_rng(data["master_seed"]).choice(
                2**31, size=n, replace=False)[45000:]))
        used.update(seeds)
        records.append({"path": str(path), "sha256": sha(path), "seed_count": len(seeds)})
    return used, records


def reserve_seeds(partition: str, used: set[int], rows: int) -> tuple[list[int], list[int], list[int]]:
    master = PARTITIONS[partition][1]
    if master in used:
        raise RuntimeError(f"Reserved master seed already used: {master}")
    streams = np.random.SeedSequence(master).spawn(3)
    rng = np.random.default_rng(streams[0])
    selected = []
    while len(selected) < rows:
        candidate = int(rng.integers(0, 2**31))
        if candidate not in used:
            selected.append(candidate)
            used.add(candidate)
    noise = [int(x) for x in np.random.default_rng(streams[1]).integers(0, 2**32, rows)]
    nuisance = [int(x) for x in np.random.default_rng(streams[2]).integers(0, 2**32, rows)]
    return selected, noise, nuisance


def field_components(seed: int) -> tuple[np.ndarray, float]:
    """Reconstruct source B vector and B1 gradient fraction from a row seed."""
    rng = np.random.default_rng(seed)
    rng.uniform(0, 1)  # P1 draw; its numeric range does not affect state.
    rng.uniform(0, 1)  # Unused temperature draw in stochastic source.
    gradient_unit = rng.uniform(0, 1)
    rng.uniform(0, 1)  # Zero-width b_perp draw still advances source RNG.
    magnitude = rng.uniform(20e-6, 70e-6)
    cosine = rng.uniform(-1, 1)
    angle = rng.uniform(0, 2 * np.pi)
    vector = np.array([magnitude * np.sqrt(1 - cosine**2) * np.cos(angle),
                       magnitude * np.sqrt(1 - cosine**2) * np.sin(angle),
                       magnitude * cosine], dtype="<f8")
    return vector, gradient_unit


def field_fingerprint(seed: int) -> str:
    """Hash source-sampled field parameters from a metadata row seed."""
    vector, gradient_unit = field_components(seed)
    return hashlib.sha256(vector.tobytes() + np.float64(gradient_unit).tobytes()).hexdigest()


def consumed_field_fingerprints() -> tuple[set[str], dict]:
    """Reconstruct only metadata-seeded scalar families; never open payloads."""
    sources = [ORIGINAL, ARCHIVE / "production_50k/manifest.json"]
    sources += sorted((STRESS / "data").glob("*/manifest.json"))
    fingerprints: set[str] = set()
    counts = {}
    for path in sources:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        seeds = set()
        for key in ("train_seeds", "val_seeds", "test_seeds", "sample_seeds"):
            seeds.update(map(int, data.get(key, [])))
        fingerprints.update(field_fingerprint(seed) for seed in seeds)
        counts[str(path)] = len(seeds)
    holdout = ARCHIVE / "production_50k_v2_aic_holdout_2026-10/manifest.json"
    if holdout.exists():
        data = json.loads(holdout.read_text())
        seeds = np.random.default_rng(data["master_seed"]).choice(
            2**31, size=45000 + data["row_count"], replace=False)[45000:]
        fingerprints.update(field_fingerprint(int(seed)) for seed in seeds)
        counts[str(holdout)] = len(seeds)
    return fingerprints, counts


def _source_imports():
    sys.path.insert(0, str(SIM_REPO / "src"))
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
    from nv_sensor_sim.pipelines.batch_generate import _generate_split_stochastic
    from nv_sensor_sim.physics.parameters import compute_linewidth
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
    return (SimOSAdapter, OUNoiseConfig, SimulationConfig, _generate_split_stochastic,
            compute_linewidth, apply_shot_noise, photons_for_dip_snr)


def verify(out: Path, partition: str) -> dict:
    dest = out / partition
    if dest.is_symlink() or not dest.is_dir() or dest.stat().st_mode & 0o222:
        raise RuntimeError("Partition directory absent, symlinked, or writable")
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["partition"] != partition or set(manifest["cells"]) != set(CELLS):
        raise RuntimeError("Partition identity or cells changed")
    expected = {"manifest.json"} | {entry["file"] for entry in manifest["cells"].values()}
    if {p.name for p in dest.iterdir()} != expected:
        raise RuntimeError("Unexpected or missing partition file")
    field_ids = manifest["field_ids"]
    nuisance_ids = manifest["nuisance_group_ids"]
    if len(set(field_ids)) != manifest["rows_per_cell"] or len(set(nuisance_ids)) != len(field_ids):
        raise RuntimeError("Field or nuisance group identity mismatch")
    for cell, entry in manifest["cells"].items():
        path = dest / entry["file"]
        if path.is_symlink() or path.stat().st_mode & 0o222 or sha(path) != entry["sha256"]:
            raise RuntimeError(f"Hash or read-only mismatch: {cell}")
        with np.load(path, allow_pickle=False) as arrays:
            if arrays["spectra"].shape != (len(field_ids), 100):
                raise RuntimeError(f"Row/grid mismatch: {cell}")
            if arrays["truth_vectors_T"].shape != (len(field_ids), 3):
                raise RuntimeError(f"Field shape mismatch: {cell}")
            if not np.array_equal(arrays["sample_seeds"], manifest["sample_seeds"]):
                raise RuntimeError(f"Seed mismatch: {cell}")
    if manifest_path.stat().st_mode & 0o222:
        raise RuntimeError("Manifest writable")
    return {"partition": partition, "manifest_sha256": sha(manifest_path),
            "rows_per_cell": len(field_ids), "total_rows": sum(x["rows"] for x in manifest["cells"].values())}


def generate(out: Path, partition: str, *, rows_override: int | None = None) -> dict:
    started = time.monotonic()
    cpu_started = time.process_time()
    rows, master = PARTITIONS[partition]
    if rows_override is not None:
        rows = rows_override  # Tiny tests only; the CLI never accepts an override.
    if partition == "val" and not (COORDINATION / "FREEZE1.md").is_file():
        raise RuntimeError("Validation requires coordinator Freeze 1")
    if partition == "final" and not (COORDINATION / "FREEZE2.md").is_file():
        raise RuntimeError("Final requires coordinator Freeze 2")
    if partition == "final" and not (out / "exclusive-access-receipt.json").is_file():
        raise RuntimeError("Final requires an exclusive access receipt")
    if out.is_symlink() or (out / partition).exists():
        raise RuntimeError("Symlinked root or existing partition refused")
    ledger = REPO / ".scratch/compute_ledger.jsonl"
    if ledger.exists():
        prior_wall = sum(json.loads(line).get("wall_seconds", 0) for line in ledger.read_text().splitlines()
                         if json.loads(line).get("job") == "scalar_repair_generation")
        if prior_wall >= 1200:
            raise RuntimeError("Cumulative generation cap reached")
    used, searched = scan_used_seeds()
    for other in PARTITIONS:
        manifest_path = out / other / "manifest.json"
        if manifest_path.exists():
            used.update(_seed_values(json.loads(manifest_path.read_text())))
    seeds, noise_seeds, nuisance_seeds = reserve_seeds(partition, used, rows)
    prior_fingerprints, fingerprint_sources = consumed_field_fingerprints()
    fingerprints = [field_fingerprint(seed) for seed in seeds]
    overlap = len(set(fingerprints) & prior_fingerprints)
    if overlap or len(set(fingerprints)) != rows:
        raise RuntimeError(f"Field fingerprint overlap or duplicate: {overlap}")
    original = json.loads(ORIGINAL.read_text())
    (SimOSAdapter, OUNoiseConfig, SimulationConfig, render, compute_linewidth,
     apply_shot_noise, photons_for_dip_snr) = _source_imports()
    out.mkdir(parents=True, exist_ok=True)
    dest = out / partition
    dest.mkdir()
    write_json(dest / "INCOMPLETE.json", {"partition": partition})
    base = {}
    broadened = {}
    widths = sorted({cell[0] for cell in CELLS.values()})
    for width in widths:
        p1 = (np.pi * width * 1e6 - 1 / 1.48e-6) * 9.9e-6
        if not np.isclose(compute_linewidth(p1), width * 1e6):
            raise RuntimeError("Linewidth inversion mismatch")
        config = SimulationConfig(random_seed=master, use_optics=False, include_nitrogen=False,
                                  n_freq_points=100, mw_freq_range_Hz=(2.82e9, 2.92e9))
        adapter = SimOSAdapter(config)
        spectra = np.empty((rows, 100))
        labels = np.empty((rows, 3))
        params = np.empty((rows, 5))
        freq = None
        aliasing = 0
        for index, (seed, nuisance_seed) in enumerate(zip(seeds, nuisance_seeds)):
            # The second sweep is the one-step OU realization. One independent
            # trajectory seed per field; repeated sample seed preserves identity.
            with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings(record=True) as seen:
                warnings.simplefilter("always")
                x, b, p, returned, f = render(
                    adapter, config, [seed, seed], OUNoiseConfig(**original["ou_params"]),
                    nuisance_seed, (p1, p1), tuple(original["test_b1_gradient_range"]),
                    (0., 0.), (.005, .015), 100, partition, field_sampling="spherical",
                    b_mag_range_T=(20e-6, 70e-6))
            if not np.array_equal(b[0], b[1]) or list(returned) != [seed, seed]:
                raise RuntimeError("Field identity changed within nuisance pair")
            predicted_b, predicted_gradient = field_components(seed)
            np.testing.assert_array_equal(b[1], predicted_b)
            np.testing.assert_allclose(
                (p[1, 2] - original["test_b1_gradient_range"][0]) /
                np.diff(original["test_b1_gradient_range"])[0], predicted_gradient,
                atol=1e-15, rtol=0)
            spectra[index], labels[index], params[index] = x[1], b[1], p[1]
            if freq is None:
                freq = f
            elif not np.array_equal(freq, f):
                raise RuntimeError("Frequency grid changed")
            aliasing += sum("aliasing" in str(w.message).lower() for w in seen)
        if base:
            np.testing.assert_array_equal(labels, next(iter(base.values()))[1])
            np.testing.assert_array_equal(params[:, 1:], next(iter(base.values()))[2][:, 1:])
        factors = params[:, 4, None] * (1 + params[:, 2, None] * np.linspace(-.5, .5, 10))
        actual = width * 1e6 * np.sqrt(1 + getattr(config, "base_saturation_s0", .1) * factors**2)
        broadened[width] = {"intrinsic_fwhm_hz": width * 1e6, "p1_ppm": p1,
                            "rendered_component_fwhm_hz_range": [float(actual.min()), float(actual.max())],
                            "aliasing_warning_count": aliasing}
        base[width] = (spectra, labels, params, freq)
    records = {}
    for name, (width, contrast, snr, slope, offset_mhz) in CELLS.items():
        x, b, params, freq = base[width]
        depth = np.max(1 - x, axis=1, keepdims=True)
        if np.any(depth <= 0):
            raise RuntimeError("Nonpositive dip depth")
        scaled = 1 - (1 - x) * (contrast / depth)
        shifted = np.array([np.interp(freq - offset_mhz * 1e6, freq, row,
                                      left=row[0], right=row[-1]) for row in scaled])
        signal = shifted + slope * (freq - (freq[0] + freq[-1]) / 2) / (freq[-1] - freq[0])
        photons = None if snr is None else photons_for_dip_snr(.30 * contrast, snr)
        if photons is not None:
            signal = np.array([apply_shot_noise(row, photons, seed)
                               for row, seed in zip(signal, noise_seeds)])
        if not np.isfinite(signal).all():
            raise RuntimeError(f"Nonfinite spectra: {name}")
        path = dest / f"{name}.npz"
        np.savez_compressed(path, spectra=signal, truth_vectors_T=b, frequencies_hz=freq,
                            sample_seeds=seeds, nuisance_params=params, noise_seeds=noise_seeds)
        records[name] = {"file": path.name, "sha256": sha(path), "rows": rows,
                         "intrinsic_fwhm_mhz": width, "contrast": contrast,
                         "reference_snr": snr, "slope": slope,
                         "frequency_offset_hz": offset_mhz * 1e6,
                         "photons_per_point": photons,
                         "actual_broadened_fwhm_hz_range": broadened[width]["rendered_component_fwhm_hz_range"]}
    elapsed = time.monotonic() - started
    cpu = time.process_time() - cpu_started
    if partition == "dev" and elapsed > 600:
        raise RuntimeError("Development generation exceeded ten-minute cap")
    if elapsed > 1200 or resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > 8 * 1024**3:
        raise RuntimeError("Generation time or memory cap exceeded")
    source_files = ["adapters/simos_adapter.py", "pipelines/batch_generate.py",
                    "physics/lineshape.py", "physics/parameters.py", "physics/shot_noise.py",
                    "physics/noise_injection.py"]
    source_root = SIM_REPO / "src/nv_sensor_sim"
    manifest = {
        "schema": 1, "partition": partition, "rows_per_cell": rows, "total_rows": rows * len(CELLS),
        "master_seed": master, "sample_seeds": seeds, "noise_seeds": noise_seeds,
        "nuisance_seeds": nuisance_seeds, "field_ids": [f"{partition}-{i:04d}" for i in range(rows)],
        "nuisance_group_ids": [f"{partition}-ou-{i:04d}" for i in range(rows)],
        "field_parameter_fingerprints": fingerprints,
        "overlap_check": {"seed_overlap": 0, "field_fingerprint_overlap": overlap,
                          "consumed_fingerprint_sources": fingerprint_sources},
        "seed_search": searched, "excluded_master_seeds": sorted(EXCLUDED),
        "single_orientation": True, "frequency_grid_hz": freq.tolist(),
        "field_prior": {"magnitude_uT": [20, 70], "magnitude_distribution": "uniform",
                        "direction": "isotropic spherical"},
        "nuisance_distribution": {"ou": original["ou_params"],
                                  "b1_gradient_uniform_range": original["test_b1_gradient_range"],
                                  "b_perp_T": 0, "ou_steps_per_field": 2, "saved_step": 1,
                                  "independent_trajectory_per_field": True},
        "units": {"spectra": "normalized fluorescence", "truth_vectors_T": "T",
                  "frequencies_hz": "Hz", "nuisance_params": ["ppm", "K", "unitless", "T", "unitless"]},
        "cells": records, "rendered_linewidths": {str(k): v for k, v in broadened.items()},
        "noise_reference_fraction": .30,
        "generator_commit": subprocess.check_output(["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip(),
        "generator_commit_contains_script": subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", "HEAD:scripts/make_scalar_repair_partitions.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0,
        "generator_sha256": sha(Path(__file__)), "stress_generator_sha256": sha(REPO / "experiments/scalar_stress_test/generate_stress_data.py"),
        "protocol_sha256": sha(PROTOCOL),
        "simulator_commit": subprocess.check_output(["git", "-C", str(SIM_REPO), "rev-parse", "HEAD"], text=True).strip(),
        "source_sha256": {name: sha(source_root / name) for name in source_files},
        "wall_seconds": elapsed, "cpu_seconds": cpu,
        "peak_memory_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label_or_baseline_summary_disclosed": False,
    }
    write_json(dest / "manifest.json", manifest)
    (dest / "INCOMPLETE.json").unlink()
    for path in dest.iterdir():
        path.chmod(0o444)
    dest.chmod(0o555)
    result = verify(out, partition)
    result.update({"wall_seconds": elapsed, "cpu_seconds": cpu,
                   "peak_memory_bytes": manifest["peak_memory_bytes"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=PARTITIONS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    result = verify(args.out, args.partition) if args.verify else generate(args.out, args.partition)
    if not args.verify:
        ledger = REPO / ".scratch/compute_ledger.jsonl"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("a") as stream:
            stream.write(json.dumps({"job": "scalar_repair_generation", "partition": args.partition,
                                     "manifest_sha256": result["manifest_sha256"],
                                     "wall_seconds": result["wall_seconds"],
                                     "cpu_seconds": result["cpu_seconds"],
                                     "peak_memory_bytes": result["peak_memory_bytes"],
                                     "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat()}) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
