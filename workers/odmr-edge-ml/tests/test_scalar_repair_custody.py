"""Custody release binding and atomic access checks using manufactured spectra."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from scripts import scalar_repair_custody as custody


def fixture(tmp_path, partition, rows_override=None):
    root = tmp_path / "data"
    dest = root / partition
    dest.mkdir(parents=True)
    rows = rows_override or {"val": 512, "final": 1024}[partition]
    seeds = np.arange(17, 17 + rows)
    cells = {}
    for name in custody.verify.__globals__["CELLS"]:
        path = dest / f"{name}.npz"
        np.savez_compressed(path, spectra=np.zeros((rows, 100)),
                            truth_vectors_T=np.zeros((rows, 3)), sample_seeds=seeds)
        cells[name] = {"file": path.name, "sha256": custody.sha(path), "rows": rows}
        path.chmod(0o444)
    frozen = tmp_path / "source-freeze.json"
    frozen.write_text(json.dumps({"schema": 1, "stage": 1 if partition == "val" else 2}))
    gate = tmp_path / ("FREEZE1.md" if partition == "val" else "FREEZE2.md")
    gate.write_text(f"approved\nfreeze_receipt_sha256: {custody.sha(frozen)}\n")
    custody.verify.__globals__["write_json"](dest / "manifest.json", {
        "partition": partition, "cells": cells, "rows_per_cell": rows,
        "field_ids": [f"{partition}-{i}" for i in range(rows)],
        "nuisance_group_ids": [f"{partition}-ou-{i}" for i in range(rows)],
        "sample_seeds": seeds.tolist(), "noise_seeds": (seeds + rows).tolist(),
        "nuisance_seeds": (seeds + 2 * rows).tolist(),
        "gate_document_sha256": custody.sha(gate)})
    (dest / "manifest.json").chmod(0o444)
    dest.chmod(0o555)
    return root, gate, frozen


def cli(*args, success=True):
    result = subprocess.run([sys.executable, str(Path(custody.__file__)), *map(str, args)],
                            text=True, capture_output=True)
    assert (result.returncode == 0) == success, result.stderr
    return json.loads(result.stdout) if success else result.stderr


@pytest.mark.parametrize("partition", ["val", "final"])
def test_cli_round_trip_and_repeat_access(tmp_path, partition):
    root, gate, frozen = fixture(tmp_path, partition)
    assert cli("check-gate", "--partition", partition, "--gate-doc", gate,
               "--freeze-receipt", frozen)["gate_document_sha256"] == custody.sha(gate)
    access = root / "exclusive-access-receipt.json" if partition == "final" else tmp_path / "val-access.json"
    common = ("--partition", partition, "--data-root", root, "--gate-doc", gate,
              "--freeze-receipt", frozen)
    value = cli("access-receipt", *common, "--grantee", "Codex scalar evaluator", "--out", access)
    assert set(value) == custody.ACCESS_KEYS
    assert value["freeze_receipt_sha256"] == custody.sha(frozen)
    assert "already exists" in cli("access-receipt", *common, "--grantee", "second",
                                   "--out", access, success=False)
    release = tmp_path / "release.json"
    issued = cli("release", *common, "--access-receipt", access, "--out", release)
    assert set(issued) == custody.RELEASE_KEYS | {"paths"}
    assert cli("verify-release", "--release", release) == issued
    manifest = root / partition / "manifest.json"
    manifest.chmod(0o644)
    manifest.write_text(manifest.read_text() + " ")
    manifest.chmod(0o444)
    assert "Exclusive access receipt binding mismatch" in cli("verify-release", "--release", release, success=False)


def test_gate_stage_and_replacement_rejected(tmp_path):
    root, gate, frozen = fixture(tmp_path, "val")
    assert custody.check_gate("val", gate, frozen) == custody.sha(gate)
    wrong = tmp_path / "wrong.json"
    wrong.write_text(json.dumps({"schema": 1, "stage": 2}))
    with pytest.raises(RuntimeError, match="stage"):
        custody.check_gate("val", gate, wrong)
    gate.write_text(f"replacement\nfreeze_receipt_sha256: {custody.sha(frozen)}\n")
    with pytest.raises(RuntimeError, match="manifest gate"):
        custody.access_receipt(root, "val", "evaluator", tmp_path / "access.json", gate, frozen)


def test_access_binding_rechecked(tmp_path):
    root, gate, frozen = fixture(tmp_path, "val")
    access = tmp_path / "access.json"
    custody.access_receipt(root, "val", "evaluator", access, gate, frozen)
    value = json.loads(access.read_text())
    value["data_manifest_sha256"] = "0" * 64
    access.write_text(json.dumps(value))
    with pytest.raises(RuntimeError, match="binding"):
        custody.release("val", root, gate, frozen, tmp_path / "release.json", access)


@pytest.mark.parametrize("partition", ["val", "final"])
def test_self_consistent_one_row_partition_is_rejected(tmp_path, partition):
    root, gate, frozen = fixture(tmp_path, partition, rows_override=1)
    out = root / "exclusive-access-receipt.json" if partition == "final" else tmp_path / "access.json"
    with pytest.raises(RuntimeError, match="Registered partition row count mismatch"):
        custody.access_receipt(root, partition, "evaluator", out, gate, frozen)
    assert not out.exists()


def test_failed_output_publish_can_retry_only_same_receipt(tmp_path, monkeypatch):
    root, gate, frozen = fixture(tmp_path, "val")
    out = tmp_path / "access.json"
    link = custody.os.link

    def fail_output(source, destination):
        if Path(destination) == out:
            raise OSError("injected receipt write failure")
        return link(source, destination)

    monkeypatch.setattr(custody.os, "link", fail_output)
    with pytest.raises(OSError, match="injected"):
        custody.access_receipt(root, "val", "evaluator", out, gate, frozen)
    assert (root / "exclusive-val-access-reservation.json").exists()
    assert not out.exists()
    monkeypatch.setattr(custody.os, "link", link)
    with pytest.raises(RuntimeError, match="already exists"):
        custody.access_receipt(root, "val", "different", out, gate, frozen)
    value = custody.access_receipt(root, "val", "evaluator", out, gate, frozen)
    assert json.loads(out.read_text()) == value
