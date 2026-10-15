"""Source and reservation checks. Standard-library only; no numerical imports."""
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "experiments/sparse_acquisition_screen"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authorize_stage(gate_path, status):
    gate = json.loads(Path(gate_path).read_text())
    if gate.get("status") != status:
        raise RuntimeError("numerical screen is unregistered; root accounting gate required")
    if gate.get("allow_training") is not False or gate.get("allow_final_evaluation") is not False:
        raise RuntimeError("this lane permits classical development only")
    required = {str(p.relative_to(ROOT)) for p in PACKAGE.iterdir()
                if p.suffix in {".py", ".md", ".json"}}
    required |= {"experiments/scalar_information_limit/forward.py"}
    required |= {str(p.relative_to(ROOT)) for p in (ROOT/"tests").glob("test_sparse*.py")}
    if not required.issubset(gate["source_files"]):
        raise RuntimeError("incomplete source/protocol freeze")
    for relative, digest in gate["source_files"].items():
        candidate = (ROOT / relative).resolve(strict=True)
        candidate.relative_to(ROOT)
        if sha(candidate) != digest:
            raise RuntimeError("frozen source mismatch: " + relative)
    if not re.fullmatch(r"[0-9a-f]{40}", gate.get("source_commit", "")):
        raise RuntimeError("missing pinned source commit")
    if gate.get("qualification_spec_sha256") != sha(PACKAGE / "qualification_spec.json"):
        raise RuntimeError("preregistered qualification specification mismatch")
    receipt_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not receipt_path:
        raise RuntimeError("run through the registered accounting wrapper")
    receipt = json.loads(Path(receipt_path).read_text())
    digest = sha(gate_path)
    if (receipt.get("status") != "running"
            or receipt.get("parent_pid") != os.getppid()
            or receipt.get("gate_sha256") != digest
            or receipt.get("accounting_authority") != "spark2-reservation-journal-v1"
            or not receipt.get("central_reservation_id")
            or not re.fullmatch(r"[0-9a-f]{64}", receipt.get("central_spec_sha256", ""))
            or os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != digest
            or os.environ.get("TYCHON_NUMERICAL_RUN_ID") != receipt["central_reservation_id"]):
        raise RuntimeError("accounting context does not bind this child and reservation")
    import fcntl
    # This is a supervisor-held per-job lock. Central reservation controls concurrency.
    with open(receipt["shared_lock_path"], "r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise RuntimeError("remote supervisor does not hold its job lock")
    return gate
