"""Recompute a public bundle using its independently supplied manifest hash."""
import argparse,json
from pathlib import Path
import numpy as np
from budget import sha
from metrics import load_arrays,compute

def equivalent(a,b,path="metrics"):
    if isinstance(a,dict):
        if set(a)!=set(b):raise AssertionError(path+": keys")
        for key in a:equivalent(a[key],b[key],path+"."+key)
    elif isinstance(a,list):
        if len(a)!=len(b):raise AssertionError(path+": length")
        for i,(x,y) in enumerate(zip(a,b)):equivalent(x,y,path+"."+str(i))
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        if not np.isclose(a,b,rtol=1e-10,atol=1e-10):raise AssertionError(path+": value")
    elif a!=b:raise AssertionError(path+": value")

def run(bundle,expected):
    manifest_path=bundle/"bundle-manifest.json"
    if sha(manifest_path)!=expected:raise ValueError("expected bundle-manifest hash mismatch")
    manifest=json.loads(manifest_path.read_text())
    if manifest["status"]!="complete":raise ValueError("incomplete bundle")
    for name,digest in manifest["files"].items():
        path=bundle/name
        if Path(name).name!=name or path.is_symlink():raise ValueError("unsafe bundle path")
        if sha(path)!=digest:raise ValueError("artifact hash mismatch: "+name)
    pred=load_arrays(bundle/"predictions.npz");truth=load_arrays(bundle/"truth.npz")
    indices=np.load(bundle/"bootstrap_indices.npy",allow_pickle=False)
    result=compute(pred,truth,indices)
    equivalent(result,json.loads((bundle/"metrics.json").read_text()))
    print(json.dumps({"status":"pass","gate_pass":result["gate"]["pass"],
        "rows":len(pred["row_ids"]),"fields":result["partition_fields"],
        "mode":"saved outputs only; no spectrum generation or estimator inference"}))
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--bundle",type=Path,required=True)
    p.add_argument("--expected-manifest-sha256",required=True)
    a=p.parse_args();run(a.bundle,a.expected_manifest_sha256)
