"""Top-level builder for the orbit-in-the-loop benchmark.

Loads ``configs/orbit_benchmark_v1.yaml``, propagates each TLE, and returns
``(batches, producer_manifest)`` matching the input contract of
``tychon_shared_data.orbit_in_the_loop.OrbitDatasetWriter.write_all``.

This module performs no disk I/O on its outputs; the writer (in
tychon-shared-data) is responsible for parquet shards and the typed
``OrbitManifest`` JSON sidecar.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from .adcs import ADCS_RULE_ID, ADCS_RULE_VERSION, QUATERNION_CONVENTION
from .igrf_field import IGRF_MODEL_VERSION, _ppigrf_version, epoch_decimal_year
from .sgp4_propagator import FRAME_NOTE, SGP4_VERSION
from .trajectory import OrbitSpec, build_trajectory_batch


_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_V1_PATH = _REPO_ROOT / "configs" / "orbit_benchmark_v1.yaml"


def _verify_tle_checksum(line: str) -> None:
    if len(line) != 69:
        raise ValueError(f"TLE line must be 69 chars, got {len(line)}: {line!r}")
    s = 0
    for c in line[:-1]:
        if c.isdigit():
            s += int(c)
        elif c == "-":
            s += 1
    expected = s % 10
    last = line[-1]
    if not last.isdigit():
        raise ValueError(
            f"TLE checksum mismatch: line ends in {last!r}, expected digit {expected}: {line!r}"
        )
    actual = int(last)
    if expected != actual:
        raise ValueError(
            f"TLE checksum mismatch: line ends in {actual}, expected {expected}: {line!r}"
        )


def _git_sha(repo_path: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def _tychon_shared_data_git_sha() -> str:
    """Best-effort lookup of the installed tychon-shared-data package SHA.

    The path is hard-coded to the local sibling-repo convention; an
    air-gapped Spark would have ``~/projects/tychon-shared-data`` synced via
    Syncthing. Falls back to "unknown" cleanly if not present.
    """
    candidate = Path.home() / "projects" / "tychon-shared-data"
    if not candidate.exists():
        return "unknown"
    return _git_sha(candidate)


def load_benchmark_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read v1 YAML and verify every TLE checksum before returning."""
    cfg_path = Path(path) if path is not None else _DEFAULT_V1_PATH
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    for entry in cfg["orbits"]:
        line1 = entry["tle"]["line1"].strip()
        line2 = entry["tle"]["line2"].strip()
        _verify_tle_checksum(line1)
        _verify_tle_checksum(line2)
    return cfg


def build_orbit_benchmark(
    config_path: str | Path | None = None,
) -> tuple[list[dict[str, np.ndarray]], dict[str, Any]]:
    """Run the full SGP4 → IGRF-14 → nadir → payload chain for every orbit in the v1 config.

    Returns
    -------
    batches : list[dict[str, np.ndarray]]
        One ``TrajectoryBatch`` per orbit_id, each a 15-key dict matching
        ``tychon_shared_data.orbit_in_the_loop.ORBIT_COLUMNS``.
    producer_manifest : dict
        All sub-dicts (``sgp4``, ``igrf``, ``adcs``, ``splits``, ``orbits``,
        ``units``, ``master_seed``, ``sample_dt_s``) needed by
        ``OrbitDatasetWriter.write_manifest``. The writer fills in
        per-shard ``shard_path`` / ``sha256`` / ``n_samples``.
    """
    cfg = load_benchmark_config(config_path)
    igrf_date = datetime.fromisoformat(cfg["igrf_date"])

    batches: list[dict[str, np.ndarray]] = []
    orbits_meta: list[dict[str, Any]] = []
    tles_meta: list[dict[str, Any]] = []

    for entry in cfg["orbits"]:
        line1 = entry["tle"]["line1"].strip()
        line2 = entry["tle"]["line2"].strip()
        spec = OrbitSpec(
            orbit_id=int(entry["orbit_id"]),
            line1=line1,
            line2=line2,
            duration_s=float(cfg["duration_s"]),
            dt_s=float(cfg["dt_s"]),
        )
        batch, meta = build_trajectory_batch(spec, igrf_date)
        batches.append(batch)
        orbits_meta.append(
            {
                "orbit_id": meta["orbit_id"],
                "tle_epoch_utc": meta["tle_epoch_utc"],
                "n_samples": meta["n_samples"],
                "label": entry.get("label", ""),
            }
        )
        tles_meta.append(
            {
                "orbit_id": int(entry["orbit_id"]),
                "line1": line1,
                "line2": line2,
                "label": entry.get("label", ""),
            }
        )

    units = {
        "t": "s_since_orbit_epoch",
        "lat": "deg",
        "lon": "deg",
        "alt": "m",
        "roll": "rad",
        "pitch": "rad",
        "yaw": "rad",
        "q_eb": "unit_quaternion",
        "B_payload_x": "T",
        "B_payload_y": "T",
        "B_payload_z": "T",
    }

    producer_manifest: dict[str, Any] = {
        "master_seed": int(cfg["master_seed"]),
        "sample_dt_s": float(cfg["dt_s"]),
        "sgp4": {
            "tles": tles_meta,
            "frame_note": FRAME_NOTE,
            "sgp4_version": SGP4_VERSION,
        },
        "igrf": {
            "model_version": IGRF_MODEL_VERSION,
            "epoch_decimal_year": epoch_decimal_year(igrf_date),
            "ppigrf_version": _ppigrf_version(),
        },
        "adcs": {
            "attitude_convention": "ZYX_intrinsic_tait_bryan",
            "quaternion_convention": QUATERNION_CONVENTION,
            "pointing_rule_id": ADCS_RULE_ID,
            "pointing_rule_version": ADCS_RULE_VERSION,
        },
        "splits": cfg.get("splits", {"all": [m["orbit_id"] for m in orbits_meta]}),
        "orbits": orbits_meta,
        "units": units,
        "generator_git_sha": _git_sha(_REPO_ROOT),
        "tychon_shared_data_git_sha": _tychon_shared_data_git_sha(),
    }

    return batches, producer_manifest


__all__ = [
    "build_orbit_benchmark",
    "load_benchmark_config",
]
