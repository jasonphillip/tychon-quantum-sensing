"""Fresh synthetic drift/calibration benchmark; frozen FPGA core stays unchanged."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
CORE = ROOT.parent / "boxcar_readout64.cpp"
MODEL = ROOT.parent / "artifacts/cpu_v2/model.json"
CORE_SHA = "b657467dfe0051d7945851f1bdb4db408b56921f34de55f78e322ae84a003af7"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def alpha_constant(t, delta, drive, kappa, initial=0j):
    rate = kappa / 2 + 1j * delta
    steady = -1j * drive / rate
    return steady + (initial-steady)*np.exp(-rate*np.asarray(t))


def alpha_relax(t, label, event_us, delta, chi, drive, kappa):
    """Prescribed classical qubit jump, continuous conditional cavity amplitude."""
    t = np.asarray(t)
    if label not in (0, 1) or event_us < 0 or kappa <= 0 or np.any(t < 0):
        raise ValueError("invalid conditional cavity domain")
    result = alpha_constant(t, delta+(2*label-1)*chi, drive, kappa)
    if label and np.isfinite(event_us):
        after = t >= event_us
        before_jump = alpha_constant(event_us, delta+chi, drive, kappa)
        result[after] = alpha_constant(t[after]-event_us, delta-chi, drive, kappa, before_jump)
    return result


def rk4_relax(t, label, event, delta, chi, drive, kappa, step=0.0005):
    value, previous, output = 0j, 0.0, []
    for end in t:
        boundaries = [previous]
        if label and previous < event < end:
            boundaries.append(event)
        boundaries.append(float(end))
        for a, b in zip(boundaries[:-1], boundaries[1:]):
            if b == a:
                continue
            state = label if (a+b)/2 < event else 0
            rate = kappa/2+1j*(delta+(2*state-1)*chi)
            def rhs(x):
                return -rate*x-1j*drive
            count = math.ceil((b-a)/step)
            dt = (b-a)/count
            for _ in range(count):
                k1 = rhs(value)
                k2 = rhs(value+dt*k1/2)
                k3 = rhs(value+dt*k2/2)
                k4 = rhs(value+dt*k3)
                value += dt*(k1+2*k2+2*k3+k4)/6
        output.append(value)
        previous = float(end)
    return np.array(output)


def physics_checks(c):
    t = np.arange(c["samples"])*c["sample_interval_us"]
    rows = []
    for label, event, shift in ((0,np.inf,0),(1,np.inf,0),(1,0,0),(1,0.001,-3.7),
                                (1,0.37,3.7),(1,1.274,-3.7),(1,t[-1],0),(1,2,3.7)):
        args = (t,label,event,c["base_detuning_rad_per_us"]+shift,c["base_chi_rad_per_us"],
                c["base_drive_rad_per_us"],c["base_kappa_rad_per_us"])
        error = float(np.max(abs(alpha_relax(*args)-rk4_relax(*args))))
        rows.append({"label":label,"event_us":event if np.isfinite(event) else None,"detuning_shift":shift,"max_error":error})
    return {"passed":all(r["max_error"] <= c["correctness_acceptance"]["independent_piecewise_rk4_max_error"] for r in rows),"cases":rows}


def group_parameters(rng, scenario, c):
    names = ("detuning_add_mhz","kappa_factor","drive_factor","gain","phase_rad","iq_gain","iq_skew",
             "noise_sigma","noise_ar1","t1_us","postcal_phase_rad")
    p = {name:float(rng.uniform(*scenario[name])) for name in names}
    p["offset"] = rng.uniform(*scenario["offset"],2).tolist()
    p["postcal_offset"] = rng.uniform(*scenario["postcal_offset"],2).tolist()
    p["shot_dc_sigma"] = scenario["shot_dc_sigma"]
    p["delta"] = c["base_detuning_rad_per_us"]+2*np.pi*p["detuning_add_mhz"]
    p["drive"] = c["base_drive_rad_per_us"]*p["drive_factor"]
    p["kappa"] = c["base_kappa_rad_per_us"]*p["kappa_factor"]
    return p


def receiver_records(rng, p, c, shots_per_class, postcal=False):
    t = np.arange(c["samples"])*c["sample_interval_us"]
    x, labels, events = [], [], []
    phase = p["phase_rad"]+(p["postcal_phase_rad"] if postcal else 0)
    rotation = np.array([[np.cos(phase),np.sin(phase)],[-np.sin(phase),np.cos(phase)]])
    imbalance = np.array([[1,p["iq_skew"]],[0,p["iq_gain"]]])
    matrix = p["gain"]*rotation@imbalance
    offset = np.array(p["offset"])+(np.array(p["postcal_offset"]) if postcal else 0)
    for label in (0,1):
        for _ in range(shots_per_class):
            event = float(rng.exponential(p["t1_us"])) if label else np.inf
            a = alpha_relax(t,label,event,p["delta"],c["base_chi_rad_per_us"],p["drive"],p["kappa"])
            signal = np.column_stack((a.real,a.imag))@matrix+offset
            noise = rng.normal(size=(len(t),2))
            phi = p["noise_ar1"]
            for k in range(1,len(t)):
                noise[k] = phi*noise[k-1]+np.sqrt(1-phi*phi)*noise[k]
            signal += p["noise_sigma"]*noise+rng.normal(0,p["shot_dc_sigma"],2)
            x.append(signal.reshape(-1)); labels.append(label); events.append(event)
    return np.array(x),np.array(labels,dtype=np.uint8),np.array(events)


def nominal_templates(c):
    t = np.arange(c["samples"])*c["sample_interval_us"]
    templates=[]
    for label in (0,1):
        a=alpha_relax(t,label,np.inf,c["base_detuning_rad_per_us"],c["base_chi_rad_per_us"],c["base_drive_rad_per_us"],c["base_kappa_rad_per_us"])
        templates.append(np.column_stack((a.real,a.imag)))
    return np.array(templates)


def fit_affine(calibration, labels, c):
    """No hidden physical parameters or evaluation labels enter this fit."""
    observed=np.stack([calibration[labels==label].mean(0).reshape(-1,2) for label in (0,1)]).reshape(-1,2)
    nominal=nominal_templates(c).reshape(-1,2)
    design=np.column_stack((nominal,np.ones(len(nominal))))
    fitted,_,rank,_=np.linalg.lstsq(design,observed,rcond=None)
    matrix,offset=fitted[:2],fitted[2]
    sv=np.linalg.svd(matrix,compute_uv=False)
    condition=float(sv[0]/sv[-1]) if sv[-1] else np.inf
    valid=bool(rank==3 and sv[-1]>=c["calibration"]["minimum_singular_value"] and condition<=c["calibration"]["maximum_condition_number"])
    return {"matrix":matrix.tolist(),"offset":offset.tolist(),"condition":condition,"minimum_singular_value":float(sv[-1]),"valid":valid}


def apply_affine(x, fitted):
    if not fitted["valid"]:
        raise ValueError("invalid calibration cannot be silently applied")
    return ((x.reshape(-1,2)-np.array(fitted["offset"]))@np.linalg.inv(np.array(fitted["matrix"]))).reshape(x.shape)


def local_classifiers(x,y,c):
    means=np.stack([x[y==j].mean(0) for j in (0,1)])
    delta=means[1]-means[0]; center=means.mean(0)
    residual=x-means[y]
    covariance=residual.T@residual/(len(y)-2)
    s=c["lda_shrinkage"]
    covariance=(1-s)*covariance+s*np.trace(covariance)/x.shape[1]*np.eye(x.shape[1])
    lda=np.linalg.solve(covariance,delta)
    return {"local_matched_filter":(delta,-float(delta@center)),"local_lda":(lda,-float(lda@center))}


def integer_score(x,model):
    if not np.all(np.isfinite(x)):
        raise ValueError("nonfinite input")
    raw=np.rint(x*2048)
    clipped=np.count_nonzero((raw < -32768)|(raw > 32767))
    q=np.clip(raw,-32768,32767).astype(np.int16)
    weights=np.asarray(model["weight_int16"],dtype=np.int64)
    score=q.astype(np.int64)@weights+model["bias_int64"]
    return q,score,int(clipped)


def summary(rows,scenario,partition):
    selected=[r for r in rows if r["scenario"]==scenario and r["partition"]==partition]
    methods=("raw_boxcar","calibrated_boxcar","local_matched_filter","local_lda")
    out={"groups":len(selected),"shots":sum(r["shots"] for r in selected)}
    for method in methods:
        eligible=[r for r in selected if r[method] is not None]
        correct=sum(r[method] for r in eligible)
        count=sum(r["shots"] for r in eligible)
        out[method]={"correct":correct,"shots":count,"accuracy":correct/count if count else None,
                     "coverage":count/out["shots"] if out["shots"] else 0,
                     "worst_group_accuracy":min((r[method]/r["shots"] for r in eligible),default=None)}
    out["calibration_gain"]=(out["calibrated_boxcar"]["accuracy"]-out["raw_boxcar"]["accuracy"] if out["calibrated_boxcar"]["accuracy"] is not None else None)
    out["relaxed_excited_shots"]=sum(r["relaxed_excited_shots"] for r in selected)
    return out


def write_pack(out,x,scores,labels,meta,c,model):
    pack=out/"board_replay";pack.mkdir()
    x=np.asarray(x,dtype="<i2");scores=np.asarray(scores,dtype="<i8");labels=np.asarray(labels,dtype="u1")
    x.tofile(pack/"inputs_i16.bin");scores.tofile(pack/"expected_scores_i64.bin");labels.tofile(pack/"labels_u8.bin")
    (pack/"records.json").write_text(json.dumps(meta,indent=2)+"\n")
    if not (np.array_equal(x,np.fromfile(pack/"inputs_i16.bin",dtype="<i2").reshape(-1,128)) and np.array_equal(scores,np.fromfile(pack/"expected_scores_i64.bin",dtype="<i8"))):
        raise RuntimeError("export roundtrip failed")
    manifest={"schema":"readout_board_replay_v2","records":len(x),"input_dtype":"int16 little-endian","input_shape":[len(x),128],
              "input_order":"I0,Q0,I1,Q1,...,I63,Q63","input_fraction_bits":11,"input_bytes_per_record":256,
              "output_dtype":"int64 little-endian","output_fraction_bits":25,"output_bytes_per_record":8,
              "decision":"score>=0 means initially excited; agreement with labels is not guaranteed",
              "model_sha256":c["source_model_sha256"],"core_sha256":CORE_SHA,
              "weight_i":model["weight_int16"][0],"weight_q":model["weight_int16"][1],"bias":model["bias_int64"],
              "source":"frozen final synthetic shots; raw and host-calibrated paired views",
              "sha256":{p.name:sha(p) for p in sorted(pack.iterdir()) if p.is_file()}}
    (pack/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    return manifest


def run(c,out):
    start=time.perf_counter()
    if sha(MODEL)!=c["source_model_sha256"] or sha(CORE)!=CORE_SHA:
        raise RuntimeError("frozen model or core changed")
    model=json.loads(MODEL.read_text())
    physics=physics_checks(c)
    (out/"physics.json").write_text(json.dumps(physics,indent=2)+"\n")
    if not physics["passed"]:
        raise RuntimeError("independent physics check failed before dataset generation")
    rows,groups,calmeta=[],[],[]
    eval_x,eval_y,eval_group,eval_events=[],[],[],[]
    cal_x,cal_y,cal_group=[],[],[]
    board_x,board_score,board_y,board_meta=[],[],[],[]
    gid=0
    clipped_total=0
    for si,scenario in enumerate(c["scenarios"]):
        for pi,(partition,count) in enumerate(c["groups_per_partition"].items()):
            for gi in range(count):
                streams=[np.random.default_rng(np.random.SeedSequence(c["seed"],spawn_key=(si,pi,gi,j))) for j in range(3)]
                p=group_parameters(streams[0],scenario,c)
                calibration,cy,_=receiver_records(streams[1],p,c,c["calibration_shots_per_class"],False)
                x,y,events=receiver_records(streams[2],p,c,c["evaluation_shots_per_class"],True)
                fit=fit_affine(calibration,cy,c)
                fit.update(group=gid,scenario=scenario["name"],partition=partition)
                calmeta.append(fit)
                local=local_classifiers(calibration,cy,c)
                xq,score,clipped=integer_score(x,model);clipped_total+=clipped
                row={"group":gid,"scenario":scenario["name"],"partition":partition,"shots":len(y),
                     "raw_boxcar":int(np.sum((score>=0)==y)),"calibrated_boxcar":None,
                     "relaxed_excited_shots":int(np.sum((y==1)&(events<(c["samples"]-1)*c["sample_interval_us"]))) }
                for name,(w,bias) in local.items():
                    row[name]=int(np.sum(((x@w+bias)>=0)==y))
                qcal,scal=None,None
                if fit["valid"]:
                    corrected=apply_affine(x,fit)
                    qcal,scal,clipped=integer_score(corrected,model);clipped_total+=clipped
                    row["calibrated_boxcar"]=int(np.sum((scal>=0)==y))
                rows.append(row);groups.append({"id":gid,"scenario":scenario["name"],"partition":partition,**p})
                eval_x.extend(x);eval_y.extend(y);eval_group.extend([gid]*len(y));eval_events.extend(events)
                cal_x.extend(calibration);cal_y.extend(cy);cal_group.extend([gid]*len(cy))
                if partition=="final":
                    for j in range(len(y)):
                        for mode,q,s in (("raw",xq,score),("calibrated",qcal,scal)):
                            if q is None:
                                continue
                            board_x.append(q[j]);board_score.append(s[j]);board_y.append(y[j])
                            board_meta.append({"record":len(board_x)-1,"group":gid,"scenario":scenario["name"],"shot":j,"mode":mode})
                gid+=1
    np.savez_compressed(out/"evaluation.npz",x=np.array(eval_x),y=np.array(eval_y,dtype=np.uint8),group=np.array(eval_group,dtype=np.int32),event_us=np.array(eval_events))
    np.savez_compressed(out/"calibration.npz",x=np.array(cal_x),y=np.array(cal_y,dtype=np.uint8),group=np.array(cal_group,dtype=np.int32))
    for name,obj in (("groups.json",groups),("calibration_fits.json",calmeta),("group_results.json",rows)):
        (out/name).write_text(json.dumps(obj,indent=2)+"\n")
    summaries={s["name"]:{part:summary(rows,s["name"],part) for part in c["groups_per_partition"]} for s in c["scenarios"]}
    manifest=write_pack(out,board_x,board_score,board_y,board_meta,c,model)
    compiler=shutil.which("c++")
    if not compiler:
        raise RuntimeError("C++ compiler required for reference export proof")
    command=[compiler,"-std=c++11","-O2","-Wall","-Wextra","-Werror",str(ROOT/"replay_reference.cpp"),"-o",str(out/"replay_reference")]
    build=subprocess.run(command,capture_output=True,text=True,check=True)
    run_command=[str(out/"replay_reference"),str(out/"board_replay/inputs_i16.bin"),str(out/"board_replay/expected_scores_i64.bin")]
    execution=subprocess.run(run_command,capture_output=True,text=True,check=True)
    (out/"reference_receipt.json").write_text(json.dumps({"compile_command":command,"command":run_command,"stdout":execution.stdout,"stderr":execution.stderr,"compile_stderr":build.stderr,"exit_code":execution.returncode},indent=2)+"\n")
    thresholds=c["utility_acceptance"]
    nominal=summaries["nominal"]["final"];drift=summaries["receiver_drift"]["final"]
    utility={"nominal_accuracy":nominal["calibrated_boxcar"]["accuracy"]>=thresholds["nominal_calibrated_accuracy_min"],
             "receiver_drift_accuracy":drift["calibrated_boxcar"]["accuracy"]>=thresholds["receiver_drift_calibrated_accuracy_min"],
             "receiver_drift_calibration_gain":drift["calibration_gain"]>=thresholds["receiver_drift_absolute_gain_min"],
             "calibration_coverage":min(nominal["calibrated_boxcar"]["coverage"],drift["calibrated_boxcar"]["coverage"])>=thresholds["nominal_and_drift_calibration_coverage_min"]}
    partitions=[{g["id"] for g in groups if g["partition"]==part} for part in c["groups_per_partition"]]
    separated=all(not(a&b) for i,a in enumerate(partitions) for b in partitions[i+1:])
    metrics={"correctness_passed":bool(physics["passed"] and separated and execution.returncode==0 and sha(CORE)==CORE_SHA and sha(MODEL)==c["source_model_sha256"]),
             "utility_passed":all(utility.values()),"utility_gates":utility,"summaries":summaries,
             "evaluation_shots":len(eval_y),"calibration_shots":len(cal_y),"physical_groups":len(groups),
             "board_replay_records":manifest["records"],"clipped_input_values":clipped_total,
             "invalid_calibration_groups":sum(not g["valid"] for g in calmeta),"elapsed_s":time.perf_counter()-start,
             "scope":"synthetic stress, classical host calibration and unchanged integer core; no new GPU, sensor or FPGA execution",
             "versions":{"python":platform.python_version(),"numpy":np.__version__,"platform":platform.platform()}}
    (out/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    return metrics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    c=json.loads((ROOT/"config.json").read_text())
    shutil.copy2(ROOT/"config.json",args.output/"config.json")
    provenance={"argv":sys.argv,"utc":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                "sha256":{str(p):sha(p) for p in (ROOT/"config.json",ROOT/"run_stress.py",ROOT/"replay_reference.cpp",CORE,MODEL)}}
    (args.output/"provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
    try:
        metrics=run(c,args.output)
    except Exception as exc:
        (args.output/"failure.json").write_text(json.dumps({"type":type(exc).__name__,"message":str(exc)},indent=2)+"\n")
        raise
    print(json.dumps({"correctness_passed":metrics["correctness_passed"],"utility_passed":metrics["utility_passed"],"groups":metrics["physical_groups"],"board_records":metrics["board_replay_records"],"elapsed_s":metrics["elapsed_s"],"final":{k:v["final"] for k,v in metrics["summaries"].items()}},indent=2))
    return 0 if metrics["correctness_passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())
