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


# The frozen hybrid test imports three experiment modules by top-level name.
# Keep those aliases private to its collection and test execution.
from contextlib import contextmanager
import sys

_HYBRID_TEST = "test_nv_hybrid_screen.py"
_HYBRID_ALIASES = ("estimators", "physics", "forward")
_HYBRID_BINDINGS = pytest.StashKey[dict]()
_MISSING_MODULE = object()


@contextmanager
def _hybrid_import_scope(bindings=None):
    previous_path = list(sys.path)
    previous_modules = {name: sys.modules.get(name, _MISSING_MODULE)
                        for name in _HYBRID_ALIASES}
    try:
        for name in _HYBRID_ALIASES:
            sys.modules.pop(name, None)
        if bindings is not None:
            sys.modules.update(bindings)
        yield
    finally:
        sys.path[:] = previous_path
        for name, module in previous_modules.items():
            if module is _MISSING_MODULE:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_make_collect_report(collector):
    """Isolate only the hybrid module while pytest imports and collects it."""
    if not isinstance(collector, pytest.Module) or collector.path.name != _HYBRID_TEST:
        yield
        return
    with _hybrid_import_scope():
        outcome = yield
        if outcome.get_result().passed:
            collector.stash[_HYBRID_BINDINGS] = {
                name: sys.modules[name] for name in _HYBRID_ALIASES
            }


@pytest.fixture(scope="module", autouse=True)
def _hybrid_imports_during_tests(request):
    """Keep string-based unittest.mock.patch targets bound to the hybrid module."""
    if request.node.path.name != _HYBRID_TEST:
        yield
        return
    with _hybrid_import_scope(request.node.stash[_HYBRID_BINDINGS]):
        yield
