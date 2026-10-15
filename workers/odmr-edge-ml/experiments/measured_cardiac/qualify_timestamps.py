"""Prospective timestamp-only qualification. Signal-column bytes are never decoded."""
from __future__ import annotations
from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import zipfile
from .access import authorize
from .metadata import sha256, safe_member

ARCHIVE_SHA256 = "b3d79874553f3d8a9434a5daba1002765c810b134f98697b1f0cb58f09232e1f"
ARCHIVE_BYTES = 1783355725
MAX_ROWS_PER_BLOCK = 4_000_000
MAX_LINE_BYTES = 512
MAX_RELATIVE_INTERVAL_DEVIATION = 0.02
MAX_CHUNK_RATE_DEVIATION = 0.001
MIN_STUDY_DURATION_SECONDS = 600.0

def matching_member(archive, recording):
    matches = [info for info in archive.infolist()
               if hashlib.sha256(info.filename.encode("utf-8")).hexdigest() == recording["member_name_sha256"]]
    if len(matches) != 1:
        raise ValueError("Member identity is absent or ambiguous.")
    info = matches[0]
    if not safe_member(info.filename) or info.is_dir():
        raise ValueError("Unsafe recording member.")
    if info.file_size != recording["member_bytes"] or format(info.CRC, "08x") != recording["member_crc32"]:
        raise ValueError("Member metadata differs from custody.")
    return info

