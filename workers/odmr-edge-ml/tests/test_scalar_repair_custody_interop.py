"""Exercise the custody CLI against the evaluator's actual authorization code."""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts import make_scalar_repair_partitions as generator
from scripts import scalar_repair_custody as custody

REPO = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get("SCALAR_REPAIR_CYCLE_SRC", REPO)) / "experiments/scalar_repair_cycle"
pytestmark = pytest.mark.skipif(not (SOURCE / "gates.py").is_file(),
                                reason="scalar evaluator source not available")


def cli(*args, success=True):
    result = subprocess.run([sys.executable, str(Path(custody.__file__)), *map(str, args)],
                            text=True, capture_output=True)
    assert (result.returncode == 0) == success, result.stderr
    return json.loads(result.stdout) if success else result.stderr


def expand_manufactured_partition(data_root, partition):
    """Expand a one-row test fixture to the registered count without another renderer run."""
    rows = {"val": 512, "final": 1024}[partition]
    dest = data_root / partition
    dest.chmod(0o755)
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["rows_per_cell"] = rows
    manifest["total_rows"] = 7 * rows
    manifest["field_ids"] = [f"{partition}-{i:04d}" for i in range(rows)]
    manifest["nuisance_group_ids"] = [f"{partition}-ou-{i:04d}" for i in range(rows)]
    manifest["sample_seeds"] = list(range(10000, 10000 + rows))
    manifest["noise_seeds"] = list(range(20000, 20000 + rows))
    manifest["nuisance_seeds"] = list(range(30000, 30000 + rows))
    manifest["nuisance_fields"] = [dict(manifest["nuisance_fields"][0],
        trajectory_seed=manifest["nuisance_seeds"][i],
        nuisance_group_id=manifest["nuisance_group_ids"][i]) for i in range(rows)]
    for entry in manifest["cells"].values():
        path = dest / entry["file"]
        with np.load(path, allow_pickle=False) as source:
            arrays = {key: np.repeat(source[key], rows, axis=0)
                      if key != "frequencies_hz" else source[key] for key in source.files}
        arrays["sample_seeds"] = np.asarray(manifest["sample_seeds"])
        arrays["noise_seeds"] = np.asarray(manifest["noise_seeds"])
        path.chmod(0o644)
        np.savez_compressed(path, **arrays)
        entry["rows"] = rows
        entry["sha256"] = custody.sha(path)
        path.chmod(0o444)
    manifest_path.chmod(0o644)
    manifest_path.write_text(json.dumps(manifest))
    manifest_path.chmod(0o444)
    dest.chmod(0o555)


def model_manifest(tmp_path, gates):
    items = []
    for seed in (42, 20261014, 20261015):
        checkpoint = tmp_path / f"model-{seed}.bin"
        export = tmp_path / f"model-{seed}.tflite"
        checkpoint.write_bytes(f"checkpoint-{seed}".encode())
        export.write_bytes(f"export-{seed}".encode())
        items.append({"arm": "C_direct", "seed": seed, "name": f"model-{seed}",
                      "checkpoint": str(checkpoint), "checkpoint_sha256": gates.sha(checkpoint),
                      "export": str(export), "export_sha256": gates.sha(export)})
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"candidates": items}))
    return path


def manufactured_decision_cells():
    """Fixed passing metrics; no held-out spectrum is scored by this test."""
    labels = ("robust_prior_fit", "conditional_likelihood", "edge_ols__int8", "joint_fit__int8")
    cells = {}
    for cell in ("clean", "realistic_anchor"):
        metrics, comparisons = {}, {}
        for index, label in enumerate(labels):
            metrics[label] = dict(mae_uT=10 + index, p90_abs_uT=20,
                                  hard_invalid_fraction=0.0, valid_fraction=.98,
                                  all_seeds_reliable=True, median_pipeline_seconds=.01)
            for baseline in ("training_mean", "training_median"):
                comparisons[f"{label}_minus_{baseline}"] = {"ci95_uT": [-2.0, -1.0]}
        cells[cell] = dict(decision_metrics=metrics, paired_comparisons=comparisons)
    return cells


