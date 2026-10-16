"""Reuse both frozen source guards and add P0 source pins."""
import hashlib
from pathlib import Path
from experiments.vector_classical_qualification.access import authorize as prior_authorize
PACKAGE=Path(__file__).resolve().parent

def source_pins():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(PACKAGE.iterdir()) if p.suffix in (".py",".json",".md")}

def authorize(path, expected_hash, phase):
    gate, context=prior_authorize(path, expected_hash, phase)
    if gate.get("p0_source_sha256") != source_pins():
        raise PermissionError("Every P0 source/protocol must be pinned")
    if gate.get("classical_source_commit") != "18395df0080fb6f712eebe37a51d6ae55a09dd7f":
        raise PermissionError("Wrong frozen classical source")
    return gate,context
