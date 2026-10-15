"""Exercise the custody CLI against the evaluator's actual authorization code."""
from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

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


def test_evaluator_authorizes_both_stages_and_rejects_substitutions(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(SOURCE))
    gates = importlib.import_module("gates")
    try:
        gates.versions()
    except importlib.metadata.PackageNotFoundError:
        # The custody fixture tests hashes and stage binding without numerical evaluation.
        monkeypatch.setattr(gates, "versions", lambda: {name: "fixture-unavailable"
                            for name in gates.DEPENDENCIES})
    monkeypatch.setattr(generator, "LEDGER", tmp_path / "generation-ledger.jsonl")
    data_root = tmp_path / "data"
    generator.generate(data_root, "dev-r2", rows_override=1)
    dev_metadata = json.loads((data_root / "dev-r2/manifest.json").read_text())
    dev_metadata["partition"] = "dev"
    dev_manifest = tmp_path / "development-manifest.json"
    dev_manifest.write_text(json.dumps(dev_metadata))
    models = model_manifest(tmp_path, gates)
    first = tmp_path / "source-freeze-1.json"
    first_hash = gates.create_freeze(1, first, models, evaluation_root=tmp_path / "evaluation",
                                     development_manifest=dev_manifest)
    summary = tmp_path / "validation-summary.json"
    summary.write_text(json.dumps({"partition": "val", "validation_can_proceed": True,
                                   "freeze_sha256": first_hash, "selection": {"candidate": "fixture"}}))
    second = tmp_path / "source-freeze-2.json"
    gates.create_freeze(2, second, models, prior=first, prior_hash=first_hash, validation=summary)

    for partition, frozen in (("val", first), ("final", second)):
        gate = tmp_path / ("FREEZE1.md" if partition == "val" else "FREEZE2.md")
        gate.write_text(f"Custodian reviewed manufactured fixture.\nfreeze_receipt_sha256: {custody.sha(frozen)}\n")
        common = ("--partition", partition, "--data-root", data_root,
                  "--gate-doc", gate, "--freeze-receipt", frozen)
        cli("check-gate", "--partition", partition, "--gate-doc", gate,
            "--freeze-receipt", frozen)
        generator.generate(data_root, partition, rows_override=1, gate_doc=gate)
        access = (data_root / "exclusive-access-receipt.json" if partition == "final"
                  else tmp_path / "val-access.json")
        cli("access-receipt", *common, "--grantee", "Codex scalar evaluator", "--out", access)
        assert "already exists" in cli("access-receipt", *common, "--grantee", "repeat",
                                       "--out", tmp_path / f"second-{partition}.json", success=False)
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
        gate.write_text(original_gate.decode() + "Replacement approval.\n")
        replacement_release = json.loads(released.read_text())
        replacement_release["gate_document_sha256"] = custody.sha(gate)
        released.write_text(json.dumps(replacement_release))
        assert "manifest gate document mismatch" in cli("verify-release", "--release", released, success=False)
        gate.write_bytes(original_gate)
