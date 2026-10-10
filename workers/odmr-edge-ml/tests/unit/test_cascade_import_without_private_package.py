"""Cascade training imports without the private manifest dependency."""

import os
import subprocess
import sys
from pathlib import Path


def test_cascade_train_stage_import_without_private_package():
    repo_src = Path(__file__).resolve().parents[2] / "src"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        (str(repo_src), env.get("PYTHONPATH", ""))
    )
    code = """
import sys
sys.modules['tychon_shared_data'] = None
import odmr_edge_ml.cascade.train_stage
import odmr_edge_ml.cascade as c
assert 'emit_cascade_manifest' in c.__all__
try:
    c.emit_cascade_manifest
except ImportError:
    pass
else:
    raise AssertionError('manifest emitter unexpectedly imported')
"""
    result = subprocess.run(
        (sys.executable, "-c", code),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
