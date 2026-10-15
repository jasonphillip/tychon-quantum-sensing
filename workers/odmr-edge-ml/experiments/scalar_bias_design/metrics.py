"""Metrics from committed saved predictions; truth opens only after commitment checks."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path
import numpy as np
from budget import sha,write_json,bindings,BOOTSTRAP_SEED

CELLS=("realistic_anchor","wide_lines","low_snr")
GAMMA=abs(-1.76085963023e11*1.000357)/(2*np.pi)*1e-12

def load_arrays(path):
    with np.load(path,allow_pickle=False) as archive:return {name:archive[name] for name in archive.files}

def summary(error,failed,boundary,timing):
    absolute=np.abs(error)
    return {"n":len(error),"mae_uT":float(absolute.mean()),
        "rmse_uT":float(np.sqrt(np.mean(error**2))),"median_abs_uT":float(np.median(absolute)),
        "p90_abs_uT":float(np.quantile(absolute,.9)),"p95_abs_uT":float(np.quantile(absolute,.95)),
        "max_abs_uT":float(absolute.max()),"failure_fraction":float(failed.mean()),
        "raw_fit_coverage":float(1-failed.mean()),"boundary_fraction":float(boundary.mean()),
        "median_latency_seconds":float(np.median(timing)),
        "p95_latency_seconds":float(np.quantile(timing,.95)),"total_fit_seconds":float(timing.sum())}

def compute(pred,truth,indices):
    if not np.array_equal(pred["row_ids"],truth["row_id"]):raise ValueError("prediction/truth row alignment")
    if not np.isfinite(pred["estimate_uT"]).all():raise ValueError("nonfinite operational prediction")
    if pred["failed"].dtype!=np.bool_ or pred["boundary"].dtype!=np.bool_:
        raise ValueError("failure and boundary flags must be boolean")
    if not np.all(pred["estimate_uT"][pred["failed"]]==45.):raise ValueError("failed rows must use fallback45")
    if not np.isfinite(pred["elapsed_seconds"]).all() or np.any(pred["elapsed_seconds"]<0):
        raise ValueError("invalid saved timing")
    if not np.issubdtype(indices.dtype,np.integer):raise ValueError("bootstrap indices must be integers")
    n=len(np.unique(truth["field_index"]))
    if indices.shape!=(5000,n) or indices.min()<0 or indices.max()>=n:raise ValueError("bootstrap dimensions")
    output={"partition_fields":n,"bootstrap_seed":BOOTSTRAP_SEED,
        "bootstrap_resamples":5000,"quantile_method":"linear","cells":{}}
    for cell in CELLS:
        groups={};arrays={}
        for bias in (0,250):
            mask=np.array([name.endswith(":bias"+str(bias)) for name in pred["row_ids"]])&(truth["cell"]==cell)
            select=np.flatnonzero(mask);select=select[np.argsort(truth["field_index"][select])]
            if not np.array_equal(truth["field_index"][select],np.arange(n)):raise ValueError("paired field rows")
            y=truth["field_uT"][select];estimate=pred["estimate_uT"][select]
            fail=pred["failed"][select];boundary=pred["boundary"][select];timing=pred["elapsed_seconds"][select]
            groups[str(bias)]=summary(estimate-y,fail,boundary,timing)
            groups[str(bias)]["constant45"]=summary(45-y,np.zeros(n,bool),np.zeros(n,bool),np.zeros(n))
            arrays[bias]=(select,y,estimate,fail,boundary,timing)
        _,y0,e0,*_=arrays[0];selected,y,e,fail,boundary,timing=arrays[250]
        if not np.array_equal(y,y0):raise ValueError("unpaired labels")
        contrasts={}
        for name,difference in (("biased_minus_zero",abs(e-y)-abs(e0-y)),
                                ("biased_minus_constant45",abs(e-y)-abs(45-y))):
            boot=difference[indices].mean(axis=1)
            contrasts[name]={"mean_uT":float(difference.mean()),
                "ci95_uT":np.quantile(boot,[.025,.975]).tolist()}
        temperature=truth["temperature_K"][selected]
        bins=[]
        for lower,upper in ((-np.inf,288.15),(288.15,293.15),(293.15,298.15),(298.15,np.inf)):
            mask=(temperature>=lower)&(temperature<upper)
            bins.append({"lower_K":None if not np.isfinite(lower) else lower,
                "upper_K":None if not np.isfinite(upper) else upper,"n":int(mask.sum()),
                "biased":summary(e[mask]-y[mask],fail[mask],boundary[mask],timing[mask]) if mask.any() else None,
                "zero_bias":summary(e0[mask]-y[mask],arrays[0][3][mask],arrays[0][4][mask],
                                    arrays[0][5][mask]) if mask.any() else None})
        sensitivity={}
        for delta in (-5,-1,0,1,5):
            changed=np.where(fail,45.,e-delta)
            sensitivity[str(delta)]=summary(changed-y,fail,boundary,timing)
        thermal=np.abs(.0742*(temperature-293.15)/GAMMA)
        output["cells"][cell]={"arms":groups,"paired_contrasts":contrasts,
            "temperature_bins":bins,"calibration_shift_uT":sensitivity,
            "single_line_temperature_error_uT":{"reference_K":293.15,
                "mean":float(thermal.mean()),"p95":float(np.quantile(thermal,.95)),"max":float(thermal.max())}}
    anchor=output["cells"]["realistic_anchor"];biased=anchor["arms"]["250"];c=anchor["paired_contrasts"]
    conditions={"beats_zero":c["biased_minus_zero"]["ci95_uT"][1]<-.5,
        "beats_constant":c["biased_minus_constant45"]["ci95_uT"][1]<-.5,
        "mae":biased["mae_uT"]<=2,"p90":biased["p90_abs_uT"]<=5,
        "failure":biased["failure_fraction"]<=.01}
    output["gate"]={"conditions":conditions,"pass":all(conditions.values()),
        "claim":"Conditional simulated known-axis measurement-design comparison only."}
    return output

def committed(args,bound):
    relative=args.commitment.relative_to(args.code_root)
    data=subprocess.check_output(["git","-C",str(args.code_root),"show",
                                  args.commitment_revision+":"+relative.as_posix()])
    if data!=args.commitment.read_bytes():raise ValueError("commitment bytes are not committed")
    subprocess.run(["git","-C",str(args.code_root),"merge-base","--is-ancestor",
                    args.commitment_revision,"HEAD"],check=True,capture_output=True)
    record=json.loads(data);receipt=json.loads((args.predictions/"receipt.json").read_text())
    if record["prediction_sha256"]!=sha(args.predictions/"predictions.npz"):raise ValueError("prediction commitment mismatch")
    if record["prediction_receipt_sha256"]!=sha(args.predictions/"receipt.json"):raise ValueError("receipt commitment mismatch")
    if receipt["status"]!="complete":raise ValueError("prediction process did not complete")
    for key in ("freeze_sha256","access_sha256","input_manifest_sha256"):
        if record[key]!=bound[key] or receipt[key]!=bound[key]:raise ValueError("prediction custody binding mismatch")
    if receipt["starts_sha256"]!=sha(args.predictions/"starts.json"):raise ValueError("start diagnostics mismatch")
    return sha(args.commitment)

def run(args):
    manifest=args.data/"manifest.json"
    # Check commit before claiming metric access or opening truth.
    record=json.loads(manifest.read_text())
    bound={"input_manifest_sha256":sha(manifest),
        "freeze_sha256":sha(args.freeze) if args.freeze else None,
        "access_sha256":sha(args.access) if args.access else None}
    commitment_sha=committed(args,bound)
    _,verified=bindings(args,manifest,"metrics")
    if verified!=bound:raise ValueError("metric custody binding drift")
    args.out.mkdir(parents=True,exist_ok=False)
    receipt={"status":"running",**bound,"prediction_commitment_sha256":commitment_sha,
             "prediction_commitment_revision":args.commitment_revision}
    try:
        if sha(args.data/"truth.npz")!=record["files"]["truth.npz"]:raise ValueError("truth hash mismatch")
        pred=load_arrays(args.predictions/"predictions.npz");truth=load_arrays(args.data/"truth.npz")
        indices=np.random.default_rng(BOOTSTRAP_SEED).integers(0,record["fields"],size=(5000,record["fields"]))
        result=compute(pred,truth,indices)
        np.save(args.out/"bootstrap_indices.npy",indices,allow_pickle=False)
        write_json(args.out/"metrics.json",result)
        copies={"inputs.npz":args.data/"inputs.npz","truth.npz":args.data/"truth.npz",
            "seed-record.json":args.data/"seed-record.json","input-manifest.json":manifest,
            "predictions.npz":args.predictions/"predictions.npz","starts.json":args.predictions/"starts.json",
            "prediction-receipt.json":args.predictions/"receipt.json","prediction-commitment.json":args.commitment}
        for name,source in copies.items():shutil.copyfile(source,args.out/name)
        receipt.update(status="complete",gate_pass=result["gate"]["pass"])
    except Exception as exc:
        receipt.update(status="failed",error=type(exc).__name__+": "+str(exc));raise
    finally:write_json(args.out/"metric-receipt.json",receipt)
    files={p.name:sha(p) for p in args.out.iterdir() if p.is_file()}
    write_json(args.out/"bundle-manifest.json",{"status":"complete","files":files,
        "protocol_sha256":sha(args.protocol),**bound})
    print(json.dumps({"status":"complete","gate_pass":receipt["gate_pass"],
        "bundle_manifest_sha256":sha(args.out/"bundle-manifest.json")}))
if __name__=="__main__":
    p=argparse.ArgumentParser()
    for name in ("data","predictions","out","registration","protocol","code-root","commitment"):
        p.add_argument("--"+name,type=Path,required=True)
    for name in ("freeze","access"):p.add_argument("--"+name,type=Path)
    p.add_argument("--commitment-revision",required=True);run(p.parse_args())
