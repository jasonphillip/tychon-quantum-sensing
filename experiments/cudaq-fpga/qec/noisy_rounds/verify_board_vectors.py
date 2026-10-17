"""Standard-library verification of compressed syndrome replay vectors."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
QEC=ROOT.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory):
    manifest=json.loads((directory/"manifest.json").read_text())
    n=manifest["count"]
    assert len(manifest["cases"])==n
    assert len({v["case_id"] for v in manifest["cases"]})==n
    for name,entry in manifest["files"].items():
        path=directory/name
        assert path.stat().st_size==entry["bytes"]
        assert sha(path)==entry["sha256"]
    assert sha(QEC/"qec_decoder.cpp")==manifest["fixed_core_sha256"]
    assert sha(QEC/"qec_tables.h")==manifest["fixed_header_sha256"]
    table=json.loads((QEC/"artifacts/mac_retry/correction_tables.json").read_text())["fixed_ml"]
    inputs=(directory/"inputs_u8.bin").read_bytes()
    expected=[value[0] for value in struct.iter_unpack("<I",(directory/"expected_corrections_u32.bin").read_bytes())]
    assert len(inputs)==len(expected)==n
    for i,(syndrome,correction) in enumerate(zip(inputs,expected)):
        assert table[syndrome]==correction,manifest["cases"][i]["case_id"]
        assert correction < (1<<18)
    return {"status":"passed","count":n,"all_uint32_corrections_exact":True,
            "core_and_header_unchanged":True,"all_binary_hashes_verified":True,
            "distinct_syndromes":len(set(inputs)),"evidence":"host reference only; no hardware access"}


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",required=True,type=Path)
    args=parser.parse_args()
    print(json.dumps(verify(args.directory.resolve()),indent=2))
