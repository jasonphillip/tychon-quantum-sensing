"""Preserve every previous source guard and add the P1 package pins."""
import hashlib
import os
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
    from experiments.vector_line_comparator.access import source_pins as tied_pins
    if gate.get("tied_source_sha256")!=tied_pins():raise PermissionError("Every tied comparator source must be pinned")
    if gate.get("tied_source_commit")!="436bce3d14a4ae8575545b17d101fd66ae882b28":raise PermissionError("Frozen tied comparator identity required")
    return gate,context


def assert_cuda_environment():
    """The approved supervisor installs this before its Torch import."""
    required=":4096:8"
    if os.environ.get("CUBLAS_WORKSPACE_CONFIG")!=required:
        raise RuntimeError("Supervisor deterministic cuBLAS prerequisite is absent or changed")
    return required
