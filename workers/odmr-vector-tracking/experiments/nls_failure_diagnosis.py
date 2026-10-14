"""Task 5: bounded historical diagnosis and dev-only cold-acquisition comparison.

No comparison root manifest, val, or final data is opened. Truth is used for scoring
only on dev. The historical cohort explicitly retains the published truth-at-t0 seed.
Classification flags are diagnostic observations, not established causal explanations.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import types

import h5py
import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from odmr_vector_tracking.evaluation.metrics import (  # noqa: E402
    crossing_events, full_vector_lock, full_vector_lock_stats, physical_line_index,
)
from odmr_vector_tracking.evaluation.rows import fieldcone_metrics_row  # noqa: E402
from odmr_vector_tracking.tracking.nls_baseline import NLSTracker  # noqa: E402

BASE = "ba640fc2b8303ef0c0dc7f6506b8152fd0635e75"
MODULE = "src/odmr_vector_tracking/tracking/nls_baseline.py"


def digest(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def frozen_module():
    source = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{BASE}:{MODULE}"], text=True)
    module = types.ModuleType("task5_frozen_nls")
    exec(compile(source, f"git:{BASE}:{MODULE}", "exec"), module.__dict__)
    return module, hashlib.sha256(source.encode()).hexdigest()


def observed_exchange(tracked, truth_lines, collision, linewidth):
    """A resolved reciprocal assignment swap across a labeled collision window."""
    assignment = physical_line_index(tracked, truth_lines, linewidth)
    for start, end in crossing_events(collision):
        before = assignment[max(0,start-5):start]
        after = assignment[end+1:end+6]
        if not len(before) or not len(after):
            continue
        def mode(window):
            result = []
            for column in window.T:
                values, counts = np.unique(column,return_counts=True)
                best = int(np.argmax(counts))
                result.append(int(values[best]) if counts[best] > len(column)/2 else -1)
            return result
        pre, post = mode(before), mode(after)
        for a in range(len(pre)):
            for b in range(a+1,len(pre)):
                if pre[a] >= 0 and pre[b] >= 0 and pre[a] != pre[b]:
                    if post[a] == pre[b] and post[b] == pre[a]:
                        return True
    return False


def score(truth, prediction, bias, dt):
    """Apply the registered fallback and loss accounting before shared metrics."""
    original = np.asarray(prediction,dtype=float)
    missing = ~np.isfinite(original).all(axis=1)
    # Zero vectors have undefined direction and are treated as no usable estimate.
    missing |= np.linalg.norm(original,axis=1) < 1e-12
    fixed = original.copy()
    previous = np.asarray(bias,dtype=float)
    for t in range(len(fixed)):
        if missing[t]:
            fixed[t] = previous
        else:
            previous = fixed[t].copy()
    row = fieldcone_metrics_row(truth,fixed,dt_s=dt)
    lock = full_vector_lock(truth,fixed) & ~missing
    row.update(full_vector_lock_stats(lock))
    row["lost"] = bool(row["lost"] or missing.mean() > .1)
    row.update(n_valid_frames=int((~missing).sum()), nonfinite_frames=int(missing.sum()),
               never_acquired_first20=not bool(lock[:20].any()))
    return row


def run_frozen(module, spectra, initial, options):
    """Instrument solver/decode calls without changing frozen estimator arithmetic."""
    tracker = module.NLSTracker(**options)
    solver, decode = module.least_squares, module.blue_invert_field
    solve_times, decode_times, residuals = [], [], []
    def timed_solver(*args,**kwargs):
        t=time.perf_counter(); result=solver(*args,**kwargs)
        solve_times.append(time.perf_counter()-t)
        residuals.append(float(np.sqrt(np.mean(result.fun**2))))
        return result
    def timed_decode(*args,**kwargs):
        t=time.perf_counter(); result=decode(*args,**kwargs)
        decode_times.append(time.perf_counter()-t)
        return result
    module.least_squares, module.blue_invert_field = timed_solver, timed_decode
    started=time.perf_counter()
    try:
        result=tracker.run(spectra,initial)
    finally:
        module.least_squares,module.blue_invert_field=solver,decode
    total=time.perf_counter()-started
    samples=np.asarray(solve_times)+np.asarray(decode_times)
    # The legacy run fits every frame then decodes every frame. Exact instrumented
    # solver + decode samples omit Python bookkeeping; charge that total to frame zero.
    samples[0]+=max(0,total-float(samples.sum()))
    return result,dict(frame_seconds=samples.tolist(),residual_rms=residuals)


def summarize(rows):
    losses=[row for row in rows if row["lost"]]
    flags=collections.Counter(flag for row in losses for flag in row["diagnostic_flags"])
    return dict(n_sequences=len(rows), lost_sequences=len(losses),
        lost_rate=len(losses)/len(rows),
        lock_fraction=float(np.mean([r["lock_frac"] for r in rows])),
        angular_p90_of_sequence_p90_deg=float(np.percentile([r["ae_p90_deg"] for r in rows],90)),
        mean_sequence_rmse_mT=1000*float(np.mean([r["rmse_T"] for r in rows])),
        nonfinite_frames=sum(r["nonfinite_frames"] for r in rows),
        sequences_with_nonfinite=sum(r["nonfinite_frames"]>0 for r in rows),
        diagnostic_flag_counts=dict(flags),
        unclassified_lost=sum(not r["diagnostic_flags"] for r in losses),
        linewidth_probes_pending=sum(r["lost"] and not r["linewidth_probe_complete"] for r in rows))


def evaluate(args):
    if args.cpu is not None:
        if args.cpu not in os.sched_getaffinity(0):
            raise ValueError(f"CPU {args.cpu} is not allowed")
        os.sched_setaffinity(0,{args.cpu})
    began=time.monotonic(); cpu_began=time.process_time()
    original,source_hash=frozen_module()
    from odmr_vector_tracking.tracking.acquisition import acquire_centers_with_diagnostics
    historical=ROOT/"data/sequence_eval_fieldcone_v1"
    dev=[ROOT/f"data/comparison_test_v1/dev/clean/seed_{i}" for i in range(args.dev_seeds)]
    cohorts=[("historical_fieldcone_120_legacy_truth_init",[historical],True),
             ("dev_clean_cold_acquisition",dev,False)]
    result={"created_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
        "base_commit":BASE,"frozen_nls_sha256":source_hash,"repaired_nls_sha256":digest(ROOT/MODULE),
        "script_sha256":digest(__file__),"environment":{"python":sys.version,
        "numpy":np.__version__,"scipy":scipy.__version__,"platform":platform.platform(),
        "processor":platform.processor(),"affinity":sorted(os.sched_getaffinity(0)),
        "thread_limits":{k:os.environ.get(k) for k in ("OPENBLAS_NUM_THREADS","OMP_NUM_THREADS","MKL_NUM_THREADS")}},
        "configuration":{"E1":"frozen pre-Task5 module, all published defaults",
        "E2":{"multi_start":True,"profile":"lorentzian","estimate_linewidth":True},
        "linewidth":"manifest rendered linewidth, else intrinsic; estimation only if both absent",
        "latency":"solver + decode samples; initialization and Python bookkeeping charged to first frame; one warmup sequence per estimator/cohort excluded",
        "classification":"Nonexclusive indicators on lost sequences; residual threshold is cohort/estimator median x3, not proof of a local minimum. Width changes test sensitivity, not causation.",
        "caps":{"cpu_seconds":args.cpu_budget,"wall_seconds":args.wall_budget}},
        "cohorts":{},"parity_checks":[]}
    result["shared_acquisition_sha256"]=digest(ROOT/"src/odmr_vector_tracking/tracking/acquisition.py")
    result["protocol_sha256"]=digest(ROOT/"docs/comparison_study_protocol_2026-10.md")
    result["configuration"]["line_depths"]="None for both E1 and E2; source depths predate augmentation and are not permitted calibration"
    def remaining():
        return time.process_time()-cpu_began<args.cpu_budget and time.monotonic()-began<args.wall_budget
    def save():
        result["elapsed_wall_s"]=time.monotonic()-began
        result["elapsed_cpu_s"]=time.process_time()-cpu_began
        args.output.parent.mkdir(parents=True,exist_ok=True)
        temporary=args.output.with_suffix(".tmp")
        temporary.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
        temporary.replace(args.output)
    for label,paths,truth_init in cohorts:
        cohort={"initialization":"true frame0 centers; historical diagnostic only, ineligible comparison" if truth_init else "shared observed frame0 detector plus fixed bias; no truth",
                "datasets":[],"rows":{"E1":[],"E2":[]},"summary":{},"latency":{}}
        result["cohorts"][label]=cohort
        timings={"E1":[],"E2":[]}; warm=False
        pending=[]
        for directory in paths:
            manifest=json.loads((directory/"manifest.json").read_text())
            dataset=directory/"dataset.h5"
            cohort["datasets"].append({"path":str(directory.relative_to(ROOT)),"dataset_sha256":digest(dataset),
              "dataset_md5":digest(dataset,"md5"),"manifest_sha256":digest(directory/"manifest.json"),
              "manifest_data_md5":manifest.get("data_md5")})
            width=manifest.get("linewidth_rendered_Hz") or manifest.get("linewidth_Hz")
            bias=np.asarray(manifest["bias_direction_uvw"],dtype=float)
            bias*=float(manifest["bias_B0_T"])/np.linalg.norm(bias)
            with h5py.File(dataset,"r") as stream:
                data=stream["test"];frequencies=data["frequencies"][:]
                options=dict(frequencies=frequencies,linewidth_Hz=width,line_depths=None)
                for index in range(min(len(data["spectra"]),args.limit or 10**9)):
                    if not remaining():
                        result["incomplete_reason"]="CPU or wall budget reached before all sequences";save();return result
                    spectra=np.asarray(data["spectra"][index],dtype=float)
                    acq_t=time.perf_counter()
                    if truth_init:
                        initial=data["resonance_freqs"][index,0];acq={"legacy_truth_init":True}
                    else:
                        initial,acq=acquire_centers_with_diagnostics(spectra[0],frequencies,
                            linewidth_Hz=width,bias_field_t=bias)
                    acq_time=time.perf_counter()-acq_t
                    if not warm:
                        plain=original.NLSTracker(**options).run(spectra,initial)
                        current=NLSTracker(**options).run(spectra,initial)
                        equal={name:bool(np.array_equal(getattr(plain,name),getattr(current,name),equal_nan=True))
                            for name in ("tracked_freqs","pred_axis","pred_transition","locked","B_est")}
                        if not all(equal.values()):raise RuntimeError("E1 parity failed")
                        result["parity_checks"].append({"cohort":label,"all_arrays_exact":equal,
                            "frozen_prediction_sha256":hashlib.sha256(plain.B_est.tobytes()).hexdigest()})
                        NLSTracker(**options,multi_start=True,estimate_linewidth=True).run(spectra,initial)
                        warm=True
                    for estimator in ("E1","E2"):
                        if estimator=="E1":
                            estimate,diagnostics=run_frozen(original,spectra,initial,options)
                        else:
                            tracker=NLSTracker(**options,multi_start=True,estimate_linewidth=True)
                            estimate=tracker.run(spectra,initial);diagnostics=tracker.diagnostics_
                        truth=data["B_true"][index]; truth_lines=data["resonance_freqs"][index]
                        row=score(truth,estimate.B_est,bias,float(manifest["dt_s"]))
                        row.update(replicate=directory.name,sequence_index=index,
                            acquisition=acq,residual_rms_median=float(np.median(diagnostics["residual_rms"])),
                            exchange_swap_observed=observed_exchange(estimate.tracked_freqs,truth_lines,
                                data["collision_mask"][index],width),diagnostic_flags=[],
                            linewidth_probe_complete=not row["lost"],linewidth_probes={})
                        cohort["rows"][estimator].append(row)
                        samples=np.asarray(diagnostics["frame_seconds"]);samples[0]+=acq_time
                        timings[estimator].extend(samples.tolist())
                        if row["lost"]:
                            pending.append((directory,index,estimator,row))
                    print(json.dumps({"cohort":label,"replicate":directory.name,"sequence":index,
                        "E1_lost":cohort["rows"]["E1"][-1]["lost"],
                        "E2_lost":cohort["rows"]["E2"][-1]["lost"]}),flush=True)
                    save()
        # Width sensitivity reruns are diagnostic, never used to select E2 settings.
        for directory,index,estimator,row in pending:
            if not remaining():break
            manifest=json.loads((directory/"manifest.json").read_text())
            width=manifest.get("linewidth_rendered_Hz") or manifest["linewidth_Hz"]
            bias=np.asarray(manifest["bias_direction_uvw"],dtype=float)
            bias*=manifest["bias_B0_T"]/np.linalg.norm(bias)
            with h5py.File(directory/"dataset.h5","r") as stream:
                data=stream["test"];spectra=data["spectra"][index];frequencies=data["frequencies"][:]
                # Keep the original acquisition seeds fixed while changing fit width only.
                initial=(data["resonance_freqs"][index,0] if truth_init else
                    acquire_centers_with_diagnostics(spectra[0],frequencies,linewidth_Hz=width,bias_field_t=bias)[0])
                for factor in (.5,2.):
                    if not remaining():break
                    options=dict(frequencies=frequencies,linewidth_Hz=width*factor,
                                 line_depths=None,max_step_lw=6/factor)
                    tracker=(original.NLSTracker(**options) if estimator=="E1" else
                             NLSTracker(**options,multi_start=True,estimate_linewidth=True))
                    estimate=tracker.run(spectra,initial)
                    row["linewidth_probes"][str(factor)]=score(data["B_true"][index],estimate.B_est,bias,manifest["dt_s"])["lost"]
                row["linewidth_probe_complete"]=len(row["linewidth_probes"])==2
        for estimator,rows in cohort["rows"].items():
            median=float(np.median([r["residual_rms_median"] for r in rows]))
            for row in rows:
                if not row["lost"]:continue
                flags=row["diagnostic_flags"]
                if row["never_acquired_first20"]:flags.append("never_acquired")
                if row["exchange_swap_observed"]:flags.append("exchange_swap")
                if row["residual_rms_median"]>3*median:flags.append("local_minimum")
                if any(value!=row["lost"] for value in row["linewidth_probes"].values()):flags.append("wrong_linewidth")
            cohort["summary"][estimator]=summarize(rows)
            cohort["latency"][estimator]={"median_ms":1000*float(np.median(timings[estimator])),
                "p90_ms":1000*float(np.percentile(timings[estimator],90)),"frames":len(timings[estimator])}
        save()
    result["complete"]=all(not s["linewidth_probes_pending"] for c in result["cohorts"].values() for s in c["summary"].values())
    save();return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=ROOT/"docs/nls_baseline_diagnosis_2026-10.json")
    parser.add_argument("--limit",type=int,help="bounded pilot sequence count per dataset")
    parser.add_argument("--dev-seeds",type=int,choices=(1,2,3),default=3)
    parser.add_argument("--cpu",type=int,default=1)
    parser.add_argument("--cpu-budget",type=float,default=2600)
    parser.add_argument("--wall-budget",type=float,default=3600)
    args=parser.parse_args()
    if args.limit is not None and args.limit<1:parser.error("--limit must be positive")
    result=evaluate(args)
    print(json.dumps({"complete":result.get("complete",False),"elapsed_wall_s":result["elapsed_wall_s"],
                      "summary":{k:v["summary"] for k,v in result["cohorts"].items()}},indent=2))
    return 0 if result.get("complete") else 2


if __name__=="__main__":raise SystemExit(main())
