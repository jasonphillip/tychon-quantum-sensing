"""Focused validation cases for the simulator manifest contract."""

import pytest

from odmr_edge_ml.data.contracts import ContractViolation, validate_manifest
from tests.unit.test_data_contracts import make_valid_manifest


def test_hand_built_valid_manifest_passes():
    validate_manifest(make_valid_manifest())


@pytest.mark.parametrize("value", [-1, 0, 1.5, True])
def test_frequency_dimension_must_be_positive_integer(value):
    manifest = make_valid_manifest()
    manifest["n_freq_points"] = value
    with pytest.raises(ContractViolation, match="n_freq_points"):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", [
    "freq_range_Hz",
    "p1_concentration_range_ppm",
    "temperature_range_K",
    "b1_gradient_range",
    "b_perp_range_T",
])
@pytest.mark.parametrize("bound", [float("nan"), float("inf"), float("-inf")])
def test_range_bounds_must_be_finite(field, bound):
    manifest = make_valid_manifest()
    manifest[field][0] = bound
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", [
    "freq_range_Hz",
    "p1_concentration_range_ppm",
    "temperature_range_K",
])
def test_positive_range_scales(field):
    manifest = make_valid_manifest()
    manifest[field][0] = 0
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(manifest)


@pytest.mark.parametrize("value", [0.0, -1.0, float("nan"), float("inf")])
def test_concentrator_scale_must_be_positive_and_finite(value):
    manifest = make_valid_manifest()
    manifest["concentrator_amplification"] = value
    with pytest.raises(ContractViolation, match="concentrator_amplification"):
        validate_manifest(manifest)


@pytest.mark.parametrize("field", ["train_seeds", "val_seeds", "test_seeds"])
def test_duplicate_seed_within_split_fails(field):
    manifest = make_valid_manifest()
    manifest[field][1] = manifest[field][0]
    with pytest.raises(ContractViolation, match=field):
        validate_manifest(manifest)


def test_split_indices_remain_disjoint():
    manifest = make_valid_manifest()
    manifest["val_indices"][0] = manifest["train_indices"][0]
    with pytest.raises(ContractViolation, match="train_indices.*val_indices"):
        validate_manifest(manifest)
