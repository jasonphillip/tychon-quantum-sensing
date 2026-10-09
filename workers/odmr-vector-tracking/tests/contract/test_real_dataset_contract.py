"""Contract tier: the REAL upstream dataset conforms to the v1 contract — AND is detectable.

Runs when a real ``nv-sensor-sim`` dataset is present: set ``ODMR_VT_REAL_DATASET``, or rely
on the default symlinks ``data/sequence_sanity_v0`` / ``data/sequence_train_v1``. Skips
otherwise, so the suite stays green on machines without the artifacts.

Beyond schema validation, this asserts the **detector contract**: with a data-scaled
threshold the classical peak detector must actually lock pre-crossing (mean locked fraction
> 0.9). The originally published Increment-1 bar was retracted (2026-07-01) because the
default absolute threshold exceeded the real ~0.4% dip depth — the detector returned zero
peaks and a frozen tracker was scored. This test makes that failure mode impossible to
reintroduce silently.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

from odmr_vector_tracking.data.contract import validate_dataset_dir

_ENV = os.environ.get("ODMR_VT_REAL_DATASET")
_CANDIDATES = [Path(_ENV)] if _ENV else [
    Path("data/sequence_sanity_v0"),
    Path("data/sequence_train_v1"),
]
_PRESENT = [p for p in _CANDIDATES if (p / "manifest.json").exists()]

pytestmark = pytest.mark.skipif(
    not _PRESENT,
    reason=f"no real dataset at {[str(p) for p in _CANDIDATES]} (set ODMR_VT_REAL_DATASET)",
)


@pytest.mark.parametrize("dataset_dir", _PRESENT, ids=lambda p: p.name)
def test_real_dataset_passes_v1_contract(dataset_dir: Path) -> None:
    manifest = validate_dataset_dir(dataset_dir)
    assert manifest.get("contract_version", "v1") == "v1"


@pytest.mark.parametrize("dataset_dir", _PRESENT, ids=lambda p: p.name)
def test_classical_detector_locks_pre_crossing(dataset_dir: Path) -> None:
    """Data-scaled detector must see the real peaks: pre-crossing locked fraction > 0.9."""
    from odmr_vector_tracking.data import SequenceDatasetLoader
    from odmr_vector_tracking.tracking.classical import ClassicalTracker, auto_peak_min_depth

    ld = SequenceDatasetLoader(dataset_dir)
    m = ld.manifest
    ds = ld.load_split("test")
    locked_pre = []
    for n in range(min(8, ds.spectra.shape[0])):  # a slice is plenty for the guard
        depth = auto_peak_min_depth(ds.spectra[n], line_depths=m.get("line_depths"))
        trk = ClassicalTracker(
            ds.frequencies, linewidth_Hz=m["linewidth_Hz"], peak_min_depth=depth
        )
        res = trk.run(ds.spectra[n], init_freqs=ds.resonance_freqs[n, 0])
        cf = np.where(ds.collision_mask[n])[0]
        first = int(cf.min()) if cf.size else ds.spectra.shape[1]
        if first > 0:
            locked_pre.append(float(res.locked[:first].mean()))
    assert locked_pre, "no pre-crossing frames found to check"
    assert float(np.mean(locked_pre)) > 0.9