"""Keep all frozen guards; bind new source and the unchanged learned artifacts."""
import hashlib
from pathlib import Path
from experiments.vector_initializer_development.access import authorize as prior_authorize
PACKAGE=Path(__file__).resolve().parent
P1_COMMIT="c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e"

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def source_pins():return {p.name:sha(p) for p in sorted(PACKAGE.iterdir()) if p.suffix in (".py",".md",".json")}
def authorize(path,expected_hash,phase):
    gate,context=prior_authorize(path,expected_hash,phase)
    if gate.get("challenge_source_sha256")!=source_pins():raise PermissionError("Every challenge source must be pinned")
    if gate.get("p1_frozen_commit")!=P1_COMMIT:raise PermissionError("Wrong frozen P1 identity")
    expected_stage="verification" if phase=="challenge_verification" else "development"
    if gate.get("stage")!=expected_stage:raise PermissionError("Wrong accounting stage")
    return gate,context

def frozen_inputs(gate):
    records=gate.get("frozen_inputs",{})
    if set(records)!={"model-final.pt","scaling.npz","setup.json"}:raise PermissionError("Exactly three frozen P1 inputs required")
    result={}
    for name,item in records.items():
        path=Path(item["path"])
        if not path.is_absolute() or path.name!=name or sha(path)!=item["sha256"]:raise PermissionError("Frozen P1 artifact mismatch")
        result[name]=path
    return result
