"""Batch-one CPU timing; development comparison reuses prior classical outputs."""
import argparse,json,os,platform,shutil,time
from pathlib import Path
import numpy as np
import scipy
from guard import authorize,output,write,sha,seed,qualification
from estimators import Estimator

CLASSICAL=("analytic_multistart","coarse_grid","lookup","fixed_single","grid_single","lookup_single")
THREAD_KEYS=("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")

def runtime():
    return {"hostname":platform.node(),"machine":platform.machine(),
            "python":platform.python_version(),"numpy":np.__version__,"scipy":scipy.__version__,
            "threads":{key:os.environ.get(key) for key in THREAD_KEYS},
            "worker_count":1,"gpu_inference":False}

def main():
    p=argparse.ArgumentParser()
    for key in ("approval","data","out"):p.add_argument("--"+key,required=True)
    p.add_argument("--weights");p.add_argument("--qualification");p.add_argument("--reuse-classical")
    p.add_argument("--methods",nargs="+",default=list(CLASSICAL))
    a=p.parse_args()
    data=Path(a.data);manifest=json.loads((data/"manifest.json").read_text())
    selected=set(a.methods)
    if len(selected)!=len(a.methods):raise ValueError("duplicate method")
    if manifest["split"]=="development":
        if selected==set(CLASSICAL):
            phase="profile"
            if a.reuse_classical or a.weights:raise ValueError("initial classical profile only")
        elif a.methods==["hybrid"] and a.reuse_classical:
            phase="compare"
        else:raise ValueError("development: six classical methods once, then hybrid-only with saved classical outputs")
    elif manifest["split"]=="nuisance":
        phase="compare_nuisance"
        if selected!=set(CLASSICAL)|{"hybrid"} or a.reuse_classical:
            raise ValueError("fresh nuisance split requires all seven methods once")
    else:raise ValueError("do not profile training samples")
    auth=authorize(a.approval,phase)
    if "hybrid" in selected:
        if not a.weights or sha(a.weights)!=auth.get("weights_sha256"):
            raise RuntimeError("root-frozen initializer hash required")
        if not a.qualification:raise RuntimeError("frozen development qualification required")
        qualification(a.qualification,auth)
    if sha(data/"inputs.npz")!=manifest["files"]["inputs.npz"]:raise ValueError("input hash mismatch")
    current_runtime=runtime();records={};parent=None;startup={}
    if a.reuse_classical:
        previous=Path(a.reuse_classical)
        parent=json.loads((previous/"receipt.json").read_text())
        if sha(previous/"predictions.json")!=parent["prediction_sha256"]:
            raise ValueError("classical prediction hash mismatch")
        if parent["input_manifest_sha256"]!=sha(data/"manifest.json") or parent["runtime"]!=current_runtime:
            raise ValueError("classical reuse requires identical data, host, runtimes and threads")
        records=json.loads((previous/"predictions.json").read_text())
        if set(records)!=set(CLASSICAL) or parent.get("reused_classical") is not None:
            raise ValueError("reuse must point to the original six-method profile")
        q=json.loads(Path(a.qualification).read_text())
        if q["prediction_receipt_sha256"]!=sha(previous/"receipt.json"):
            raise ValueError("qualification does not bind this classical profile")
    out=output(a.out)
    if parent is not None:
        shutil.copyfile(previous/"predictions.json",out/"classical-predictions.json")
        shutil.copyfile(previous/"receipt.json",out/"classical-receipt.json")
    with np.load(data/"inputs.npz",allow_pickle=False) as z:observed=z["spectra"]
    if observed.shape!=(manifest["rows"],100):raise ValueError("input shape mismatch")
    models={}
    for name in a.methods:
        start=time.perf_counter();models[name]=Estimator(name,a.weights);startup[name]=time.perf_counter()-start
        records[name]=[]
    rng=np.random.default_rng(seed(auth,"timing_order"));load_before=list(os.getloadavg())
    for index,y in enumerate(observed):
        for name in rng.permutation(a.methods):
            records[name].append({"row":index,**models[name](y)})
    write(out/"predictions.json",records)
    reused=None if parent is None else {
        "prediction_sha256":sha(out/"classical-predictions.json"),
        "receipt_sha256":sha(out/"classical-receipt.json"),
        "qualification_sha256":sha(a.qualification)}
    write(out/"receipt.json",{
        "approval_sha256":auth["approval_sha256"],"run_id":os.environ["TYCHON_NUMERICAL_RUN_ID"],
        "input_manifest_sha256":sha(data/"manifest.json"),"prediction_sha256":sha(out/"predictions.json"),
        "startup_seconds":startup,"runtime":current_runtime,
        "load_average_before":load_before,"load_average_after":list(os.getloadavg()),
        "weights_sha256":sha(a.weights) if a.weights else None,"reused_classical":reused,
        "timing":"batch1 preprocessing, proposal, refinement, residual decision and fallback; excludes file IO; no omitted warmup rows",
        "timing_design":"separate wall runs on identical host/runtime; saved classical timings reused" if parent else
                        "randomized within-row method order in one run",
        "scope":"component_efficiency_only"})
if __name__=="__main__":main()
