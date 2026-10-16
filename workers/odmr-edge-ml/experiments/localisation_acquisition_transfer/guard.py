"""Approval and supervisor contract; imports no numerical library."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

PACKAGE = Path(__file__).resolve().parent
STUDY = "localisation-acquisition-transfer-2026-10-15"


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
            or approval.get("claim_scope") != "conditional_single_acquisition_transfer_of_unchanged_classical_calibration_models"):
        raise RuntimeError("explicit root phase approval required")
    required = {str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*.py")} | {"protocol.json", "geometry.json"}
    hashes = approval.get("source_sha256", {})
    if not required <= set(hashes):
        raise RuntimeError("complete source pins required")
    for name, expected in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE / relative) != expected:
            raise RuntimeError("source drift: " + name)
    if phase == "evaluate" and read_json(PACKAGE / "protocol.json")["status"] != "FROZEN":
        raise RuntimeError("transfer requires frozen protocol")
    if approval.get("model_execution_authorized") != ("fixed_gp_prediction_only" if phase == "evaluate" else False):
        raise RuntimeError("only the approved fixed GP prediction phase is allowed")
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
    dependencies = approval.get("dependency_sha256", {})
    for name, expected in dependencies.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("dependency paths must be source-relative")
        if sha256(PACKAGE.parents[1] / relative) != expected:
            raise RuntimeError("frozen dependency drift")
    required_dependencies = {"experiments/localisation_redesign/models.py",
                             "experiments/localisation_redesign/metrics.py",
                             "experiments/localisation_redesign/__init__.py"}
    raw_package = PACKAGE.parent / "localisation_raw_compatibility"
    required_dependencies |= {str(p.relative_to(PACKAGE.parents[1])) for p in raw_package.rglob("*.py")}
    required_dependencies |= {"experiments/localisation_raw_compatibility/protocol.json"}
    if not required_dependencies <= set(dependencies):
        raise RuntimeError("complete frozen extractor and predictor pins required")
    return approval


def bind(approval, name, path):
    if approval.get(name + "_sha256") != sha256(path):
        raise RuntimeError("input drift: " + name)
