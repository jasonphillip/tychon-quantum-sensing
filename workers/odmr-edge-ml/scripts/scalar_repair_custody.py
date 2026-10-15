#!/usr/bin/env python3
"""Verify sealed scalar partitions and issue hash-bound custody releases."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_scalar_repair_partitions import append_ledger, sha, verify, write_json

HEX = re.compile(r"[0-9a-f]{64}\Z")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def require_keys(value: dict, keys: set[str]) -> None:
    if set(value) != keys:
        raise RuntimeError(f"Schema mismatch: expected {sorted(keys)}")


def checked_receipt(path: Path, partition: str, manifest_sha: str,
                    gate_sha: str | None = None) -> dict:
    receipt = read_json(path)
    required = {"partition", "data_manifest_sha256", "approved"}
    if not required <= receipt.keys() or receipt["partition"] != partition or \
            receipt["data_manifest_sha256"] != manifest_sha or receipt["approved"] is not True:
        raise RuntimeError("Receipt partition, manifest, or approval mismatch")
    if gate_sha is not None and receipt.get("gate_document_sha256") != gate_sha:
        raise RuntimeError("Receipt gate document mismatch")
    return receipt


def access_receipt(data_root: Path, partition: str, grantee: str, out: Path) -> dict:
    if partition != "final" or not grantee.strip():
        raise RuntimeError("Final partition and nonempty grantee required")
    manifest_sha = verify(data_root, partition)["manifest_sha256"]
    marker = data_root / "exclusive-final-access.json"
    existing = [path for path in data_root.rglob("*receipt*.json")
                if path.is_file() and read_json(path).get("partition") == partition]
    if marker.exists() or out.exists() or existing:
        raise RuntimeError("Exclusive access receipt already exists")
    receipt = {"partition": partition, "data_manifest_sha256": manifest_sha,
               "grantee": grantee}
    if out.resolve() == marker.resolve():
        raise RuntimeError("Receipt output must differ from reservation marker")
    out.parent.mkdir(parents=True, exist_ok=True)
    with marker.open("x") as stream:
        stream.write(json.dumps(receipt, sort_keys=True) + "\n")
    try:
        with out.open("x") as stream:
            stream.write(json.dumps(receipt, sort_keys=True) + "\n")
    except BaseException:
        marker.unlink()
        raise
    return receipt


def release(partition: str, data_root: Path, gate_doc: Path, freeze_receipt: Path,
            out: Path, access: Path | None = None) -> dict:
    if partition not in {"val", "final"}:
        raise RuntimeError("Release partition must be val or final")
    expected_gate = "FREEZE1.md" if partition == "val" else "FREEZE2.md"
    if gate_doc.name != expected_gate or not gate_doc.is_file():
        raise RuntimeError(f"Expected {expected_gate}")
    if partition == "final" and access is None:
        raise RuntimeError("Final release requires exclusive access receipt")
    if partition == "val" and access is not None:
        raise RuntimeError("Validation release cannot have access receipt")
    manifest_sha = verify(data_root, partition)["manifest_sha256"]
    gate_sha = sha(gate_doc)
    checked_receipt(freeze_receipt, partition, manifest_sha, gate_sha)
    paths = {"data_root": os.path.relpath(data_root.resolve(), out.parent.resolve()),
             "gate_document": os.path.relpath(gate_doc.resolve(), out.parent.resolve()),
             "freeze_receipt": os.path.relpath(freeze_receipt.resolve(), out.parent.resolve())}
    value = {"partition": partition, "data_manifest_sha256": manifest_sha,
             "freeze_receipt_sha256": sha(freeze_receipt),
             "gate_document_sha256": gate_sha, "approved": True, "paths": paths}
    if access is not None:
        receipt = read_json(access)
        require_keys(receipt, {"partition", "data_manifest_sha256", "grantee"})
        if receipt["partition"] != "final" or receipt["data_manifest_sha256"] != manifest_sha:
            raise RuntimeError("Exclusive access receipt mismatch")
        marker = data_root / "exclusive-final-access.json"
        if not marker.is_file() or read_json(marker) != receipt:
            raise RuntimeError("Exclusive access reservation absent or mismatched")
        value["exclusive_access_receipt_sha256"] = sha(access)
        paths["access_receipt"] = os.path.relpath(access.resolve(), out.parent.resolve())
    if out.exists():
        raise RuntimeError("Release already exists")
    out.parent.mkdir(parents=True, exist_ok=True)
    write_json(out, value)
    verify_release(out)
    return value


def verify_release(path: Path) -> dict:
    value = read_json(path)
    partition = value.get("partition")
    if partition not in {"val", "final"}:
        raise RuntimeError("Invalid release partition")
    keys = {"partition", "data_manifest_sha256", "freeze_receipt_sha256",
            "gate_document_sha256", "approved", "paths"}
    path_keys = {"data_root", "gate_document", "freeze_receipt"}
    if partition == "final":
        keys.add("exclusive_access_receipt_sha256")
        path_keys.add("access_receipt")
    require_keys(value, keys)
    if value["approved"] is not True or any(not isinstance(value[k], str) or not HEX.fullmatch(value[k])
                                             for k in keys if k.endswith("_sha256")):
        raise RuntimeError("Invalid release hash or approval")
    paths = value["paths"]
    if not isinstance(paths, dict):
        raise RuntimeError("Invalid release paths")
    require_keys(paths, path_keys)
    if any(not isinstance(p, str) or not p for p in paths.values()):
        raise RuntimeError("Invalid release path")
    root = path.parent
    data_root = (root / paths["data_root"]).resolve()
    gate = (root / paths["gate_document"]).resolve()
    freeze = (root / paths["freeze_receipt"]).resolve()
    manifest_sha = verify(data_root, partition)["manifest_sha256"]
    if manifest_sha != value["data_manifest_sha256"] or sha(gate) != value["gate_document_sha256"] \
            or sha(freeze) != value["freeze_receipt_sha256"]:
        raise RuntimeError("Release hash mismatch")
    if gate.name != ("FREEZE1.md" if partition == "val" else "FREEZE2.md"):
        raise RuntimeError("Wrong gate document")
    checked_receipt(freeze, partition, manifest_sha, value["gate_document_sha256"])
    if partition == "final":
        access = (root / paths["access_receipt"]).resolve()
        if sha(access) != value["exclusive_access_receipt_sha256"]:
            raise RuntimeError("Access receipt hash mismatch")
        receipt = read_json(access)
        require_keys(receipt, {"partition", "data_manifest_sha256", "grantee"})
        if receipt["partition"] != partition or receipt["data_manifest_sha256"] != manifest_sha:
            raise RuntimeError("Access receipt partition or manifest mismatch")
        marker = read_json(data_root / "exclusive-final-access.json")
        if marker != receipt:
            raise RuntimeError("Access reservation mismatch")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    rel = sub.add_parser("release")
    rel.add_argument("--partition", choices=["val", "final"], required=True)
    rel.add_argument("--data-root", type=Path, required=True)
    rel.add_argument("--gate-doc", type=Path, required=True)
    rel.add_argument("--freeze-receipt", type=Path, required=True)
    rel.add_argument("--access-receipt", type=Path)
    rel.add_argument("--out", type=Path, required=True)
    acc = sub.add_parser("access-receipt")
    acc.add_argument("--data-root", type=Path, required=True)
    acc.add_argument("--partition", choices=["final"], required=True)
    acc.add_argument("--grantee", required=True)
    acc.add_argument("--out", type=Path, required=True)
    ver = sub.add_parser("verify-release")
    ver.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    started, cpu_started = time.monotonic(), time.process_time()
    value = None
    try:
        if args.command == "release":
            value = release(args.partition, args.data_root, args.gate_doc, args.freeze_receipt,
                            args.out, args.access_receipt)
        elif args.command == "access-receipt":
            value = access_receipt(args.data_root, args.partition, args.grantee, args.out)
        else:
            value = verify_release(args.release)
    finally:
        append_ledger("scalar_repair_custody_" + args.command.replace("-", "_"),
                      getattr(args, "partition", None), started, cpu_started, value is not None)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
