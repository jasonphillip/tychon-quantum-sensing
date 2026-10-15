"""Independent NumPy-only verification of saved metrics; no model or renderer imports."""
import argparse,hashlib,json,math
from pathlib import Path
import numpy as np

METHODS=("analytic_multistart","coarse_grid","lookup","fixed_single","grid_single","lookup_single")
def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def check(condition,message):
    if not condition:raise ValueError(message)
def close(actual,expected,label):
    if isinstance(expected,dict):
        check(set(actual)==set(expected),label+" keys")
        for key,value in expected.items():close(actual[key],value,label+"."+key)
    elif isinstance(expected,list):
        check(len(actual)==len(expected),label+" length")
        for i,value in enumerate(expected):close(actual[i],value,label+"."+str(i))
    elif type(expected) is bool or expected is None or isinstance(expected,str):
        check(type(actual) is type(expected) and actual==expected,label)
    else:check(math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-12),label)
def acceptable(value):
    return value["mae_uT"]<=2 and value["p90_uT"]<=5 and value["failure_fraction"]<=.01

def verify(args):
    data=Path(args.data);pred=Path(args.predictions);report_path=Path(args.report)
    check(digest(report_path)==args.report_sha256,"pinned report")
    report=read(report_path);manifest=read(data/"manifest.json");receipt=read(pred/"receipt.json")
    check(report["claim_scope"]=="component_efficiency_only","scope")
    check(report["split"]==manifest["split"],"split")
    check(digest(data/"manifest.json")==receipt["input_manifest_sha256"]==report["data_manifest_sha256"],"data binding")
    for name,h in manifest["files"].items():
        check(name in ("inputs.npz","truth.npz"),"artifact name")
        check(digest(data/name)==h,"artifact hash "+name)
    check(digest(pred/"receipt.json")==report["prediction_receipt_sha256"],"receipt hash")
    check(digest(pred/"predictions.json")==receipt["prediction_sha256"],"predictions hash")
    runtime=receipt["runtime"]
    check(runtime["worker_count"]==1 and runtime["gpu_inference"] is False,"CPU timing")
    check(set(runtime["threads"])=={"OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS"} and
          all(value=="1" for value in runtime["threads"].values()),"thread count")
    check(all(math.isfinite(value) and value>=0 for value in receipt["startup_seconds"].values()),"startup")
    records=read(pred/"predictions.json")
    check(set(records) in (set(METHODS),set(METHODS)|{"hybrid"}),"six classical references")
    reused=receipt["reused_classical"]
    if reused is not None:
        check(manifest["split"]=="development","reuse split")
        check(digest(pred/"classical-predictions.json")==reused["prediction_sha256"],"parent predictions hash")
        check(digest(pred/"classical-receipt.json")==reused["receipt_sha256"],"parent receipt hash")
        parent=read(pred/"classical-receipt.json");parent_records=read(pred/"classical-predictions.json")
        check(parent["runtime"]==runtime and parent["input_manifest_sha256"]==receipt["input_manifest_sha256"],"matched reuse")
        check(parent["prediction_sha256"]==reused["prediction_sha256"] and parent["reused_classical"] is None,"original profile")
        check(set(parent_records)==set(METHODS) and all(records[name]==parent_records[name] for name in METHODS),"unmodified classical rows")
        check(set(receipt["startup_seconds"])=={"hybrid"},"hybrid-only new timing")
    else:check(set(receipt["startup_seconds"])==set(records),"all timed methods")
    with np.load(data/"truth.npz",allow_pickle=False) as z:truth=z["field"]
    n=manifest["rows"]
    check(truth.shape==(n,) and n==report["rows"] and np.isfinite(truth).all(),"truth")
    with np.load(data/"inputs.npz",allow_pickle=False) as z:
        check(z["spectra"].shape==(n,100) and np.isfinite(z["spectra"]).all(),"spectra shape")
    statistics={};absolute_errors={}
    for name,rows in records.items():
        check(len(rows)==n and [row["row"] for row in rows]==list(range(n)),"row alignment")
        starts=6 if name=="analytic_multistart" else (2 if name in ("coarse_grid","lookup") else 1)
        for row in rows:
            check(all(type(row[key]) is bool for key in ("failed","accepted","fallback","boundary")),"boolean flags")
            check(row["failed"]!=row["accepted"],"complementary acceptance")
            check(not row["failed"] or row["estimate"]==45,"failed operational estimate")
            check(name!="analytic_multistart" or not row["fallback"],"no duplicated multistart")
            check(type(row["nfev"]) is int and 0<=row["nfev"]<=80*(starts+6*row["fallback"]),"fit budget")
            residual=row["score"]
            check(residual is None or (math.isfinite(residual) and residual>=0),"residual")
            check(not row["accepted"] or (residual is not None and residual<=2),"acceptance residual")
        estimates=np.asarray([row["estimate"] for row in rows],dtype=float)
        seconds=np.asarray([row["seconds"] for row in rows],dtype=float)
        check(np.isfinite(estimates).all() and ((estimates>=20)&(estimates<=70)).all(),"estimates")
        check(np.isfinite(seconds).all() and (seconds>0).all(),"latency")
        error=np.abs(estimates-truth);absolute_errors[name]=error
        statistics[name]={"mae_uT":float(np.sum(error)/n),"p90_uT":float(np.percentile(error,90)),
          "failure_fraction":sum(row["failed"] for row in rows)/n,
          "fallback_fraction":sum(row["fallback"] for row in rows)/n,
          "boundary_fraction":sum(row["boundary"] for row in rows)/n,
          "false_acceptance_gt5_fraction":sum(row["accepted"] and value>5 for row,value in zip(rows,error))/n,
          "mean_nfev":sum(row["nfev"] for row in rows)/n,
          "latency_ms":{f"p{value}":float(np.quantile(seconds,value/100)*1000) for value in (50,95,99)}}
    close(report["summary"],statistics,"summary")
    adequate=[name for name in METHODS if acceptable(statistics[name])]
    selected=min(adequate,key=lambda name:(statistics[name]["latency_ms"]["p95"],name)) if adequate else None
    close(report["fastest_adequate_classical"],selected,"fastest")
    close(report["classical_accuracy_qualified"],bool(adequate),"qualification")
    check(report["timing_design"]==receipt["timing_design"],"timing disclosure")
    if "hybrid" in records:
        check(args.qualification is not None,"qualification path required")
        q=read(args.qualification)
        check(digest(args.qualification)==report["qualification_sha256"],"frozen qualification hash")
        check(set(q["summary"])==set(METHODS) and q["classical_accuracy_qualified"] is True,"qualification structure")
        q_adequate=[name for name in METHODS if acceptable(q["summary"][name])]
        chosen=min(q_adequate,key=lambda name:(q["summary"][name]["latency_ms"]["p95"],name))
        check(q["fastest_adequate_classical"]==chosen,"frozen baseline choice")
        if reused is not None:
            check(reused["qualification_sha256"]==report["qualification_sha256"] and
                  q["prediction_receipt_sha256"]==reused["receipt_sha256"],"qualification reuse binding")
        indices_path=report_path.with_suffix(".bootstrap.npy")
        check(digest(indices_path)==report["bootstrap_indices_sha256"],"saved bootstrap hash")
        indices=np.load(indices_path,allow_pickle=False)
        check(indices.dtype.kind in "iu" and indices.shape==(2000,n) and
              (indices>=0).all() and (indices<n).all(),"saved bootstrap indices")
        delta=absolute_errors["hybrid"]-absolute_errors[chosen]
        resampled=np.sum(delta[indices],axis=1)/n
        interval=np.quantile(resampled,[.025,.975])
        speed=statistics[chosen]["latency_ms"]["p95"]/statistics["hybrid"]["latency_ms"]["p95"]
        expected={"baseline":chosen,"added_mae_uT":float(np.sum(delta)/n),
          "added_mae_ci95":[float(x) for x in interval],"p95_speedup":float(speed),
          "baseline_adequate_on_this_split":acceptable(statistics[chosen]),
          "screen_pass":bool(acceptable(statistics[chosen]) and acceptable(statistics["hybrid"]) and interval[1]<.1 and speed>=2)}
        close(report["comparison"],expected,"comparison")
    else:
        check(report["comparison"] is None and report["bootstrap_indices_sha256"] is None and
              report["qualification_sha256"] is None,"no candidate comparison")
    return {"status":"PASS","rows":n,"methods":list(records),"report_sha256":digest(report_path),
            "data_manifest_sha256":digest(data/"manifest.json"),"prediction_receipt_sha256":digest(pred/"receipt.json"),
            "checks":"saved hashes, row pairing, flags, operational failures, fit limits, metrics, latency, reference selection, paired interval and gates",
            "limits":"No inference, fresh timing, training, or proof of instrument usefulness."}

def main():
    p=argparse.ArgumentParser()
    for key in ("data","predictions","report","report-sha256","out"):p.add_argument("--"+key,required=True)
    p.add_argument("--qualification");args=p.parse_args()
    target=Path(args.out)
    if target.exists():raise FileExistsError(target)
    try:result=verify(args)
    except Exception as error:
        target.write_text(json.dumps({"status":"FAIL","error":str(error)},indent=2)+"\n")
        raise
    with target.open("x") as f:json.dump(result,f,indent=2,allow_nan=False);f.write("\n")
    print("RESULT: PASS")
if __name__=="__main__":main()
