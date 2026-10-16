"""Root approval, complete source pins, and held parent-supervisor lock."""
from __future__ import annotations
import fcntl
import hashlib
import json
import os
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent

def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source_pins():
    return {p.name: sha256(p) for p in sorted(PACKAGE.iterdir())
            if p.suffix in (".py", ".json", ".md")}

def authorize(gate_path, expected_hash, phase):
    if sha256(gate_path) != expected_hash:
        raise PermissionError("Root approval hash mismatch")
    gate = json.loads(Path(gate_path).read_text())
    if gate.get("status") != "APPROVED" or gate.get("lane") != "vector":
        raise PermissionError("Root vector approval required")
    if gate.get("phase") != phase or not gate.get("campaign"):
        raise PermissionError("Wrong approved phase or missing campaign")
    if gate.get("source_sha256") != source_pins():
        raise PermissionError("Every source, configuration and protocol must be pinned")
    authority = gate.get("accounting_authority")
    if not isinstance(authority, str) or not authority.strip():
        raise PermissionError("Accounting authority must be pinned")
    context_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not context_path:
        raise PermissionError("No numerical supervisor context")
    context = json.loads(Path(context_path).read_text())
    if context.get("status") != "running" or context.get("parent_pid") != os.getppid():
        raise PermissionError("Supervisor must be the direct parent")
    if context.get("gate_sha256") != expected_hash or context.get("accounting_authority") != authority:
        raise PermissionError("Supervisor identity mismatch")
    for field in ("central_reservation_id", "central_spec_sha256"):
        if not isinstance(context.get(field), str) or not context[field]:
            raise PermissionError("Missing reservation identity")
    if os.environ.get("TYCHON_NUMERICAL_RUN_ID") != context["central_reservation_id"]:
        raise PermissionError("Run ID mismatch")
    if os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != expected_hash:
        raise PermissionError("Environment approval mismatch")
    lock_path = Path(context.get("shared_lock_path", ""))
    if not lock_path.is_file():
        raise PermissionError("Supervisor lock missing")
    with lock_path.open("r") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(handle, fcntl.LOCK_UN)
            raise PermissionError("Supervisor does not hold the lock")
    return gate, context
