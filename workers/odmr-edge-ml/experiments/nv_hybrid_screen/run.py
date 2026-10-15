"""Batch-one matched CPU timing; no dataset creation or training."""
import argparse,json,os,platform,time
from pathlib import Path
import numpy as np
from guard import authorize,output,write,sha,seed
from estimators import Estimator
def main():
    p=argparse.ArgumentParser()
    for k in ("approval","data","out"):p.add_argument("--"+k,required=True)
    p.add_argument("--weights");p.add_argument("--methods",nargs="+",default=["analytic_multistart","coarse_grid","lookup"])
    a=p.parse_args()
    data=Path(a.data);manifest=json.loads((data/"manifest.json").read_text())
    phase="profile" if "hybrid" not in a.methods else "compare"
    if manifest["split"]=="nuisance":phase="compare_nuisance"
    auth=authorize(a.approval,phase)
    if "hybrid" in a.methods and (not a.weights or sha(a.weights)!=auth.get("weights_sha256")):
        raise RuntimeError("root-frozen initializer hash required")
    if len(set(a.methods))!=len(a.methods):raise ValueError("duplicate method")
    out=output(a.out)
    if manifest["split"]=="train":raise ValueError("do not profile training samples")
    if sha(data/"inputs.npz")!=manifest["files"]["inputs.npz"]:raise ValueError("input hash mismatch")
    with np.load(data/"inputs.npz",allow_pickle=False) as z:observed=z["spectra"]
    models={};startup={}
    for name in a.methods:
        t=time.perf_counter();models[name]=Estimator(name,a.weights);startup[name]=time.perf_counter()-t
    rng=np.random.default_rng(seed(auth,"timing_order"));records={k:[] for k in a.methods}
    # Each row is timed once per method; randomized within-row order avoids systematic drift.
    for i,y in enumerate(observed):
        for name in rng.permutation(a.methods):
            records[name].append({"row":i,**models[name](y)})
    write(out/"predictions.json",records)
    write(out/"receipt.json",{"approval_sha256":auth["approval_sha256"],"input_manifest_sha256":sha(data/"manifest.json"),
        "prediction_sha256":sha(out/"predictions.json"),"startup_seconds":startup,"python":platform.python_version(),
        "numpy":np.__version__,"machine":platform.machine(),"worker_count":1,"gpu_inference":False,
        "weights_sha256":sha(a.weights) if a.weights else None,"timing":"batch1 preprocessing + proposal + refinement + residual decision + fallback; excludes file IO; no warmup rows omitted"})
if __name__=="__main__":main()
