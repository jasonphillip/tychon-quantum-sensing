"""Pure module-cache regressions; no spectra, optimizer, training, or subprocess."""
import sys
from types import ModuleType
from unittest.mock import patch

import pytest


@pytest.fixture
def isolation_plugin(request):
    matches = [plugin for plugin in request.config.pluginmanager.get_plugins()
               if hasattr(plugin, "_hybrid_import_scope")]
    assert len(matches) == 1
    return matches[0]


@pytest.mark.parametrize("scalar_first", [False, True], ids=["hybrid-first", "scalar-first"])
def test_collection_orders_and_runtime_patch_binding(isolation_plugin, monkeypatch, scalar_first):
    names = isolation_plugin._HYBRID_ALIASES
    scalar = {name: ModuleType(name) for name in names}
    hybrid = {name: ModuleType(name) for name in names}
    exec('def refine(): return "scalar"', scalar["estimators"].__dict__)
    exec('def refine(): return "hybrid"\ndef run(): return refine()', hybrid["estimators"].__dict__)
    scalar["estimators"].GRID = object()
    unrelated = ModuleType("hybrid_test_unrelated")
    monkeypatch.setitem(sys.modules, unrelated.__name__, unrelated)
    monkeypatch.setattr(sys, "path", list(sys.path))
    initial_path = list(sys.path)
    for name in names:
        if scalar_first:
            monkeypatch.setitem(sys.modules, name, scalar[name])
        else:
            monkeypatch.delitem(sys.modules, name, raising=False)

    # Simulate the frozen hybrid module's top-level imports during collection.
    with isolation_plugin._hybrid_import_scope():
        assert all(name not in sys.modules for name in names)
        sys.modules.update(hybrid)
        sys.path.insert(0, "/synthetic/hybrid-test-imports")
        captured = {name: sys.modules[name] for name in names}
    assert sys.path == initial_path
    assert sys.modules[unrelated.__name__] is unrelated
    for name in names:
        if scalar_first:
            assert sys.modules[name] is scalar[name]
        else:
            assert name not in sys.modules
            monkeypatch.setitem(sys.modules, name, scalar[name])

    # Collection has now loaded both modules, in either order.
    with isolation_plugin._hybrid_import_scope(captured):
        with patch("estimators.refine", return_value="patched-hybrid") as refine:
            assert hybrid["estimators"].run() == "patched-hybrid"
            refine.assert_called_once_with()
            assert scalar["estimators"].refine() == "scalar"
    assert all(sys.modules[name] is scalar[name] for name in names)
    assert sys.path == initial_path
    assert sys.modules[unrelated.__name__] is unrelated


def test_collection_error_restores_paths_and_aliases(isolation_plugin, monkeypatch):
    original = ModuleType("estimators")
    monkeypatch.setitem(sys.modules, "estimators", original)
    monkeypatch.setattr(sys, "path", list(sys.path))
    before_path = list(sys.path)
    before_modules = {name: sys.modules.get(name) for name in isolation_plugin._HYBRID_ALIASES}
    with pytest.raises(RuntimeError, match="manufactured collection failure"):
        with isolation_plugin._hybrid_import_scope():
            sys.modules["estimators"] = ModuleType("estimators")
            sys.path.insert(0, "/synthetic/failed-import")
            raise RuntimeError("manufactured collection failure")
    assert sys.path == before_path
    for name, module in before_modules.items():
        assert sys.modules.get(name) is module
