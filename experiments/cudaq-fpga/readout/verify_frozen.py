"""Verify published frozen bytes and replay integer scores without regenerating data."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    source_map = json.loads((ROOT / "SOURCE_MAP.json").read_text())
    for name, item in source_map["files"].items():
        if digest(ROOT / name) != item["public_sha256"]:
            raise RuntimeError(f"published file hash mismatch: {name}")
    pack = ROOT / "stress_v2/artifacts/frozen_v2/board_replay"
    manifest = json.loads((pack / "manifest.json").read_text())
    for name, expected in manifest["sha256"].items():
        if digest(pack / name) != expected:
            raise RuntimeError(f"frozen replay hash mismatch: {name}")
    count = manifest["records"]
    for name, width in [("inputs_i16.bin", 256), ("expected_scores_i64.bin", 8), ("labels_u8.bin", 1)]:
        if (pack / name).stat().st_size != count * width:
            raise RuntimeError(f"invalid record length: {name}")
    if len(json.loads((pack / "records.json").read_text())) != count:
        raise RuntimeError("record metadata count mismatch")
    compiler = shutil.which("c++")
    if compiler is None:
        raise RuntimeError("a C++11 compiler named c++ is required")
    with tempfile.TemporaryDirectory(prefix="readout-verify-") as tmp:
        executable = Path(tmp) / "replay_reference"
        subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "stress_v2/replay_reference.cpp"), "-o", str(executable)], check=True)
        subprocess.run([str(executable), str(pack / "inputs_i16.bin"),
                        str(pack / "expected_scores_i64.bin")], check=True)
    print(f"PASS: {len(source_map['files'])} published hashes; {count} frozen replay records")


if __name__ == "__main__":
    main()
