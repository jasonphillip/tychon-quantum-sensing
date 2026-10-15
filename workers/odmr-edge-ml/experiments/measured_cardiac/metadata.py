"""Metadata-only eligibility checks. Missing evidence is never inferred from filenames."""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path, PurePosixPath

RECORD_ID = "20703822"
ARCHIVE_BYTES = 1783355725
ARCHIVE_MD5 = "fa0735af9ae6d7ede58706a84b9196d3"
MAX_MEMBERS = 128
MAX_TOTAL_BYTES = 16 * 1024**3
MAX_MEMBER_BYTES = 8 * 1024**3

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return bool(name) and not p.is_absolute() and ".." not in p.parts and "\\" not in name and ":" not in name and "\x00" not in name

def finite_number(value, *, positive=False):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and (not positive or value > 0)

def load_manifest(path: Path) -> dict:
    if path.stat().st_size > 2 * 1024**2:
        raise ValueError("Metadata manifest exceeds 2 MiB.")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Manifest must be a JSON object.")
    return value

def eligibility(manifest: dict) -> dict:
    errors, warnings, capabilities = [], [], []
    archive = manifest.get("archive", {})
    if manifest.get("schema_version") != 1 or str(manifest.get("record_id")) != RECORD_ID:
        errors.append("wrong_schema_or_immutable_record")
    if archive.get("bytes") != ARCHIVE_BYTES or archive.get("md5") != ARCHIVE_MD5:
        errors.append("archive_repository_identity_unverified")
    digest = archive.get("sha256", "")
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        errors.append("custody_sha256_missing")
    if archive.get("custody_verified") is not True:
        errors.append("custody_not_verified")
    if manifest.get("license") != "CC-BY-4.0":
        errors.append("license_unverified")
    recordings = manifest.get("recordings", [])
    if not recordings:
        errors.append("no_recording_metadata")
    ids = set()
    for r in recordings:
        rid = r.get("id", "MISSING")
        prefix = str(rid) + ":"
        local = []
        if rid in ids or rid == "MISSING":
            local.append("duplicate_or_missing_id")
        ids.add(rid)
        if not safe_member(r.get("member", "")):
            local.append("unsafe_or_missing_member")
        if r.get("experiment_kind") != "human_cardiac":
            local.append("not_verified_human_cardiac_recording")
        for name in ("session_id", "acquisition_evidence", "channel_evidence", "group_evidence"):
            if not isinstance(r.get(name), str) or not r[name].strip():
                local.append(name + "_missing")
        if not r.get("participant_id"):
            warnings.append(prefix + "participant_unknown_within_recording_claims_only")
        if r.get("acquisition_filters", {}).get("known") is not True:
            local.append("acquisition_filter_response_unknown")
        if not r.get("acquisition_filters", {}).get("evidence"):
            local.append("acquisition_filter_evidence_missing")
        clock = r.get("clock", {})
        if not finite_number(clock.get("sample_rate_hz"), positive=True) or not finite_number(clock.get("timestamp_seconds_per_unit"), positive=True):
            local.append("sample_clock_units_unknown")
        if not clock.get("evidence") or clock.get("shared_clock") is not True:
            local.append("shared_channel_clock_unverified")
        if not finite_number(r.get("duration_seconds"), positive=True):
            local.append("duration_metadata_missing")
        fmt = r.get("format", {})
        if not isinstance(fmt.get("header_lines"), int) or isinstance(fmt.get("header_lines"), bool) or not 0 <= fmt["header_lines"] <= 2000:
            local.append("header_boundary_unknown")
        if fmt.get("delimiter") not in (",", ";", "\t", "whitespace"):
            local.append("unsupported_text_delimiter")
        if not isinstance(fmt.get("timestamp_column"), int) or isinstance(fmt.get("timestamp_column"), bool) or fmt["timestamp_column"] < 0:
            local.append("timestamp_column_unknown")
        channels = r.get("channels", [])
        primary = [c for c in channels if c.get("role") == "primary_magnetic"]
        ecg = [c for c in channels if c.get("role") == "ecg_trigger"]
        if len(primary) != 1:
            local.append("exactly_one_calibrated_primary_required")
        if len(ecg) != 1:
            local.append("exactly_one_timing_only_ecg_required")
        columns = []
        for c in channels:
            col = c.get("column")
            if not isinstance(col, int) or isinstance(col, bool) or col < 0:
                local.append("channel_column_unknown")
            else:
                columns.append(col)
            if not c.get("id") or not c.get("role_evidence"):
                local.append("channel_role_evidence_missing")
        if len(set(columns)) != len(columns) or fmt.get("timestamp_column") in columns:
            local.append("channel_column_collision")
        if primary:
            calibration = primary[0].get("calibration", {})
            gain = calibration.get("tesla_per_unit")
            if not finite_number(gain) or gain == 0 or not finite_number(calibration.get("offset_raw")):
                local.append("signed_magnetic_calibration_missing")
            if not calibration.get("evidence") or calibration.get("applies_to_recording") != rid:
                local.append("calibration_provenance_missing")
            if not finite_number(calibration.get("relative_uncertainty")) or calibration["relative_uncertainty"] < 0:
                local.append("calibration_uncertainty_unknown")
        errors.extend(prefix + x for x in local)
        if not local:
            capabilities.append({"recording": rid, "operation": "within_recording_reproducibility_proxy"})
        refs = [c for c in channels if c.get("role") == "reference_noise"]
        reference_ok = bool(refs) and all(c.get("synchronous") is True and c.get("cardiac_leakage_bound_verified") is True and c.get("reference_evidence") for c in refs)
        if reference_ok and not local:
            capabilities.append({"recording": rid, "operation": "causal_reference_cancellation"})
        else:
            warnings.append(prefix + "adaptive_cancellation_blocked_no_verified_noise_reference")
    return {"eligible": not errors, "errors": sorted(set(errors)), "warnings": sorted(set(warnings)), "capabilities": capabilities,
            "clean_mcg_target": False, "clinical_accuracy_supported": False, "signal_values_read": False}
