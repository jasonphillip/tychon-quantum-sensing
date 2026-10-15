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


def inspect_positions(manifest_path):
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    if manifest.get("schema_version") != 1 or manifest.get("dataset_doi") != "10.5281/zenodo.19855773":
        raise ValueError("wrong dataset contract")
    if manifest.get("measured_only") is not True or manifest.get("positions_unit") != "um":
        raise ValueError("measured-only provenance and micrometre position units are required")
    if not all(re.fullmatch(r"[0-9a-f]{64}", manifest.get(key, "")) for key in ("archive_sha256", "extraction_source_sha256")):
        raise ValueError("original archive and custody extraction hashes required")
    if manifest.get("license") != "CC-BY-4.0" or not manifest.get("source_members"):
        raise ValueError("license and exact original archive members required")
    if manifest.get("position_reference") != "motor_stage_xy_fixed_target_height_and_orientation":
        raise ValueError("independent stage-label reference must be explicit")
    if manifest.get("source_row_alignment_status") != "verified_figS4_main_byte_identity":
        raise ValueError("custody must verify the main arrays match their Fig.S4 source bytes")
    headers = {}
    keys = ("positions",) if "positions" in manifest else ("position_x", "position_y")
    for key in keys:
        headers[key] = npy_header(checked_path(path.parent, manifest[key]))
    n = headers[keys[0]]["shape"][0]
    expected = [n, 2] if keys == ("positions",) else [n]
    if any(headers[k]["shape"] != expected for k in keys):
        raise ValueError("expected stage positions [N,2] or separate x/y [N]")
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


def positions_only(manifest_path):
    """Read only approved position labels, never feature files or their headers."""
    import numpy as np
    path = Path(manifest_path).resolve()
    manifest, metadata = inspect_positions(path)
    if "positions" in manifest:
        y = np.load(checked_path(path.parent, manifest["positions"]), allow_pickle=False)
    else:
        y = np.column_stack([np.load(checked_path(path.parent, manifest[k]), allow_pickle=False)
                             for k in ("position_x", "position_y")])
    y = np.asarray(y, dtype=float)
    if not np.isfinite(y).all():
        raise ValueError("nonfinite stage labels")
    return y, manifest, metadata


def possible_sessions(manifest_path, positions):
    """Conservative memberships; never pretend archive order proves acquisition order."""
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    catalog = read_json(checked_path(path.parent, manifest["raw_position_catalog"]))
    lookup = {}
    for row in catalog:
        key = tuple(float(v) for v in row["position_um"])
        session = row["session_id"]
        if len(key) != 2 or not isinstance(session, str) or not session:
            raise ValueError("invalid source position/session catalog")
        lookup.setdefault(key, set()).add(session)
    groups = [sorted(lookup.get(tuple(float(v) for v in row), set())) for row in positions]
    if any(not group for group in groups):
        raise ValueError("a fitted-array position has no raw-file session provenance")
    return groups


def supplied_position_summary(manifest_path, positions):
    """Compare label tables only; never infer a unique row match from duplicates."""
    import numpy as np
    from collections import Counter
    path = Path(manifest_path).resolve()
    manifest = read_json(path)
    names = ("supplied_train_positions", "supplied_validation_positions", "supplied_test_positions", "published_test_labels")
    if not all(name in manifest for name in names):
        return {"status": "not_provided_no_split_relationship_claim"}
    tables = {}
    for name in names:
        source = checked_path(path.parent, manifest[name])
        header = npy_header(source)
        if len(header["shape"]) != 2 or header["shape"][1] != 2:
            raise ValueError("supplied stage-coordinate table has wrong shape")
        values = np.asarray(np.load(source, allow_pickle=False), dtype=float)
        if not np.isfinite(values).all():
            raise ValueError("nonfinite supplied stage-coordinate table")
        tables[name] = [tuple(float(v) for v in row) for row in values]
    count = Counter(tuple(float(v) for v in row) for row in positions)
    combined = Counter(row for name in names[:3] for row in tables[name])
    return {
        "status": "position_labels_only_not_prediction_reproduction",
        "rows": {name: len(rows) for name, rows in tables.items()},
        "unique_positions": {name: len(set(rows)) for name, rows in tables.items()},
        "coordinate_overlap": {a + "__" + b: len(set(tables[a]) & set(tables[b]))
                               for a, b in ((names[0], names[1]), (names[0], names[2]), (names[1], names[2]))},
        "combined_supplied_position_multiset_matches_main": combined == count,
        "supplied_test_equals_published_labels_in_order": tables[names[2]] == tables[names[3]],
        "supplied_rows_with_ambiguous_main_position_match": {name: sum(count[row] > 1 for row in rows)
                                                            for name, rows in tables.items()},
        "row_indices_reconstructed": False,
        "separate_day_raw_test_identity_established": False,
    }


def inspect_bundle(manifest_path):
    path = Path(manifest_path).resolve()
    manifest, metadata = inspect_positions(path)
    if manifest.get("feature_order") != "channel_major_splitting_std1_std2_MHz":
        raise ValueError("feature semantics must be explicit")
    if manifest.get("feature_calibration_access") not in ("independent", "per_sample_only"):
        raise ValueError("features must not use held-out aggregate calibration")
    n = metadata["n"]
    if "features" in manifest:
        header = npy_header(checked_path(path.parent, manifest["features"]))
        if header["shape"] != [n, 24]:
            raise ValueError("expected features [N,24]")
        metadata["headers"]["features"] = header
    else:
        if manifest.get("native_fit_units") != "GHz" or manifest.get("native_to_feature_factor") != 1000:
            raise ValueError("native GHz-to-MHz conversion must be explicit")
        for name in ("fit_parameters", "fit_standard_deviations"):
            header = npy_header(checked_path(path.parent, manifest[name]))
            if header["shape"] != [n, 8, 6] or not re.fullmatch(r"[<>=|]f[48]", header["dtype"]):
                raise ValueError("expected plain floating fitted arrays [N,8,6]")
            metadata["headers"][name] = header
    return manifest, metadata


def arrays(manifest_path, indices=None):
    # Called only after the numerical guard. mmap avoids reading other rows.
    import numpy as np
    path = Path(manifest_path).resolve()
    manifest, metadata = inspect_bundle(path)
    if indices is None:
        raise ValueError("feature access requires explicit approved row indices")
    y, _, _ = positions_only(path)
    y = y[indices]
    if "features" in manifest:
        x = np.load(checked_path(path.parent, manifest["features"]), allow_pickle=False, mmap_mode="r")[indices]
    else:
        p = np.load(checked_path(path.parent, manifest["fit_parameters"]), allow_pickle=False, mmap_mode="r")[indices]
        s = np.load(checked_path(path.parent, manifest["fit_standard_deviations"]), allow_pickle=False, mmap_mode="r")[indices]
        x = np.stack((np.abs(p[:, :, 1] - p[:, :, 4]), s[:, :, 1], s[:, :, 4]), axis=2).reshape(len(indices), 24) * 1000.0
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(y).all() or (x <= 0).any():
        raise ValueError("invalid measured rows; no silent filtering is permitted")
    return x, y, manifest, metadata
