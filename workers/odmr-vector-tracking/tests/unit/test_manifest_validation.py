"""Focused boundary cases for manifest-only validation."""

from __future__ import annotations

import copy

import pytest

from odmr_vector_tracking.data.contract import ContractViolation, validate_manifest


@pytest.fixture
def manifest() -> dict:
    # Hand-built; independent of the synthetic dataset generator.
    return {
        "generator_git_sha": "abc", "config_hash": "hash", "generated_at": "today",
        "backend": "test", "master_seed": 0,
        "train_seeds": [11, 12], "val_seeds": [13], "test_seeds": [14],
        "n_spectra_train": 2, "n_spectra_val": 1, "n_spectra_test": 1,
        "train_indices": [0, 1], "val_indices": [2], "test_indices": [3],
        "n_timesteps": 2, "dt_s": 0.001, "n_lines": 8, "hyperfine": False,
        "linewidth_Hz": 1.0e6, "collision_threshold_linewidths": 1.0,
        "n_freq_points": 3, "freq_range_Hz": [2.7e9, 3.0e9],
        "bias_B0_T": 0.005, "bias_direction_uvw": [0.2, 0.1, 1.0],
        "sweep_description": "test", "units": {
            "frequency": "Hz", "magnetic_field": "T", "time": "s"
        },
    }


def test_hand_built_manifest_passes(manifest: dict) -> None:
    validate_manifest(manifest)


@pytest.mark.parametrize("field", ["n_timesteps", "n_lines", "n_freq_points"])
@pytest.mark.parametrize("value", [-1, 0])
def test_invalid_dimensions(manifest: dict, field: str, value: int) -> None:
    bad = copy.deepcopy(manifest)
    bad[field] = value
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(bad)


@pytest.mark.parametrize("field", ["n_spectra_train", "n_spectra_val", "n_spectra_test"])
def test_negative_split_count(manifest: dict, field: str) -> None:
    bad = copy.deepcopy(manifest)
    bad[field] = -1
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(bad)


@pytest.mark.parametrize("bound", [float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("field", ["freq_range_Hz", "sweep_scalar_range_T"])
def test_nonfinite_range_bound(manifest: dict, field: str, bound: float) -> None:
    bad = copy.deepcopy(manifest)
    bad[field] = [bound, 3.0e9] if field == "freq_range_Hz" else [bound, 1.0]
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(bad)


@pytest.mark.parametrize("field", ["dt_s", "linewidth_Hz", "collision_threshold_linewidths", "bias_B0_T"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_physical_scale(manifest: dict, field: str, value: float) -> None:
    bad = copy.deepcopy(manifest)
    bad[field] = value
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(bad)


def test_duplicate_seed_within_split(manifest: dict) -> None:
    bad = copy.deepcopy(manifest)
    bad["train_seeds"] = [11, 11]
    with pytest.raises(ContractViolation, match="train_seeds"):
        validate_manifest(bad)


@pytest.mark.parametrize("field,indices", [
    ("val_indices", [1]),
    ("train_indices", [0, 0]),
    ("test_indices", [4]),
])
def test_invalid_split_indices(manifest: dict, field: str, indices: list[int]) -> None:
    bad = copy.deepcopy(manifest)
    bad[field] = indices
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(bad)
