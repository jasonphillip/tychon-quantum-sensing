"""Test-only shim for environments without TensorFlow (for example CI).

The frozen scalar repair gates record dependency versions (experiments/scalar_repair_cycle/
gates.py, versions(); models.py, interpreter_contract()), which needs TensorFlow's
distribution metadata. Where that metadata is absent, the tests in
tests/test_scalar_repair_cycle.py run against a deterministic, clearly labelled synthetic
version record instead. Production code and the pinned test module are unchanged; the
synthetic record exists only inside these tests and never reaches a real freeze.
"""
import importlib.metadata
import pytest

SYNTHETIC_GATE_VERSIONS = {
    "numpy": "test-fixture",
    "scipy": "test-fixture",
    "torch": "test-fixture",
    "tensorflow": "test-fixture-not-installed",
    "int8_interpreter": {"backend": "test-fixture-not-installed", "version": "test-fixture"},
}


def _has_distribution(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


@pytest.fixture(autouse=True)
def _synthetic_gate_versions_without_tensorflow(request, monkeypatch):
    """Function-scoped: only tests in test_scalar_repair_cycle.py, only without TensorFlow metadata."""
    if request.node.path.name != "test_scalar_repair_cycle.py" or _has_distribution("tensorflow"):
        return
    gates = request.module.gates
    monkeypatch.setattr(gates, "versions", lambda: {k: (dict(v) if isinstance(v, dict) else v)
                                                    for k, v in SYNTHETIC_GATE_VERSIONS.items()})
