"""Export frozen host vectors and prove the optimized fixed-input C++ core."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--artifacts", type=Path, required=True)
    args = p.parse_args()
    out = args.artifacts
    model = json.loads((out/"model.json").read_text())
    if model["selected"] != "boxcar":
        raise ValueError("two-weight optimization applies only to selected boxcar")
    w = np.array(model["weight_int16"], dtype=np.int16)
    if not (np.all(w[::2] == w[0]) and np.all(w[1::2] == w[1])):
        raise ValueError("coefficient repetition check failed")
    data = np.load(out/"fixed_test_vectors.npz", allow_pickle=False)
    x = data["x_int16"]
    edge = np.stack([np.full(128, -32768, dtype=np.int16), np.full(128, 32767, dtype=np.int16),
                     np.where(w >= 0, 32767, -32768).astype(np.int16), np.where(w >= 0, -32768, 32767).astype(np.int16)])
    x = np.concatenate([x, edge])
    expected = x.astype(np.int64)@w.astype(np.int64)+model["bias_int64"]
    values = lambda row: ",".join(str(int(v)) for v in row)
    text = "#pragma once\n#include <stdint.h>\n"
    text += f"static const unsigned VECTOR_COUNT = {len(x)};\n"
    text += "static const int16_t WEIGHTS[128] = {"+values(w)+"};\n"
    text += f"static const int64_t BIAS = {model['bias_int64']}LL;\n"
    text += "static const int16_t INPUTS["+str(len(x))+"][128] = {\n"+",\n".join("{"+values(row)+"}" for row in x)+"\n};\n"
    text += "static const int64_t EXPECTED["+str(len(x))+"] = {"+",".join(str(int(v))+"LL" for v in expected)+"};\n"
    (out/"hls_vectors.h").write_text(text)
    compiler = shutil.which("c++")
    if not compiler:
        raise RuntimeError("C++ compiler required")
    command = [compiler, "-std=c++11", "-O2", "-Wall", "-Wextra", "-Werror", "-I", str(out),
               str(ROOT/"fixed_readout128.cpp"), str(ROOT/"boxcar_readout64.cpp"), str(ROOT/"host_testbench.cpp"), "-o", str(out/"host_testbench")]
    compile_result = subprocess.run(command, check=True, capture_output=True, text=True)
    result = subprocess.run([str(out/"host_testbench")], check=True, capture_output=True, text=True)
    receipt = {"compile_command": command, "command": [str(out/"host_testbench")], "exit_code": result.returncode,
               "stdout": result.stdout, "stderr": result.stderr, "compiler_stderr": compile_result.stderr,
               "vectors": len(x), "generic_multiplies": 128, "boxcar_multiplies": 2,
               "boxcar_coefficient_storage_bytes": 12, "evidence": "host execution only"}
    (out/"cpp_receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(result.stdout, end="")


if __name__ == "__main__":
    main()
