#!/usr/bin/env python3
"""Check source freezes and issue hash-bound scalar custody artifacts."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_scalar_repair_partitions import append_ledger, sha, verify

HEX = re.compile(r"[0-9a-f]{64}\Z")
GATE_LINE = re.compile(r"^freeze_receipt_sha256: ([0-9a-f]{64})$", re.MULTILINE)
ACCESS_KEYS = {"schema", "partition", "data_manifest_sha256", "freeze_receipt_sha256", "status", "grantee"}
RELEASE_KEYS = {"schema", "partition", "approved", "data_manifest_sha256", "freeze_receipt_sha256",
                "gate_document_sha256", "exclusive_access_receipt_sha256"}
PATH_KEYS = {"data_root", "gate_document", "freeze_receipt", "access_receipt"}


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON object required: {path}")
    return value


def require_keys(value: dict, keys: set[str]) -> None:
    if set(value) != keys:
        raise RuntimeError(f"Schema mismatch: expected {sorted(keys)}")


def require_hash(value: object) -> None:
    if not isinstance(value, str) or not HEX.fullmatch(value):
        raise RuntimeError("Invalid SHA256 hash")


def check_gate(partition: str, gate_doc: Path, freeze_receipt: Path) -> str:
    if partition not in {"val", "final"}:
        raise RuntimeError("Gate partition must be val or final")
    expected = "FREEZE1.md" if partition == "val" else "FREEZE2.md"
    if gate_doc.name != expected or gate_doc.is_symlink() or freeze_receipt.is_symlink():
        raise RuntimeError(f"Expected unsymlinked {expected} and source freeze")
    frozen = read_json(freeze_receipt)
    if type(frozen.get("schema")) is not int or frozen["schema"] != 1 or \
            type(frozen.get("stage")) is not int or frozen["stage"] != (1 if partition == "val" else 2):
        raise RuntimeError("Source freeze schema or stage mismatch")
    matches = GATE_LINE.findall(gate_doc.read_text())
    if len(matches) != 1 or matches[0] != sha(freeze_receipt):
        raise RuntimeError("Gate document freeze hash mismatch")
    return sha(gate_doc)


def checked_partition(data_root: Path, partition: str, gate_doc: Path, freeze_receipt: Path) -> tuple[str, str, str]:
    manifest_sha = verify(data_root, partition)["manifest_sha256"]
    gate_sha = check_gate(partition, gate_doc, freeze_receipt)
    manifest = read_json(data_root / partition / "manifest.json")
    if manifest.get("gate_document_sha256") != gate_sha:
        raise RuntimeError("Generated manifest gate document mismatch")
    return manifest_sha, gate_sha, sha(freeze_receipt)


def reservation(data_root: Path, partition: str) -> Path:
    return (data_root / "exclusive-access-receipt.json" if partition == "final"
            else data_root / "exclusive-val-access-reservation.json")


def checked_access(path: Path, data_root: Path, partition: str, manifest_sha: str, freeze_sha: str) -> dict:
    if path.is_symlink():
        raise RuntimeError("Symlinked access receipt")
    value = read_json(path)
    require_keys(value, ACCESS_KEYS)
    if type(value["schema"]) is not int or value["schema"] != 1 or value["partition"] != partition or \
            value["data_manifest_sha256"] != manifest_sha or value["freeze_receipt_sha256"] != freeze_sha or \
            value["status"] != "authorized" or not isinstance(value["grantee"], str) or not value["grantee"].strip():
        raise RuntimeError("Exclusive access receipt binding mismatch")
    marker = reservation(data_root, partition)
    if partition == "final" and path.resolve() != marker.resolve():
        raise RuntimeError("Final receipt must be the data-root exclusive receipt")
    if read_json(marker) != value:
        raise RuntimeError("Exclusive access reservation mismatch")
    return value


def access_receipt(data_root: Path, partition: str, grantee: str, out: Path,
                   gate_doc: Path, freeze_receipt: Path) -> dict:
    if not grantee.strip():
        raise RuntimeError("Nonempty grantee required")
    manifest_sha, _, freeze_sha = checked_partition(data_root, partition, gate_doc, freeze_receipt)
    marker = reservation(data_root, partition)
    if out.exists() or marker.exists():
        raise RuntimeError("Exclusive access receipt already exists")
    if partition == "final" and out.resolve() != marker.resolve():
        raise RuntimeError("Final receipt must be the data-root exclusive receipt")
    if partition == "val" and out.resolve() == marker.resolve():
        raise RuntimeError("Validation receipt needs a separate explicit output")
    value = {"schema": 1, "partition": partition, "data_manifest_sha256": manifest_sha,
             "freeze_receipt_sha256": freeze_sha, "status": "authorized", "grantee": grantee}
    out.parent.mkdir(parents=True, exist_ok=True)
    data_root.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, sort_keys=True) + "\n"
    with marker.open("x") as stream:  # Atomic per-partition reservation.
        stream.write(payload)
    if out.resolve() != marker.resolve():
        with out.open("x") as stream:
            stream.write(payload)
    return value


def release(partition: str, data_root: Path, gate_doc: Path, freeze_receipt: Path,
            out: Path, access: Path) -> dict:
    manifest_sha, gate_sha, freeze_sha = checked_partition(data_root, partition, gate_doc, freeze_receipt)
    checked_access(access, data_root, partition, manifest_sha, freeze_sha)
    paths = {"data_root": os.path.relpath(data_root.resolve(), out.parent.resolve()),
             "gate_document": os.path.relpath(gate_doc.resolve(), out.parent.resolve()),
             "freeze_receipt": os.path.relpath(freeze_receipt.resolve(), out.parent.resolve()),
             "access_receipt": os.path.relpath(access.resolve(), out.parent.resolve())}
    value = {"schema": 1, "partition": partition, "approved": True,
             "data_manifest_sha256": manifest_sha, "freeze_receipt_sha256": freeze_sha,
             "gate_document_sha256": gate_sha, "exclusive_access_receipt_sha256": sha(access),
             "paths": paths}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")
    verify_release(out)
    return value


def verify_release(path: Path, data_root: Path | None = None, gate_doc: Path | None = None,
                   freeze_receipt: Path | None = None, access: Path | None = None) -> dict:
    value = read_json(path)
    require_keys(value, RELEASE_KEYS | ({"paths"} if "paths" in value else set()))
    partition = value["partition"]
    if type(value["schema"]) is not int or value["schema"] != 1 or partition not in {"val", "final"} or value["approved"] is not True:
        raise RuntimeError("Invalid release schema, partition, or approval")
    for key in RELEASE_KEYS:
        if key.endswith("_sha256"):
            require_hash(value[key])
    if "paths" in value:
        paths = value["paths"]
        if not isinstance(paths, dict):
            raise RuntimeError("Invalid release paths")
        require_keys(paths, PATH_KEYS)
        if any(not isinstance(p, str) or not p or Path(p).is_absolute() for p in paths.values()):
            raise RuntimeError("Release paths must be relative")
        data_root, gate_doc, freeze_receipt, access = (
            (path.parent / paths[k]).resolve() for k in ("data_root", "gate_document", "freeze_receipt", "access_receipt"))
    if any(item is None for item in (data_root, gate_doc, freeze_receipt, access)):
        raise RuntimeError("Release verification needs custody artifact paths")
    manifest_sha, gate_sha, freeze_sha = checked_partition(data_root, partition, gate_doc, freeze_receipt)
    checked_access(access, data_root, partition, manifest_sha, freeze_sha)
    expected = {"data_manifest_sha256": manifest_sha, "freeze_receipt_sha256": freeze_sha,
                "gate_document_sha256": gate_sha, "exclusive_access_receipt_sha256": sha(access)}
    if any(value[k] != v for k, v in expected.items()):
        raise RuntimeError("Release hash mismatch")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gate = sub.add_parser("check-gate")
    gate.add_argument("--partition", choices=["val", "final"], required=True)
    gate.add_argument("--gate-doc", type=Path, required=True)
    gate.add_argument("--freeze-receipt", type=Path, required=True)
    acc = sub.add_parser("access-receipt")
    acc.add_argument("--partition", choices=["val", "final"], required=True)
    acc.add_argument("--data-root", type=Path, required=True)
    acc.add_argument("--gate-doc", type=Path, required=True)
    acc.add_argument("--freeze-receipt", type=Path, required=True)
    acc.add_argument("--grantee", required=True)
    acc.add_argument("--out", type=Path, required=True)
    rel = sub.add_parser("release")
    rel.add_argument("--partition", choices=["val", "final"], required=True)
    rel.add_argument("--data-root", type=Path, required=True)
    rel.add_argument("--gate-doc", type=Path, required=True)
    rel.add_argument("--freeze-receipt", type=Path, required=True)
    rel.add_argument("--access-receipt", type=Path, required=True)
    rel.add_argument("--out", type=Path, required=True)
    ver = sub.add_parser("verify-release")
    ver.add_argument("--release", type=Path, required=True)
    ver.add_argument("--data-root", type=Path)
    ver.add_argument("--gate-doc", type=Path)
    ver.add_argument("--freeze-receipt", type=Path)
    ver.add_argument("--access-receipt", type=Path)
    args = parser.parse_args()
    started, cpu_started = time.monotonic(), time.process_time()
    value = None
    try:
        if args.command == "check-gate":
            value = {"gate_document_sha256": check_gate(args.partition, args.gate_doc, args.freeze_receipt)}
        elif args.command == "access-receipt":
            value = access_receipt(args.data_root, args.partition, args.grantee, args.out,
                                   args.gate_doc, args.freeze_receipt)
        elif args.command == "release":
            value = release(args.partition, args.data_root, args.gate_doc, args.freeze_receipt,
                            args.out, args.access_receipt)
        else:
            value = verify_release(args.release, args.data_root, args.gate_doc,
                                   args.freeze_receipt, args.access_receipt)
    finally:
        append_ledger("scalar_repair_custody_" + args.command.replace("-", "_"),
                      getattr(args, "partition", None), started, cpu_started, value is not None)
    print(json.dumps(value, sort_keys=True))


if __name__ == "__main__":
    main()
