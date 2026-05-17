"""Unit tests for manifest contract validation."""

import pytest

from odmr_edge_ml.data.contracts import (
    ContractViolation,
    validate_manifest,
    vector_readiness_view,
)


def make_valid_manifest() -> dict:
    """Factory for a minimal valid manifest dict."""
    return {
        "generator_git_sha": "abc123def456",
        "config_hash": "4a05cac7b958",
        "simos_version": "0.2.3",
        "qutip_version": "5.2.3",
        "backend": "qutip",
        "generated_at": "2026-03-26T19:30:08.209895+00:00",
        "master_seed": 12345,
        "train_seeds": [100, 200, 300],
        "val_seeds": [400, 500],
        "test_seeds": [600, 700],
        "n_spectra_train": 3,
        "n_spectra_val": 2,
        "n_spectra_test": 2,
        "train_indices": [0, 1, 2],
        "val_indices": [3, 4],
        "test_indices": [5, 6],
        "n_freq_points": 100,
        "freq_range_Hz": [2.82e9, 2.92e9],
        "p1_concentration_range_ppm": [1.0, 300.0],
        "temperature_range_K": [280.0, 320.0],
        "b1_gradient_range": [0.05, 0.30],
        "b_perp_range_T": [0.0, 50e-6],
        "units": {
            "frequency": "Hz",
            "magnetic_field": "T",
            "temperature": "K",
            "p1_concentration": "ppm",
            "b1_gradient": "fraction",
            "b_perp": "T",
            "time": "s",
        },
    }


def test_valid_manifest_passes():
    validate_manifest(make_valid_manifest())


def test_missing_field_raises():
    m = make_valid_manifest()
    del m["master_seed"]
    with pytest.raises(ContractViolation, match="Missing required fields"):
        validate_manifest(m)


def test_wrong_type_raises():
    m = make_valid_manifest()
    m["master_seed"] = "not_an_int"
    with pytest.raises(ContractViolation, match="expected int"):
        validate_manifest(m)


def test_seed_count_mismatch_raises():
    m = make_valid_manifest()
    m["train_seeds"] = [100, 200]  # should be 3
    with pytest.raises(ContractViolation, match="train_seeds length"):
        validate_manifest(m)


def test_index_count_mismatch_raises():
    m = make_valid_manifest()
    m["val_indices"] = [3]  # should be 2
    with pytest.raises(ContractViolation, match="val_indices length"):
        validate_manifest(m)


def test_overlapping_train_test_seeds_raises():
    m = make_valid_manifest()
    m["test_seeds"] = [100, 700]  # 100 overlaps with train
    with pytest.raises(ContractViolation, match="Train/test seed overlap"):
        validate_manifest(m)


def test_overlapping_train_val_seeds_raises():
    m = make_valid_manifest()
    m["val_seeds"] = [200, 500]  # 200 overlaps with train
    with pytest.raises(ContractViolation, match="Train/val seed overlap"):
        validate_manifest(m)


def test_overlapping_val_test_seeds_raises():
    m = make_valid_manifest()
    m["val_seeds"] = [600, 500]  # 600 overlaps with test
    with pytest.raises(ContractViolation, match="Val/test seed overlap"):
        validate_manifest(m)


def test_inverted_range_raises():
    m = make_valid_manifest()
    m["temperature_range_K"] = [320.0, 280.0]  # inverted
    with pytest.raises(ContractViolation, match="min.*max"):
        validate_manifest(m)


def test_missing_unit_raises():
    m = make_valid_manifest()
    del m["units"]["temperature"]
    with pytest.raises(ContractViolation, match="Missing required unit.*temperature"):
        validate_manifest(m)


def test_wrong_unit_value_raises():
    m = make_valid_manifest()
    m["units"]["frequency"] = "GHz"  # should be Hz
    with pytest.raises(ContractViolation, match="expected 'Hz'"):
        validate_manifest(m)


def test_empty_provenance_raises():
    m = make_valid_manifest()
    m["generator_git_sha"] = "   "
    with pytest.raises(ContractViolation, match="generator_git_sha.*empty"):
        validate_manifest(m)


# ---------------------------------------------------------------------------
# Optional vector-readiness fields (B2.6 scaffold, 2026-05-17)


def test_legacy_manifest_without_vector_fields_validates():
    """Manifests written before the vector extension must still validate."""
    m = make_valid_manifest()
    for k in (
        "bias_B0_T",
        "bias_direction_uvw",
        "concentrator_amplification",
        "magnet_drift_ppm_per_K",
    ):
        assert k not in m
    validate_manifest(m)


def test_legacy_manifest_returns_defaults_via_view():
    view = vector_readiness_view(make_valid_manifest())
    assert view["bias_B0_T"] == 0.0
    assert view["bias_direction_uvw"] == [0.0, 0.0, 1.0]
    assert view["concentrator_amplification"] == 1.0
    assert view["magnet_drift_ppm_per_K"] == 0.0


def test_full_vector_manifest_validates():
    m = make_valid_manifest()
    m["bias_B0_T"] = 1.0e-3
    m["bias_direction_uvw"] = [1.0, 0.0, 0.0]
    m["concentrator_amplification"] = 25.0
    m["magnet_drift_ppm_per_K"] = 50.0
    validate_manifest(m)
    view = vector_readiness_view(m)
    assert view["bias_B0_T"] == 1.0e-3
    assert view["concentrator_amplification"] == 25.0


def test_vector_field_wrong_type_raises():
    m = make_valid_manifest()
    m["bias_B0_T"] = "1e-3"  # string instead of float
    with pytest.raises(ContractViolation, match="bias_B0_T.*expected float"):
        validate_manifest(m)


def test_bias_direction_wrong_length_raises():
    m = make_valid_manifest()
    m["bias_direction_uvw"] = [1.0, 0.0]
    with pytest.raises(ContractViolation, match="3 elements"):
        validate_manifest(m)


def test_bias_direction_non_unit_raises():
    m = make_valid_manifest()
    m["bias_direction_uvw"] = [1.0, 1.0, 0.0]  # |v| = sqrt(2) ≠ 1
    with pytest.raises(ContractViolation, match="unit-norm"):
        validate_manifest(m)
