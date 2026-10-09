"""Check the real HIL test's mode behavior in isolated pytest processes."""

from pathlib import Path

pytest_plugins = ["pytester"]

HIL_TEST = Path(__file__).with_name("test_verify_bit_exact_ci.py")
HIL_NODE = f"{HIL_TEST}::test_hil_capture_matches_numpy_reference"


def test_empty_captures_fail_only_in_hil_mode(pytester):
    empty_captures = pytester.path / "empty_hil"
    empty_captures.mkdir()
    package = pytester.path / "tychon_shared_data" / "cascade"
    package.mkdir(parents=True)
    (package.parent / "__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "cascade_ref.py").write_text(
        "def compose_int8(*args, **kwargs): pass\n"
        "def verify_bit_exact(*args, **kwargs): pass\n"
    )
    (package / "manifest.py").write_text("class CascadeManifest: pass\n")
    pytester.makepyfile(hil_override=f"""
from pathlib import Path

def pytest_collection_modifyitems(items):
    for item in items:
        if item.name == "test_hil_capture_matches_numpy_reference":
            item.module.HIL_FIXTURES_DIR = Path({str(empty_captures)!r})
""")

    hil = pytester.runpytest_subprocess("-p", "hil_override", HIL_NODE, "--mode=hil", "-q")
    assert hil.ret == 1
    hil.stdout.fnmatch_lines(["*no HIL captures under *empty_hil*", "*1 failed*"])
    assert "1 skipped" not in hil.stdout.str()

    local = pytester.runpytest_subprocess("-p", "hil_override", HIL_NODE, "-q")
    assert local.ret == 0
    local.stdout.fnmatch_lines(["*1 skipped*"])


def test_missing_shared_data_fails_only_in_hil_mode(pytester):
    pytester.makepyfile(hil_missing_package="""
import sys

def pytest_sessionstart(session):
    sys.modules["tychon_shared_data"] = None
""")
    hil = pytester.runpytest_subprocess(
        "-p", "hil_missing_package", HIL_NODE, "--mode=hil", "-q"
    )
    assert hil.ret == 1
    hil.stdout.fnmatch_lines(["*tychon-shared-data module*missing from Python import path*", "*1 failed*"])
    assert "1 skipped" not in hil.stdout.str()

    local = pytester.runpytest_subprocess("-p", "hil_missing_package", HIL_NODE, "-q")
    assert local.ret == 0
    local.stdout.fnmatch_lines(["*1 skipped*"])
