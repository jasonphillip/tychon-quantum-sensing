"""Verify published bytes and compiled decoder parity; do not resample trials."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    source_map = json.loads((ROOT / "SOURCE_MAP.json").read_text())
    for entry in source_map["files"]:
        path = ROOT / entry["published_path"]
        data = path.read_bytes()
        require(len(data) == entry["published_bytes"], f"Size differs: {path.name}")
        require(hashlib.sha256(data).hexdigest() == entry["published_sha256"],
                f"Published hash differs: {path.name}")
    tables = json.loads((ROOT / "artifacts/mac_retry/correction_tables.json").read_text())
    compiler = shutil.which(os.environ.get("CXX", "c++"))
    require(compiler is not None, "C++11 compiler required; set CXX if needed")
    with tempfile.TemporaryDirectory(prefix="qec-verify-") as temporary:
        binary = Path(temporary) / "qec_host"
        subprocess.run([compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "qec_decoder.cpp"), str(ROOT / "host_benchmark.cpp"),
                        "-o", str(binary)], check=True, timeout=60)
        output = subprocess.run([str(binary), "--dump"], check=True,
                                capture_output=True, text=True, timeout=30).stdout
    rows = [list(map(int, line.split())) for line in output.splitlines()]
    require(len(rows) == 256, "Expected every syndrome exactly once")
    for syndrome, row in enumerate(rows):
        require(row == [syndrome, tables["fixed_ml"][syndrome],
                        tables["separate_css"][syndrome], tables["joint_min_weight"][syndrome]],
                f"Compiled correction differs for syndrome {syndrome}")
    board = ROOT / "noisy_rounds/artifacts/frozen_v1/board_vectors"
    inputs = (board / "inputs_u8.bin").read_bytes()
    expected = list(struct.iter_unpack("<I", (board / "expected_corrections_u32.bin").read_bytes()))
    require(len(inputs) == len(expected) == 4864, "Unexpected replay length")
    for index, (syndrome, correction) in enumerate(zip(inputs, expected)):
        require(rows[syndrome][1] == correction[0], f"Compiled replay differs at {index}")
    metrics = json.loads((ROOT / "noisy_rounds/artifacts/frozen_v1/metrics.json").read_text())
    cell = next(row for row in metrics["cells"] if row["cell_id"] == "r9_p0.01_q0.01")
    require([cell[name]["failure_count"] for name in
             ("last_noisy", "majority_noisy", "final_perfect", "spacetime_pymatching")]
            == [3003, 6421, 1591, 738], "Frozen comparison differs")
    print(json.dumps({"status": "PASS", "published_files_verified": len(source_map["files"]),
                      "compiled_table_comparisons": 768, "compiled_replay_corrections": 4864,
                      "scientific_trials_regenerated": 0, "hardware_access": False}, indent=2))


if __name__ == "__main__":
    main()
