"""Bounded ZIP/text loader. Inventory never decompresses scientific arrays."""
from __future__ import annotations
import csv
import hashlib
import io
import math
import stat
import zipfile
from pathlib import Path
from .access import SignalAccess
from .metadata import (ARCHIVE_BYTES, MAX_MEMBERS, MAX_MEMBER_BYTES, MAX_TOTAL_BYTES,
                       eligibility, load_manifest, safe_member, sha256)

def inventory(archive: Path) -> list[dict]:
    if archive.stat().st_size != ARCHIVE_BYTES:
        raise ValueError("Incomplete or unexpected archive size; custody is not complete.")
    with zipfile.ZipFile(archive) as z:
        entries = z.infolist()
        if len(entries) > MAX_MEMBERS or sum(x.file_size for x in entries) > MAX_TOTAL_BYTES:
            raise ValueError("Archive expansion limit exceeded.")
        names = [x.filename for x in entries]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate archive members.")
        for info in entries:
            if not safe_member(info.filename) or info.file_size > MAX_MEMBER_BYTES:
                raise ValueError("Unsafe member or member too large.")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode) or (info.flag_bits & 1):
                raise ValueError("Links and encrypted members are unsupported.")
            if info.compress_size and info.file_size / info.compress_size > 1000:
                raise ValueError("Unexpected archive compression ratio.")
        return [{"member_name_sha256": hashlib.sha256(x.filename.encode()).hexdigest(), "bytes": x.file_size, "compressed_bytes": x.compress_size,
                 "crc32": format(x.CRC, "08x"), "directory": x.is_dir()} for x in entries]

def iter_rows(archive: Path, manifest_path: Path, recording_id: str, access: SignalAccess,
              *, max_rows: int, start_seconds: float, stop_seconds: float):
    """Yield timestamp and raw channels only inside an approved contiguous interval.

    No resampling, interpolation, target fabrication, notebook execution, or full-array loading.
    The caller must save rejection counts and map magnetic units with the pinned calibration.
    """
    if not isinstance(access, SignalAccess) or access.access_mode != "waveform_values" or recording_id not in access.allowed_recordings:
        raise PermissionError("Recording not authorized.")
    if sha256(manifest_path) != access.manifest_sha256:
        raise PermissionError("Manifest changed after authorization.")
    if not isinstance(max_rows, int) or isinstance(max_rows, bool) or max_rows < 1:
        raise ValueError("An explicit positive row cap is required.")
    if not math.isfinite(start_seconds) or not math.isfinite(stop_seconds) or not 0 <= start_seconds < stop_seconds:
        raise ValueError("Invalid contiguous interval.")
    if not any(a <= start_seconds < stop_seconds <= b for a, b in access.allowed_intervals.get(recording_id, ())):
        raise PermissionError("Requested interval crosses a frozen partition or guard interval.")
    manifest = load_manifest(manifest_path)
    verdict = eligibility(manifest)
    if not verdict["eligible"]:
        raise ValueError("Metadata is ineligible: " + ", ".join(verdict["errors"]))
    if sha256(archive) != manifest["archive"]["sha256"]:
        raise ValueError("Archive differs from immutable custody copy.")
    inventory(archive)
    recording = next(r for r in manifest["recordings"] if r["id"] == recording_id)
    fmt, clock = recording["format"], recording["clock"]
    channels = recording["channels"]
    columns = [c["column"] for c in channels]
    timestamp_column = fmt["timestamp_column"]
    largest = max([timestamp_column, *columns])
    count, previous, origin = 0, None, None
    with zipfile.ZipFile(archive) as z, z.open(recording["member"]) as raw:
        with io.TextIOWrapper(raw, encoding=fmt.get("encoding", "utf-8"), errors="strict") as stream:
            for _ in range(fmt["header_lines"]):
                if not stream.readline():
                    raise ValueError("Missing documented header.")
            for line in stream:
                if len(line) > 65536:
                    raise ValueError("Unexpected text row size.")
                if not line.strip():
                    continue
                parts = line.split() if fmt["delimiter"] == "whitespace" else next(csv.reader([line], delimiter=fmt["delimiter"]))
                if len(parts) <= largest:
                    raise ValueError("Row has fewer columns than the pinned schema.")
                timestamp = float(parts[timestamp_column]) * clock["timestamp_seconds_per_unit"]
                if not math.isfinite(timestamp):
                    raise ValueError("Nonfinite timestamp.")
                if previous is not None and timestamp <= previous:
                    raise ValueError("Nonmonotonic or duplicate timestamps.")
                if origin is None:
                    origin = timestamp
                if previous is not None:
                    expected_dt = 1.0 / clock["sample_rate_hz"]
                    if abs((timestamp - previous) / expected_dt - 1.0) > 0.01:
                        raise ValueError("Timestamp gap/jitter exceeds frozen 1% loader tolerance.")
                previous = timestamp
                relative = timestamp - origin
                if relative >= stop_seconds:
                    return
                if relative < start_seconds:
                    continue
                if count >= max_rows:
                    raise ValueError("Row cap exceeded.")
                values = [float(parts[i]) for i in columns]
                if not all(math.isfinite(x) for x in values):
                    raise ValueError("Nonfinite sample; reject recording rather than silently interpolate.")
                count += 1
                yield relative, dict(zip((c["id"] for c in channels), values))

def to_tesla(raw_value: float, channel: dict) -> float:
    calibration = channel["calibration"]
    return (raw_value - calibration["offset_raw"]) * calibration["tesla_per_unit"]