def qualify_recording(archive, recording):
    """Read only ASCII time prefixes; never decode, convert, print, or retain signal text."""
    info = matching_member(archive, recording)
    times = array("d")
    second_count, block, previous = 0, 0, None
    first_step_min, first_step_max = math.inf, 0.0
    first_header = []
    with archive.open(info) as stream:
        for _ in range(7):
            header = stream.readline(MAX_LINE_BYTES + 1)
            if len(header) > MAX_LINE_BYTES or not header.startswith(b"%"):
                raise ValueError("Seven documented comment-header lines required.")
            first_header.append(header)
        if hashlib.sha256(b"".join(first_header)).hexdigest() != recording.get("header_sha256"):
            # A missing header hash means the custodian supplied six-line prefixes only.
            # Qualification records the full seven-line hash; root must bind it before values.
            if recording.get("header_sha256") is not None:
                raise ValueError("Recording header changed after custody.")
        for raw in iter(lambda: stream.readline(MAX_LINE_BYTES + 1), b""):
            if len(raw) > MAX_LINE_BYTES:
                raise ValueError("Unexpected row length.")
            if not raw.strip():
                continue
            prefix, delimiter, ignored_signal_bytes = raw.partition(b";")
            if delimiter != b";" or b";" in ignored_signal_bytes:
                raise ValueError("Expected exactly one time/value separator.")
            # Only the timestamp is numerically decoded. The voltage column is discarded.
            try:
                timestamp = float(prefix)
            except ValueError:
                raise ValueError("Invalid timestamp column.") from None
            if not math.isfinite(timestamp):
                raise ValueError("Nonfinite timestamp.")
            if previous is not None and timestamp < previous:
                if block != 0 or not times or timestamp != times[0]:
                    raise ValueError("Unexpected time reset or differing channel origin.")
                block = 1
                previous = None
            if previous is not None and timestamp <= previous:
                raise ValueError("Duplicate or unordered timestamp.")
            if block == 0:
                if len(times) >= MAX_ROWS_PER_BLOCK:
                    raise ValueError("Timestamp row cap exceeded.")
                if previous is not None:
                    step = timestamp - previous
                    first_step_min = min(first_step_min, step)
                    first_step_max = max(first_step_max, step)
                times.append(timestamp)
            else:
                if second_count >= len(times) or timestamp != times[second_count]:
                    raise ValueError("ECG/NV exported timestamp arrays differ.")
                second_count += 1
            previous = timestamp
    if block != 1 or len(times) < 3 or second_count != len(times):
        raise ValueError("Exactly two equal-length channel blocks are required.")
    dt = (times[-1] - times[0]) / (len(times) - 1)
    worst = max(abs(first_step_min / dt - 1), abs(first_step_max / dt - 1))
    chunks = []
    for index in range(10):
        start = index * (len(times) - 1) // 10
        stop = (index + 1) * (len(times) - 1) // 10
        chunks.append((times[stop] - times[start]) / (stop - start))
    drift = max(abs(value / dt - 1) for value in chunks)
    duration = times[-1] - times[0]
    problems = []
    if worst > MAX_RELATIVE_INTERVAL_DEVIATION:
        problems.append("sampling_interval_variation_exceeds_2_percent")
    if drift > MAX_CHUNK_RATE_DEVIATION:
        problems.append("chunk_sample_rate_variation_exceeds_0_1_percent")
    if duration < MIN_STUDY_DURATION_SECONDS:
        problems.append("less_than_600_seconds_for_registered_voltage_blocks")
    relative = lambda value: value - times[0]
    # Prospective windows do not use the voltage values, beat locations, or later quality.
    windows = []
    for name, start, stop in (("candidate", 0., 120.), ("reference_a", 180., 360.), ("reference_b", 420., 600.)):
        start_index = next((i for i, value in enumerate(times) if relative(value) >= start), None)
        stop_index = next((i for i, value in enumerate(times) if relative(value) >= stop), len(times))
        windows.append({"name": name, "start_seconds": start, "stop_seconds": stop,
                        "first_sample": start_index, "stop_sample_exclusive": stop_index})
    return {"recording_id": recording["id"], "participant_id": recording["participant_id"],
            "session_id": recording["session_id"], "split": recording["split"],
            "timestamp_only_eligible": not problems, "errors": problems,
            "rows_per_channel": len(times), "duration_seconds": duration,
            "sample_rate_hz": 1. / dt, "mean_interval_seconds": dt,
            "maximum_relative_interval_deviation": worst, "maximum_chunk_rate_deviation": drift,
            "exported_timestamp_arrays_identical": True,
            "full_header_sha256": hashlib.sha256(b"".join(first_header)).hexdigest(),
            "timestamp_array_sha256": hashlib.sha256(times.tobytes()).hexdigest(),
            "timestamp_array_encoding": "native-endian float64; host byte order recorded in run",
            "exact_windows": windows, "waveform_values_decoded": 0,
            "physical_channel_delay_verified": False, "magnetic_calibration_used": False,
            "acquisition_filter_response_known": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--approval-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    access = authorize(args.approval, args.approval_sha256, args.manifest, timestamps_only=True)
    manifest = json.loads(args.manifest.read_text())
    if manifest.get("schema_version") != 2 or manifest.get("analysis_domain") != "recorded_voltage":
        raise ValueError("Expected the frozen voltage-domain metadata manifest.")
    if args.archive.stat().st_size != ARCHIVE_BYTES or sha256(args.archive) != ARCHIVE_SHA256:
        raise ValueError("Archive differs from verified immutable custody.")
    records = manifest["recordings"]
    if {r["id"] for r in records} != set(access.allowed_recordings):
        raise PermissionError("Approval must name exactly the timestamp qualification recordings.")
    args.out.mkdir(parents=True, exist_ok=False)
    results = []
    with zipfile.ZipFile(args.archive) as archive:
        for recording in records:
            try:
                result = qualify_recording(archive, recording)
            except (ValueError, OSError, zipfile.BadZipFile) as exc:
                # Do not expose participant-named ZIP member paths in errors.
                result = {"recording_id": recording["id"], "timestamp_only_eligible": False,
                          "error_type": type(exc).__name__, "reason": str(exc) if isinstance(exc, ValueError) else "archive_or_io_failure",
                          "waveform_values_decoded": 0}
            with (args.out / (recording["id"] + ".json")).open("x") as stream:
                json.dump(result, stream, indent=2)
                stream.write("\n")
            results.append(result)
            print(json.dumps({"recording_id": recording["id"], "timestamp_only_eligible": result["timestamp_only_eligible"]}), flush=True)
    import sys
    summary = {"status": "PASS" if all(r["timestamp_only_eligible"] for r in results) else "STOP",
               "stage": "timestamp_qualification_only", "waveform_values_decoded": 0,
               "manifest_sha256": sha256(args.manifest), "approval_sha256": args.approval_sha256,
               "archive_sha256": ARCHIVE_SHA256, "byteorder": sys.byteorder, "recordings": results,
               "scientific_waveform_comparison_authorized": False}
    with (args.out / "summary.json").open("x") as stream:
        json.dump(summary, stream, indent=2)
        stream.write("\n")
    return 0 if summary["status"] == "PASS" else 2

if __name__ == "__main__":
    raise SystemExit(main())
