"""Frozen scalar evaluation; validation and final require hash-bound custody releases."""
import argparse, datetime, json, os, sys, time
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from estimators import (GRID,TRAIN_MEAN,TRAIN_MEDIAN,robust_fit,edge_ols,
    likelihood_magnitude,checked_fallback,metrics,paired_ci,prior_median)
from models import sha,module,records,DirectModels
from gates import authorize,verify_sources
from decisions import decide,final_decision
from timing import measure
CELLS=("clean","realistic_anchor","wide_lines","low_snr","negative_slope","negative_offset","higher_contrast")

def dump(path,data):
    def clean(x):
        if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
        if isinstance(x,list):return [clean(v) for v in x]
        if isinstance(x,float) and not np.isfinite(x):return None
        return x
    Path(path).write_text(json.dumps(clean(data),indent=2,allow_nan=False)+"\n")
def preflight(data,partition="dev"):
    data=Path(data)
    if data.name not in (("dev","dev-r2") if partition=="dev" else (partition,)):raise ValueError("development runner refuses validation and final" if partition=="dev" else "partition path mismatch")
    if data.is_symlink() or data.stat().st_mode&0o222:raise ValueError("development directory is not sealed")
    path=data/"manifest.json"
    if path.is_symlink() or path.stat().st_mode&0o222:raise ValueError("manifest is not sealed")
    m=json.loads(path.read_text())
    if m.get("partition")!=data.name or not m.get("single_orientation"):raise ValueError("wrong partition/cohort")
    if m["rows_per_cell"]!={"dev":256,"val":512,"final":1024}[partition]:raise ValueError("partition size mismatch")
    if set(m["cells"])!=set(CELLS):raise ValueError("condition set changed")
    if len(set(m["field_ids"]))!=m["rows_per_cell"]:raise ValueError("duplicate fields")
    if len(m["nuisance_group_ids"])!=m["rows_per_cell"]:raise ValueError("missing nuisance groups")
    for r in m["cells"].values():
        p=data/r["file"]
        if Path(r["file"]).name!=r["file"] or p.is_symlink() or p.stat().st_mode&0o222:
            raise ValueError("unsafe or unsealed payload path")
    return m
def raw_accounting(prediction,raw_magnitude,fallback,hard,amb,truth,raw_projection=None):
    prediction=np.asarray(prediction);raw=np.asarray(raw_magnitude);fallback=np.asarray(fallback,bool)
    support=np.isfinite(raw)&((raw<20)|(raw>70))
    invalid=(~np.isfinite(raw))|support
    projection_counts={}
    if raw_projection is not None:
        proj=np.asarray(raw_projection)
        proj_bad=(~np.isfinite(proj))|((proj<0)|(proj>70))
        invalid|=proj_bad
        projection_counts=dict(nonfinite_raw_projection_count=int((~np.isfinite(proj)).sum()),
            raw_projection_support_violations=int((np.isfinite(proj)&((proj<0)|(proj>70))).sum()))
    valid=~(fallback|hard|amb|invalid)
    result=dict(fallback_count=int(fallback.sum()),common_input_hard_invalid_count=int(hard.sum()),
        method_invalid_count=int(invalid.sum()),nonfinite_raw_count=int((~np.isfinite(raw)).sum()),
        raw_output_support_violations=int(support.sum()),ambiguous_count=int(amb.sum()),
        reliable_valid_count=int(valid.sum()),n=len(raw),
        accepted_only=metrics(prediction[valid],np.asarray(truth)[valid]) if valid.any() else None,**projection_counts)
    return result,valid

def reserve_evaluation(out,partition,manifest_hash,freeze_hash,frozen):
    expected=Path(frozen["evaluation_root"])/("results-"+partition)
    if Path(out).resolve()!=expected.resolve():raise ValueError("output differs from frozen evaluation root")
    access=expected.parent/(partition.upper()+"_EVALUATOR_ACCESS.json")
    if access.exists():raise ValueError("reserved partition already consumed by evaluator")
    if expected.exists():raise ValueError("reserved output already exists")
    expected.parent.mkdir(parents=True,exist_ok=True)
    with access.open("x") as stream:
        json.dump(dict(partition=partition,manifest_sha256=manifest_hash,freeze_sha256=freeze_hash,status="in_progress"),stream)
    return access

