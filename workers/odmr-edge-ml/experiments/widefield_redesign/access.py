"""Source and supervisor bindings. No environment-only numerical authorization."""
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path

CONTRACT = "a3683e0dafa3c422e995c960f8c38bb6160fef63b5a97f38c42e47457e0bc33f"
STUDY = "widefield-redesign-2026-10-15"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def write_json(path, record):
    with Path(path).open("x") as f:
        json.dump(record, f, indent=2, sort_keys=True, allow_nan=False)
        f.write("\n")


def validate_protocol(path):
    p = json.loads(Path(path).read_text())
    contract = {k: v for k, v in p.items() if k != "status"}
    h = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if p["status"] != "FROZEN" or h != CONTRACT:
        raise ValueError("Unfrozen or unimplemented protocol")
    return p


def gate(path, phase):
    path = Path(path)
    a = json.loads(path.read_text())
    ah = sha(path)
    if a.get("status") != "approved" or a.get("study") != STUDY or phase not in a.get("phases", []):
        raise ValueError("Phase not released")
    if os.environ.get("TYCHON_NUMERICAL_APPROVAL_SHA256") != ah:
        raise ValueError("Approval environment mismatch")
    rid = os.environ.get("TYCHON_NUMERICAL_RUN_ID")
    cp = Path(os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT", ""))
    if rid not in a.get("allowed_run_ids", []) or cp.name != "context.json" or cp.parent.name != rid or cp.is_symlink():
        raise ValueError("Supervisor identity missing")
    c = json.loads(cp.read_text())
    if (c.get("status") != "running" or c.get("parent_pid") != os.getppid()
        or c.get("gate_sha256") != ah or c.get("central_reservation_id") != rid
        or not a.get("accounting_authority") or c.get("accounting_authority") != a["accounting_authority"]
        or not re.fullmatch("[0-9a-f]{64}", c.get("central_spec_sha256", ""))):
        raise ValueError("No active approved numerical parent")
    lock = Path(c.get("shared_lock_path", ""))
    if lock != cp.parent / "active.lock" or lock.is_symlink():
        raise ValueError("Unexpected lock")
    with lock.open("rb") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            raise ValueError("Numerical lock is not held")
    root = Path(__file__).resolve().parents[2]
    required = {str(p.relative_to(root)) for p in Path(__file__).parent.glob("*.py")}
    required |= {"experiments/widefield_redesign/protocol.json", "experiments/measured_widefield/io.py"}
    if not required <= a.get("source_files", {}).keys():
        raise ValueError("Incomplete source freeze")
    for name, expected in a["source_files"].items():
        p = root / name
        if not p.resolve().is_relative_to(root) or p.is_symlink() or sha(p) != expected:
            raise ValueError("Source drift: " + name)
    protocol = root / "experiments/widefield_redesign/protocol.json"
    if sha(protocol) != a.get("protocol_sha256"):
        raise ValueError("Protocol pin mismatch")
    a["protocol"] = validate_protocol(protocol)
    for name, expected in a.get("inputs", {}).items():
        p = Path(name)
        if not p.is_absolute() or p.is_symlink() or sha(p) != expected:
            raise ValueError("Input pin mismatch")
    return a
