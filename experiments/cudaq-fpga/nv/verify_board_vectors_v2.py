"""Verify immutable NV board replay binaries against the frozen integer reference."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from nv_model import ROOT, integer_match


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    n=manifest["count"]
    assert len(manifest["cases"])==n
    assert len({r["case_id"] for r in manifest["cases"]})==n
    for name,record in manifest["files"].items():
        path=directory/name
        assert path.stat().st_size==record["bytes"],name
        assert sha(path)==record["sha256"],name
    q=np.fromfile(directory/"inputs_i16.bin",dtype="<i2").reshape(n,128)
    idx=np.fromfile(directory/"expected_indices_u16.bin",dtype="<u2")
    score=np.fromfile(directory/"expected_scores_u64.bin",dtype="<u8")
    assert idx.shape==score.shape==(n,)
    rom=ROOT/"artifacts/cpu_frozen_v1/templates_i16le.bin"
    assert sha(rom)==manifest["rom_sha256"]
    assert sha(ROOT/"nv_match.c")==manifest["core_sha256"]
    templates=np.fromfile(rom,dtype="<i2").reshape(121,128)
    for case,(x,i,s) in enumerate(zip(q,idx,score)):
        assert integer_match(x,templates)==(int(i),int(s)),manifest["cases"][case]["case_id"]
        # Check the host MMIO runner's exact unsigned 32-bit score reconstruction.
        low=int(s)&0xffffffff
        high=int(s)>>32
        assert (high<<32)|low==int(s)
    return {"status":"passed","vectors":n,"input_shape":[n,128],
            "index_dtype":"uint16 little-endian","score_dtype":"uint64 little-endian",
            "all_full_scores_and_indices_exact":True,"binary_hashes_verified":True,
            "core_and_rom_unchanged":True,"largest_expected_score":int(score.max()),
            "evidence":"host reference only; this command performs no FPGA access"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.directory.resolve()),indent=2))