def test_evaluator_authorizes_both_stages_and_rejects_substitutions(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SOURCE))
    gates = importlib.import_module("gates")
    decisions = importlib.import_module("decisions")
    runner = importlib.import_module("run_development")
    # The supplied evaluator export has no .git directory; its source commit is 041c3e5.
    if not (gates.ROOT / ".git").exists():
        original_check_output = gates.subprocess.check_output

        def exported_commit(command, **kwargs):
            if command == ["git", "-C", str(gates.ROOT), "rev-parse", "HEAD"]:
                return "041c3e5\n"
            return original_check_output(command, **kwargs)

        monkeypatch.setattr(gates.subprocess, "check_output", exported_commit)
    try:
        gates.versions()
    except importlib.metadata.PackageNotFoundError:
        # The custody fixture tests hashes and stage binding without numerical evaluation.
        monkeypatch.setattr(gates, "versions", lambda: {name: "fixture-unavailable"
                            for name in gates.DEPENDENCIES})
    monkeypatch.setattr(generator, "LEDGER", tmp_path / "generation-ledger.jsonl")
    monkeypatch.setattr(generator, "scan_used_seeds", lambda roots: (set(generator.EXCLUDED), []))
    monkeypatch.setattr(generator, "consumed_field_fingerprints", lambda roots: (set(), []))
    data_root = tmp_path / "data"
    generator.generate(data_root, "dev-r2", rows_override=1)
    dev_manifest = data_root / "dev-r2/manifest.json"
    dev_hash = custody.sha(dev_manifest)
    models = model_manifest(tmp_path, gates)
    first = tmp_path / "source-freeze-1.json"
    evaluation_root = tmp_path / "evaluation"
    first_hash = gates.create_freeze(1, first, models, evaluation_root=evaluation_root,
                                     development_manifest=dev_manifest,
                                     development_manifest_hash=dev_hash)
    assert json.loads(first.read_text())["development_manifest_sha256"] == dev_hash
    assert not (data_root / "val").exists()

    def custody_round_trip(partition, frozen):
        gate = tmp_path / ("FREEZE1.md" if partition == "val" else "FREEZE2.md")
        gate.write_text(f"Custodian reviewed manufactured fixture.\nfreeze_receipt_sha256: {custody.sha(frozen)}\n")
        common = ("--partition", partition, "--data-root", data_root,
                  "--gate-doc", gate, "--freeze-receipt", frozen)
        cli("check-gate", "--partition", partition, "--gate-doc", gate,
            "--freeze-receipt", frozen)
        generator.generate(data_root, partition, rows_override=1, gate_doc=gate)
        expand_manufactured_partition(data_root, partition)
        assert json.loads((data_root / partition / "manifest.json").read_text())["gate_document_sha256"] == custody.sha(gate)
        assert not ((data_root / partition).stat().st_mode & 0o222)
        access = (data_root / "exclusive-access-receipt.json" if partition == "final"
                  else tmp_path / "val-access.json")
        cli("access-receipt", *common, "--grantee", "Codex scalar evaluator", "--out", access)
        assert "already exists" in cli("access-receipt", *common, "--grantee", "repeat",
                                       "--out", access if partition == "final" else
                                       tmp_path / f"second-{partition}.json", success=False)
        released = tmp_path / f"release-{partition}.json"
        cli("release", *common, "--access-receipt", access, "--out", released)
        cli("verify-release", "--release", released)
        assert gates.authorize(data_root / partition, partition, frozen, custody.sha(frozen),
                               released, custody.sha(released), gate, access)["stage"] == (1 if partition == "val" else 2)

        wrong_gate = tmp_path / ("wrong/FREEZE1.md" if partition == "val" else "wrong/FREEZE2.md")
        wrong_gate.parent.mkdir(exist_ok=True)
        wrong_gate.write_text("freeze_receipt_sha256: " + "0" * 64 + "\n")
        assert "Gate document freeze hash mismatch" in cli("check-gate", "--partition", partition,
            "--gate-doc", wrong_gate, "--freeze-receipt", frozen, success=False)

        wrong_freeze = tmp_path / f"wrong-freeze-{partition}.json"
        wrong_freeze.write_text(json.dumps({"schema": 1, "stage": 2 if partition == "val" else 1}))
        assert "stage mismatch" in cli("check-gate", "--partition", partition,
            "--gate-doc", gate, "--freeze-receipt", wrong_freeze, success=False)

        original_access = access.read_bytes()
        altered = json.loads(original_access)
        altered["data_manifest_sha256"] = "0" * 64
        access.write_text(json.dumps(altered))
        assert "binding mismatch" in cli("verify-release", "--release", released, success=False)
        access.write_bytes(original_access)

        original_gate = gate.read_bytes()
        original_release = released.read_bytes()
        gate.write_text(original_gate.decode() + "Replacement approval.\n")
        replacement_release = json.loads(released.read_text())
        replacement_release["gate_document_sha256"] = custody.sha(gate)
        released.write_text(json.dumps(replacement_release))
        assert "manifest gate document mismatch" in cli("verify-release", "--release", released, success=False)
        gate.write_bytes(original_gate)
        released.write_bytes(original_release)
        return released

    val_release = custody_round_trip("val", first)
    summary = evaluation_root / "results-val/SUMMARY.json"
    second = tmp_path / "source-freeze-2.json"
    with pytest.raises(FileNotFoundError, match="SUMMARY.json"):
        gates.create_freeze(2, second, models, prior=first, prior_hash=first_hash,
                            validation=summary)
    assert not second.exists()

    manifest_hash = custody.sha(data_root / "val/manifest.json")
    evaluator_access = runner.reserve_evaluation(summary.parent, "val", manifest_hash,
                                                  first_hash, json.loads(first.read_text()))
    summary.parent.mkdir()
    cells = manufactured_decision_cells()
    selection = decisions.decide(cells)
    assert selection["can_proceed"]
    runner.dump(summary, dict(status="complete", partition="val", freeze_sha256=first_hash,
                              scope="manufactured scalar interop fixture", cells=cells, timing={},
                              selection=selection, validation_can_proceed=True,
                              final_decision=None, seconds=0.0, manifest_sha256=manifest_hash))
    with pytest.raises(FileNotFoundError, match="RECEIPT.json"):
        gates.create_freeze(2, second, models, prior=first, prior_hash=first_hash,
                            validation=summary)
    assert not second.exists()

    summary_hash = custody.sha(summary)
    receipt = dict(partition="val", freeze_sha256=first_hash,
                   custody_release_sha256=custody.sha(val_release), started_utc="manufactured",
                   manifest_sha256=manifest_hash,
                   model_records=json.loads(first.read_text())["model_records"],
                   scope="manufactured scalar interop fixture", warmup_manifest_sha256=dev_hash,
                   sources={p.name: gates.sha(p) for p in SOURCE.glob("*.py")},
                   status="complete", seconds=0.0, summary_sha256=summary_hash)
    runner.dump(summary.parent / "RECEIPT.json", receipt)
    runner.dump(evaluator_access, dict(json.loads(evaluator_access.read_text()),
                                       status="complete", summary_sha256=summary_hash))
    assert evaluator_access.name == "VAL_EVALUATOR_ACCESS.json"
    second_hash = gates.create_freeze(2, second, models, prior=first,
                                      prior_hash=first_hash, validation=summary)
    second_data = json.loads(second.read_text())
    assert second_data["parent_freeze_sha256"] == first_hash
    assert second_data["validation_summary_sha256"] == summary_hash
    assert second_data["validation_receipt_sha256"] == custody.sha(summary.parent / "RECEIPT.json")
    assert second_data["validation_access_sha256"] == custody.sha(evaluator_access)
    assert second_hash == custody.sha(second)
    custody_round_trip("final", second)
