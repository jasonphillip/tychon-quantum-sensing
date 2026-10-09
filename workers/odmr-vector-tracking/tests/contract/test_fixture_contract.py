"""Contract tier: the synthetic fixture conforms to the v1 data contract.

This is the integration boundary spec. The synthetic fixture and the real upstream dataset must
both satisfy it; here we assert it for the fixture (always generatable) so the loader/metrics/
baseline are exercised against the exact schema before real data lands.
"""

from __future__ import annotations

import h5py
import numpy as np
import pytest

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.data.contract import (
    DATASET_SCHEMA,
    VALID_SPLITS,
    validate_dataset_dir,
)
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8
from tests.fixtures.synthetic import write_synthetic_h5

_SMALL = {"train": 2, "val": 1, "test": 1}


@pytest.fixture
def dataset_dir(tmp_path):
    return write_synthetic_h5(tmp_path, _SMALL, n_freq=120, n_timesteps=80)


def test_fixture_passes_full_contract(dataset_dir) -> None:
    manifest = validate_dataset_dir(dataset_dir)  # manifest + dataset, raises on violation
    assert manifest["contract_version"] == "v1"


def test_fixture_has_all_datasets_with_correct_dtypes(dataset_dir) -> None:
    with h5py.File(dataset_dir / "dataset.h5", "r") as f:
        for split in VALID_SPLITS:
            g = f[split]
            assert isinstance(g, h5py.Group)
            for name, (exp_dtype, _shape) in DATASET_SCHEMA.items():
                assert name in g, f"{split}/{name} missing"
                ds = g[name]
                assert isinstance(ds, h5py.Dataset)
                assert np.dtype(ds.dtype) == np.dtype(exp_dtype)


def test_fixture_contains_inter_axis_crossing(dataset_dir) -> None:
    """The whole point of the fixture: a labeled crossing between two different NV axes."""
    line_collision = SequenceDatasetLoader(dataset_dir).load_split("train").line_collision
    found = False
    for ni in range(line_collision.shape[0]):
        for ti in range(line_collision.shape[1]):
            flagged = np.where(line_collision[ni, ti])[0]
            if flagged.size >= 2 and np.unique(LINE_AXIS_8[flagged]).size > 1:
                found = True
                break
    assert found, "fixture must contain a labeled inter-axis crossing"
