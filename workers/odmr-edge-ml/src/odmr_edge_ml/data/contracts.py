"""Manifest contract validation for upstream simulator datasets.

Validates incoming manifest.json files against the expected schema.
Standalone — does not import from the upstream simulator.
"""

from __future__ import annotations

import json
from pathlib import Path


class ContractViolation(ValueError):
    """Raised when a simulator manifest fails contract validation."""


# All 23 fields required in a valid manifest
REQUIRED_MANIFEST_FIELDS: dict[str, type] = {
    # Provenance
    "generator_git_sha": str,
    "config_hash": str,
    "simos_version": str,
    "qutip_version": str,
    "backend": str,
    "generated_at": str,
    # Seeds
    "master_seed": int,
    "train_seeds": list,
    "val_seeds": list,
    "test_seeds": list,
    # Split counts
    "n_spectra_train": int,
    "n_spectra_val": int,
    "n_spectra_test": int,
    # Split indices
    "train_indices": list,
    "val_indices": list,
    "test_indices": list,
    # Spectral params
    "n_freq_points": int,
    "freq_range_Hz": list,
    # Corruption ranges
    "p1_concentration_range_ppm": list,
    "temperature_range_K": list,
    "b1_gradient_range": list,
    "b_perp_range_T": list,
    # Units
    "units": dict,
}

REQUIRED_UNITS: dict[str, str] = {
    "frequency": "Hz",
    "magnetic_field": "T",
    "temperature": "K",
    "p1_concentration": "ppm",
    "b1_gradient": "fraction",
    "b_perp": "T",
    "time": "s",
}

# Optional vector-readiness fields added 2026-05-17 for the
# ``production_50k_v3_vector`` lineage (B2.6 — flux-concentrator + 8-FCNN
# + BLUE projection scaffold). All four have backwards-compatible defaults
# so legacy datasets (production_50k, production_50k_v2_aic) still validate.
OPTIONAL_VECTOR_FIELDS: dict[str, tuple[type, object]] = {
    # Static bias field magnitude at the diamond (Tesla). 0.0 = legacy
    # bias-free Earth-field regime; flux-concentrator path bumps this to
    # ~0.5–1 mT after amplification; permanent-magnet path uses 2–5 mT.
    "bias_B0_T": (float, 0.0),
    # Lab-frame unit vector of the bias field. Default along +z so the
    # legacy single-axis longitudinal regime keeps the same geometry.
    "bias_direction_uvw": (list, [0.0, 0.0, 1.0]),
    # Multiplicative amplification factor from the magnetic concentrator
    # caps (Acosta-style soft-magnetic geometry). 1.0 = no concentrator.
    "concentrator_amplification": (float, 1.0),
    # Linear drift of the bias-field magnitude with temperature, in parts
    # per million per Kelvin. Permanent-magnet path nonzero; concentrator
    # path defaults to zero (Earth's field is the source, not the magnet).
    "magnet_drift_ppm_per_K": (float, 0.0),
}

# Range fields that must have exactly 2 elements with lo <= hi
_RANGE_FIELDS = [
    "freq_range_Hz",
    "p1_concentration_range_ppm",
    "temperature_range_K",
    "b1_gradient_range",
    "b_perp_range_T",
]

# Provenance fields that must be non-empty strings
_PROVENANCE_FIELDS = [
    "generator_git_sha",
    "config_hash",
    "simos_version",
    "qutip_version",
    "generated_at",
]