def run(a):
    start=time.monotonic()
    m=preflight(a.data,a.mode)
    if sha(a.data/"manifest.json")!=a.data_manifest_sha256:raise ValueError("manifest differs from accepted custody delivery")
    frozen=None
    if a.mode!="dev":
        if a.limit or not a.timing_isolated:raise ValueError("reserved evaluation requires full rows and isolated timing")
        if not all((a.freeze,a.freeze_sha256,a.release,a.release_sha256,a.gate_document,a.access_receipt)):
            raise ValueError("missing pinned custody arguments")
        frozen=authorize(a.data,a.mode,a.freeze,a.freeze_sha256,a.release,a.release_sha256,a.gate_document,a.access_receipt)
    warmups={}
    if not a.limit:
        if not a.warmup_data or not a.warmup_manifest_sha256:raise ValueError("fixed development warm-up inputs required")
        wm=preflight(a.warmup_data,"dev")
        if sha(a.warmup_data/"manifest.json")!=a.warmup_manifest_sha256:raise ValueError("warm-up manifest hash mismatch")
        if frozen and a.warmup_manifest_sha256!=frozen["development_manifest_sha256"]:
            raise ValueError("warm-up differs from frozen development manifest")
        for cell,record in wm["cells"].items():
            payload=a.warmup_data/record["file"]
            if sha(payload)!=record["sha256"]:raise ValueError("warm-up payload hash mismatch")
            with np.load(payload,allow_pickle=False) as z:warmups[cell]=np.array(z["spectra"][:4])
    chosen=records(a.model_manifest)
    if frozen and chosen!=frozen["model_records"]:raise ValueError("candidate identities differ from frozen set")
    evaluation_access=reserve_evaluation(a.out,a.mode,a.data_manifest_sha256,a.freeze_sha256,frozen) if frozen else None
    if a.out.exists():raise ValueError("existing output refuses overwrite")
    # Artifact identities and metadata precede the exclusive development access receipt.
    a.out.mkdir(parents=True)
    receipt=dict(partition=a.mode,freeze_sha256=a.freeze_sha256,custody_release_sha256=a.release_sha256,started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        manifest_sha256=sha(a.data/"manifest.json"),model_records=chosen,
        scope="synthetic scalar evaluation",warmup_manifest_sha256=a.warmup_manifest_sha256,sources={p.name:sha(p) for p in HERE.glob("*.py")})
    with (a.out/"ACCESS.json").open("x") as stream:json.dump(receipt,stream,indent=2)
    for r in m["cells"].values():
        if sha(a.data/r["file"])!=r["sha256"]:raise ValueError("development payload hash changed")
    repo=HERE.parents[1]
    pidmod=module("scalar_repair_pid",repo/"src/odmr_edge_ml/evaluation/pid_proxy.py")
    old=module("scalar_repair_original_fit",repo/"experiments/scalar_fit_baseline.py")
    models=DirectModels(repo,chosen)
    detector=pidmod.DerivativeZeroCrossingPID(GRID)
    summary={};fit_seconds=[];grid_seconds=[];rows_seen=0;shared_identity=None
    for ci,cell in enumerate(CELLS):
        remaining=a.limit-rows_seen if a.limit else m["rows_per_cell"]
        n=min(m["rows_per_cell"],max(0,remaining//(len(CELLS)-ci))) if a.limit else m["rows_per_cell"]
        if n==0:continue
        with np.load(a.data/m["cells"][cell]["file"],allow_pickle=False) as z:
            np.testing.assert_array_equal(z["frequencies_hz"],GRID)
            np.testing.assert_array_equal(z["sample_seeds"],m["sample_seeds"])
            fulltruth=np.asarray(z["truth_vectors_T"])
            if shared_identity is None:shared_identity=fulltruth.copy()
            else:np.testing.assert_array_equal(fulltruth,shared_identity)
            spectra=np.asarray(z["spectra"][:n]);truth=np.linalg.norm(fulltruth[:n],axis=1)*1e6
        groups=np.asarray(m["nuisance_group_ids"][:n])
        if spectra.shape!=(n,100) or not np.isfinite(spectra).all():raise ValueError("invalid development data")
        fits=[robust_fit(y) for y in spectra]
        fit_seconds.extend(f.seconds for f in fits)
        hard=np.array([f.hard_invalid for f in fits]);amb=np.array([f.ambiguous and not f.hard_invalid for f in fits])
        rawlocks=np.array([detector.estimate(y).lock_bin for y in spectra])
        rawpid=np.array([detector.estimate(y).b_mag_uT for y in spectra])
        edge=np.array([edge_ols(y)[0] for y in spectra])
        edgelocks=np.array([detector.estimate(y).lock_bin for y in edge])
        fitted=spectra-np.array([f.slope_per_MHz for f in fits])[:,None]*((GRID-2.87e9)/1e6)[None,:]
        fitlocks=np.array([f.lock_bin for f in fits])
        saved={"truth_uT":truth,"group_ids":groups,"field_ids":np.asarray(m["field_ids"][:n]),
            "sample_seeds":np.asarray(m["sample_seeds"][:n]),"common_hard_invalid":hard,"common_ambiguous":amb,
            "raw_projection_robust_fit":np.array([f.raw_projection_uT for f in fits])}
        predictions={"training_mean":np.full(n,TRAIN_MEAN),"training_median":np.full(n,TRAIN_MEDIAN),
            "unchanged_PID":rawpid,"robust_prior_fit":np.array([f.prediction_uT for f in fits])}
        fallback={"robust_prior_fit":hard.copy()};flags={};quant={}
        saved["raw__robust_prior_fit"]=np.array([f.raw_magnitude_uT for f in fits])
        oldpred=[];oldbad=[];oldraw=[];oldmag=[]
        for row in spectra:
            val=float("nan");magnitude=float("nan")
            try:
                val,_=old.fit_field_magnitude(row,GRID)
                value=prior_median(val);magnitude=value;bad=False
            except (RuntimeError,ValueError,FloatingPointError):
                value=TRAIN_MEDIAN;bad=True
            oldpred.append(value);oldbad.append(bad);oldraw.append(val);oldmag.append(magnitude)
        predictions["original_prior_fit"]=np.array(oldpred);fallback["original_prior_fit"]=np.array(oldbad)
        saved["raw_projection_original_fit"]=np.array(oldraw)
        saved["raw__original_prior_fit"]=np.array(oldmag)
        saved["raw__unchanged_PID"]=rawpid
        fallback["unchanged_PID"]=~np.isfinite(rawpid)
        predictions["unchanged_PID"]=np.where(fallback["unchanged_PID"],TRAIN_MEDIAN,rawpid)
        grid=[]
        for row,f in zip(spectra,fits):
            t=time.perf_counter();grid.append(likelihood_magnitude(row,f));grid_seconds.append(time.perf_counter()-t)
        predictions["conditional_likelihood"]=np.array([v["prediction_uT"] for v in grid])
        fallback["conditional_likelihood"]=np.array([v["hard_invalid"] for v in grid])
        saved["likelihood_interval90_uT"]=np.array([v["interval90_uT"] for v in grid])
        saved["raw__conditional_likelihood"]=np.array([v["raw_prediction_uT"] for v in grid])
        for policy,signal,locks in (("identity",spectra,rawlocks),("edge_ols",edge,edgelocks),("joint_fit",fitted,fitlocks)):
            raw,stats=models.predict(signal,locks);quant[policy]=stats
            for name,value in raw.items():
                label=policy+"__"+name
                # Identity is a descriptive unchanged control, not a repaired candidate.
                if policy=="identity":
                    pred=value;bad=~np.isfinite(value)
                    if bad.any():pred=np.where(bad,TRAIN_MEDIAN,pred)
                else:
                    pred,bad=checked_fallback(value,hard)
                predictions[label]=pred;fallback[label]=bad;saved["raw__"+label]=value
        scored={k:metrics(v,truth) for k,v in predictions.items()}
        for k,v in predictions.items():
            saved["pred__"+k]=v
            if k in fallback:
                raw_value=saved.get("raw__"+k,v)
                projection=saved.get("raw_projection_original_fit") if k=="original_prior_fit" else (
                    saved.get("raw_projection_robust_fit") if k=="robust_prior_fit" else None)
                flags[k],valid=raw_accounting(v,raw_value,fallback[k],hard,amb,truth,projection)
                saved["fallback__"+k]=fallback[k];saved["reliable_valid__"+k]=valid
        disagreement={}
        for policy in ("identity","edge_ols","joint_fit"):
            disagreement[policy]={}
            for seed in (42,20261014,20261015):
                fp=saved[f"raw__{policy}__C_direct_seed{seed}__fp32"]
                qi=saved[f"raw__{policy}__C_direct_seed{seed}__int8"]
                finite=np.isfinite(fp)&np.isfinite(qi);delta=abs(fp[finite]-qi[finite])
                disagreement[policy][str(seed)]=dict(finite_pairs=int(finite.sum()),n=n,
                    mean_abs_uT=float(delta.mean()) if len(delta) else None,
                    p95_abs_uT=float(np.quantile(delta,.95)) if len(delta) else None,
                    max_abs_uT=float(delta.max()) if len(delta) else None)
        comparisons={}
        pipeline_timing=measure(spectra,models,detector,warmups[cell],count=16) if not a.limit else {}
        decision_metrics={}
        losses_by_label={}
        for name in ("robust_prior_fit","conditional_likelihood"):
            losses_by_label[name]=abs(predictions[name]-truth)
            decision_metrics[name]=dict(mae_uT=scored[name]["mae_uT"],p90_abs_uT=scored[name]["p90_abs_uT"],
                hard_invalid_fraction=float(fallback[name].mean()),
                valid_fraction=float((~(fallback[name]|hard|amb)).mean()),
                median_pipeline_seconds=pipeline_timing.get(name,{}).get("median_pipeline_seconds",0.))
        for policy in ("edge_ols","joint_fit"):
            for precision in ("fp32","int8"):
                label=policy+"__"+precision
                names=[f"{policy}__C_direct_seed{seed}__{precision}" for seed in (42,20261014,20261015)]
                loss=np.mean([abs(predictions[k]-truth) for k in names],axis=0)
                losses_by_label[label]=loss
                decision_metrics[label]=dict(mae_uT=float(loss.mean()),p90_abs_uT=float(np.quantile(loss,.9)),
                    hard_invalid_fraction=float(np.mean([fallback[k].mean() for k in names])),
                    valid_fraction=float(np.mean([(~(fallback[k]|hard|amb)).mean() for k in names])),
                    all_seeds_reliable=all((~(fallback[k]|hard|amb)).mean()>=.95 for k in names),
                    median_pipeline_seconds=float(np.mean([pipeline_timing.get(k,{}).get("median_pipeline_seconds",0.) for k in names])))
        if not a.limit:
            for policy in ("edge_ols","joint_fit"):
                for precision in ("fp32","int8"):
                    labels=[f"{policy}__C_direct_seed{s}__{precision}" for s in (42,20261014,20261015)]
                    losses=np.mean([abs(predictions[k]-truth) for k in labels],axis=0)
                    for base in ("training_mean","training_median","robust_prior_fit","conditional_likelihood"):
                        comparisons[f"{policy}__{precision}_minus_{base}"]=paired_ci(losses-abs(predictions[base]-truth),groups)
            for name in ("robust_prior_fit","conditional_likelihood"):
                for base in ("training_mean","training_median"):
                    comparisons[name+"_minus_"+base]=paired_ci(abs(predictions[name]-truth)-abs(predictions[base]-truth),groups)
        # Per-seed gates and INT8 degradation use the same paired group draws.
        seed_gates={}
        if not a.limit:
            for policy in ("edge_ols","joint_fit"):
                for seed in (42,20261014,20261015):
                    for precision in ("fp32","int8"):
                        label=f"{policy}__C_direct_seed{seed}__{precision}"
                        per_base={base:paired_ci(abs(predictions[label]-truth)-abs(predictions[base]-truth),groups)
                            for base in ("training_mean","training_median")}
                        seed_gates[label]=dict(prediction_passed=bool(scored[label]["p90_abs_uT"]<=25 and
                            all(v["ci95_uT"][1]<-.5 for v in per_base.values())),paired_constants=per_base,
                            reliable_valid_fraction=flags[label]["reliable_valid_count"]/n)
                    fp=f"{policy}__C_direct_seed{seed}__fp32";qi=f"{policy}__C_direct_seed{seed}__int8"
                    comparisons[f"{policy}_seed{seed}_int8_minus_fp32"]=paired_ci(abs(predictions[qi]-truth)-abs(predictions[fp]-truth),groups)
                comparisons[policy+"_mean_int8_minus_fp32"]=paired_ci(
                    losses_by_label[policy+"__int8"]-losses_by_label[policy+"__fp32"],groups)
                for precision in ("fp32","int8"):
                    decision_metrics[policy+"__"+precision]["all_seeds_reliable"] &= all(
                        seed_gates[f"{policy}__C_direct_seed{seed}__{precision}"]["prediction_passed"] for seed in (42,20261014,20261015))
        path=a.out/(cell+"_predictions.npz");np.savez_compressed(path,**saved)
        summary[cell]=dict(n=n,metrics=scored,flags=flags,quantization=quant,paired_comparisons=comparisons,
            decision_metrics=decision_metrics,seed_gates=seed_gates,pipeline_timing=pipeline_timing,
            fp32_int8_disagreement=disagreement,warmup_manifest_sha256=a.warmup_manifest_sha256,
            predictions_sha256=sha(path),scope=a.mode+"; conditional likelihood intervals uncalibrated")
        dump(a.out/(cell+"_fit_diagnostics.json"),[f.as_dict() for f in fits])
        dump(a.out/(cell+"_metrics.json"),summary[cell])
        rows_seen+=n
        print(json.dumps(dict(cell=cell,n=n,fit_mae=scored["robust_prior_fit"]["mae_uT"],
            likelihood_mae=scored["conditional_likelihood"]["mae_uT"],hard_invalid=int(hard.sum()),
            ambiguous=int(amb.sum()))),flush=True)
    times=dict(rows=rows_seen,fit_median_s=float(np.median(fit_seconds)),fit_p95_s=float(np.quantile(fit_seconds,.95)),
        fit_total_s=float(sum(fit_seconds)),grid_total_s=float(sum(grid_seconds)))
    times["projected_final_fit_grid_single_core_s"]=7168*(sum(fit_seconds)+sum(grid_seconds))/rows_seen
    if frozen:
        verify_sources(frozen)
        if records(a.model_manifest)!=frozen["model_records"]:raise ValueError("model artifact drift during campaign")
    selection=decide(summary) if not a.limit else None
    if a.mode=="final":selection=frozen["selection"]
    report=dict(status="complete",partition=a.mode,freeze_sha256=a.freeze_sha256,
        scope="synthetic scalar; prior-dependent magnitude",cells=summary,timing=times,
        selection=selection,validation_can_proceed=bool(a.mode=="val" and selection["can_proceed"]),
        final_decision=final_decision(summary,selection) if a.mode=="final" else None,
        seconds=time.monotonic()-start,manifest_sha256=receipt["manifest_sha256"])
    dump(a.out/"SUMMARY.json",report);dump(a.out/"RECEIPT.json",dict(receipt,status="complete",seconds=report["seconds"],summary_sha256=sha(a.out/"SUMMARY.json")))
    if evaluation_access:
        completed=json.loads(evaluation_access.read_text())
        dump(evaluation_access,dict(completed,status="complete",summary_sha256=sha(a.out/"SUMMARY.json")))
    print(json.dumps(dict(complete=True,seconds=report["seconds"],timing=times)),flush=True)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=("dev","val","final"),default="dev")
    p.add_argument("--data-manifest-sha256",required=True)
    p.add_argument("--data",type=Path,required=True);p.add_argument("--model-manifest",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--limit",type=int,default=0)
    p.add_argument("--freeze",type=Path);p.add_argument("--freeze-sha256")
    p.add_argument("--release",type=Path);p.add_argument("--release-sha256")
    p.add_argument("--gate-document",type=Path);p.add_argument("--access-receipt",type=Path)
    p.add_argument("--warmup-data",type=Path);p.add_argument("--warmup-manifest-sha256")
    p.add_argument("--timing-isolated",action="store_true",help="operator confirms competing numerical workers are paused")
    a=p.parse_args()
    if any(os.environ.get(k)!="1" for k in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")):
        p.error("run with one numerical thread, preferably through job_receipt.py")
    if a.limit<0 or a.limit>128:p.error("--limit is 0 (full dev) or at most 128 for profiling")
    run(a)
if __name__=="__main__":main()
