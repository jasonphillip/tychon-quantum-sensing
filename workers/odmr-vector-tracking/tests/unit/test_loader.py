"""Unit tests for the sequence loader."""

from __future__ import annotations

import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader

from odmr_vector_tracking.data import SequenceDatasetLoader
from tests.fixtures.synthetic import write_synthetic_h5

_SMALL = {"train": 2, "val": 1, "test": 1}


@pytest.fixture
def dataset_dir(tmp_path):
    return write_synthetic_h5(tmp_path, _SMALL, n_freq=120, n_timesteps=80)


def test_load_split_shapes_and_dtypes(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir)
    ds = ld.load_split("train")
    N, T, F, L = 2, 80, 120, 8
    assert ds.spectra.shape == (N, T, F) and ds.spectra.dtype == np.float32
    assert ds.frequencies.shape == (F,) and ds.frequencies.dtype == np.float32
    assert ds.B_true.shape == (N, T, 3) and ds.B_true.dtype == np.float32
    assert ds.resonance_freqs.shape == (N, T, L)
    assert ds.line_axis.shape == (N, T, L) and ds.line_axis.dtype == np.int8
    assert ds.line_transition.dtype == np.int8
    assert ds.collision_mask.shape == (N, T) and ds.collision_mask.dtype == np.bool_
    assert ds.line_collision.shape == (N, T, L) and ds.line_collision.dtype == np.bool_
    assert ds.bias.shape == (3,) and ds.bias.dtype == np.float32
    assert ds.seeds.shape == (N,) and ds.seeds.dtype == np.int64


def test_all_splits_present(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir)
    assert ld.load_split("val").n_sequences == 1
    assert ld.load_split("test").n_sequences == 1


def test_invalid_split_raises(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir)
    with pytest.raises(ValueError):
        ld.load_split("nope")


def test_properties(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir)
    assert ld.n_timesteps == 80
    assert ld.n_lines == 8
    assert ld.n_freq_points == 120
    assert ld.bias.shape == (3,)


def test_to_torch_item_and_batch(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir)
    td = ld.to_torch("train")
    assert len(td) == 2
    item = td[0]
    assert set(item) == {
        "spectra", "B_true", "resonance_freqs", "line_axis",
        "line_transition", "collision_mask", "line_collision", "seed",
    }
    assert item["spectra"].shape == (80, 120) and item["spectra"].dtype == torch.float32
    assert item["line_axis"].dtype == torch.int64
    assert item["collision_mask"].dtype == torch.bool
    assert td.frequencies.shape == (120,) and td.bias.shape == (3,)

    batch = next(iter(DataLoader(td, batch_size=2)))
    assert batch["spectra"].shape == (2, 80, 120)


def test_normalize_option(dataset_dir) -> None:
    ld = SequenceDatasetLoader(dataset_dir, normalize=True)
    s = ld.load_split("train").spectra
    assert s.min() >= -1e-6 and s.max() <= 1.0 + 1e-6
