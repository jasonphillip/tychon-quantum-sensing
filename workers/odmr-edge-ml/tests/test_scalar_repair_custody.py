"""Custody release binding and exclusive-access checks."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts import scalar_repair_custody as custody


def sealed_partition(tmp_path, partition):
    root = tmp_path / "data"
    dest = root / partition
    dest.mkdir(parents=True)
    cells = {}
    for name in custody.verify.__globals__["CELLS"]:
        path = dest / f"{name}.npz"
        np.savez_compressed(path, spectra=np.ones((1, 100)),
                            truth_vectors_T=np.zeros((1, 3)), sample_seeds=[17])
        cells[name] = {"file": path.name, "sha256": custody.sha(path), "rows": 1}
        path.chmod(0o444)
    custody.write_json(dest / "manifest.json", {
        "partition": partition, "cells": cells, "rows_per_cell": 1,
        "field_ids": [f"{partition}-0"], "nuisance_group_ids": [f"{partition}-ou-0"],
        "sample_seeds": [17], "noise_seeds": [18], "nuisance_seeds": [19]})
    (dest / "manifest.json").chmod(0o444)
    dest.chmod(0o555)
    return root


def freeze(tmp_path, root, partition):
    gate = tmp_path / ("FREEZE1.md" if partition == "val" else "FREEZE2.md")
    gate.write_text("frozen\n")
    receipt = tmp_path / "freeze.json"
    custody.write_json(receipt, {"partition": partition,
                                  "data_manifest_sha256": custody.verify(root, partition)["manifest_sha256"],
                                  "gate_document_sha256": custody.sha(gate), "approved": True})
    return gate, receipt


def test_validation_release_rechecks_all_hashes(tmp_path):
    root = sealed_partition(tmp_path, "val")
    gate, receipt = freeze(tmp_path, root, "val")
    out = tmp_path / "release.json"
    custody.release("val", root, gate, receipt, out)
    assert custody.verify_release(out)["partition"] == "val"
    (root / "val/manifest.json").chmod(0o644)
    with (root / "val/manifest.json").open("a") as stream:
        stream.write(" ")
    (root / "val/manifest.json").chmod(0o444)
    with pytest.raises(RuntimeError, match="Release hash mismatch"):
        custody.verify_release(out)


def test_release_cli_round_trip(tmp_path):
    root = sealed_partition(tmp_path, "val")
    gate, receipt = freeze(tmp_path, root, "val")
    out = tmp_path / "release.json"
    script = Path(custody.__file__)
    issued = subprocess.run([sys.executable, str(script), "release", "--partition", "val",
                             "--data-root", str(root), "--gate-doc", str(gate),
                             "--freeze-receipt", str(receipt), "--out", str(out)],
                            check=True, text=True, capture_output=True)
    checked = subprocess.run([sys.executable, str(script), "verify-release", "--release", str(out)],
                             check=True, text=True, capture_output=True)
    assert json.loads(issued.stdout) == json.loads(checked.stdout)


def test_wrong_partition_receipt_rejected(tmp_path):
    root = sealed_partition(tmp_path, "val")
    gate, receipt = freeze(tmp_path, root, "val")
    value = json.loads(receipt.read_text())
    value["partition"] = "final"
    custody.write_json(receipt, value)
    with pytest.raises(RuntimeError, match="Receipt partition"):
        custody.release("val", root, gate, receipt, tmp_path / "release.json")


def test_final_requires_one_exclusive_receipt(tmp_path):
    root = sealed_partition(tmp_path, "final")
    gate, receipt = freeze(tmp_path, root, "final")
    out = tmp_path / "release.json"
    with pytest.raises(RuntimeError, match="requires exclusive"):
        custody.release("final", root, gate, receipt, out)
    access = tmp_path / "access.json"
    issued = subprocess.run([sys.executable, str(Path(custody.__file__)), "access-receipt",
                             "--data-root", str(root), "--partition", "final",
                             "--grantee", "campaign-1", "--out", str(access)],
                            check=True, text=True, capture_output=True)
    assert json.loads(issued.stdout) == json.loads(access.read_text())
    with pytest.raises(RuntimeError, match="already exists"):
        custody.access_receipt(root, "final", "campaign-2", tmp_path / "second.json")
    custody.release("final", root, gate, receipt, out, access)
    assert custody.verify_release(out)["exclusive_access_receipt_sha256"] == custody.sha(access)
    access.write_text(access.read_text() + " ")
    with pytest.raises(RuntimeError, match="Access receipt hash mismatch"):
        custody.verify_release(out)