def validate_manifest(manifest: dict) -> None:
    """Validate a simulator manifest dict against the expected schema.

    Parameters
    ----------
    manifest : dict
        Parsed manifest dictionary.

    Raises
    ------
    ContractViolation
        If any validation check fails.
    """
    # 1. Required fields present
    missing = set(REQUIRED_MANIFEST_FIELDS) - set(manifest)
    if missing:
        raise ContractViolation(f"Missing required fields: {sorted(missing)}")

    # 2. Type checks
    for field_name, expected_type in REQUIRED_MANIFEST_FIELDS.items():
        value = manifest[field_name]
        if not isinstance(value, expected_type):
            raise ContractViolation(
                f"Field '{field_name}': expected {expected_type.__name__}, "
                f"got {type(value).__name__}"
            )

    # 3. Seed counts match split sizes
    for seeds_key, count_key in [
        ("train_seeds", "n_spectra_train"),
        ("val_seeds", "n_spectra_val"),
        ("test_seeds", "n_spectra_test"),
    ]:
        if len(manifest[seeds_key]) != manifest[count_key]:
            raise ContractViolation(
                f"{seeds_key} length ({len(manifest[seeds_key])}) != "
                f"{count_key} ({manifest[count_key]})"
            )

    # 4. Index counts match split sizes
    for indices_key, count_key in [
        ("train_indices", "n_spectra_train"),
        ("val_indices", "n_spectra_val"),
        ("test_indices", "n_spectra_test"),
    ]:
        if len(manifest[indices_key]) != manifest[count_key]:
            raise ContractViolation(
                f"{indices_key} length ({len(manifest[indices_key])}) != "
                f"{count_key} ({manifest[count_key]})"
            )

    # 5. Pairwise disjoint seeds (train ∩ val ∩ test = ∅)
    train_set = set(manifest["train_seeds"])
    val_set = set(manifest["val_seeds"])
    test_set = set(manifest["test_seeds"])

    overlap = train_set & test_set
    if overlap:
        raise ContractViolation(f"Train/test seed overlap: {overlap}")
    overlap = train_set & val_set
    if overlap:
        raise ContractViolation(f"Train/val seed overlap: {overlap}")
    overlap = val_set & test_set
    if overlap:
        raise ContractViolation(f"Val/test seed overlap: {overlap}")

    # 6. Range fields: 2 elements, lo <= hi
    for range_field in _RANGE_FIELDS:
        r = manifest[range_field]
        if len(r) != 2:
            raise ContractViolation(
                f"{range_field}: expected 2 elements, got {len(r)}"
            )
        if r[0] > r[1]:
            raise ContractViolation(f"{range_field}: min ({r[0]}) > max ({r[1]})")

    # 7. Units dict has required keys with correct values
    units = manifest["units"]
    for unit_key, expected_val in REQUIRED_UNITS.items():
        if unit_key not in units:
            raise ContractViolation(f"Missing required unit: '{unit_key}'")
        if units[unit_key] != expected_val:
            raise ContractViolation(
                f"Unit '{unit_key}': expected '{expected_val}', got '{units[unit_key]}'"
            )

    # 8. Provenance fields non-empty
    for prov_field in _PROVENANCE_FIELDS:
        if not manifest[prov_field].strip():
            raise ContractViolation(f"Provenance field '{prov_field}' is empty")

    # 9. Optional vector-readiness fields: if present, must have the
    # declared type. Missing keys are fine — they fall back to the defaults
    # via :func:`vector_readiness_view`.
    for field_name, (expected_type, _default) in OPTIONAL_VECTOR_FIELDS.items():
        if field_name not in manifest:
            continue
        value = manifest[field_name]
        if not isinstance(value, expected_type):
            raise ContractViolation(
                f"Optional vector field '{field_name}': expected "
                f"{expected_type.__name__}, got {type(value).__name__}"
            )
        if field_name == "bias_direction_uvw":
            if len(value) != 3:
                raise ContractViolation(
                    f"bias_direction_uvw must have 3 elements, got {len(value)}"
                )
            norm_sq = sum(float(c) ** 2 for c in value)
            if abs(norm_sq - 1.0) > 1e-6:
                raise ContractViolation(
                    f"bias_direction_uvw must be unit-norm; got |v|^2 = {norm_sq:.6f}"
                )


def vector_readiness_view(manifest: dict) -> dict:
    """Project a manifest onto the optional vector-readiness fields with defaults.

    Returns a dict keyed by the names in :data:`OPTIONAL_VECTOR_FIELDS`. Used
    by the 8-FCNN training script to know whether to spawn 8 windowed
    instances (bias_B0_T > 0 and a known amplification) or fall back to the
    legacy scalar model (bias_B0_T == 0).
    """
    out: dict = {}
    for name, (_t, default) in OPTIONAL_VECTOR_FIELDS.items():
        out[name] = manifest.get(name, default)
    return out


def validate_manifest_file(path: Path | str) -> dict:
    """Load a JSON manifest from disk, validate, and return the parsed dict.

    Parameters
    ----------
    path : Path or str
        Path to manifest.json.

    Returns
    -------
    dict
        Validated manifest dictionary.

    Raises
    ------
    ContractViolation
        If validation fails.
    FileNotFoundError
        If path does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")

    with open(path) as f:
        manifest = json.load(f)

    validate_manifest(manifest)
    return manifest
