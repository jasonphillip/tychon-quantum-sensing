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


def test_geometric_gaps_and_total_label_accounting():
    protocol = json.loads((PACKAGE / "protocol.json").read_text())
    # Whole repeated positions must stay together, even in manufactured data.
    positions = np.array([[x + .5, y + .5] for x in range(12) for y in range(12) for _ in range(4)])
    manifest = {"operating_bounds_um": [[0, 12], [0, 12]]}
    with patch.object(partition, "arrays", return_value=(None, positions, manifest, {"manifest_sha256": "fixture"})):
        result = partition.make_partition("unused", protocol, "fixture-only-salt")
    train, valid, test = [set(result[name]) for name in ("train", "validation", "test")]
    assert not train & valid and not train & test and not valid & test
    assert result["small_label_budget"] == len(train) + len(valid)
    assert result["full_label_budget"] == len(result["full_train"]) + len(valid)
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
    labels = np.zeros((64, 2))
    candidate = np.column_stack((np.ones(64), np.zeros(64)))
    classical = candidate * 2
    full = candidate * 1.5
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
