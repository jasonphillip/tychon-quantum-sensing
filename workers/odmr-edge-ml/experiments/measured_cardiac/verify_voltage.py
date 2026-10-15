"""Independent saved-output arithmetic and decision verification; no archive or inference."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np

GRID=np.arange(-400,800)/2000.
DURATIONS=(30,60,120)
FLOORS=(.1,.25,.5)
BASELINES=("raw_mean","raw_median","raw_trimmed","notch_mean","notch_median","notch_trimmed")
QUALIFICATION_SHA="b109aaf7f2da8b147ecf8b32966f9665b8ddf14ea4888db578e8f6df214a01d6"
BLOCK_DURATIONS={"c30":30,"c60":60,"c120":120,"reference_a":180,"reference_b":180}
TEMPLATE_IDS=["P1-S%02d"%i for i in range(1,11)]

def check_block_schema(flags):
    if set(flags)!=set(BLOCK_DURATIONS):raise ValueError("Exactly five registered block flags required.")
    for name,duration in BLOCK_DURATIONS.items():
        if isinstance(flags[name].get("duration_seconds"),bool) or flags[name].get("duration_seconds")!=duration:
            raise ValueError("Registered block duration changed.")

def check_template_schema(context):
    if context.get("template_recording_ids")!=TEMPLATE_IDS:raise ValueError("Exact ordered ten-record P1 template bank required.")
    bank=np.asarray(context.get("templates"),dtype=float)
    if bank.shape!=(10,1200) or not np.isfinite(bank).all():raise ValueError("Invalid frozen template bank shape or values.")

def array_equal(a,b):
    a,b=np.asarray(a),np.asarray(b)
    if a.shape!=b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():return False
    scale=max(float(np.max(np.abs(a),initial=0)),float(np.max(np.abs(b),initial=0)),1e-300)
    return bool(np.max(np.abs(a-b),initial=0)<=1e-9*scale)

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()

def mean(x):return np.sum(x,axis=0)/len(x) if len(x) else np.zeros(1200)
def median(x):return np.quantile(x,.5,axis=0) if len(x) else np.zeros(1200)

def aggregate(x,kind):
    if kind=="mean":return mean(x)
    if kind=="median":return median(x)
    cut=len(x)//10
    return mean(np.sort(x,axis=0)[cut:len(x)-cut])

def metric(p,r):
    n=len(r)
    energy=math.fsum(float(x)*float(x) for x in r)
    if energy<=0:return {"nrmse":None,"correlation":None,"amplitude_ratio":None,"same_polarity":False,"peak_shift_seconds":None,"width_ratio":None,"preserves":False}
    ip=max(range(n),key=lambda i:abs(p[i])); ir=max(range(n),key=lambda i:abs(r[i]))
    amplitude=abs(float(p[ip])/float(r[ir])); same=bool(p[ip]*r[ir]>0)
    shift=abs(float(GRID[ip]-GRID[ir]))
    def width(x):
        weights=[float(z)*float(z) for z in x]; total=math.fsum(weights)
        if total<=0:return 0.
        center=math.fsum(float(t)*w for t,w in zip(GRID,weights))/total
        return math.sqrt(math.fsum((float(t)-center)**2*w for t,w in zip(GRID,weights))/total)
    rw=width(r); ratio=width(p)/rw if rw>0 else 0.
    pe=math.fsum(float(x)*float(x) for x in p)
    correlation=math.fsum(float(a)*float(b) for a,b in zip(p,r))/math.sqrt(pe*energy) if pe>0 else 0.
    return {"nrmse":math.sqrt(math.fsum((float(a)-float(b))**2 for a,b in zip(p,r))/energy),
            "correlation":correlation,"amplitude_ratio":amplitude,"same_polarity":same,
            "peak_shift_seconds":shift,"width_ratio":ratio,
            "preserves":bool(same and .8<=amplitude<=1.2 and shift<=.020000000001 and .8<=ratio<=1.25)}

def close(a,b,path="root"):
    if isinstance(a,dict):
        if not isinstance(b,dict) or set(a)!=set(b):raise ValueError("Field mismatch: "+path)
        for k in a:close(a[k],b[k],path+"."+k)
    elif isinstance(a,(list,tuple)):
        if not isinstance(b,(list,tuple)) or len(a)!=len(b):raise ValueError("Length mismatch: "+path)
        for i,(x,y) in enumerate(zip(a,b)):close(x,y,path+"."+str(i))
    elif isinstance(a,bool) or a is None or isinstance(a,str):
        if a!=b:raise ValueError("Value mismatch: "+path)
    elif not math.isclose(float(a),float(b),rel_tol=1e-8,abs_tol=1e-10):raise ValueError("Arithmetic mismatch: "+path)

def check_record_arrays(arrays,flags):
    check_block_schema(flags)
    if not np.array_equal(arrays["grid_seconds"],GRID):raise ValueError("Unexpected interpolation grid.")
    for name,flag in flags.items():
        pref=name+"__"
        raw,notch=arrays[pref+"raw"],arrays[pref+"notch"]
        if raw.shape!=notch.shape or raw.ndim!=2 or raw.shape[1]!=1200:raise ValueError("Invalid beat shapes.")
        for key,value in arrays.items():
            if not np.isfinite(value).all():raise ValueError("Nonfinite saved array.")
        accepted=arrays[pref+"accepted_times"]; completion=arrays[pref+"completion_times"]
        trigger=arrays[pref+"trigger_times"]; decision=arrays[pref+"decision_times"]
        if len(accepted)!=len(raw) or len(completion)!=len(raw) or len(arrays[pref+"quality"])!=len(raw):raise ValueError("Inconsistent beat count.")
        if len(trigger)!=len(decision):raise ValueError("Missing trigger decision times.")
        if np.any(decision<trigger) or np.any(decision-trigger>.052):raise ValueError("Causal trigger confirmation bound failed.")
        if np.any(accepted-.2<10) or np.any(completion>flag["duration_seconds"]) or np.any(np.diff(accepted)<.6-1e-10):raise ValueError("Overlapping or incomplete beat windows.")
        if not np.allclose(completion,accepted+.4,rtol=0,atol=1e-10):raise ValueError("Completion time mismatch.")
        if not all(t in set(trigger.tolist()) for t in accepted):raise ValueError("Beat without recorded trigger.")
        close(flag["beat_count"],len(raw));close(flag["trigger_count"],len(trigger))
        close(flag["yield"],len(raw)/len(trigger) if len(trigger) else 0.)
        for values in (raw,notch):
            scale=max(float(np.max(np.abs(values),initial=0)),1e-300)
            if np.max(np.abs(np.mean(values,axis=1)),initial=0)>1e-9*scale:raise ValueError("Beat centering mismatch.")
        close(flag["quality_scale"],float(np.median(arrays[pref+"warm_variances"])))
    # All shorter candidate inputs must be exact prefixes of the same registered stream.
    for duration in (30,60):
        count=flags["c"+str(duration)]["beat_count"]
        for field in ("raw","notch","quality","accepted_times","completion_times"):
            if not np.array_equal(arrays["c"+str(duration)+"__"+field],arrays["c120__"+field][:count]):raise ValueError("Candidate prefix disagreement.")

def evaluate_score(p,a,b,threshold,valid):
    ma,mb=metric(p,a),metric(p,b)
    error=max(ma["nrmse"],mb["nrmse"]) if ma["nrmse"] is not None and mb["nrmse"] is not None else None
    return {"reference_a":ma,"reference_b":mb,"error":error,
            "passes":bool(error is not None and error<=threshold and ma["preserves"] and mb["preserves"] and valid)}

def verify(directory):
    load=lambda name:json.loads((directory/name).read_text())
    summary=load("summary.json")
    records=summary["records"]
    expected={"development":["P1-S%02d"%i for i in range(1,11)],"validation":["P2-S01"],"final":["P3-S01"]}[summary["phase"]]
    if records!=expected:raise ValueError("Participant partition changed or session omitted.")
    required={"manifest-input.json","qualification-input.json","source-provenance.json"}
    required|={key+suffix for key in records for suffix in ("-beats.npz","-flags.json")}
    if summary["phase"]!="development":required.add("frozen-configuration-input.json")
    if summary["phase"]=="final":required.add("validation-summary-input.json")
    if summary.get("stage")!="reference_eligibility":
        required.add("evaluation-context.json")
        required|={key+suffix for key in records for suffix in ("-predictions.npz","-metrics.json")}
        if summary["phase"]=="development":required.add("frozen-configuration.json")
    if set(summary["artifact_sha256"])!=required:raise ValueError("Incomplete artifact manifest.")
    for name,checksum in summary["artifact_sha256"].items():
        if Path(name).name!=name or digest(directory/name)!=checksum:raise ValueError("Artifact checksum mismatch.")
    provenance=load("source-provenance.json");package=Path(__file__).resolve().parent
    if set(provenance["source_sha256"])!={p.name for p in package.glob("*.py")}:
        raise ValueError("Source inventory changed.")
    for name,checksum in provenance["source_sha256"].items():
        if digest(package/name)!=checksum:raise ValueError("Scientific source changed: "+name)
    for name,field in (("protocol.md","protocol_sha256"),("voltage-protocol.md","voltage_protocol_sha256"),("waveform-protocol.md","waveform_protocol_sha256")):
        if digest(package/name)!=provenance[field]:raise ValueError("Protocol changed.")
    if digest(directory/"manifest-input.json")!=summary["manifest_sha256"] or digest(directory/"qualification-input.json")!=summary["qualification_sha256"]:
        raise ValueError("Source metadata changed.")
    if summary["qualification_sha256"]!=QUALIFICATION_SHA or provenance["timestamp_qualification_sha256"]!=QUALIFICATION_SHA or provenance["manifest_sha256"]!=summary["manifest_sha256"]:
        raise ValueError("Qualified source identity changed.")
    qualification=load("qualification-input.json");qmap={r["recording_id"]:r for r in qualification["recordings"]}
    manifest=load("manifest-input.json");mmap={r["id"]:r for r in manifest["recordings"]}
    saved={}; flags={}; refs={}; gates={}
    for key in records:
        with np.load(directory/(key+"-beats.npz"),allow_pickle=False) as archive:saved[key]={name:archive[name] for name in archive.files}
        meta=load(key+"-flags.json"); flags[key]=meta["flags"]
        if meta["recording_id"]!=key:raise ValueError("Record identity mismatch.")
        close(meta["timestamp_indices"],qmap[key]["exact_windows"])
        close(meta["source_member_name_sha256"],mmap[key]["member_name_sha256"])
        close(meta["participant_id"],mmap[key]["participant_id"])
        close(meta["split"],mmap[key]["split"])
        check_record_arrays(saved[key],flags[key])
        a,b=(mean(saved[key][n+"__notch"]) for n in ("reference_a","reference_b")); refs[key]=(a,b)
        ab,ba=metric(a,b),metric(b,a)
        error=max(ab["nrmse"],ba["nrmse"]) if ab["nrmse"] is not None and ba["nrmse"] is not None else None
        counts=[flags[key][n]["beat_count"] for n in ("reference_a","reference_b")]
        yields=[flags[key][n]["yield"] for n in ("reference_a","reference_b")]
        good=bool(error is not None and error<=.5 and ab["correlation"]>=.8 and ab["preserves"] and ba["preserves"] and min(counts)>=100 and min(yields)>=.9)
        gate={"passes":good,"error":error,"a_against_b":ab,"b_against_a":ba,"counts":counts,"yields":yields}
        close(gate,meta["reference_gate"],key+".reference_gate");gates[key]=gate
    close(summary["reference_passes"],sum(g["passes"] for g in gates.values()))
    close(summary["required_reference_passes"],len(records))
    if summary.get("stage")=="reference_eligibility":
        if all(g["passes"] for g in gates.values()) or summary["status"]!="STOP":raise ValueError("Incorrect reference stop.")
        return {"verified":True,"scientific_status":"STOP","stage":"reference_eligibility","reference_passes":summary["reference_passes"],"records":records}
    if not all(g["passes"] for g in gates.values()):raise ValueError("Candidate comparison bypassed failed reference gate.")
    context=load("evaluation-context.json");threshold=context["threshold"];floors=tuple(context["floors"])
    check_template_schema(context)
    if summary["phase"]!="development":
        frozen=load("frozen-configuration-input.json")
        checksum=digest(directory/"frozen-configuration-input.json")
        if checksum!=context["frozen_configuration_sha256"] or checksum!=summary["frozen_configuration_sha256"] or frozen["status"]!="PASS":raise ValueError("Development freeze mismatch.")
        close(threshold,frozen["threshold"]);close(list(floors),[frozen["floor"]])
        close(context["templates"],frozen["templates"]);close(context["template_recording_ids"],frozen["template_recording_ids"])
        if summary["phase"]=="final":
            validation=load("validation-summary-input.json")
            if validation["status"]!="PASS" or validation["phase"]!="validation" or validation["frozen_configuration_sha256"]!=checksum:raise ValueError("Final bypassed passing validation.")
    if summary["phase"]=="development":
        close(threshold,float(np.clip(1.5*np.median([g["error"] for g in gates.values()]),.15,.5)))
        if floors!=FLOORS:raise ValueError("Development configurations changed.")
        for i,key in enumerate(context["template_recording_ids"]):
            t=(refs[key][0]+refs[key][1])/2; t=t/math.sqrt(float(np.mean(t*t)))
            if not array_equal(t,context["templates"][i]):raise ValueError("Template construction changed.")
    wins={str(f):0 for f in floors}
    for key in records:
        scale=float(np.median(saved[key]["c120__warm_variances"]));close(scale,context["quality_variance_scales"][key])
        templates=[np.asarray(t) for name,t in zip(context["template_recording_ids"],context["templates"]) if name!=key]
        actual=load(key+"-metrics.json");result={};a,b=refs[key]
        with np.load(directory/(key+"-predictions.npz"),allow_pickle=False) as predicted:
            if not array_equal(a,predicted["reference_a"]) or not array_equal(b,predicted["reference_b"]):raise ValueError("Reference prediction mismatch.")
            for duration in DURATIONS:
                prefix="c"+str(duration)+"__";f=flags[key]["c"+str(duration)]
                valid=f["beat_count"]>=10 and f["yield"]>=.9
                pred={name:aggregate(saved[key][prefix+name.split("_")[0]],name.split("_")[1]) for name in BASELINES}
                pred["constant"]=np.zeros(1200)
                cm=mean(saved[key][prefix+"notch"])
                ts=[t*float(np.dot(t,cm))/float(np.dot(t,t)) if float(np.dot(t,t))>0 else np.zeros(1200) for t in templates]
                ti=min(range(len(ts)),key=lambda i:float(np.sum((ts[i]-cm)**2))) if ts else -1
                pred["template"]=ts[ti] if ti>=0 else np.zeros(1200)
                for floor in floors:
                    name="quality_"+str(floor);q=saved[key][prefix+"quality"]
                    w=np.minimum(np.maximum(1/(q/scale+floor),1/(4*floor)),1/floor) if scale>0 else np.zeros(len(q))
                    pred[name]=np.sum(saved[key][prefix+"notch"]*w[:,None],axis=0)/float(np.sum(w)) if np.sum(w)>0 else np.zeros(1200)
                    if not array_equal(w,predicted["weights_"+str(duration)+"__"+name]):raise ValueError("Weight mismatch.")
                scores={name:evaluate_score(p,a,b,threshold,valid) for name,p in pred.items()}
                null=min(scores[n]["error"] for n in ("constant","template"))
                for floor in floors:
                    s=scores["quality_"+str(floor)];s["null_guard"]=bool(not scores["constant"]["passes"] and not scores["template"]["passes"] and s["error"]<=.9*null)
                    s["passes"]=bool(s["passes"] and s["null_guard"])
                for name,p in pred.items():
                    if not array_equal(p,predicted["prediction_"+str(duration)+"__"+name]):raise ValueError("Saved estimate mismatch.")
                result[str(duration)]={"valid_candidate_block":valid,"template_index":ti,"scores":scores}
        base=min((t for t in DURATIONS if any(result[str(t)]["scores"][n]["passes"] for n in BASELINES)),default=None)
        advantages={}
        for floor in floors:
            name="quality_"+str(floor);short=min((t for t in DURATIONS if result[str(t)]["scores"][name]["passes"]),default=None)
            ratio=short/base if short is not None and base is not None else None
            advantages[name]={"candidate_seconds":short,"best_classical_seconds":base,"ratio":ratio,"passes":bool(ratio is not None and ratio<=.75)}
            wins[str(floor)]+=int(advantages[name]["passes"])
        close({"durations":result,"advantages":advantages,"recording_id":key},actual,key+".metrics")
    chosen=max(floors,key=lambda f:(wins[str(f)],-f));required=9 if summary["phase"]=="development" else 1
    close(wins,summary["quality_wins"]);close(chosen,summary["selected_floor"]);close(required,summary["required_wins"])
    status="PASS" if wins[str(chosen)]>=required and min(context["quality_variance_scales"].values())>0 else "STOP"
    if summary["status"]!=status:raise ValueError("Scientific decision mismatch.")
    if summary["phase"]=="development":
        frozen=load("frozen-configuration.json")
        close(frozen["floor"],chosen);close(frozen["threshold"],threshold);close(frozen["selection_wins"],wins)
        close(frozen["templates"],context["templates"]);close(frozen["template_recording_ids"],context["template_recording_ids"])
        if frozen["status"]!=status:raise ValueError("Frozen selection status mismatch.")
    return {"verified":True,"scientific_status":status,"stage":"method_comparison","records":records,"quality_wins":wins,"selected_floor":chosen}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--input",type=Path,required=True);p.add_argument("--out",type=Path,required=True)
    args=p.parse_args();verdict=verify(args.input);verdict["summary_sha256"]=digest(args.input/"summary.json")
    with args.out.open("x") as stream:json.dump(verdict,stream,indent=2);stream.write("\n")
    print(json.dumps(verdict));return 0 if verdict["scientific_status"]=="PASS" else 2

if __name__=="__main__":raise SystemExit(main())
