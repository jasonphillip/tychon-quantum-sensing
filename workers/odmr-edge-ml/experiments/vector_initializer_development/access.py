"""Preserve every previous source guard and add the P1 package pins."""
import hashlib
from pathlib import Path
from experiments.vector_noise_qualification.access import authorize as previous_authorize
PACKAGE=Path(__file__).resolve().parent

def source_pins():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(PACKAGE.iterdir())
            if p.suffix in (".py",".json",".md")}

def authorize(path,expected_hash,phase):
    gate,context=previous_authorize(path,expected_hash,phase)
    if gate.get("p1_source_sha256")!=source_pins():raise PermissionError("Every P1 source must be pinned")
    if gate.get("execution")!={"phase":phase}:raise PermissionError("Wrong P1 execution phase")
    return gate,context
