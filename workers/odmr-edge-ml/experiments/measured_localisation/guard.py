"""Fail-closed numerical approval; standard-library imports only."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

PACKAGE = Path(__file__).resolve().parent


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def authorize(path, phase):
    approval = read_json(path)
    digest = sha256(path)
    if approval.get("status") != "APPROVED" or approval.get("study") != "measured-localisation-2026-10-15":
        raise RuntimeError("root has not approved this measured-data study")
    if phase not in approval.get("phases", []):
        raise RuntimeError("phase is not authorized")
    geometry_only = phase == "partition"
    required_scope = "position_labels_only_geometry" if geometry_only else "measured_fixed_geometry_motor_stage_position"
    if approval.get("claim_scope") != required_scope:
        raise RuntimeError("claim scope mismatch")
    required = {str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*.py")} | {"protocol.json"}
    frozen = approval.get("source_sha256", {})
    if not required <= set(frozen):
        raise RuntimeError("complete implementation/protocol freeze required")
    for name, expected in frozen.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE / relative) != expected:
            raise RuntimeError("source hash mismatch: " + name)
    if geometry_only and (approval.get("phases") != ["partition"]
                          or approval.get("signal_values_authorized") is not False
                          or approval.get("model_execution_authorized") is not False):
        raise RuntimeError("geometry approval must authorize positions only")
    if not geometry_only and read_json(PACKAGE / "protocol.json").get("status") != "FROZEN":
        raise RuntimeError("root must freeze the protocol before numerical work")
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise RuntimeError("one numerical thread is required")
    context_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not context_path:
        raise RuntimeError("a root accounting supervisor is required")
    context = read_json(context_path)
    if (context.get("status") != "running"
            or context.get("parent_pid") != os.getppid()
            or context.get("gate_sha256") != digest
            or context.get("accounting_authority") != approval.get("accounting_authority")
            or not approval.get("accounting_authority")
            or not context.get("central_reservation_id")
            or not re.fullmatch(r"[0-9a-f]{64}", context.get("central_spec_sha256", ""))
            or os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != digest
            or os.environ.get("TYCHON_NUMERICAL_RUN_ID") != context["central_reservation_id"]):
        raise RuntimeError("accounting receipt does not bind this process and approval")
    with open(context["shared_lock_path"], "r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise RuntimeError("supervisor must hold its per-job lock")
    if type(approval.get("random_seed")) is not int or not 0 <= approval["random_seed"] < 2 ** 63 or not approval.get("partition_salt"):
        raise RuntimeError("registered seed and partition salt required")
    approval["approval_sha256"] = digest
    return approval


def bind_file(approval, key, path):
    if approval.get(key) != sha256(path):
        raise RuntimeError("unapproved input: " + key)
