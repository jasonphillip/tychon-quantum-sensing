"""Contract tier: the REAL upstream dataset conforms to the v1 contract.

Pre-written and skipped until the real ``nv-sensor-sim`` time-series + collision dataset exists.
Point ``ODMR_VT_REAL_DATASET`` at the dataset directory (containing ``dataset.h5`` +
``manifest.json``), or drop it at ``./data/real``. When present, this flips from skip → run with
no other change — the same validator the synthetic fixture passes (the swap point in the
integration checklist).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from odmr_vector_tracking.data.contract import validate_dataset_dir

_ENV = os.environ.get("ODMR_VT_REAL_DATASET")
_REAL_DIR = Path(_ENV) if _ENV else Path("data/real")

pytestmark = pytest.mark.skipif(
    not (_REAL_DIR / "manifest.json").exists(),
    reason=f"real dataset not available at {_REAL_DIR} (set ODMR_VT_REAL_DATASET)",
)


def test_real_dataset_passes_v1_contract() -> None:
    manifest = validate_dataset_dir(_REAL_DIR)
    assert manifest["contract_version"] == "v1"
