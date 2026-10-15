"""Custody contract and header-only inspection. Never infer scientific units."""
import ast
import json
from pathlib import Path
import struct
import re

from .guard import read_json, sha256


def checked_path(root, entry):
    rel = Path(entry["path"])
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("bundle paths must remain relative to its directory")
    path = (root / rel).resolve(strict=True)
    path.relative_to(root.resolve())
    if sha256(path) != entry["sha256"]:
        raise ValueError("custody payload hash mismatch: " + str(rel))
    return path


def npy_header(path):
    with Path(path).open("rb") as handle:
        if handle.read(6) != b"\x93NUMPY":
            raise ValueError("only ordinary NPY arrays are accepted")
        version = tuple(handle.read(2))
        if version == (1, 0):
            length = struct.unpack("<H", handle.read(2))[0]
            encoding = "latin1"
        elif version in ((2, 0), (3, 0)):
            length = struct.unpack("<I", handle.read(4))[0]
            encoding = "utf8" if version == (3, 0) else "latin1"
        else:
            raise ValueError("unsupported NPY version")
        if length > 65536:
            raise ValueError("unexpectedly large NPY header")
        header = ast.literal_eval(handle.read(length).decode(encoding))
    if not isinstance(header.get("descr"), str) or "O" in header["descr"]:
        raise ValueError("object and structured arrays are prohibited")
    return {"shape": list(header["shape"]), "dtype": header["descr"],
            "fortran_order": header["fortran_order"]}


def inspect_bundle(manifest_path):
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("dataset_doi") != "10.5281/zenodo.19855773":
        raise ValueError("wrong dataset contract")
    if manifest.get("measured_only") is not True or manifest.get("positions_unit") != "um":
        raise ValueError("measured-only provenance and micrometre position units are required")
    if manifest.get("feature_order") != "channel_major_splitting_std1_std2_MHz":
        raise ValueError("feature semantics must be explicit")
    if not all(re.fullmatch(r"[0-9a-f]{64}", manifest.get(key, "")) for key in ("archive_sha256", "extraction_source_sha256")):
        raise ValueError("original archive and custody extraction hashes required")
    if manifest.get("license") != "CC-BY-4.0" or not manifest.get("source_members"):
        raise ValueError("license and exact original archive members required")
    if manifest.get("position_reference") != "motor_stage_xy_fixed_target_height_and_orientation":
        raise ValueError("independent stage-label reference must be explicit")
    if manifest.get("feature_calibration_access") not in ("independent", "per_sample_only"):
        raise ValueError("features must not use held-out aggregate calibration")
    headers = {}
    for key in ("features", "positions"):
        headers[key] = npy_header(checked_path(path.parent, manifest[key]))
    n = headers["features"]["shape"][0]
    if headers["features"]["shape"] != [n, 24] or headers["positions"]["shape"] != [n, 2]:
        raise ValueError("expected measured features [N,24] and stage positions [N,2]")
    ids = read_json(checked_path(path.parent, manifest["sample_ids"]))
    if len(ids) != n or len(set(ids)) != n or not all(isinstance(x, str) for x in ids):
        raise ValueError("unique stable sample IDs required")
    if "acquisition_groups" in manifest:
        groups = read_json(checked_path(path.parent, manifest["acquisition_groups"]))
        if len(groups) != n:
            raise ValueError("acquisition grouping length mismatch")
    if "supplied_splits" in manifest:
        supplied = read_json(checked_path(path.parent, manifest["supplied_splits"]))
        flattened = [i for key in ("train", "validation", "test") for i in supplied[key]]
        if len(flattened) != len(set(flattened)) or any(type(i) is not int or not 0 <= i < n for i in flattened):
            raise ValueError("invalid supplied reproduction splits")
    return manifest, {"manifest_sha256": sha256(path), "n": n, "headers": headers,
                      "signal_values_inspected": False, "archive_sha256": manifest["archive_sha256"]}


def arrays(manifest_path, indices=None):
    # Called only after the numerical guard. mmap avoids reading other rows.
    import numpy as np
    path = Path(manifest_path).resolve()
    manifest, metadata = inspect_bundle(path)
    x = np.load(checked_path(path.parent, manifest["features"]), allow_pickle=False, mmap_mode="r")
    y = np.load(checked_path(path.parent, manifest["positions"]), allow_pickle=False, mmap_mode="r")
    if indices is not None:
        x, y = np.asarray(x[indices], dtype=float), np.asarray(y[indices], dtype=float)
        if not np.isfinite(x).all() or not np.isfinite(y).all() or (x <= 0).any():
            raise ValueError("invalid measured rows; no silent filtering is permitted")
    return x, y, manifest, metadata
