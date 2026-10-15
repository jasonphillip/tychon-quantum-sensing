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
LEDGER = REPO / ".scratch/compute_ledger.jsonl"
RECIPE = REPO / "docs/production_50k_v2_aic.manifest.json"
PROTOCOL = REPO / "experiments/scalar_stress_test/PROTOCOL.md"
PARTITIONS = {"dev-r2": (256, 202610163), "val": (512, 202610161), "final": (1024, 202610162)}
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


def git_head(path: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                            text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else None


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def append_ledger(job: str, partition: str | None, started: float, cpu_started: float,
                  success: bool, **extra: object) -> None:
    if os.environ.get("SCALAR_REPAIR_PARENT_JOB"):
        return
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    entry = {"job": job, "partition": partition, "success": success,
             "wall_seconds": time.monotonic() - started,
             "cpu_seconds": time.process_time() - cpu_started,
             "peak_memory_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
             "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(), **extra}
    with LEDGER.open("a") as stream:
        stream.write(json.dumps(entry, sort_keys=True) + "\n")


def prior_generation_wall() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(float(row.get("wall_seconds", 0)) for line in LEDGER.read_text().splitlines()
               if (row := json.loads(line)).get("job") == "scalar_repair_generation")


def check_budget(started: float, prior_wall: float, partition: str) -> None:
    elapsed = time.monotonic() - started
    if prior_wall + elapsed > 1200:
        raise RuntimeError("Cumulative generation cap exceeded")
    if partition.startswith("dev") and elapsed > 600:
        raise RuntimeError("Development generation exceeded ten-minute cap")
    if resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024 > 8 * 1024**3:
        raise RuntimeError("Generation memory cap exceeded")


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


def manifest_paths(roots: list[Path]) -> list[tuple[str, Path, Path]]:
    paths = []
    for label, base in [("repo-docs", REPO / "docs"),
                        ("repo-experiments", REPO / "experiments")] + [
                            (f"root-{i:02d}", root) for i, root in enumerate(roots, 1)]:
        if base.is_dir():
            paths.extend((label, base, p) for p in base.rglob("*manifest*.json") if p.is_file())
    return sorted(paths, key=lambda item: (item[0], str(item[2])))


def scan_used_seeds(roots: list[Path] | None = None) -> tuple[set[int], list[dict]]:
    used = set(EXCLUDED)
    records = []
    for label, base, path in manifest_paths(roots or []):
        data = json.loads(path.read_text())
        seeds = _seed_values(data)
        # The target repair holdout omits row seeds, but its public recipe
        # reconstructs them exactly from this manifest's master seed and count.
        if path.parent.name == "production_50k_v2_aic_holdout_2026-10" and path.name == "manifest.json":
            n = 45000 + int(data["row_count"])
            seeds.update(map(int, np.random.default_rng(data["master_seed"]).choice(
                2**31, size=n, replace=False)[45000:]))
        used.update(seeds)
        records.append({"root_label": label, "relative_path": str(path.relative_to(base)),
                        "sha256": sha(path), "seed_count": len(seeds)})
    return used, records


def reserve_seeds(partition: str, used: set[int], rows: int) -> tuple[list[int], list[int], list[int]]:
    master = PARTITIONS[partition][1]
    if master in used:
        raise RuntimeError(f"Reserved master seed already used: {master}")
    streams = np.random.SeedSequence(master).spawn(4)
    rng = np.random.default_rng(streams[0])
    selected = []
    occupied = set(used)
    while len(selected) < rows:
        candidate = int(rng.integers(0, 2**31))
        if candidate not in occupied:
            selected.append(candidate)
            occupied.add(candidate)
    def unique(stream: np.random.SeedSequence) -> list[int]:
        draw = np.random.default_rng(stream)
        values = []
        while len(values) < rows:
            candidate = int(draw.integers(0, 2**32))
            if candidate not in occupied:
                values.append(candidate)
                occupied.add(candidate)
        return values
    noise = unique(streams[1])
    nuisance = unique(streams[2])
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


def consumed_field_fingerprints(roots: list[Path] | None = None) -> tuple[set[str], dict]:
    """Reconstruct only metadata-seeded scalar families; never open payloads."""
    sources = [(label, base, path) for label, base, path in manifest_paths(roots or [])
               if path.name == "manifest.json" and
               (path.parent.name in {"production_50k", "production_50k_v2_aic"}
                or path.parent.parent.name == "data")]
    fingerprints: set[str] = set()
    counts = {}
    for label, base, path in sources:
        data = json.loads(path.read_text())
        seeds = set()
        for key in ("train_seeds", "val_seeds", "test_seeds", "sample_seeds"):
            seeds.update(map(int, data.get(key, [])))
        fingerprints.update(field_fingerprint(seed) for seed in seeds)
        counts[f"{label}/{path.relative_to(base)}"] = len(seeds)
    for label, base, holdout in manifest_paths(roots or []):
        if holdout.parent.name != "production_50k_v2_aic_holdout_2026-10" or holdout.name != "manifest.json":
            continue
        data = json.loads(holdout.read_text())
        seeds = np.random.default_rng(data["master_seed"]).choice(
            2**31, size=45000 + data["row_count"], replace=False)[45000:]
        fingerprints.update(field_fingerprint(int(seed)) for seed in seeds)
        counts[f"{label}/{holdout.relative_to(base)}"] = len(seeds)
    return fingerprints, counts


def _source_imports(sim_src: Path | None = None):
    sim_src = sim_src or (Path(os.environ["NV_SENSOR_SIM_SRC"]) if os.environ.get("NV_SENSOR_SIM_SRC") else None)
    if sim_src is not None:
        sys.path.insert(0, str(sim_src))
    from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
    from nv_sensor_sim.config import OUNoiseConfig, SimulationConfig
    from nv_sensor_sim.pipelines.batch_generate import _sample_spherical_field
    from nv_sensor_sim.physics.lineshape import corrupt_spectrum
    from nv_sensor_sim.physics.noise_injection import sample_ou_trajectory_pair
    from nv_sensor_sim.physics.parameters import compute_linewidth
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
    import nv_sensor_sim
    source_root = Path(nv_sensor_sim.__file__).resolve().parent
    return (SimOSAdapter, OUNoiseConfig, SimulationConfig, _sample_spherical_field,
            corrupt_spectrum, sample_ou_trajectory_pair, compute_linewidth,
            apply_shot_noise, photons_for_dip_snr, source_root)


def render_field(adapter, seed: int, T_K: float, mw_power_scale: float, p1: float,
                 gradient_range: tuple[float, float], sample_spherical, corrupt_spectrum):
    """One simulator row, preserving _generate_split_stochastic's RNG draw order."""
    rng = np.random.default_rng(seed)
    sampled_p1 = rng.uniform(p1, p1)
    rng.uniform(0.0, 1.0)
    b1_grad = rng.uniform(*gradient_range)
    b_perp = rng.uniform(0., 0.)
    B_vec = sample_spherical(rng, (20e-6, 70e-6))
    adapter.config.temperature_K = T_K
    adapter.config.B_field_T = B_vec
    adapter.config.p1_concentration_ppm = sampled_p1
    freqs, signal, _ = corrupt_spectrum(adapter, adapter.config, b1_grad, b_perp,
                                         p1_ppm=sampled_p1, mw_power_scale=mw_power_scale)
    return signal, B_vec, np.array([sampled_p1, T_K, b1_grad, b_perp, mw_power_scale]), freqs


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
    seeds = manifest["sample_seeds"] + manifest["noise_seeds"] + manifest["nuisance_seeds"]
    if len(set(seeds)) != len(seeds):
        raise RuntimeError("Sample, noise, or trajectory seed collision")
    nuisance_fields = manifest.get("nuisance_fields")
    if nuisance_fields is not None:
        if len(nuisance_fields) != len(field_ids):
            raise RuntimeError("Nuisance field count mismatch")
        for i, field in enumerate(nuisance_fields):
            if field["trajectory_seed"] != manifest["nuisance_seeds"][i] or \
                    field["nuisance_group_id"] != nuisance_ids[i] or \
                    not 0 <= field["sample_index"] < field["horizon"]:
                raise RuntimeError("Nuisance field metadata mismatch")
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
            if nuisance_fields is not None:
                if not np.array_equal(arrays["nuisance_params"][:, 1],
                                      [field["T_K"] for field in nuisance_fields]) or \
                        not np.array_equal(arrays["nuisance_params"][:, 4],
                                           [field["mw_power_scale"] for field in nuisance_fields]):
                    raise RuntimeError(f"Nuisance metadata mismatch: {cell}")
    if manifest_path.stat().st_mode & 0o222:
        raise RuntimeError("Manifest writable")
    return {"partition": partition, "manifest_sha256": sha(manifest_path),
            "rows_per_cell": len(field_ids), "total_rows": sum(x["rows"] for x in manifest["cells"].values())}


def _generate(out: Path, partition: str, *, rows_override: int | None = None,
              gate_doc: Path | None = None, seed_search_roots: list[Path] | None = None,
              sim_src: Path | None = None) -> dict:
    started = time.monotonic()
    cpu_started = time.process_time()
    prior_wall = prior_generation_wall()
    rows, master = PARTITIONS[partition]
    if rows_override is not None:
        rows = rows_override  # Tiny tests only; the CLI never accepts an override.
    if partition in ("val", "final"):
        expected = "FREEZE1.md" if partition == "val" else "FREEZE2.md"
        if gate_doc is None or gate_doc.name != expected or not gate_doc.is_file():
            raise RuntimeError(f"{partition} requires --gate-doc {expected}")
    gate_sha = sha(gate_doc) if gate_doc else None
    if out.is_symlink() or (out / partition).exists():
        raise RuntimeError("Symlinked root or existing partition refused")
    if prior_wall >= 1200:
        raise RuntimeError("Cumulative generation cap reached")
    roots = seed_search_roots or []
    if rows_override is None and not roots:
        raise RuntimeError("Generation requires at least one --seed-search-root")
    if any(not root.is_dir() for root in roots):
        raise RuntimeError("Seed search root absent")
    used, searched = scan_used_seeds(roots)
    for manifest_path in out.glob("*/manifest.json"):
        used.update(_seed_values(json.loads(manifest_path.read_text())))
    seeds, noise_seeds, nuisance_seeds = reserve_seeds(partition, used, rows)
    if len(set(seeds + noise_seeds + nuisance_seeds)) != 3 * rows or set(seeds + noise_seeds + nuisance_seeds) & used:
        raise RuntimeError("Seed collision within or across partitions")
    prior_fingerprints, fingerprint_sources = consumed_field_fingerprints(roots)
    fingerprints = [field_fingerprint(seed) for seed in seeds]
    overlap = len(set(fingerprints) & prior_fingerprints)
    if overlap or len(set(fingerprints)) != rows:
        raise RuntimeError(f"Field fingerprint overlap or duplicate: {overlap}")
    recipe = json.loads(RECIPE.read_text())["config"]
    horizon = int(recipe["splits"]["train"])
    if recipe["noise_mode"] != "stochastic" or horizon <= 0:
        raise RuntimeError("Unexpected production stochastic training recipe")
    out.mkdir(parents=True, exist_ok=True)
    dest = out / partition
    dest.mkdir()
    write_json(dest / "INCOMPLETE.json", {"partition": partition})
    (SimOSAdapter, OUNoiseConfig, SimulationConfig, sample_spherical,
     corrupt_spectrum, sample_trajectory, compute_linewidth,
     apply_shot_noise, photons_for_dip_snr, source_root) = _source_imports(sim_src)
    index_streams = np.random.SeedSequence(master).spawn(4)[3].spawn(rows)
    indices = [int(np.random.default_rng(stream).integers(0, horizon)) for stream in index_streams]
    ou = OUNoiseConfig(**recipe["ou_noise"])
    nuisances = []
    for seed, index in zip(nuisance_seeds, indices):
        check_budget(started, prior_wall, partition)
        T, B1 = sample_trajectory(ou, index + 1, seed=seed)
        nuisances.append((float(T[-1]), float(B1[-1])))
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
        for index, (seed, (T_K, mw_scale)) in enumerate(zip(seeds, nuisances)):
            check_budget(started, prior_wall, partition)
            with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings(record=True) as seen:
                warnings.simplefilter("always")
                x, b, p, f = render_field(adapter, seed, T_K, mw_scale, p1,
                                          tuple(recipe["test_b1_gradient_range"]),
                                          sample_spherical, corrupt_spectrum)
            predicted_b, predicted_gradient = field_components(seed)
            np.testing.assert_array_equal(b, predicted_b)
            np.testing.assert_allclose(
                (p[2] - recipe["test_b1_gradient_range"][0]) /
                np.diff(recipe["test_b1_gradient_range"])[0], predicted_gradient,
                atol=1e-15, rtol=0)
            spectra[index], labels[index], params[index] = x, b, p
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
    check_budget(started, prior_wall, partition)
    source_files = ["adapters/simos_adapter.py", "pipelines/batch_generate.py",
                    "physics/lineshape.py", "physics/parameters.py", "physics/shot_noise.py",
                    "physics/noise_injection.py"]
    manifest = {
        "schema": 1, "partition": partition, "rows_per_cell": rows, "total_rows": rows * len(CELLS),
        "master_seed": master, "sample_seeds": seeds, "noise_seeds": noise_seeds,
        "nuisance_seeds": nuisance_seeds, "trajectory_seeds": nuisance_seeds,
        "field_ids": [f"{partition}-{i:04d}" for i in range(rows)],
        "nuisance_group_ids": [f"{partition}-ou-{i:04d}" for i in range(rows)],
        "nuisance_fields": [{"trajectory_seed": seed, "horizon": horizon, "sample_index": k,
                             "T_K": T, "mw_power_scale": b1, "nuisance_group_id": f"{partition}-ou-{i:04d}"}
                            for i, (seed, k, (T, b1)) in enumerate(zip(nuisance_seeds, indices, nuisances))],
        "field_parameter_fingerprints": fingerprints,
        "overlap_check": {"seed_overlap": 0, "field_fingerprint_overlap": overlap,
                          "consumed_fingerprint_sources": fingerprint_sources},
        "seed_search": searched, "excluded_master_seeds": sorted(EXCLUDED),
        "single_orientation": True, "frequency_grid_hz": freq.tolist(),
        "field_prior": {"magnitude_uT": [20, 70], "magnitude_distribution": "uniform",
                        "direction": "isotropic spherical"},
        "nuisance_distribution": {"ou": recipe["ou_noise"],
                                  "b1_gradient_uniform_range": recipe["test_b1_gradient_range"],
                                  "b_perp_T": 0, "horizon": horizon,
                                  "sample_index_rule": "uniform integer 0..H-1, independent per-field stream",
                                  "independent_trajectory_per_field": True},
        "horizon_source_sha256": sha(RECIPE),
        "gate_document_sha256": gate_sha,
        "units": {"spectra": "normalized fluorescence", "truth_vectors_T": "T",
                  "frequencies_hz": "Hz", "nuisance_params": ["ppm", "K", "unitless", "T", "unitless"]},
        "cells": records, "rendered_linewidths": {str(k): v for k, v in broadened.items()},
        "noise_reference_fraction": .30,
        "generator_commit": git_head(REPO),
        "generator_commit_contains_script": subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", "HEAD:scripts/make_scalar_repair_partitions.py"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0,
        "generator_sha256": sha(Path(__file__)), "stress_generator_sha256": sha(REPO / "experiments/scalar_stress_test/generate_stress_data.py"),
        "protocol_sha256": sha(PROTOCOL),
        "simulator_commit": git_head(source_root),
        "source_sha256": {name: sha(source_root / name) for name in source_files},
        "wall_seconds": elapsed, "cpu_seconds": cpu,
        "peak_memory_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "label_or_baseline_summary_disclosed": False,
    }
    check_budget(started, prior_wall, partition)
    if gate_doc and sha(gate_doc) != gate_sha:
        raise RuntimeError("Gate document changed during generation")
    write_json(dest / "manifest.json", manifest)
    check_budget(started, prior_wall, partition)
    (dest / "INCOMPLETE.json").unlink()
    for path in dest.iterdir():
        path.chmod(0o444)
    dest.chmod(0o555)
    result = verify(out, partition)
    result.update({"wall_seconds": elapsed, "cpu_seconds": cpu,
                   "peak_memory_bytes": manifest["peak_memory_bytes"]})
    return result


def generate(out: Path, partition: str, *, rows_override: int | None = None,
             gate_doc: Path | None = None, seed_search_roots: list[Path] | None = None,
             sim_src: Path | None = None) -> dict:
    started, cpu_started = time.monotonic(), time.process_time()
    result = None
    try:
        result = _generate(out, partition, rows_override=rows_override, gate_doc=gate_doc,
                           seed_search_roots=seed_search_roots, sim_src=sim_src)
        return result
    finally:
        append_ledger("scalar_repair_generation", partition, started, cpu_started,
                      result is not None,
                      **({"manifest_sha256": result["manifest_sha256"]} if result else {}))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--partition", choices=PARTITIONS)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--gate-doc", type=Path)
    parser.add_argument("--seed-search-root", type=Path, action="append", default=[])
    parser.add_argument("--sim-src", type=Path)
    args = parser.parse_args()
    if args.test:
        started, cpu_started = time.monotonic(), time.process_time()
        children_before = resource.getrusage(resource.RUSAGE_CHILDREN)
        child_cpu_before = children_before.ru_utime + children_before.ru_stime
        env = dict(os.environ, SCALAR_REPAIR_PARENT_JOB="test")
        try:
            completed = subprocess.run([sys.executable, "-m", "pytest", "-q", "--disable-warnings",
                                        "-p", "no:cacheprovider",
                                        str(REPO / "tests/test_make_scalar_repair_partitions.py"),
                                        str(REPO / "tests/test_scalar_repair_custody.py")], env=env, check=False)
        finally:
            children_after = resource.getrusage(resource.RUSAGE_CHILDREN)
            append_ledger("scalar_repair_test", None, started, cpu_started,
                          "completed" in locals() and completed.returncode == 0,
                          cpu_seconds=time.process_time() - cpu_started +
                          children_after.ru_utime + children_after.ru_stime - child_cpu_before,
                          peak_memory_bytes=max(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                                children_after.ru_maxrss) * 1024)
        raise SystemExit(completed.returncode)
    if args.partition is None or args.out is None:
        parser.error("--partition and --out are required for generation or verification")
    if args.verify:
        started, cpu_started = time.monotonic(), time.process_time()
        result = None
        try:
            result = verify(args.out, args.partition)
        finally:
            append_ledger("scalar_repair_verify", args.partition, started, cpu_started,
                          result is not None)
    else:
        result = generate(args.out, args.partition, gate_doc=args.gate_doc,
                          seed_search_roots=args.seed_search_root, sim_src=args.sim_src)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
