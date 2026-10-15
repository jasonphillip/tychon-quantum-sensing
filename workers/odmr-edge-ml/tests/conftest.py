"""Collection rules for test environments without optional heavy dependencies."""
import importlib.metadata

import pytest


def _has_distribution(name: str) -> bool:
    try:
        importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return False
    return True


def pytest_collection_modifyitems(config, items):
    # The frozen scalar repair gates record dependency versions, including TensorFlow
    # (experiments/scalar_repair_cycle/gates.py, versions()). Their tests need that
    # distribution's metadata; CI does not install TensorFlow, so they run only locally.
    if _has_distribution("tensorflow"):
        return
    skip = pytest.mark.skip(reason="needs TensorFlow distribution metadata (frozen gates.versions()); not installed here")
    for item in items:
        if item.path.name == "test_scalar_repair_cycle.py":
            item.add_marker(skip)
