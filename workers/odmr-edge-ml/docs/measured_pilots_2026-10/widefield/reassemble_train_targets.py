"""Reassemble a byte-preserving evidence archive outside its Git checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def reassemble(manifest, expected_manifest_sha256, destination):
    manifest = Path(manifest).resolve(strict=True)
    if digest(manifest) != expected_manifest_sha256:
        raise ValueError("Parts manifest hash mismatch")
    record = json.loads(manifest.read_text())
    if record["schema"] != "byte-preserving-archive-parts-v1":
        raise ValueError("Unsupported parts manifest")
    source = Path(__file__).resolve()
    checkout = next((p for p in source.parents if (p / ".git").exists()), None)
    if checkout is None:
        raise ValueError("Run this utility from its Git checkout")
    requested = Path(destination).expanduser().absolute()
    target = requested.parent.resolve(strict=True) / requested.name
    if target == checkout or checkout in target.parents:
        raise ValueError("Output must be outside the checkout")
    if target.exists() or target.is_symlink():
        raise FileExistsError("Output already exists")
    parts = record["parts"]
    if not parts or len({p["file"] for p in parts}) != len(parts):
        raise ValueError("Empty or duplicate parts")
    paths = []
    for part in parts:
        name = part["file"]
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Part names must be basenames")
        path = manifest.parent / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Part must be a regular, nonsymlink file")
        if not 0 < part["bytes"] < 8 * 1024 * 1024:
            raise ValueError("Invalid part size")
        if path.stat().st_size != part["bytes"] or digest(path) != part["sha256"]:
            raise ValueError("Part size or hash mismatch: " + name)
        paths.append(path)
    if sum(p["bytes"] for p in parts) != record["original_bytes"]:
        raise ValueError("Part byte counts do not match original")
    created = False
    try:
        with target.open("xb") as output:
            created = True
            for path in paths:
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        output.write(block)
            output.flush()
            os.fsync(output.fileno())
        if target.stat().st_size != record["original_bytes"]:
            raise ValueError("Reassembled byte count mismatch")
        if digest(target) != record["original_sha256"]:
            raise ValueError("Reassembled archive hash mismatch")
    except BaseException:
        if created:
            target.unlink(missing_ok=True)
        raise
    return {"status": "PASS", "bytes": record["original_bytes"],
            "sha256": record["original_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        result = reassemble(args.manifest, args.expected_manifest_sha256, args.out)
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, "Reassembly refused: " + str(error) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
