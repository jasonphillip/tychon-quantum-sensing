"""Development reporting and fail-closed useful-bottleneck gate."""
import argparse,json
from pathlib import Path
import numpy as np
from guard import authorize,write,sha,seed
def main():
    p=argparse.ArgumentParser()
    for k in ("approval","data","predictions","out"):p.add_argument("--"+k,required=True)
    a=p.parse_args();data=Path(a.data);pred=Path(a.predictions)
    manifest=json.loads((data/"manifest.json").read_text())
    auth=authorize(a.approval,"score_nuisance" if manifest["split"]=="nuisance" else "score")
    receipt=json.loads((pred/"receipt.json").read_text())
    if sha(data/"manifest.json")!=receipt["input_manifest_sha256"] or sha(pred/"predictions.json")!=receipt["prediction_sha256"]:
        raise ValueError("prediction/data binding mismatch")
    if sha(data/"truth.npz")!=manifest["files"]["truth.npz"]:raise ValueError("truth hash mismatch")
    with np.load(data/"truth.npz",allow_pickle=False) as z:truth=z["field"]
    records=json.loads((pred/"predictions.json").read_text());summary={};errors={}
    for name,rows in records.items():
        rows=sorted(rows,key=lambda r:r["row"])
        if [r["row"] for r in rows]!=list(range(len(truth))):raise ValueError("row mismatch")
        estimate=np.array([r["estimate"] for r in rows]);latency=np.array([r["seconds"] for r in rows])
        if not np.isfinite(estimate).all() or not np.isfinite(latency).all() or np.any(latency<0):raise ValueError("invalid output")
        error=np.abs(estimate-truth);errors[name]=error
        summary[name]={"mae_uT":float(error.mean()),"p90_uT":float(np.quantile(error,.9)),
          "failure_fraction":float(np.mean([r["failed"] for r in rows])),
          "fallback_fraction":float(np.mean([r["fallback"] for r in rows])),
          "false_acceptance_gt5_fraction":float(np.mean([r["accepted"] and e>5 for r,e in zip(rows,error)])),
          "latency_ms":{f"p{q}":float(np.percentile(latency,q)*1000) for q in (50,95,99)}}
    adequate=[k for k,v in summary.items() if k!="hybrid" and v["mae_uT"]<=2 and v["p90_uT"]<=5 and v["failure_fraction"]<=.01]
    fastest=min(adequate,key=lambda k:summary[k]["latency_ms"]["p95"]) if adequate else None
    cycle=auth.get("cycle",{});required=("processing_deadline_ms","acquisition_ms","settling_ms","transfer_ms","recovery_ms")
    declared=all(isinstance(cycle.get(k),(float,int)) and cycle[k]>=0 for k in required) and bool(cycle.get("requirement_source"))
    fraction=None;gate=False
    if fastest and declared:
        processing=summary[fastest]["latency_ms"]["p50"];other=sum(cycle[k] for k in required if k!="processing_deadline_ms")
        fraction=processing/(processing+other) if processing+other else 0
        gate=summary[fastest]["latency_ms"]["p95"]>cycle["processing_deadline_ms"]>0 and fraction>=.2
    comparison=None
    if "hybrid" in errors and fastest:
        rng=np.random.default_rng(seed(auth,"bootstrap"));ix=rng.integers(0,len(truth),size=(2000,len(truth)))
        delta=errors["hybrid"]-errors[fastest];ci=np.percentile(delta[ix].mean(axis=1),[2.5,97.5])
        h=summary["hybrid"];speedup=summary[fastest]["latency_ms"]["p95"]/h["latency_ms"]["p95"]
        comparison={"baseline":fastest,"added_mae_ci95":ci.tolist(),"p95_speedup":float(speedup),
          "screen_pass":bool(ci[1]<.1 and speedup>=2 and h["mae_uT"]<=2 and h["p90_uT"]<=5 and h["failure_fraction"]<=.01)}
    write(a.out,{"scope":"development only; no final adoption decision","summary":summary,"fastest_adequate_classical":fastest,
      "cycle":cycle,"processing_fraction":fraction,"training_bottleneck_gate":gate,"comparison":comparison,
      "prediction_receipt_sha256":sha(pred/"receipt.json"),"approval_sha256":auth["approval_sha256"]})
if __name__=="__main__":main()
