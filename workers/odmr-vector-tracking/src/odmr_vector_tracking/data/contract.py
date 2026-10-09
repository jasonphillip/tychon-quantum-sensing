"""v1 shared-data-contract validation for the time-series ODMR tracker datasets.

Validates the JSON sidecar manifest and the HDF5 dataset against the **v1** contract
(orchestrator-owned). This is the consumer side of the integration interface documented in
``docs/design/03_data_contract.md``; the upstream ``nv-sensor-sim`` session produces to the same
spec. Standalone — does not import ``nv_sensor_sim``.

Mirrors ``odmr_edge_ml.data.contracts`` (``REQUIRED_*`` dicts + ``validate_manifest`` with
numbered checks + ``ContractViolation``), extended for the temporal sequence schema (N, T, F, L)
and HDF5 dataset shape/dtype validation.

Contract changelog v0→v1: added ``line_collision (N,T,L)`` and ``seeds (N,)``.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np

CONTRACT_VERSION = "v1"

VALID_SPLITS = ("train", "val", "test")


class ContractViolation(ValueError):
    """Raised when a dataset/manifest fails v1 contract validation."""


# --- Manifest schema --------------------------------------------------------------------

# Required manifest fields and their JSON types. "Existing provenance/seed fields PLUS" the v1
# temporal/spectral additions, per the orchestrator spec.
# Field names follow the **actual upstream output** (verified against
# nv-sensor-sim/.../sequence_sanity_v0/manifest.json): the static-dataset ``n_spectra_*`` and
# ``freq_range_Hz`` names carry over to the sequence sets, and there is no ``contract_version``
# field (it is optional below). These differ from the orchestrator's prose paraphrase
# (``n_sequences_*`` / ``mw_window_Hz``) — flagged in docs/design/03_data_contract.md.
REQUIRED_MANIFEST_FIELDS: dict[str, type | tuple[type, ...]] = {
    # Provenance
    "generator_git_sha": str,
    "config_hash": str,
    "generated_at": str,
    "backend": str,
    # Seeds + split sizes
    "master_seed": int,
    "train_seeds": list,
    "val_seeds": list,
    "test_seeds": list,
    "n_spectra_train": int,
    "n_spectra_val": int,
    "n_spectra_test": int,
    # Temporal / spectral params (v1)
    "n_timesteps": int,
    "dt_s": (int, float),
    "n_lines": int,
    "hyperfine": bool,
    "linewidth_Hz": (int, float),
    "collision_threshold_linewidths": (int, float),
    "n_freq_points": int,
    "freq_range_Hz": list,
    # Bias + sweep description
    "bias_B0_T": (int, float),
    "bias_direction_uvw": list,
    "sweep_description": str,
    # Units
    "units": dict,
}

REQUIRED_UNITS: dict[str, str] = {
    "frequency": "Hz",
    "magnetic_field": "T",
    "time": "s",
}

# Range fields: exactly 2 elements with lo <= hi.
_RANGE_FIELDS = ["freq_range_Hz"]

# Provenance fields that must be non-empty strings.
_PROVENANCE_FIELDS = ["generator_git_sha", "config_hash", "generated_at", "backend"]

_SEED_FIELDS = [
    ("train_seeds", "n_spectra_train"),
    ("val_seeds", "n_spectra_val"),
    ("test_seeds", "n_spectra_test"),
]


def validate_manifest(manifest: dict) -> None:
    """Validate a manifest dict against the v1 schema.

    Raises
    ------
    ContractViolation
        If any check fails.
    """
    # 1. Required fields present.
    missing = set(REQUIRED_MANIFEST_FIELDS) - set(manifest)
    if missing:
        raise ContractViolation(f"Missing required manifest fields: {sorted(missing)}")

    # 2. Type checks.
    for field_name, expected_type in REQUIRED_MANIFEST_FIELDS.items():
        value = manifest[field_name]
        # bool is a subclass of int; guard so an int field doesn't silently accept a bool.
        if expected_type is int and isinstance(value, bool):
            raise ContractViolation(f"Field '{field_name}': expected int, got bool")
        if not isinstance(value, expected_type):
            names = (
                expected_type.__name__
                if isinstance(expected_type, type)
                else "/".join(t.__name__ for t in expected_type)
            )
            raise ContractViolation(
                f"Field '{field_name}': expected {names}, got {type(value).__name__}"
            )

    # 3. Contract version — optional (the upstream manifest does not carry it); if present it
    # must match.
    if "contract_version" in manifest and manifest["contract_version"] != CONTRACT_VERSION:
        raise ContractViolation(
            f"contract_version must be '{CONTRACT_VERSION}' if present, got "
            f"'{manifest['contract_version']}'"
        )

    # 4. Seed-list lengths match split sizes.
    for seeds_key, count_key in _SEED_FIELDS:
        if len(manifest[seeds_key]) != manifest[count_key]:
            raise ContractViolation(
                f"{seeds_key} length ({len(manifest[seeds_key])}) != "
                f"{count_key} ({manifest[count_key]})"
            )

    # 5. Pairwise-disjoint seed lists (train ∩ val ∩ test = ∅).
    train_set = set(manifest["train_seeds"])
    val_set = set(manifest["val_seeds"])
    test_set = set(manifest["test_seeds"])
    for (a_name, a), (b_name, b) in [
        (("train", train_set), ("val", val_set)),
        (("train", train_set), ("test", test_set)),
        (("val", val_set), ("test", test_set)),
    ]:
        overlap = a & b
        if overlap:
            raise ContractViolation(f"{a_name}/{b_name} seed overlap: {sorted(overlap)}")

    # 6. Range fields: 2 elements, lo <= hi.
    for range_field in _RANGE_FIELDS:
        r = manifest[range_field]
        if len(r) != 2:
            raise ContractViolation(f"{range_field}: expected 2 elements, got {len(r)}")
        if r[0] > r[1]:
            raise ContractViolation(f"{range_field}: min ({r[0]}) > max ({r[1]})")

    # 7. Units dict has required keys with correct values.
    units = manifest["units"]
    for unit_key, expected_val in REQUIRED_UNITS.items():
        if unit_key not in units:
            raise ContractViolation(f"Missing required unit: '{unit_key}'")
        if units[unit_key] != expected_val:
            raise ContractViolation(
                f"Unit '{unit_key}': expected '{expected_val}', got '{units[unit_key]}'"
            )

    # 8. Provenance fields non-empty.
    for prov_field in _PROVENANCE_FIELDS:
        if not manifest[prov_field].strip():
            raise ContractViolation(f"Provenance field '{prov_field}' is empty")

    # 9. bias_direction_uvw: 3 elements, nonzero norm. The upstream stores the raw [uvw]
    # crystal direction (NOT normalized — e.g. (0.2, 0.1, 1.0)); the bias vector is
    # ``bias_B0_T · normalize(uvw)`` and the authoritative magnitude is the top-level /bias.
    bdir = manifest["bias_direction_uvw"]
    if len(bdir) != 3:
        raise ContractViolation(f"bias_direction_uvw must have 3 elements, got {len(bdir)}")
    if sum(float(c) ** 2 for c in bdir) < 1e-12:
        raise ContractViolation("bias_direction_uvw must have nonzero norm")

    # 10. Positive temporal/spectral dimensions.
    for dim_key in ("n_timesteps", "n_lines", "n_freq_points"):
        if manifest[dim_key] <= 0:
            raise ContractViolation(f"{dim_key} must be positive, got {manifest[dim_key]}")
    if manifest["dt_s"] <= 0:
        raise ContractViolation(f"dt_s must be positive, got {manifest['dt_s']}")


# --- HDF5 dataset schema ----------------------------------------------------------------

# Per-split dataset → (expected numpy dtype, symbolic shape). Symbols resolve per split:
# N = n_sequences_<split>, T = n_timesteps, F = n_freq_points, L = n_lines.
# Note: ``bias`` is NOT here — the authoritative v1 layout stores it as a single top-level
# ``/bias`` dataset (validated separately, with a per-split fallback for back-compat).
DATASET_SCHEMA: dict[str, tuple[type, tuple[object, ...]]] = {
    "spectra": (np.float32, ("N", "T", "F")),
    "frequencies": (np.float32, ("F",)),
    "B_true": (np.float32, ("N", "T", 3)),
    "resonance_freqs": (np.float32, ("N", "T", "L")),
    "line_axis": (np.int8, ("N", "T", "L")),
    "line_transition": (np.int8, ("N", "T", "L")),
    "collision_mask": (np.bool_, ("N", "T")),
    "line_collision": (np.bool_, ("N", "T", "L")),
    "seeds": (np.int64, ("N",)),
}


def _resolve_shape(symbolic: tuple[object, ...], dims: dict[str, int]) -> tuple[int, ...]:
    return tuple(int(dims[s]) if isinstance(s, str) else int(s) for s in symbolic)  # type: ignore[arg-type]


def _read(group: h5py.Group, name: str) -> np.ndarray:
    """Read an HDF5 dataset into a numpy array (narrows the h5py union type)."""
    ds = group[name]
    assert isinstance(ds, h5py.Dataset)
    return np.asarray(ds[()])


def validate_sequence_dataset(h5_path: Path | str, manifest: dict) -> None:
    """Validate an HDF5 sequence dataset against the v1 contract using its manifest.

    Checks, for every split present: each contract dataset exists with the correct dtype and
    shape (N, T, F, L resolved from the manifest), ``L == manifest['n_lines']``, label-value
    ranges (``line_axis`` ∈ {0..3}, ``line_transition`` ∈ {0,1}), and that the per-sequence
    ``seeds`` are drawn from the split's seed list.

    Raises
    ------
    ContractViolation
        If any check fails.
    FileNotFoundError
        If ``h5_path`` does not exist.
    """
    h5_path = Path(h5_path)
    if not h5_path.exists():
        raise FileNotFoundError(f"Dataset not found: {h5_path}")

    T = manifest["n_timesteps"]
    F = manifest["n_freq_points"]
    L = manifest["n_lines"]
    split_counts = {
        "train": manifest["n_spectra_train"],
        "val": manifest["n_spectra_val"],
        "test": manifest["n_spectra_test"],
    }
    split_seedlists = {
        "train": set(manifest["train_seeds"]),
        "val": set(manifest["val_seeds"]),
        "test": set(manifest["test_seeds"]),
    }

    with h5py.File(h5_path, "r") as f:
        present = [s for s in VALID_SPLITS if s in f]
        if not present:
            raise ContractViolation(
                f"No contract split groups in {h5_path.name}; expected any of {VALID_SPLITS}"
            )

        for split in present:
            g = f[split]
            if not isinstance(g, h5py.Group):
                raise ContractViolation(f"[{split}] is not an HDF5 group")
            N = split_counts[split]
            dims = {"N": N, "T": T, "F": F, "L": L}

            missing = set(DATASET_SCHEMA) - set(g.keys())
            if missing:
                raise ContractViolation(f"[{split}] missing datasets: {sorted(missing)}")

            for name, (exp_dtype, sym_shape) in DATASET_SCHEMA.items():
                ds = g[name]
                assert isinstance(ds, h5py.Dataset)  # narrowed by missing-key check above
                exp_shape = _resolve_shape(sym_shape, dims)
                if tuple(ds.shape) != exp_shape:
                    raise ContractViolation(
                        f"[{split}] '{name}': expected shape {exp_shape}, got {tuple(ds.shape)}"
                    )
                if np.dtype(ds.dtype) != np.dtype(exp_dtype):
                    raise ContractViolation(
                        f"[{split}] '{name}': expected dtype {np.dtype(exp_dtype)}, "
                        f"got {np.dtype(ds.dtype)}"
                    )

            # Label-value ranges.
            line_axis = _read(g, "line_axis")
            if line_axis.size and (line_axis.min() < 0 or line_axis.max() > 3):
                raise ContractViolation(
                    f"[{split}] line_axis values must be in 0..3, got "
                    f"[{line_axis.min()}, {line_axis.max()}]"
                )
            line_tr = _read(g, "line_transition")
            if line_tr.size and not np.isin(line_tr, (0, 1)).all():
                raise ContractViolation(
                    f"[{split}] line_transition values must be in {{0, 1}}"
                )

            # Per-sequence seeds drawn from the split's seed list.
            seeds = _read(g, "seeds")
            extra = set(int(s) for s in seeds.tolist()) - split_seedlists[split]
            if extra:
                raise ContractViolation(
                    f"[{split}] seeds not in manifest {split}_seeds: {sorted(extra)}"
                )

        # Bias: authoritative v1 stores a single top-level ``/bias`` (3,) float32. A per-split
        # ``bias`` is accepted as a back-compat fallback (the orchestrator's initially-stated
        # layout placed bias under each split); raise if neither is present.
        if "bias" in f:
            bias = f["bias"]
            assert isinstance(bias, h5py.Dataset)
            if tuple(bias.shape) != (3,):
                raise ContractViolation(f"/bias: expected shape (3,), got {tuple(bias.shape)}")
            if np.dtype(bias.dtype) != np.dtype(np.float32):
                raise ContractViolation(
                    f"/bias: expected dtype float32, got {np.dtype(bias.dtype)}"
                )
        else:
            for split in present:
                grp = f[split]
                assert isinstance(grp, h5py.Group)
                if "bias" not in grp:
                    raise ContractViolation(
                        f"bias missing: expected top-level /bias (3,) float32 or "
                        f"per-split [{split}]/bias"
                    )


def validate_dataset_dir(dataset_dir: Path | str) -> dict:
    """Load + validate ``manifest.json`` and ``dataset.h5`` in a directory; return the manifest.

    Raises
    ------
    ContractViolation
        If the manifest or dataset fails validation.
    FileNotFoundError
        If the manifest or dataset file is missing.
    """
    dataset_dir = Path(dataset_dir)
    manifest_path = dataset_dir / "manifest.json"
    h5_path = dataset_dir / "dataset.h5"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as fh:
        manifest = json.load(fh)

    validate_manifest(manifest)
    validate_sequence_dataset(h5_path, manifest)
    return manifest
