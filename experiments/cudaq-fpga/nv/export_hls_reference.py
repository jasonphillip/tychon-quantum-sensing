"""Export fixed ROM and representative vectors; compile and run portable C testbench."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import numpy as np
from nv_model import ROOT, quantize, integer_match


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(output):
    output.mkdir(parents=True,exist_ok=False)
    artifacts = ROOT/"artifacts"/"cpu_frozen_v1"
    template = np.load(artifacts/"templates.npz")["quantized"]
    dataset = np.load(artifacts/"synthetic_data.npz")
    ids = np.flatnonzero(dataset["split"]==2)[:8]
    inputs = np.array([quantize(dataset["features"][i])[0] for i in ids])
    expected = [integer_match(x,template) for x in inputs]
    def array(name,a):
        flat = np.asarray(a).reshape(-1)
        rows = [", ".join(str(int(v)) for v in flat[i:i+16]) for i in range(0,len(flat),16)]
        return "static const int16_t "+name+"["+str(len(flat))+"] = {\n    "+",\n    ".join(rows)+"\n};\n"
    rom = output/"nv_rom.h"
    rom.write_text("#ifndef NV_ROM_H\n#define NV_ROM_H\n#include <stdint.h>\n"+array("nv_templates",template)+"#endif\n")
    vectors = output/"nv_vectors.h"
    text = "#ifndef NV_VECTORS_H\n#define NV_VECTORS_H\n#include <stdint.h>\n"+array("nv_inputs",inputs)
    text += "static const uint16_t nv_expected_index[8] = {"+", ".join(str(v[0]) for v in expected)+"};\n"
    text += "static const uint64_t nv_expected_score[8] = {"+", ".join(str(v[1])+"ULL" for v in expected)+"};\n#endif\n"
    vectors.write_text(text)
    bench = output/"nv_testbench.c"
    bench.write_text('''#include <stdint.h>
#include <stdio.h>
#include "nv_rom.h"
#include "nv_vectors.h"
uint16_t nv_match(const int16_t *, const int16_t *, uint64_t *);
int main(void) {
    for (int k = 0; k < 8; ++k) {
        uint64_t score = 0;
        const uint16_t index = nv_match(&nv_inputs[k*128],nv_templates,&score);
        if (index != nv_expected_index[k] || score != nv_expected_score[k]) return 1;
    }
    puts("NV host reference: 8/8 vectors agree exactly");
    return 0;
}
''')
    compiler = shutil.which("clang") or shutil.which("cc")
    if not compiler:
        raise RuntimeError("compiler unavailable")
    command = [compiler,"-std=c99","-O2","-Wall","-Wextra","-Werror",str(ROOT/"nv_match.c"),str(bench),"-o",str(output/"nv_testbench")]
    subprocess.run(command,check=True,capture_output=True,text=True)
    tested = subprocess.run([str(output/"nv_testbench")],check=True,capture_output=True,text=True)
    report = {"status":"passed","evidence":"host C execution only","compile_command":command,
              "run_command":[str(output/"nv_testbench")],"stdout":tested.stdout,
              "sample_ids":ids.tolist(),"source_sha256":digest(ROOT/"nv_match.c"),
              "artifact_sha256":{p.name:digest(p) for p in [rom,vectors,bench]}}
    (output/"receipt.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",required=True,type=Path)
    args = parser.parse_args()
    main(args.output.resolve())
