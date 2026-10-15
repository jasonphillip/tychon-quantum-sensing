"""Explicitly approved voltage windows from immutable sequential-channel exports."""
from __future__ import annotations
from array import array
import hashlib
import json
from pathlib import Path
import sys
import zipfile
import numpy as np
from .access import authorize
from .metadata import sha256
from .qualify_timestamps import matching_member, MAX_LINE_BYTES, ARCHIVE_SHA256, ARCHIVE_BYTES

QUALIFICATION_SHA = "b109aaf7f2da8b147ecf8b32966f9665b8ddf14ea4888db578e8f6df214a01d6"
WINDOWS = ((0., 120.), (180., 360.), (420., 600.))

def prepare_access(args):
    access = authorize(args.approval, args.approval_sha256, args.manifest)
    gate = json.loads(args.approval.read_text())
    if gate.get("waveform_protocol_sha256") != sha256(Path(__file__).with_name("waveform-protocol.md")):
        raise PermissionError("Waveform protocol is not frozen.")
    if gate.get("phase") != args.phase:
        raise PermissionError("Phase is not authorized.")
    if gate.get("run_id") != access.run_id:
        raise PermissionError("Registered waveform run identity differs from the supervisor.")
    if gate.get("stage") != ("final" if args.phase=="final" else "development"):
        raise PermissionError("Waveform stage is not authorized.")
    if args.phase=="development" and (args.frozen is not None or args.validation is not None):
        raise PermissionError("Development cannot import an external selection.")
    if args.phase=="validation" and args.validation is not None:
        raise PermissionError("Validation cannot import a prior validation outcome.")
    if gate.get("timestamp_qualification_sha256") != QUALIFICATION_SHA or sha256(args.qualification) != QUALIFICATION_SHA:
        raise PermissionError("Qualified timestamps changed.")
    qualification = json.loads(args.qualification.read_text())
    if qualification["status"] != "PASS" or qualification["byteorder"] != sys.byteorder:
        raise ValueError("Qualification failed or timestamp byte order differs.")
    manifest = json.loads(args.manifest.read_text())
    selected = [r for r in manifest["recordings"] if r["split"] == {"development":"development", "validation":"validation", "final":"held"}[args.phase]]
    if set(access.allowed_recordings) != {r["id"] for r in selected}:
        raise PermissionError("Approval must include exactly the complete participant partition.")
    if any(access.allowed_intervals[r["id"]] != WINDOWS for r in selected):
        raise PermissionError("Only the three frozen windows are allowed.")
    if args.phase != "development":
        if args.frozen is None or sha256(args.frozen) != gate.get("frozen_configuration_sha256"):
            raise PermissionError("Development freeze is absent or changed.")
        if args.phase == "final":
            if args.validation is None or sha256(args.validation) != gate.get("validation_summary_sha256"):
                raise PermissionError("Validation receipt is absent or changed.")
            validation=json.loads(args.validation.read_text())
            if validation.get("status") != "PASS" or validation.get("phase")!="validation" or validation.get("frozen_configuration_sha256")!=sha256(args.frozen):
                raise PermissionError("Validation did not pass.")
    if args.archive.stat().st_size != ARCHIVE_BYTES or sha256(args.archive) != ARCHIVE_SHA256:
        raise ValueError("Immutable archive changed.")
    return access, selected, {r["recording_id"]: r for r in qualification["recordings"]}

def read_windows(archive, recording, qualified):
    """Only approved sample-index spans have voltage text converted to numbers."""
    info = matching_member(archive, recording)
    ranges = qualified["exact_windows"]
    result = {r["name"]: {"time": array("d"), "ecg": array("d"), "nv": array("d")} for r in ranges}
    times = array("d")
    block, row, previous = 0, 0, None
    with archive.open(info) as stream:
        headers = [stream.readline(MAX_LINE_BYTES+1) for _ in range(7)]
        if hashlib.sha256(b"".join(headers)).hexdigest() != qualified["full_header_sha256"]:
            raise ValueError("Qualified header changed.")
        for raw in iter(lambda: stream.readline(MAX_LINE_BYTES+1), b""):
            if len(raw) > MAX_LINE_BYTES:
                raise ValueError("Row length exceeded.")
            if not raw.strip():
                continue
            prefix, delimiter, value = raw.partition(b";")
            if delimiter != b";" or b";" in value:
                raise ValueError("Malformed row.")
            timestamp = float(prefix)
            if not np.isfinite(timestamp):
                raise ValueError("Nonfinite timestamp.")
            if previous is not None and timestamp < previous:
                if block or timestamp != times[0]:
                    raise ValueError("Unexpected channel reset.")
                block, row, previous = 1, 0, None
            if previous is not None and timestamp <= previous:
                raise ValueError("Unordered time.")
            if block == 0:
                times.append(timestamp)
            elif row >= len(times) or timestamp != times[row]:
                raise ValueError("Channel alignment changed.")
            for window in ranges:
                if window["first_sample"] <= row < window["stop_sample_exclusive"]:
                    voltage = float(value)
                    if not np.isfinite(voltage):
                        raise ValueError("Nonfinite voltage in approved window.")
                    dest = result[window["name"]]
                    dest["ecg" if block == 0 else "nv"].append(voltage)
                    if block == 0:
                        dest["time"].append(timestamp-times[0])
                    break
            previous, row = timestamp, row+1
    if block != 1 or row != len(times) or len(times) != qualified["rows_per_channel"]:
        raise ValueError("Qualified row counts changed.")
    if hashlib.sha256(times.tobytes()).hexdigest() != qualified["timestamp_array_sha256"]:
        raise ValueError("Qualified timestamp identity changed.")
    for window in ranges:
        dest = result[window["name"]]
        expected = window["stop_sample_exclusive"] - window["first_sample"]
        if any(len(v) != expected for v in dest.values()):
            raise ValueError("Incomplete approved window.")
    return {name:{k:np.asarray(v) for k,v in values.items()} for name,values in result.items()}
