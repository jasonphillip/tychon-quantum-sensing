"""Unit tests for the v1 data-contract validator."""

from __future__ import annotations

import copy

import pytest

from odmr_vector_tracking.data.contract import (
    ContractViolation,
    validate_manifest,
    validate_sequence_dataset,
)
from tests.fixtures.synthetic import make_synthetic_dataset, write_synthetic_h5

# A small, fast dataset reused across tests.
_SMALL = {"train": 2, "val": 1, "test": 1}


@pytest.fixture
def manifest() -> dict:
    _splits, mani = make_synthetic_dataset(_SMALL, n_freq=120, n_timesteps=80)
    return mani


def test_valid_manifest_passes(manifest: dict) -> None:
    validate_manifest(manifest)  # must not raise


def test_missing_field_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    del bad["n_timesteps"]
    with pytest.raises(ContractViolation, match="Missing required"):
        validate_manifest(bad)


def test_wrong_type_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["n_lines"] = "eight"
    with pytest.raises(ContractViolation, match="expected int"):
        validate_manifest(bad)


def test_wrong_contract_version_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["contract_version"] = "v0"
    with pytest.raises(ContractViolation, match="contract_version"):
        validate_manifest(bad)


def test_seed_overlap_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["val_seeds"] = list(bad["train_seeds"])  # force train/val overlap
    bad["n_spectra_val"] = len(bad["val_seeds"])
    with pytest.raises(ContractViolation, match="overlap"):
        validate_manifest(bad)


def test_non_unit_bias_direction_is_allowed(manifest: dict) -> None:
    # The upstream stores a raw (non-unit) [uvw] direction; nonzero norm is the only rule.
    ok = copy.deepcopy(manifest)
    ok["bias_direction_uvw"] = [0.2, 0.1, 1.0]
    validate_manifest(ok)  # must not raise


def test_zero_norm_bias_direction_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["bias_direction_uvw"] = [0.0, 0.0, 0.0]
    with pytest.raises(ContractViolation, match="nonzero norm"):
        validate_manifest(bad)


def test_seed_count_mismatch_raises(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["train_seeds"] = bad["train_seeds"][:-1] if bad["train_seeds"] else [1]
    with pytest.raises(ContractViolation):
        validate_manifest(bad)


def test_validate_sequence_dataset_passes(tmp_path) -> None:
    write_synthetic_h5(tmp_path, _SMALL, n_freq=120, n_timesteps=80)
    _splits, mani = make_synthetic_dataset(_SMALL, n_freq=120, n_timesteps=80)
    validate_sequence_dataset(tmp_path / "dataset.h5", mani)  # must not raise


def test_validate_sequence_dataset_shape_mismatch_raises(tmp_path) -> None:
    write_synthetic_h5(tmp_path, _SMALL, n_freq=120, n_timesteps=80)
    _splits, mani = make_synthetic_dataset(_SMALL, n_freq=120, n_timesteps=80)
    mani["n_timesteps"] = 81  # now inconsistent with the written data
    with pytest.raises(ContractViolation, match="shape"):
        validate_sequence_dataset(tmp_path / "dataset.h5", mani)
