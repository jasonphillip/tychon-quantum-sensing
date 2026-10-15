"""Signal access requires a pinned root approval and an active accounting supervisor."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from .metadata import sha256

@dataclass(frozen=True)
class SignalAccess:
    manifest_sha256: str
    allowed_recordings: frozenset[str]
    allowed_intervals: dict[str, tuple[tuple[float, float], ...]]
    approval_sha256: str
    run_id: str

def authorize(approval_path: Path, expected_approval_sha256: str, manifest_path: Path) -> SignalAccess:
    if sha256(approval_path) != expected_approval_sha256:
        raise PermissionError("Approval hash mismatch.")
    gate = json.loads(approval_path.read_text())
    if gate.get("status") != "APPROVED" or gate.get("lane") != "cardiac" or gate.get("campaign") != "nv-measured-pilots-2026-10-15":
        raise PermissionError("No root-approved cardiac gate.")
    if gate.get("stage") not in ("qualification", "development", "final"):
        raise PermissionError("Stage does not permit signal access.")
    digest = sha256(manifest_path)
    if digest != gate.get("manifest_sha256"):
        raise PermissionError("Custody metadata changed after approval.")
    package = Path(__file__).resolve().parent
    if sha256(package / "protocol.md") != gate.get("protocol_sha256"):
        raise PermissionError("Frozen protocol changed.")
    expected = gate.get("source_sha256", {})
    actual_names = {p.name for p in package.glob("*.py")}
    if set(expected) != actual_names:
        raise PermissionError("Gate must pin every package Python file.")
    for name, digest_source in expected.items():
        if sha256(package / name) != digest_source:
            raise PermissionError("Approved source changed: " + name)
    context_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not context_path:
        raise PermissionError("No active numerical-accounting context.")
    context = json.loads(Path(context_path).read_text())
    if context.get("status") != "running" or context.get("parent_pid") != os.getppid():
        raise PermissionError("Accounting supervisor must be the parent process.")
    if context.get("gate_sha256") != expected_approval_sha256:
        raise PermissionError("Accounting gate mismatch.")
    if context.get("accounting_authority") != "spark2-reservation-journal-v1":
        raise PermissionError("Unrecognized accounting authority.")
    if not context.get("central_reservation_id") or not context.get("central_spec_sha256"):
        raise PermissionError("Reservation identity missing.")
    lock_path = Path(context.get("shared_lock_path", ""))
    if not lock_path.is_file():
        raise PermissionError("Supervisor lock missing.")
    with lock_path.open("r") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(lock, fcntl.LOCK_UN)
            raise PermissionError("Supervisor does not hold the job lock.")
    records = gate.get("allowed_recordings", [])
    if not records or not all(isinstance(x, str) and x for x in records):
        raise PermissionError("Approved recording IDs missing.")
    intervals = gate.get("allowed_intervals_seconds", {})
    if set(intervals) != set(records):
        raise PermissionError("Every recording requires explicit approved intervals.")
    import math
    for blocks in intervals.values():
        if not blocks:
            raise PermissionError("Empty approved interval set.")
        for block in blocks:
            if len(block) != 2 or not all(isinstance(t, (float, int)) and not isinstance(t, bool) and math.isfinite(t) for t in block) or not 0 <= block[0] < block[1]:
                raise PermissionError("Invalid approved interval.")
    frozen = {key: tuple(tuple(block) for block in blocks) for key, blocks in intervals.items()}
    return SignalAccess(digest, frozenset(records), frozen, expected_approval_sha256, str(context["central_reservation_id"]))
