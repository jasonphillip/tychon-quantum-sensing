#!/usr/bin/env python3
"""Generate disjoint DEV/VAL partitions and protect the untouched FINAL holdout.

Version 1 adopts the released schema-1 set with --adopt-legacy. Never regenerates
v1 FINAL. Use --partition dev or val after adoption; --verify checks every present
partition and reports whether the version has all three partitions.
Masters advance by calendar month from October 2026, ordered final/dev/val:
v1=20261014/20261114/20261214; v2=20270114/20270214/20270314.
Every version has a 3000-sequence and cumulative 3600-second generation cap.
No overwrite option exists. Interrupted or failed output requires manual review.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import signal
import os
import re
import stat
import tempfile
from contextlib import contextmanager
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIM = None
MASTER_SEED = 20261014
MAX_SEQUENCES = 3000
MAX_SECONDS = 3600
REPLICATES = 3
PARTITIONS = ("final", "dev", "val")
PER_REPLICATE = {"final": 40, "dev": 14, "val": 14}
LEGACY_SECONDS = 631.5178541119676
LEGACY_SHA256 = "c4a11eeb473152355ca0d8438fd9f6219fea245418eb8c9cb6b7c126c1b72ade"
ARRAY_NAME = "dataset.h5"
HASH_RULE = "MD5 of sorted relative dataset.h5 paths (4-byte big-endian length + path UTF-8 + raw file bytes)"
SEED_SCHEDULE = "Calendar months from October 2026; three months per version, ordered final/dev/val; day 14."
# These are the files produced by the pinned sequence generators.
REPLICATE_FILES = {ARRAY_NAME, "manifest.json"}


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


def _seed(name: str, replicate: int, master_seed: int = MASTER_SEED) -> int:
    # Common random numbers pair all in-envelope trajectories across OFAT cells.
    # The extrapolation generator uses its own geometry and seed stream.
    family = "extrapolation" if name == "extrapolation" else "in_envelope"
    digest = hashlib.sha256(f"{master_seed}:{family}:{replicate}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % (2**31 - 1) + 1


def _p1_for_linewidth(mhz: float) -> float:
    from nv_sensor_sim.physics.parameters import compute_linewidth

    floor = compute_linewidth(0.0)
    target = mhz * 1e6
    if target < floor:
        raise ValueError(f"linewidth {mhz} MHz is below the physical floor")
    return (math.pi * target - 1 / 1.48e-6) * 9.9e-6


def _read_config(path: Path) -> dict:
    import yaml

    cfg = yaml.safe_load(path.read_text())
    return {key: tuple(value) if isinstance(value, list) and key in {
        "bias_direction_uvw", "sweep_scalar_range_T", "freq_range_Hz",
        "axis_contrast_scale", "reversal_turn_frac_range",
    } else value for key, value in cfg.items()}


def _call_generator(output: Path, cell: dict, seed: int, n_seq: int) -> dict:
    from nv_sensor_sim.pipelines.fieldcone_generate import generate_fieldcone_dataset
    from nv_sensor_sim.pipelines.sequence_generate import generate_sequence_dataset

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
    import h5py
    import numpy as np
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr

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


def paths(version: int) -> tuple[Path, Path]:
    return (ROOT / "data" / f"comparison_test_v{version}",
            ROOT / "docs" / f"comparison_test_v{version}.manifest.json")


def master_seed(partition: str, version: int) -> int:
    if type(version) is not int or version < 1 or partition not in PARTITIONS:
        raise ValueError("version must be positive and partition must be final/dev/val")
    month = 2026 * 12 + 9 + (version - 1) * 3 + PARTITIONS.index(partition)
    year, month0 = divmod(month, 12)
    return year * 10000 + (month0 + 1) * 100 + 14


def _safe_path(path: Path) -> None:
    """Reject filesystem links and special files within the workspace boundary."""
    path.relative_to(ROOT)
    for node in [path, *path.parents]:
        if node == ROOT:
            break
        if node.is_symlink():
            raise RuntimeError(f"symlink is forbidden: {node}")
        if node.exists() and not (node.is_dir() or node.is_file()):
            raise RuntimeError(f"special file is forbidden: {node}")
        if node.is_file() and node.stat().st_nlink != 1:
            raise RuntimeError(f"hard-linked file is forbidden: {node}")


def _children(path: Path, expected: set[str], *, directories: bool) -> None:
    _safe_path(path)
    if not path.is_dir() or {p.name for p in path.iterdir()} != expected:
        raise RuntimeError(f"unexpected or incomplete directory: {path}")
    for node in path.iterdir():
        _safe_path(node)
        if (node.is_dir() if directories else node.is_file()) is not True:
            raise RuntimeError(f"unexpected file type: {node}")


def _read_json(path: Path) -> dict:
    _safe_path(path)
    def no_duplicates(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result
    value = json.loads(path.read_text(), object_pairs_hook=no_duplicates,
                       parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
    if not isinstance(value, dict):
        raise RuntimeError(f"manifest is not an object: {path}")
    return value


def _atomic_bytes(path: Path, content: bytes) -> None:
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_manifest(path: Path, value: dict) -> None:
    _atomic_bytes(path, (json.dumps(value, indent=2, allow_nan=False) + "\n").encode())


@contextmanager
def _lock(version: int):
    _, manifest = paths(version)
    path = manifest.with_suffix(".lock")
    _safe_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, f"pid={os.getpid()}\n".encode())
        yield
    finally:
        os.close(fd)
        path.unlink()


def _number(value, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise RuntimeError(f"invalid {label}")
    return value


def _validate_partition(record: dict, partition: str, version: int) -> None:
    n = PER_REPLICATE[partition]
    expected_count = len(cells()) * REPLICATES * n
    for key, expected in {"master_seed": master_seed(partition, version),
                          "cell_count": len(cells()), "sequences_per_cell_seed": n,
                          "total_sequences": expected_count}.items():
        if type(record.get(key)) is not int or record[key] != expected:
            raise RuntimeError(f"{partition}: invalid {key}")
    _number(record.get("generation_wall_s"), "partition generation_wall_s")
    if record.get("array_hash_rule") != HASH_RULE:
        raise RuntimeError("array hash rule differs from original")
    records = record.get("cells")
    if not isinstance(records, list) or len(records) != len(cells()):
        raise RuntimeError(f"{partition}: wrong registered cell count")
    for actual, expected in zip(records, cells()):
        if not isinstance(actual, dict) or any(actual.get(k) != v for k, v in expected.items()):
            raise RuntimeError(f"{partition}: grid name, rung, order or configuration differs")
        reps = actual.get("replicates")
        if not isinstance(reps, list) or len(reps) != REPLICATES:
            raise RuntimeError("wrong replicate count")
        seeds = [_seed(expected["name"], i, record["master_seed"]) for i in range(REPLICATES)]
        if actual.get("seed") != seeds or actual.get("n_sequences") != REPLICATES * n:
            raise RuntimeError("wrong cell seeds or sequence count")
        if actual.get("n_frames") != 256:
            raise RuntimeError("wrong cell frame count")
        if not isinstance(actual.get("data_md5"), str) or not re.fullmatch(r"[0-9a-f]{32}", actual["data_md5"]):
            raise RuntimeError("malformed cell data_md5")
        for i, rep in enumerate(reps):
            for key, expected_value in {"index": i, "seed": seeds[i], "n_sequences": n,
                                        "n_frames": 256}.items():
                if type(rep.get(key)) is not int or rep[key] != expected_value:
                    raise RuntimeError(f"invalid replicate {key}")


def _validate_legacy(record: dict) -> None:
    if record.get("schema") != 1:
        raise RuntimeError("legacy adoption requires schema 1")
    _validate_partition(record, "final", 1)
    if record["generation_wall_s"] != LEGACY_SECONDS:
        raise RuntimeError("legacy generation wall time differs from released set")


def _new_manifest(version: int) -> dict:
    return {"schema": 2, "version": version, "seed_schedule": SEED_SCHEDULE,
            "sequence_cap": MAX_SEQUENCES, "generation_time_cap_s": MAX_SECONDS,
            "planned_total_sequences": sum(PER_REPLICATE.values()) * REPLICATES * len(cells()),
            "array_hash_rule": HASH_RULE, "partitions": {}, "attempts": [],
            "total_sequences": 0, "generation_wall_s": 0.0}


def _update_totals(record: dict) -> None:
    record["total_sequences"] = sum(p["total_sequences"] for p in record["partitions"].values())
    record["generation_wall_s"] = (sum(p["generation_wall_s"] for p in record["partitions"].values())
                                   + sum(a["generation_wall_s"] for a in record["attempts"]))


def _validate_manifest(record: dict, version: int, *, complete: bool) -> None:
    expected = _new_manifest(version)
    for key in ("schema", "version", "seed_schedule", "sequence_cap", "generation_time_cap_s",
                "planned_total_sequences", "array_hash_rule"):
        if record.get(key) != expected[key] or type(record.get(key)) is not type(expected[key]):
            raise RuntimeError(f"manifest {key} differs from registered protocol")
    parts = record.get("partitions")
    if not isinstance(parts, dict) or not set(parts).issubset(PARTITIONS):
        raise RuntimeError("unexpected partition")
    if complete and set(parts) != set(PARTITIONS):
        raise RuntimeError("verification requires final, dev and val")
    for name, partition in parts.items():
        _validate_partition(partition, name, version)
    attempts = record.get("attempts")
    if not isinstance(attempts, list):
        raise RuntimeError("missing generation attempt ledger")
    for attempt in attempts:
        if (attempt.get("partition") not in PARTITIONS or attempt.get("status") not in {"pending", "failed"}
                or attempt["partition"] in parts):
            raise RuntimeError("invalid generation attempt ledger")
        _number(attempt.get("generation_wall_s"), "attempt generation_wall_s")
    if attempts:
        raise RuntimeError("incomplete generation attempt; inspect partial output before proceeding")
    total = sum(p["total_sequences"] for p in parts.values())
    elapsed = sum(p["generation_wall_s"] for p in parts.values())
    if record.get("total_sequences") != total or record.get("generation_wall_s") != elapsed:
        raise RuntimeError("aggregate sequence or generation-time accounting mismatch")
    if total > MAX_SEQUENCES or expected["planned_total_sequences"] > MAX_SEQUENCES or elapsed > MAX_SECONDS:
        raise RuntimeError("cumulative version budget exceeded")
    if version == 1:
        if "final" not in parts:
            raise RuntimeError("version 1 requires adopted legacy FINAL")
        raw = record.get("legacy_manifest_utf8")
        if not isinstance(raw, str) or record.get("legacy_manifest_sha256") != LEGACY_SHA256:
            raise RuntimeError("missing or changed released legacy manifest provenance")
        if hashlib.sha256(raw.encode()).hexdigest() != LEGACY_SHA256:
            raise RuntimeError("legacy manifest SHA256 mismatch")
        legacy = json.loads(raw)
        _validate_legacy(legacy)
        if parts["final"] != {k: v for k, v in legacy.items() if k != "schema"}:
            raise RuntimeError("FINAL record differs from original legacy manifest")



def _seed_values(version: int, partition: str) -> set[int]:
    master = master_seed(partition, version)
    values = set()
    # Identical family/replicate seeds across OFAT cells are deliberate pairing.
    for name in ("clean", "extrapolation"):
        for i in range(REPLICATES):
            seed = _seed(name, i, master)
            stream = {seed, *range(seed + master, seed + master + PER_REPLICATE[partition])}
            if len(stream) != PER_REPLICATE[partition] + 1 or values & stream:
                raise RuntimeError("seed streams collide within a partition")
            values.update(stream)
    return values


def _preflight_seeds(version: int) -> None:
    versions = {version}
    docs = ROOT / "docs"
    _safe_path(docs)
    if docs.exists():
        for path in docs.glob("comparison_test_v*.manifest.json"):
            match = re.fullmatch(r"comparison_test_v([1-9][0-9]*)\.manifest\.json", path.name)
            if not match:
                continue
            other = int(match[1])
            value = _read_json(path)
            if value.get("schema") == 1 and other == 1:
                _validate_legacy(value)
            else:
                _validate_manifest(value, other, complete=False)
            versions.add(other)
    used = set()
    for item in sorted(versions):
        for partition in PARTITIONS:
            stream = _seed_values(item, partition)
            if used & stream:
                raise RuntimeError("cross-partition or cross-version seed-stream collision")
            used.update(stream)


def _verify_tree(directory: Path, record: dict, *, readonly: bool = False) -> None:
    import h5py

    _children(directory, {c["name"] for c in cells()}, directories=True)
    for cell in record["cells"]:
        cell_dir = directory / cell["name"]
        _children(cell_dir, {f"seed_{i}" for i in range(REPLICATES)}, directories=True)
        for rep in cell["replicates"]:
            rep_dir = cell_dir / f"seed_{rep['index']}"
            _children(rep_dir, REPLICATE_FILES, directories=False)
            path = rep_dir / ARRAY_NAME
            with h5py.File(path, "r") as h5:
                if h5["test/spectra"].shape[:2] != (rep["n_sequences"], rep["n_frames"]):
                    raise RuntimeError(f"wrong array shape: {path}")
        if data_md5(cell_dir) != cell["data_md5"]:
            raise RuntimeError(f"{cell['name']}: data_md5 mismatch")
    if readonly:
        for path in [directory, *directory.rglob("*")]:
            if stat.S_IMODE(path.stat().st_mode) & 0o222:
                raise RuntimeError(f"FINAL is writable: {path}")


def _verify_existing(record: dict, version: int, *, complete: bool = False) -> None:
    _validate_manifest(record, version, complete=complete)
    data, _ = paths(version)
    _children(data, set(record["partitions"]), directories=True)
    for name, partition in record["partitions"].items():
        _verify_tree(data / name, partition, readonly=name == "final")


def verify(version: int = 1) -> int:
    data, manifest = paths(version)
    record = _read_json(manifest)
    _verify_existing(record, version)
    _preflight_seeds(version)
    count = len(record["partitions"])
    status = "complete" if count == len(PARTITIONS) else "INCOMPLETE"
    names = ",".join(name for name in PARTITIONS if name in record["partitions"])
    final_status = "FINAL read-only" if "final" in record["partitions"] else "FINAL absent"
    print(f"verified v{version}: {status}, {count}/3 partitions ({names}), "
          f"{record['total_sequences']} sequences; {final_status}; "
          f"generation {record['generation_wall_s']:.6f}/{MAX_SECONDS}s")
    return 0


def adopt_legacy() -> int:
    data, manifest = paths(1)
    legacy = _read_json(manifest)
    _validate_legacy(legacy)
    _verify_tree(data, legacy)
    _preflight_seeds(1)
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != LEGACY_SHA256:
        raise RuntimeError("legacy manifest SHA256 differs from released v1")
    final = data / "final"
    record = _new_manifest(1)
    record.update(legacy_manifest_utf8=raw.decode(), legacy_manifest_sha256=LEGACY_SHA256)
    record["partitions"]["final"] = {k: v for k, v in legacy.items() if k != "schema"}
    _update_totals(record)
    moved = []
    modes = {}
    cell_modes = {}
    data_mode = stat.S_IMODE(data.stat().st_mode)
    try:
        # Retain parent owner-write on success for later DEV/VAL generation.
        # Linux also needs temporary owner-write on each moved cell directory
        # to update its parent link. Descendant and array modes stay unchanged.
        data.chmod(data_mode | stat.S_IWUSR)
        final.mkdir()
        for cell in cells():
            source = data / cell["name"]
            target = final / cell["name"]
            cell_modes[source] = stat.S_IMODE(source.stat().st_mode)
            source.chmod(cell_modes[source] | stat.S_IWUSR)
            source.rename(target)
            moved.append((source, target))
            target.chmod(cell_modes[source])
        for path in [*final.rglob("*"), final]:
            modes[path] = stat.S_IMODE(path.stat().st_mode)
            path.chmod(modes[path] & ~0o222)
        _verify_existing(record, 1)
        _write_manifest(manifest, record)
    except BaseException:
        # Restore original modes and locations; no array is opened for writing.
        for path, mode in sorted(modes.items(), key=lambda item: len(item[0].parts)):
            path.chmod(mode)
        for source, target in reversed(moved):
            target.chmod(stat.S_IMODE(target.stat().st_mode) | stat.S_IWUSR)
            target.rename(source)
        for source, mode in cell_modes.items():
            source.chmod(mode)
        if final.exists():
            final.rmdir()
        data.chmod(data_mode)
        if manifest.read_bytes() != raw:
            _atomic_bytes(manifest, raw)
        raise
    print(f"adopted untouched FINAL: 1680 sequences; legacy SHA256={record['legacy_manifest_sha256']}")
    return 0


def _resolve_sim_root(explicit: Path | None) -> Path:
    if explicit is None:
        import importlib.util
        spec = importlib.util.find_spec("nv_sensor_sim")
        if spec is None or spec.origin is None:
            raise RuntimeError("install editable nv_sensor_sim or pass --sim-root with its configs directory")
        candidates = [p for p in Path(spec.origin).resolve().parents if (p / "configs").is_dir()]
        if not candidates:
            raise RuntimeError("cannot locate nv_sensor_sim configs; pass --sim-root")
        explicit = candidates[0]
    root = explicit.expanduser().resolve()
    for name in ("sequence_train_v2.yaml", "sequence_eval_fieldcone_v1.yaml"):
        if not (root / "configs" / name).is_file():
            raise RuntimeError(f"missing simulation config: {root / 'configs' / name}")
    return root


def _generation_budget(record: dict, partition: str) -> float:
    planned = len(cells()) * REPLICATES * PER_REPLICATE[partition]
    if record["total_sequences"] + planned > MAX_SEQUENCES:
        raise RuntimeError("cumulative sequence budget exceeded")
    remaining = MAX_SECONDS - _number(record["generation_wall_s"], "cumulative generation_wall_s")
    if remaining <= 0:
        raise RuntimeError("cumulative generation-time budget exhausted")
    return remaining


def generate(partition: str, version: int, sim_root: Path | None) -> int:
    global SIM
    data, manifest = paths(version)
    _safe_path(data)
    _safe_path(manifest)
    target = data / partition
    if target.exists():
        raise FileExistsError(f"refusing to overwrite or regenerate existing {partition.upper()}: {target}")
    if manifest.exists():
        record = _read_json(manifest)
        if record.get("schema") == 1:
            raise RuntimeError("adopt the existing released set with --adopt-legacy first")
        _verify_existing(record, version)
    else:
        if version == 1:
            raise RuntimeError("v1 FINAL is legacy-only; --adopt-legacy requires its original manifest and data")
        if data.exists():
            raise RuntimeError("data exists without its manifest; refusing partial or unexpected output")
        record = _new_manifest(version)
    _preflight_seeds(version)
    remaining = _generation_budget(record, partition)
    SIM = _resolve_sim_root(sim_root)
    # Pending state survives a hard interruption and prevents an uncounted retry.
    attempt = {"partition": partition, "status": "pending", "generation_wall_s": 0.0,
               "remaining_budget_s": remaining}
    record["attempts"].append(attempt)
    _write_manifest(manifest, record)
    start = time.perf_counter()
    prior_handler = signal.getsignal(signal.SIGALRM)
    def timeout(*_):
        raise TimeoutError("cumulative 3600-second generation cap reached; partial output is not sealed")
    signal.signal(signal.SIGALRM, timeout)
    signal.setitimer(signal.ITIMER_REAL, remaining)
    try:
        data.mkdir(parents=True, exist_ok=True)
        target.mkdir()
        records = []
        n_seq = PER_REPLICATE[partition]
        master = master_seed(partition, version)
        for cell in cells():
            cell_dir = target / cell["name"]
            reps = []
            for index in range(REPLICATES):
                seed = _seed(cell["name"], index, master)
                output = cell_dir / f"seed_{index}"
                lineage = _call_generator(output, cell, seed, n_seq)
                aug = _augment(output / ARRAY_NAME, cell, seed + master)
                reps.append({"index": index, "seed": seed, "n_sequences": n_seq,
                             "n_frames": 256, "lineage": lineage, "augmentation": aug})
                print(f"{partition}/{cell['name']} seed_{index}: {n_seq} sequences; "
                      f"{time.perf_counter() - start:.1f}s", flush=True)
            records.append({**cell, "seed": [r["seed"] for r in reps],
                            "n_sequences": n_seq * REPLICATES, "n_frames": 256,
                            "replicates": reps, "data_md5": data_md5(cell_dir)})
        result = {"master_seed": master, "cell_count": len(records),
                  "sequences_per_cell_seed": n_seq, "total_sequences": len(records) * REPLICATES * n_seq,
                  "generation_wall_s": 0.0, "array_hash_rule": HASH_RULE,
                  "source_fieldcone_manifest_data_md5": "92dc06692d1975f6fcd101e70cc02d99",
                  "cells": records}
        _validate_partition(result, partition, version)
        _verify_tree(target, result)
        if partition == "final":
            for path in [*target.rglob("*"), target]:
                path.chmod(stat.S_IMODE(path.stat().st_mode) & ~0o222)
            _verify_tree(target, result, readonly=True)
        result["generation_wall_s"] = time.perf_counter() - start
        if result["generation_wall_s"] > remaining:
            timeout()
        record["attempts"].remove(attempt)
        record["partitions"][partition] = result
        _update_totals(record)
        _validate_manifest(record, version, complete=False)
        _write_manifest(manifest, record)
    except BaseException:
        # Do not delete failed output or reset consumed time. A later invocation
        # fails closed, even if the user removes the partial data directory.
        record["partitions"].pop(partition, None)
        if attempt not in record["attempts"]:
            record["attempts"].append(attempt)
        attempt.update(status="failed", generation_wall_s=time.perf_counter() - start)
        _update_totals(record)
        signal.setitimer(signal.ITIMER_REAL, 0)
        _write_manifest(manifest, record)
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior_handler)
    print(f"sealed v{version} {partition}: {result['total_sequences']} sequences; "
          f"cumulative generation {record['generation_wall_s']:.6f}/{MAX_SECONDS}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    action = ap.add_mutually_exclusive_group(required=True)
    action.add_argument("--adopt-legacy", action="store_true", help="move schema-1 v1 cells into read-only FINAL, preserving bytes and hashes")
    action.add_argument("--partition", choices=PARTITIONS, help="generate one absent partition; FINAL cannot be replaced")
    action.add_argument("--verify", action="store_true", help="verify all present partitions, hashes, seeds, caps and FINAL modes; report completeness")
    ap.add_argument("--version", type=int, default=1, help="positive version (default 1); v2 FINAL master=20270114")
    ap.add_argument("--sim-root", type=Path, help="nv-sensor-sim source root containing configs/; otherwise infer editable package root")
    args = ap.parse_args(argv)
    if args.version < 1:
        ap.error("--version must be positive")
    if args.adopt_legacy and args.version != 1:
        ap.error("legacy adoption is only valid for --version 1")
    if args.verify:
        return verify(args.version)
    with _lock(args.version):
        if args.adopt_legacy:
            return adopt_legacy()
        return generate(args.partition, args.version, args.sim_root)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"comparison set error: {exc}", file=sys.stderr)
        raise
