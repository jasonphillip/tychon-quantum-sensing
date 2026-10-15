"""Registered voltage reproducibility screen. No physiological or field-accuracy target."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import zipfile
import shutil
import numpy as np
from .metadata import sha256
from .waveform_io import prepare_access, read_windows, QUALIFICATION_SHA
from .waveform_methods import (GRID,DURATIONS,FLOORS,BASELINES,completed_beats,aggregate,candidate,
                               template_null,score,reference_gate)

def write_json(path,obj):
    with path.open("x") as stream:
        json.dump(obj,stream,indent=2,allow_nan=False)
        stream.write("\n")

def extract_record(windows,fs):
    result={}
    for seconds in DURATIONS:
        result["c"+str(seconds)]=completed_beats(windows["candidate"],fs,seconds)
    for name in ("reference_a","reference_b"):
        result[name]=completed_beats(windows[name],fs,180)
    return result

def pack(record):
    arrays={"grid_seconds":GRID}
    for name,b in record.items():
        for key in ("raw","notch","quality","warm_variances","trigger_times","decision_times","accepted_times","completion_times"):
            arrays[name+"__"+key]=b[key]
    return arrays

def flags(record):
    keys=("quality_scale","threshold","trigger_count","beat_count","yield","duration_seconds")
    return {name:{k:b[k] for k in keys} for name,b in record.items()}

def references(record):
    a,b=(record[name] for name in ("reference_a","reference_b"))
    ra,rb=aggregate(a["notch"],"mean"),aggregate(b["notch"],"mean")
    return ra,rb,reference_gate(ra,rb,[a["beat_count"],b["beat_count"]],[a["yield"],b["yield"]])

def evaluate_record(record,ra,rb,threshold,scale,templates,floors):
    result={}
    outputs={}
    for seconds in DURATIONS:
        b=record["c"+str(seconds)]
        valid=b["beat_count"]>=10 and b["yield"]>=.9
        predictions={name:aggregate(b[name.split("_")[0]],name.split("_")[1]) for name in BASELINES}
        predictions["constant"]=np.zeros(len(GRID))
        predictions["template"],template_id=template_null(templates,aggregate(b["notch"],"mean"))
        weights={}
        for floor in floors:
            name="quality_"+str(floor)
            predictions[name],weights[name]=candidate(b["notch"],b["quality"],scale,floor)
        scores={name:score(p,ra,rb,threshold) for name,p in predictions.items()}
        for s in scores.values():s["passes"]=bool(s["passes"] and valid)
        nullerror=min([scores[n]["error"] for n in ("constant","template") if scores[n]["error"] is not None],default=0.)
        for name in weights:
            s=scores[name]
            s["null_guard"]=bool(not scores["constant"]["passes"] and not scores["template"]["passes"] and s["error"] is not None and s["error"]<=.9*nullerror)
            s["passes"]=bool(s["passes"] and s["null_guard"])
        result[str(seconds)]={"valid_candidate_block":valid,"template_index":template_id,"scores":scores}
        for name,p in predictions.items():outputs["prediction_"+str(seconds)+"__"+name]=p
        for name,w in weights.items():outputs["weights_"+str(seconds)+"__"+name]=w
    baseline=min((t for t in DURATIONS if any(result[str(t)]["scores"][n]["passes"] for n in BASELINES)),default=None)
    advantages={}
    for floor in floors:
        name="quality_"+str(floor)
        shortest=min((t for t in DURATIONS if result[str(t)]["scores"][name]["passes"]),default=None)
        ratio=shortest/baseline if shortest is not None and baseline is not None else None
        advantages[name]={"candidate_seconds":shortest,"best_classical_seconds":baseline,"ratio":ratio,
                          "passes":bool(ratio is not None and ratio<=.75)}
    return {"durations":result,"advantages":advantages},outputs

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("archive","manifest","qualification","approval","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--approval-sha256",required=True)
    parser.add_argument("--phase",choices=("development","validation","final"),required=True)
    parser.add_argument("--frozen",type=Path)
    parser.add_argument("--validation",type=Path)
    args=parser.parse_args()
    started=time.monotonic()
    access,selected,qualified=prepare_access(args)
    frozen=json.loads(args.frozen.read_text()) if args.frozen else None
    if frozen and (frozen.get("status")!="PASS" or frozen.get("floor") not in FLOORS):
        raise PermissionError("No passing fixed development selection.")
    args.out.mkdir(parents=True,exist_ok=False)
    records,refs,checks,artifact_hashes={},{},{},{}
    for path,name in ((args.manifest,"manifest-input.json"),(args.qualification,"qualification-input.json"),(args.frozen,"frozen-configuration-input.json"),(args.validation,"validation-summary-input.json")):
        if path is not None:
            shutil.copyfile(path,args.out/name)
            artifact_hashes[name]=sha256(args.out/name)
    gate=json.loads(args.approval.read_text())
    write_json(args.out/"source-provenance.json",{k:gate[k] for k in ("source_sha256","protocol_sha256","voltage_protocol_sha256","waveform_protocol_sha256","manifest_sha256","timestamp_qualification_sha256")})
    artifact_hashes["source-provenance.json"]=sha256(args.out/"source-provenance.json")
    with zipfile.ZipFile(args.archive) as archive:
        for spec in selected:
            key=spec["id"]
            windows=read_windows(archive,spec,qualified[key])
            record=extract_record(windows,qualified[key]["sample_rate_hz"])
            records[key]=record
            ra,rb,check=references(record)
            refs[key]=(ra,rb)
            checks[key]=check
            path=args.out/(key+"-beats.npz")
            np.savez_compressed(path,**pack(record))
            artifact_hashes[path.name]=sha256(path)
            info={"recording_id":key,"participant_id":spec["participant_id"],"split":spec["split"],
                  "flags":flags(record),"reference_gate":check,"timestamp_indices":qualified[key]["exact_windows"],
                  "source_member_name_sha256":spec["member_name_sha256"]}
            write_json(args.out/(key+"-flags.json"),info)
            artifact_hashes[key+"-flags.json"]=sha256(args.out/(key+"-flags.json"))
            print(json.dumps({"recording_id":key,"reference_gate":check["passes"]}),flush=True)
    if not all(check["passes"] for check in checks.values()):
        write_json(args.out/"summary.json",{"status":"STOP","stage":"reference_eligibility","phase":args.phase,
                   "records":list(records),"reference_passes":sum(c["passes"] for c in checks.values()),
                   "required_reference_passes":len(records),"artifact_sha256":artifact_hashes,
                   "qualification_sha256":QUALIFICATION_SHA,"manifest_sha256":sha256(args.manifest),
                   "approval_sha256":args.approval_sha256,"run_id":access.run_id,
                   "compute_elapsed_seconds":time.monotonic()-started,
                   "reason":"At least one fixed reference pair failed. No candidate comparison or tuning performed."})
        return 2
    scales={key:float(np.median(record["c120"]["warm_variances"])) for key,record in records.items()}
    if frozen:
        threshold=frozen["threshold"]
        bank=np.asarray(frozen["templates"],dtype=float)
        bank_ids=frozen["template_recording_ids"]
        floors=(frozen["floor"],)
    else:
        finite=[r["error"] for r in checks.values() if r["error"] is not None]
        threshold=float(np.clip(1.5*np.median(finite),.15,.5)) if finite else .15
        bank_ids=list(records)
        bank=[]
        for key in bank_ids:
            value=(refs[key][0]+refs[key][1])/2
            rms=float(np.sqrt(np.mean(value**2)))
            bank.append(value/rms if rms>0 else np.zeros(len(GRID)))
        bank=np.asarray(bank)
        floors=FLOORS
    write_json(args.out/"evaluation-context.json",{"phase":args.phase,"threshold":threshold,"quality_variance_scales":scales,
               "templates":bank.tolist(),"template_recording_ids":bank_ids,"floors":list(floors),
               "frozen_configuration_sha256":sha256(args.frozen) if args.frozen else None})
    artifact_hashes["evaluation-context.json"]=sha256(args.out/"evaluation-context.json")
    comparisons={}
    for key,record in records.items():
        template_subset=bank[[i for i,name in enumerate(bank_ids) if name!=key]]
        result,outputs=evaluate_record(record,*refs[key],threshold,scales[key],template_subset,floors)
        result["recording_id"]=key
        comparisons[key]=result
        path=args.out/(key+"-predictions.npz")
        np.savez_compressed(path,reference_a=refs[key][0],reference_b=refs[key][1],**outputs)
        artifact_hashes[path.name]=sha256(path)
        write_json(args.out/(key+"-metrics.json"),result)
        artifact_hashes[key+"-metrics.json"]=sha256(args.out/(key+"-metrics.json"))
    counts={str(f):sum(r["advantages"]["quality_"+str(f)]["passes"] for r in comparisons.values()) for f in floors}
    chosen=max(floors,key=lambda f:(counts[str(f)],-f))
    required=9 if args.phase=="development" else 1
    passed=all(r["passes"] for r in checks.values()) and min(scales.values())>0 and counts[str(chosen)]>=required
    if args.phase=="development":
        write_json(args.out/"frozen-configuration.json",{"status":"PASS" if passed else "STOP","floor":chosen,
                   "threshold":threshold,"scale_policy":"Each candidate block's first ten seconds only; median of disjoint 100 ms variances.","templates":bank.tolist(),
                   "template_recording_ids":bank_ids,"selection_wins":counts,
                   "source_policy":"P1-only multiplier selection; fixed per-record input normalization; ties prefer smaller floor"})
        artifact_hashes["frozen-configuration.json"]=sha256(args.out/"frozen-configuration.json")
    summary={"status":"PASS" if passed else "STOP","phase":args.phase,"records":list(records),
             "reference_passes":sum(r["passes"] for r in checks.values()),"required_reference_passes":len(records),
             "quality_wins":counts,"selected_floor":chosen,"required_wins":required,
             "qualification_sha256":QUALIFICATION_SHA,"manifest_sha256":sha256(args.manifest),
             "approval_sha256":args.approval_sha256,"run_id":access.run_id,
             "frozen_configuration_sha256":sha256(args.frozen) if args.frozen else None,
             "artifact_sha256":artifact_hashes,"compute_elapsed_seconds":time.monotonic()-started,
             "claims":"Recorded-voltage reproducibility only. References are noisy; no physiological or absolute-field truth.",
             "hardware_work":False,"training":False}
    write_json(args.out/"summary.json",summary)
    print(json.dumps({k:summary[k] for k in ("status","phase","reference_passes","quality_wins")}),flush=True)
    return 0 if passed else 2

if __name__=="__main__":raise SystemExit(main())
