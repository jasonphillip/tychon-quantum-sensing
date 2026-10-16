"""Fail-closed root approval and source/input pins; no numerical imports."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

PACKAGE = Path(__file__).resolve().parent
STUDY = "localisation-redesign-2026-10-15"
SCOPE = "published_version_A_fitted_feature_stage_coordinate_pairs_conditional_spatial_generalization"


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


def bind_file(approval, key, path):
    if approval.get(key) != sha256(path):
        raise RuntimeError("unapproved input: " + key)


def check_source(hashes):
    required = {str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*.py")} | {"protocol.json"}
    if not required <= set(hashes):
        raise RuntimeError("complete implementation/protocol freeze required")
    for name, expected in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE / relative) != expected:
            raise RuntimeError("source hash mismatch: " + name)


def authorize(path, phase):
    approval = read_json(path)
    digest = sha256(path)
    if approval.get("status") != "APPROVED" or approval.get("study") != STUDY:
        raise RuntimeError("root has not approved this study")
    if approval.get("phases") != [phase]:
        raise RuntimeError("one explicit phase per authorization required")
    geometry_only = phase == "partition"
    scope = "position_labels_only_geometry" if geometry_only else SCOPE
    if approval.get("claim_scope") != scope:
        raise RuntimeError("claim scope mismatch")
    check_source(approval.get("source_sha256", {}))
    if read_json(PACKAGE / "protocol.json").get("status") != "FROZEN":
        raise RuntimeError("root must freeze protocol before every numerical phase")
    if geometry_only and (approval.get("signal_values_authorized") is not False
                          or approval.get("model_execution_authorized") is not False):
        raise RuntimeError("geometry may read position labels only")
    for key in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        if os.environ.get(key) != "1":
            raise RuntimeError("one numerical thread required")
    context_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not context_path:
        raise RuntimeError("root numerical supervisor required")
    context = read_json(context_path)
    if (context.get("status") != "running" or context.get("parent_pid") != os.getppid()
            or context.get("gate_sha256") != digest
            or context.get("accounting_authority") != approval.get("accounting_authority")
            or not approval.get("accounting_authority")
            or not context.get("central_reservation_id")
            or not re.fullmatch(r"[0-9a-f]{64}", context.get("central_spec_sha256", ""))
            or os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != digest
            or os.environ.get("TYCHON_NUMERICAL_RUN_ID") != context["central_reservation_id"]):
        raise RuntimeError("supervisor does not bind this process, source and approval")
    with open(context["shared_lock_path"], "r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise RuntimeError("supervisor must hold its per-job lock")
    if not geometry_only:
        seed_path = Path(approval.get("seed_receipt_path", ""))
        if not seed_path.is_absolute() or sha256(seed_path) != approval.get("seed_receipt_sha256"):
            raise RuntimeError("immutable root seed receipt is not bound")
        seeds = read_json(seed_path)
        if (seeds.get("study") != STUDY or seeds.get("generated_before_new_signal_execution") is not True
                or set(seeds) != {"study", "generated_before_new_signal_execution", "paired_training", "bootstrap"}
                or any(type(seeds.get(k)) is not int or not 0 <= seeds[k] < 2 ** 63
                       for k in ("paired_training", "bootstrap"))):
            raise RuntimeError("one paired training seed and one bootstrap seed required")
        approval["seeds"] = seeds
    approval["approval_sha256"] = digest
    return approval
