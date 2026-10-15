"""Manufactured fixtures only. Execution requires campaign fixture approval."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from experiments.measured_localisation import bundle, metrics, partition, verify_saved
from experiments.measured_localisation.guard import PACKAGE, authorize, sha256


def test_draft_approval_fails_before_numerics(tmp_path):
    path = tmp_path / "approval.json"
    path.write_text('{"status":"DRAFT"}')
    with pytest.raises(RuntimeError, match="not approved"):
        authorize(path, "develop")


def test_header_inspection_rejects_object_dtype(tmp_path):
    path = tmp_path / "unsafe.npy"
    np.save(path, np.array([{}], dtype=object))
    with pytest.raises(ValueError, match="object"):
        bundle.npy_header(path)


def test_payload_cannot_escape_bundle(tmp_path):
    with pytest.raises(ValueError, match="relative"):
        bundle.checked_path(tmp_path, {"path": "../outside.npy", "sha256": "0" * 64})


def test_positions_route_never_requires_feature_files(tmp_path):
    template = json.loads((PACKAGE / "bundle.example.json").read_text())
    np.save(tmp_path / "position_x.npy", np.array(["1305.0", "1325.0"]))
    np.save(tmp_path / "position_y.npy", np.array(["1200.0", "1220.0"]))
    (tmp_path / "sample_ids.json").write_text('["measurement_0000", "measurement_0001"]')
    for key in ("position_x", "position_y", "sample_ids"):
        template[key]["sha256"] = sha256(tmp_path / template[key]["path"])
    template["extraction_source_sha256"] = "0" * 64
    template["source_row_alignment_status"] = "published_version_A_pairs_raw_lineage_unresolved"
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(template))
    values, _, metadata = bundle.positions_only(path)
    assert values.tolist() == [[1305., 1200.], [1325., 1220.]]
    assert metadata["signal_values_inspected"] is False
    assert not (tmp_path / "fit_parameters.npy").exists()


def test_declared_width_parameter_counts():
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    assert [c["hidden"] for c in protocol["candidate_grid"]] == [24, 48, 96]
    for config in protocol["candidate_grid"]:
        width = config["hidden"]
        assert 24 * width + width + width * 2 + 2 == config["parameters"]
        assert config["device"] == "cuda"


def test_native_adapter_selects_rows_and_converts_ghz(tmp_path):
    parameters = np.zeros((2, 8, 6))
    deviations = np.ones((2, 8, 6)) * 0.002
    # The unselected row is invalid. It must not enter feature validation.
    parameters[0] = np.nan
    parameters[1, :, 1] = 2.85
    parameters[1, :, 4] = 2.89
    deviations[1, :, 4] = 0.003
    np.save(tmp_path / "p.npy", parameters)
    np.save(tmp_path / "s.npy", deviations)
    manifest = {"fit_parameters": {"path": "p.npy", "sha256": sha256(tmp_path / "p.npy")},
                "fit_standard_deviations": {"path": "s.npy", "sha256": sha256(tmp_path / "s.npy")}}
    with patch.object(bundle, "inspect_bundle", return_value=(manifest, {})):
        with patch.object(bundle, "positions_only", return_value=(np.array([[0., 0.], [1., 2.]]), manifest, {})):
            x, y, _, _ = bundle.arrays(tmp_path / "manifest.json", [1])
    np.testing.assert_allclose(x.reshape(8, 3), np.tile([40., 2., 3.], (8, 1)))
    assert y.tolist() == [[1., 2.]]


def test_geometric_gaps_and_total_label_accounting():
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    # Whole repeated positions must stay together, even in manufactured data.
    positions = np.array([[x + .5, y + .5] for x in range(12) for y in range(12) for _ in range(4)])
    manifest = {"operating_bounds_um": [[0, 12], [0, 12]]}
    protocol["partition"]["acquisition_policy"] = "spatial_within_represented_sessions_disclose_possible_overlap"
    with patch.object(partition, "positions_only", return_value=(positions, manifest, {"manifest_sha256": "fixture"})):
        with patch.object(partition, "possible_sessions", return_value=[["session01"] for _ in positions]):
            with patch.object(partition, "supplied_position_summary", return_value={"fixture": True}):
                result = partition.make_partition("unused", protocol, "fixture-only-salt")
    train, valid, test = [set(result[name]) for name in ("train", "validation", "test")]
    assert not train & valid and not train & test and not valid & test
    assert result["small_label_budget"] == (len(train) + len(valid)) // 4
    assert result["full_label_budget"] == (len(result["full_train"]) + len(valid)) // 4
    assert result["small_measurement_rows"] == len(train) + len(valid)
    assert result["possible_session_overlap"]["full_train__test"] == ["session01"]
    for i in result["full_train"]:
        for j in valid | test:
            assert np.max(np.abs(np.floor(positions[i]) - np.floor(positions[j]))) > 1
    for indices in (train, valid, test):
        for i in indices:
            duplicates = set(np.flatnonzero((positions == positions[i]).all(1)))
            assert duplicates <= indices
    assert result["test_signal_values_accessed"] is False


def test_overlap_is_rejected():
    invalid = {"train": [0], "full_train": [0], "validation": [1], "test": [0],
               "spatial_groups": ["a", "b"], "status": "qualified"}
    with pytest.raises(ValueError, match="overlap"):
        partition.validate_partition(invalid, 2)


def fixture_outputs():
    labels = np.column_stack((np.arange(64), np.zeros(64)))
    offset = np.column_stack((np.ones(64), np.zeros(64)))
    candidate = labels + offset
    classical = labels + offset * 2
    full = labels + offset * 1.5
    groups = np.array([str(i // 8) for i in range(64)])
    return labels, candidate, classical, full, groups


def test_success_and_perfect_reference_rules():
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    labels, candidate, classical, full, groups = fixture_outputs()
    result = metrics.evaluate_saved(labels, candidate, classical, full, groups, protocol, 10, 100, 17)
    assert result["gate_passed"] is True
    perfect_candidate = metrics.evaluate_saved(labels, labels, classical, full, groups, protocol, 10, 100, 17)
    assert perfect_candidate["gate_passed"] is True
    perfect_reference = metrics.evaluate_saved(labels, candidate, labels, full, groups, protocol, 10, 100, 17)
    assert perfect_reference["gate_passed"] is False
    assert perfect_reference["candidate_to_classical_mean_ratio"] is None


def test_nonfinite_prediction_cannot_disappear():
    with pytest.raises(ValueError, match="nonfinite"):
        metrics.errors(np.array([[np.nan, 0.]]), np.zeros((1, 2)))


def test_saved_public_recomputation(tmp_path):
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    labels, candidate, classical, full, groups = fixture_outputs()
    result = metrics.evaluate_saved(labels, candidate, classical, full, groups, protocol, 10, 100, 17)
    np.savez(tmp_path / "predictions.npz", labels_um=labels, candidate_um=candidate,
             classical_small_um=classical, classical_full_um=full, spatial_groups=groups,
             valid=np.ones(64, dtype=bool), row_indices=np.arange(64))
    for name, value in {"metrics.json": result, "protocol.json": protocol,
                        "verification.json": {"stage": "held_group", "confidence": True,
                        "prediction_file": "predictions.npz", "bootstrap_seed": 17,
                        "expected_row_indices": list(range(64)),
                        "small_label_budget": 10, "full_label_budget": 100}}.items():
        (tmp_path / name).write_text(json.dumps(value))
    manifest = {"files": {p.name: sha256(p) for p in tmp_path.iterdir()},
                "source_sha256": {str(p.relative_to(PACKAGE)): sha256(p) for p in PACKAGE.rglob("*.py")}}
    manifest["source_sha256"]["protocol.json"] = sha256(PACKAGE / "protocol.json")
    (tmp_path / "artifact_manifest.json").write_text(json.dumps(manifest))
    assert verify_saved.main(["--artifact", str(tmp_path)]) == 0
    # Mutation after hashing must fail before recomputation.
    (tmp_path / "metrics.json").write_text('{}')
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_saved.main(["--artifact", str(tmp_path)])
