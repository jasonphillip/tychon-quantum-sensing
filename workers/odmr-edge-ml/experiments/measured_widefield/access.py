"""Read-only approval bindings; numerical accounting belongs to the coordinator."""
import hashlib
import json
import os
import fcntl
import re
from pathlib import Path

# Prospective implementation contract, excluding only the coordinator-owned status.
# This is not a generic configuration loader: scientific JSON changes require source review.
IMPLEMENTED_PROTOCOL_SHA256 = "c9dbd64f7addf72738ad9eea1964dfac05cc3e7d255cd57b3ef3d5cfa0fd7e60"


def validate_protocol(path):
    record = json.loads(Path(path).read_text())
    if record.get("status") != "FROZEN":
        raise ValueError("Protocol must be FROZEN before numerical access")
    implementation = {key: value for key, value in record.items() if key != "status"}
    canonical = json.dumps(implementation, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if hashlib.sha256(canonical).hexdigest() != IMPLEMENTED_PROTOCOL_SHA256:
        raise ValueError("Protocol differs from the implemented scientific contract")


def supervisor_context(approval_hash, allowed_run_ids, accounting_authority):
    if not isinstance(accounting_authority, str) or not accounting_authority:
        raise ValueError("Approval must pin its accounting authority")
    run_id = os.environ.get("TYCHON_NUMERICAL_RUN_ID")
    context_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not context_path or not run_id or run_id not in allowed_run_ids:
        raise ValueError("An approved active supervisor context is required")
    path = Path(context_path)
    if path.is_symlink() or path.name != "context.json" or path.parent.name != run_id:
        raise ValueError("Unexpected supervisor context path")
    context = json.loads(path.read_text())
    if context.get("status") != "running" or context.get("parent_pid") != os.getppid():
        raise ValueError("Numerical supervisor is not the active parent")
    if context.get("gate_sha256") != approval_hash or context.get("central_reservation_id") != run_id:
        raise ValueError("Supervisor gate or reservation differs")
    if context.get("accounting_authority") != accounting_authority:
        raise ValueError("Unexpected accounting authority")
    if not re.fullmatch(r"[0-9a-f]{64}", context.get("central_spec_sha256", "")):
        raise ValueError("Missing pinned central specification identity")
    lock = Path(context.get("shared_lock_path", ""))
    if lock.is_symlink() or lock != path.parent / "active.lock":
        raise ValueError("Unexpected per-job numerical lock")
    with lock.open("rb") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return context
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    raise ValueError("Numerical supervisor does not hold its per-job lock")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def gate(approval_path, phase):
    approval_path = Path(approval_path)
    if sha(approval_path) != os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256"):
        raise ValueError("Numerical approval must match accounting environment")
    if not os.environ.get("TYCHON_NUMERICAL_RUN_ID"):
        raise ValueError("Accounting run ID required")
    approval = json.loads(approval_path.read_text())
    if approval.get("status") != "approved" or approval.get("study") != "measured-widefield-2026-10-15":
        raise ValueError("Widefield study is not approved")
    if phase not in approval.get("phases", []):
        raise ValueError("Phase is not authorized: " + phase)
    supervisor_context(sha(approval_path), approval.get("allowed_run_ids", []), approval.get("accounting_authority"))
    root = Path(__file__).resolve().parents[2]
    required = {str(p.relative_to(root)) for p in Path(__file__).parent.rglob("*.py")}
    required.add("experiments/measured_widefield/protocol.json")
    if not required <= set(approval.get("source_files", {})):
        raise ValueError("All runtime source files and protocol must be frozen")
    for relative, expected in approval["source_files"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or sha(path) != expected:
            raise ValueError("Frozen source changed: " + relative)
    protocol = root / "experiments/measured_widefield/protocol.json"
    if approval.get("protocol_sha256") != sha(protocol):
        raise ValueError("Approval protocol hash differs")
    validate_protocol(protocol)
    return approval


def verified_manifest(path, expected):
    if sha(path) != expected:
        raise ValueError("Manifest hash mismatch")
    return json.loads(Path(path).read_text())
