"""Reuse the frozen supervisor guard and add complete additive-package pins."""
from pathlib import Path
import hashlib
from experiments.vector_direct_screen.access import authorize as frozen_authorize

PACKAGE = Path(__file__).resolve().parent


def source_pins():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(PACKAGE.iterdir()) if p.suffix in (".py", ".json", ".md")}


def authorize(path, expected_hash, phase):
    gate, context = frozen_authorize(path, expected_hash, phase)
    if gate.get("additive_source_sha256") != source_pins():
        raise PermissionError("Every additive source and protocol must be pinned")
    if gate.get("frozen_source_commit") != "f5032fa3461aba2d2395bd1313c25fd9a8f98220":
        raise PermissionError("Wrong frozen scientific source")
    return gate, context
