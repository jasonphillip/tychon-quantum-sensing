"""Read-only approval bindings; numerical accounting belongs to the coordinator."""
import hashlib
import json
import os
from pathlib import Path


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
    root = Path(__file__).resolve().parents[2]
    required = {str(p.relative_to(root)) for p in Path(__file__).parent.glob("*.py")}
    required.add("experiments/measured_widefield/protocol.json")
    if not required <= set(approval.get("source_files", {})):
        raise ValueError("All runtime source files and protocol must be frozen")
    for relative, expected in approval["source_files"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or sha(path) != expected:
            raise ValueError("Frozen source changed: " + relative)
    return approval


def verified_manifest(path, expected):
    if sha(path) != expected:
        raise ValueError("Manifest hash mismatch")
    return json.loads(Path(path).read_text())
