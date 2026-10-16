"""Approval and supervisor contract; imports no numerical library."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

PACKAGE = Path(__file__).resolve().parent
STUDY = "localisation-raw-compatibility-2026-10-15"


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    with Path(path).open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def authorize(path, phase):
    approval = read_json(path)
    digest = sha256(path)
    if (approval.get("status") != "APPROVED" or approval.get("study") != STUDY
            or approval.get("phases") != [phase]
            or approval.get("claim_scope") != "training_only_raw_to_version_A_compatibility"):
        raise RuntimeError("explicit root phase approval required")
    required = {str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*.py")} | {"protocol.json"}
    hashes = approval.get("source_sha256", {})
    if not required <= set(hashes):
        raise RuntimeError("complete source pins required")
    for name, expected in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE / relative) != expected:
            raise RuntimeError("source drift: " + name)
    if phase == "qualify" and read_json(PACKAGE / "protocol.json")["status"] != "FROZEN":
        raise RuntimeError("qualification requires frozen protocol")
    if approval.get("model_execution_authorized") is not False:
        raise RuntimeError("position-model execution must remain forbidden")
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise RuntimeError("one thread required")
    context = read_json(os.environ["TYCHON_ACTIVE_NUMERICAL_CONTEXT"])
    if (context.get("status") != "running" or context.get("parent_pid") != os.getppid()
            or context.get("gate_sha256") != digest
            or context.get("accounting_authority") != "spark2-reservation-journal-v1"
            or approval.get("accounting_authority") != context["accounting_authority"]
            or not context.get("central_reservation_id")
            or not re.fullmatch("[0-9a-f]{64}", context.get("central_spec_sha256", ""))
            or os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != digest
            or os.environ.get("TYCHON_NUMERICAL_RUN_ID") != context["central_reservation_id"]):
        raise RuntimeError("supervisor does not bind this job")
    with open(context["shared_lock_path"], "r+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            raise RuntimeError("supervisor must hold per-job lock")
    return approval


def bind(approval, name, path):
    if approval.get(name + "_sha256") != sha256(path):
        raise RuntimeError("input drift: " + name)
