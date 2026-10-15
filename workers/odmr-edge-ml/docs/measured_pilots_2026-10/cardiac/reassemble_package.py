"""Restore exact cardiac evidence bytes outside the checkout using only the standard library."""
import argparse
import json
from pathlib import Path
import shutil
from reassemble_archive import digest, reassemble


def contained(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Evidence paths must stay inside the package")
    path = root / relative
    if path.is_symlink() or not path.is_file() or root not in path.resolve().parents:
        raise ValueError("Evidence must be a regular file inside the package")
    return path


def restore(package, expected_manifest_sha256, destination):
    package = Path(package).resolve(strict=True)
    manifest = contained(package, "artifact-manifest.json")
    if digest(manifest) != expected_manifest_sha256:
        raise ValueError("Package manifest hash mismatch")
    record = json.loads(manifest.read_text())
    if record["schema"] != "cardiac-evidence-publication-manifest-v1" or record["status"] == "SKELETON_NOT_EVIDENCE":
        raise ValueError("Completed evidence manifest required")
    checkout = next((p for p in package.parents if (p / ".git").exists()), None)
    if checkout is None:
        raise ValueError("Run from the public Git checkout")
    requested = Path(destination).expanduser().absolute()
    target = requested.parent.resolve(strict=True) / requested.name
    if target == checkout or checkout in target.parents:
        raise ValueError("Evidence output must be outside the checkout")
    target.mkdir(exist_ok=False)
    names = set()
    for item in record["published_artifacts"]:
        name = item["original_file"]
        if Path(name).name != name or name in names or name in (".", ".."):
            raise ValueError("Original artifact names must be unique basenames")
        names.add(name)
        output = target / name
        if item["storage"] == "direct":
            source = contained(package, item["public_file"])
            if source.stat().st_size != item["original_bytes"] or digest(source) != item["original_sha256"]:
                raise ValueError("Direct artifact hash or byte count mismatch")
            with output.open("xb") as stream, source.open("rb") as original:
                shutil.copyfileobj(original, stream, 1024 * 1024)
        elif item["storage"] == "byte_parts":
            parts = contained(package, item["parts_manifest"])
            reassemble(parts, item["parts_manifest_sha256"], output)
        else:
            raise ValueError("Unknown artifact storage kind")
        if output.stat().st_size != item["original_bytes"] or digest(output) != item["original_sha256"]:
            raise ValueError("Restored artifact does not equal the immutable original")
    if digest(target / "summary.json") != record["original_summary_sha256"]:
        raise ValueError("Original run summary identity mismatch")
    return {"status": "PASS", "restored_artifacts": len(names), "summary_sha256": record["original_summary_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    result = restore(args.package, args.expected_manifest_sha256, args.out)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
