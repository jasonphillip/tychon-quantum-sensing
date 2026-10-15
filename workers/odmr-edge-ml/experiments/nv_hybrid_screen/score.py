"""Saved-output qualification and component-efficiency comparison."""
import argparse,json
from pathlib import Path
import numpy as np
from guard import authorize,write,sha,seed,qualification

CLASSICAL=("analytic_multistart","coarse_grid","lookup","fixed_single","grid_single","lookup_single")

def summarize(records,truth):
    summary={};errors={}
    for name,rows in records.items():
        if [r["row"] for r in rows]!=list(range(len(truth))):raise ValueError("row order mismatch")
        initial=6 if name=="analytic_multistart" else (2 if name in ("coarse_grid","lookup") else 1)
        for row in rows:
            if any(type(row[k]) is not bool for k in ("failed","accepted","fallback","boundary")):
                raise ValueError("flags must be booleans")
            if row["failed"]==row["accepted"] or (row["failed"] and row["estimate"]!=45):
                raise ValueError("operational failure handling mismatch")
            if name=="analytic_multistart" and row["fallback"]:raise ValueError("duplicate multistart fallback")
            maximum=80*(initial+6*row["fallback"])
            if type(row["nfev"]) is not int or not 0<=row["nfev"]<=maximum:raise ValueError("fit budget mismatch")
            score=row["score"]
            if score is not None and (not np.isfinite(score) or score<0):raise ValueError("invalid residual")
            if row["accepted"] and (score is None or score>2):raise ValueError("residual acceptance mismatch")
        estimate=np.array([r["estimate"] for r in rows]);latency=np.array([r["seconds"] for r in rows])
        if not np.isfinite(estimate).all() or np.any((estimate<20)|(estimate>70)):
            raise ValueError("invalid estimate")
        if not np.isfinite(latency).all() or np.any(latency<=0):raise ValueError("invalid latency")
        error=np.abs(estimate-truth);errors[name]=error
        summary[name]={"mae_uT":float(error.mean()),"p90_uT":float(np.quantile(error,.9)),
            "failure_fraction":float(np.mean([r["failed"] for r in rows])),
            "fallback_fraction":float(np.mean([r["fallback"] for r in rows])),
            "boundary_fraction":float(np.mean([r["boundary"] for r in rows])),
            "false_acceptance_gt5_fraction":float(np.mean([r["accepted"] and e>5 for r,e in zip(rows,error)])),
            "mean_nfev":float(np.mean([r["nfev"] for r in rows])),
            "latency_ms":{f"p{q}":float(np.percentile(latency,q)*1000) for q in (50,95,99)}}
    return summary,errors

def adequate(record):
    return record["mae_uT"]<=2 and record["p90_uT"]<=5 and record["failure_fraction"]<=.01

def main():
    p=argparse.ArgumentParser()
    for key in ("approval","data","predictions","out"):p.add_argument("--"+key,required=True)
    p.add_argument("--qualification")
    a=p.parse_args();data=Path(a.data);pred=Path(a.predictions);out=Path(a.out)
    if out.exists() or out.with_suffix(".bootstrap.npy").exists():raise FileExistsError("exclusive scoring output required")
    manifest=json.loads((data/"manifest.json").read_text())
    if manifest["split"] not in ("development","nuisance"):raise ValueError("invalid scoring split")
    auth=authorize(a.approval,"score_nuisance" if manifest["split"]=="nuisance" else "score")
    receipt=json.loads((pred/"receipt.json").read_text())
    if sha(data/"manifest.json")!=receipt["input_manifest_sha256"] or sha(pred/"predictions.json")!=receipt["prediction_sha256"]:
        raise ValueError("prediction/data binding mismatch")
    if sha(data/"truth.npz")!=manifest["files"]["truth.npz"]:raise ValueError("truth hash mismatch")
    with np.load(data/"truth.npz",allow_pickle=False) as z:truth=z["field"]
    if truth.shape!=(manifest["rows"],) or not np.isfinite(truth).all():raise ValueError("truth shape/value mismatch")
    records=json.loads((pred/"predictions.json").read_text())
    if set(records) not in (set(CLASSICAL),set(CLASSICAL)|{"hybrid"}):raise ValueError("all six classical controls required")
    summary,errors=summarize(records,truth)
    qualified=[name for name in CLASSICAL if adequate(summary[name])]
    fastest=min(qualified,key=lambda k:(summary[k]["latency_ms"]["p95"],k)) if qualified else None
    comparison=None;bootstrap_hash=None;qualification_hash=None
    if "hybrid" in errors:
        if not a.qualification:raise RuntimeError("root-frozen development qualification required")
        q=qualification(a.qualification,auth);qualification_hash=sha(a.qualification)
        baseline=q["fastest_adequate_classical"]
        rng=np.random.default_rng(seed(auth,"bootstrap"))
        indices=rng.integers(0,len(truth),size=(2000,len(truth)),dtype=np.int64)
        with out.with_suffix(".bootstrap.npy").open("xb") as f:np.save(f,indices,allow_pickle=False)
        bootstrap_hash=sha(out.with_suffix(".bootstrap.npy"))
        delta=errors["hybrid"]-errors[baseline]
        interval=np.percentile(delta[indices].mean(axis=1),[2.5,97.5])
        speedup=summary[baseline]["latency_ms"]["p95"]/summary["hybrid"]["latency_ms"]["p95"]
        comparison={"baseline":baseline,"added_mae_uT":float(delta.mean()),"added_mae_ci95":interval.tolist(),
            "p95_speedup":float(speedup),"baseline_adequate_on_this_split":adequate(summary[baseline]),
            "screen_pass":bool(adequate(summary[baseline]) and adequate(summary["hybrid"]) and interval[1]<.1 and speedup>=2)}
    write(out,{"scope":"software component screen; no sealed final adoption decision",
        "claim_scope":"component_efficiency_only","split":manifest["split"],"rows":len(truth),
        "summary":summary,"fastest_adequate_classical":fastest,"classical_accuracy_qualified":bool(qualified),
        "comparison":comparison,"bootstrap_indices_sha256":bootstrap_hash,
        "qualification_sha256":qualification_hash,"prediction_receipt_sha256":sha(pred/"receipt.json"),
        "data_manifest_sha256":sha(data/"manifest.json"),"approval_sha256":auth["approval_sha256"],
        "timing_design":receipt["timing_design"],
        "claim_limits":"No system bandwidth, energy, instrument usefulness, measured-sensor, or FPGA compatibility claim."})
if __name__=="__main__":main()
