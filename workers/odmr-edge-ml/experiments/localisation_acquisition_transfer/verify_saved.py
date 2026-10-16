"""Recompute saved-only evidence; no feature extraction or model invocation."""
import argparse
from pathlib import Path
import sys
if __package__ in (None,""):
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    __package__="experiments.localisation_acquisition_transfer"
from .guard import read_json, sha256, PACKAGE
from .contract import check_saved_labels, decode_seed_bytes


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--result",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    root=Path(args.result).resolve();manifest=read_json(root/"manifest.json")
    for name,expected in manifest["files"].items():
        relative=Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(root/relative)!=expected:
            raise ValueError("artifact hash mismatch")
    for name,expected in manifest["source_sha256"].items():
        relative=Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE/relative)!=expected:
            raise ValueError("source hash mismatch")
    for name,expected in manifest["dependency_sha256"].items():
        relative=Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(PACKAGE.parents[1]/relative)!=expected:
            raise ValueError("dependency hash mismatch")
    import numpy as np
    from .metrics import evaluate
    geometry=read_json(root/"geometry.json");protocol=read_json(root/"protocol.json");seed=read_json(root/"seed.json")
    if (type(seed["bootstrap"]) is not int or not 0<=seed["bootstrap"]<2**256
            or seed["seed_commitment_sha256"]!=protocol["seed_commitment_sha256"]
            or seed["released_seed_sha256"]!=protocol["seed_sha256"]):
        raise ValueError("saved seed provenance differs")
    decode_seed_bytes(seed["bootstrap"].to_bytes(32,"big"),protocol["seed_sha256"])
    if protocol!=read_json(PACKAGE/"protocol.json"):
        raise ValueError("saved protocol differs from frozen source")
    if sha256(root/"geometry.json")!=protocol["geometry_sha256"]:
        raise ValueError("geometry/protocol mismatch")
    with np.load(root/"predictions.npz",allow_pickle=False) as data:
        check_saved_labels(data["labels"],geometry)
        if data["groups"].tolist()!=[r["group_id"] for r in geometry["members"]]:
            raise ValueError("saved groups differ")
        flags=read_json(root/"fit_flags.json")
        if len(flags)!=25 or any(len(row)!=8 for row in flags):
            raise ValueError("all raw fit flags required")
        expected_raw=np.asarray([all(f["valid"] for f in row) for row in flags])
        if data["valid_raw"].shape!=(25,) or not np.array_equal(data["valid_raw"],expected_raw):
            raise ValueError("raw failure flags disagree")
        if np.isfinite(data["small"][~expected_raw]).any() or np.isfinite(data["full"][~expected_raw]).any():
            raise ValueError("invalid raw case received a prediction")
        expected=evaluate(data["labels"],data["small"],data["full"],data["groups"],protocol,seed["bootstrap"])
    if expected!=read_json(root/"metrics.json"):
        raise ValueError("saved metrics differ")
    from .guard import write_json
    write_json(args.output,{"artifact_integrity":"PASS","metric_recomputation":"PASS","scientific_status":expected["status"],"metrics":expected})
    print("PASS",expected["status"])
    return 0 if expected["status"]=="PASS" else 2


if __name__=="__main__":
    raise SystemExit(main())
