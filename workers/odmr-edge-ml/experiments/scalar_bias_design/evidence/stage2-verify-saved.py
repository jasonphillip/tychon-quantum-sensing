"""Independent Stage 2 saved-output verifier; NumPy and stdlib only.
No renderer, model, fitting, old data payload, or private secret is opened.
Run only with root authorization and the shared Stage 2 budget wrapper.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import time
import traceback
import numpy as np

CELLS = ("realistic_anchor", "wide_lines", "low_snr")
WIDTHS = (5., 7., 5.)
SNRS = (10., 10., 3.)
LOW, HIGH = 2**40, 2**63
BOOT = LOW + int(hashlib.sha256(b"tychon/scalar-information-limit/2026-10-15/bootstrap").hexdigest(), 16) % (HIGH-LOW)
GAMMA = abs(-1.76085963023e11*1.000357)/(2*math.pi)*1e-12
PARAM_LOW = np.array([20., 2865., .5, .001, .9, -.08])
PARAM_HIGH = np.array([70., 2878., 12., .06, 1.1, .08])

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def load_json(path):
    return json.loads(Path(path).read_text())

def arrays(path):
    with np.load(path, allow_pickle=False) as z:
        return {k: z[k].copy() for k in z.files}

def percentile(values, fraction):
    v = np.sort(np.asarray(values))
    location = fraction*(len(v)-1)
    lo, hi = int(math.floor(location)), int(math.ceil(location))
    return float(v[lo] + (v[hi]-v[lo])*(location-lo))

def summarize(error, failed, boundary, timing):
    ab = np.abs(error)
    return dict(n=len(error), mae_uT=float(np.sum(ab)/len(ab)),
        rmse_uT=math.sqrt(float(np.dot(error,error)/len(error))),
        median_abs_uT=percentile(ab,.5), p90_abs_uT=percentile(ab,.9),
        p95_abs_uT=percentile(ab,.95), max_abs_uT=float(np.max(ab)),
        failure_fraction=float(np.count_nonzero(failed)/len(error)),
        raw_fit_coverage=float(1-np.count_nonzero(failed)/len(error)),
        boundary_fraction=float(np.count_nonzero(boundary)/len(error)),
        median_latency_seconds=percentile(timing,.5),
        p95_latency_seconds=percentile(timing,.95), total_fit_seconds=float(np.sum(timing)))

class Audit:
    def __init__(self, args):
        self.a=args
        self.report={"status":"running", "failures":[], "phases":{}, "checks":0,
            "timing_scope":"Fit latency is recorded production timing, not an independently measured estimator benchmark.",
            "provenance_requested":args.check_provenance}
        self.cache={}
    def check(self, condition, label, detail=None):
        self.report["checks"]+=1
        if not bool(condition):
            self.report["failures"].append({"label":label,"detail":detail})
    def phase(self, name, operation):
        before=len(self.report["failures"])
        try:
            operation()
        except Exception as e:
            self.report["failures"].append({"label":name+":exception",
                "error":type(e).__name__+": "+str(e),"traceback":traceback.format_exc()})
        self.report["phases"][name]="pass" if len(self.report["failures"])==before else "fail"
    def compare(self, actual, expected, label):
        if isinstance(expected, dict):
            self.check(isinstance(actual,dict),label+":object")
            if not isinstance(actual,dict):return
            self.check(set(actual)==set(expected),label+":keys")
            for k in set(actual)&set(expected):self.compare(actual[k],expected[k],label+"/"+k)
        elif isinstance(expected,list):
            self.check(isinstance(actual,list) and len(actual)==len(expected),label+":length")
            if isinstance(actual,list):
                for i,(x,y) in enumerate(zip(actual,expected)):self.compare(x,y,label+f"/{i}")
        elif isinstance(expected,bool) or expected is None or isinstance(expected,str):
            self.check(type(actual)==type(expected) and actual==expected,label+":exact")
        elif isinstance(expected,int):
            self.check(isinstance(actual,int) and not isinstance(actual,bool) and actual==expected,label+':integer-exact')
        elif isinstance(expected,float):
            self.check(isinstance(actual,(int,float)) and not isinstance(actual,bool)
                and math.isfinite(actual) and math.isclose(actual,expected,rel_tol=1e-11,abs_tol=1e-11),
                label+":number",{"actual":actual,"expected":expected})
        else:self.check(actual==expected,label+":value")
    def file_hash(self, path, expected, label):
        self.check(Path(path).is_file() and not Path(path).is_symlink(),label+":regular-file")
        if Path(path).is_file() and not Path(path).is_symlink():self.check(sha(path)==expected,label+":sha256")
    def bindings(self):
        a=self.a;b=a.bundle
        self.file_hash(b/"bundle-manifest.json",a.expected_manifest_sha256,"bundle")
        bundle=load_json(b/"bundle-manifest.json");self.cache["bundle"]=bundle
        required={"inputs.npz","truth.npz","seed-record.json","input-manifest.json","predictions.npz",
            "starts.json","prediction-receipt.json","prediction-commitment.json","metric-receipt.json",
            "metrics.json","bootstrap_indices.npy"}
        self.check(required<=set(bundle["files"]),"bundle:required-files")
        self.check(bundle["status"]=="complete","bundle:complete")
        for name,expected in bundle["files"].items():
            self.check(Path(name).name==name and name not in (".",".."),"bundle:safe-name",name)
            if Path(name).name==name:self.file_hash(b/name,expected,"bundle/"+name)
        inp=load_json(b/"input-manifest.json");pr=load_json(b/"prediction-receipt.json")
        pc=load_json(b/"prediction-commitment.json");mr=load_json(b/"metric-receipt.json")
        reg=load_json(a.registration);audit=load_json(a.seed_audit)
        self.cache.update(input_manifest=inp,prediction_receipt=pr,prediction_commitment=pc,metric_receipt=mr,seed_audit=audit)
        self.check(reg.get("stage")=="stage2" and reg.get("approved") is True,"registration:approval")
        for label,obj in [("registration",reg),("input",inp),("prediction",pr),("bundle",bundle)]:
            self.check(obj["protocol_sha256"]==sha(a.protocol),label+":protocol-hash")
        self.check(inp["registration_sha256"]==sha(a.registration),"input:registration-hash")
        self.check(inp["partition"] in ("development","evaluation"),"input:partition")
        n={"development":32,"evaluation":256}[inp["partition"]]
        self.check(inp["fields"]==n and inp["rows"]==6*n,"input:registered-size")
        for name,expected in inp["files"].items():
            self.check(name in ("inputs.npz","truth.npz","seed-record.json"),"input:safe-name",name)
            if name in ("inputs.npz","truth.npz","seed-record.json"):self.file_hash(b/name,expected,"input/"+name)
        for label,obj in [("prediction",pr),("metrics",mr)]:self.check(obj["status"]=="complete",label+":complete")
        self.check(pr["rows"]==6*n,"prediction:row-count")
        for key,file in [("prediction_sha256","predictions.npz"),("starts_sha256","starts.json")]:
            self.file_hash(b/file,pr[key],"prediction/"+key)
        self.file_hash(b/"predictions.npz",pc["prediction_sha256"],"commitment:predictions")
        self.file_hash(b/"prediction-receipt.json",pc["prediction_receipt_sha256"],"commitment:receipt")
        self.file_hash(b/"prediction-commitment.json",mr["prediction_commitment_sha256"],"metrics:commitment")
        self.check(mr["prediction_commitment_revision"]==a.expected_commitment_revision,"metrics:commit-revision")
        relative=Path(a.commitment_relative_path)
        self.check(not relative.is_absolute() and ".." not in relative.parts,"git:safe-commitment-path")
        if not relative.is_absolute() and ".." not in relative.parts:
            committed=subprocess.check_output(["git","-C",str(a.code_root),"show",a.expected_commitment_revision+":"+relative.as_posix()])
            self.check(committed==(b/"prediction-commitment.json").read_bytes(),"git:committed-prediction-bytes")
            code=subprocess.run(["git","-C",str(a.code_root),"merge-base","--is-ancestor",a.expected_commitment_revision,"HEAD"],capture_output=True).returncode
            self.check(code==0,"git:commitment-ancestor")
        values={"input_manifest_sha256":sha(b/"input-manifest.json"),"freeze_sha256":None,"access_sha256":None}
        code_manifest=load_json(a.code_manifest)
        audit_relative=a.seed_audit.resolve().relative_to(a.code_root.resolve()).as_posix()
        self.check(code_manifest["files"].get(audit_relative)==sha(a.seed_audit),"source:frozen-seed-audit")
        for name,expected in code_manifest["files"].items():
            rel=Path(name);safe=not rel.is_absolute() and ".." not in rel.parts
            self.check(safe,"source:safe-path",name)
            if safe:self.file_hash(a.code_root/rel,expected,"source/"+name)
        if inp["partition"]=="evaluation":
            for arg in ("freeze","access","secret_commitment"):self.check(getattr(a,arg) is not None,"custody:required-"+arg)
            freeze=load_json(a.freeze);access=load_json(a.access);commit=load_json(a.secret_commitment)
            self.cache.update(freeze=freeze,access=access,secret_commitment=commit)
            values.update(freeze_sha256=sha(a.freeze),access_sha256=sha(a.access))
            self.check(freeze["files"]==code_manifest["files"],"freeze:source-files")
            self.file_hash(a.code_manifest,freeze["code_manifest_sha256"],"freeze:manifest")
            for label,obj in [("freeze",freeze),("commitment",commit),("access",access)]:
                self.check(obj["protocol_sha256"]==sha(a.protocol),label+":protocol")
                self.check(obj["commitment_sha256"]==inp["commitment_sha256"],label+":secret-commitment")
            for label,obj in [("freeze",freeze),("commitment",commit)]:
                self.check(obj["registration_sha256"]==sha(a.registration),label+":registration")
            self.check(access["status"]=="authorized_once","access:status")
            self.file_hash(b/"input-manifest.json",access["data_manifest_sha256"],"access:input")
            for label,obj in [("access",access),("input",inp)]:
                self.check(obj["freeze_sha256"]==sha(a.freeze),label+":freeze")
        for label,obj in [("bundle",bundle),("prediction",pr),("commitment",pc),("metrics",mr)]:
            for key,value in values.items():self.check(obj[key]==value,label+":"+key)
        self.check(pr["runtime"]["workers"]==1,"runtime:single-worker")
        for key in ("cpu","os","python","numpy","scipy"):
            self.check(isinstance(pr["runtime"].get(key),str) and bool(pr["runtime"][key]),"runtime:"+key)
        self.check(audit["status"]=="pass","seed-audit:pass")
        self.check(audit["certificate_sha256"]=="6acd082f907d33f3e84e09156ed05951f720ef3495554ff5098ef5a678c6a081","seed-audit:registered-certificate")
    def load(self):
        b=self.a.bundle
        self.p=arrays(b/"predictions.npz");self.t=arrays(b/"truth.npz");self.i=arrays(b/"inputs.npz")
        self.indices=np.load(b/"bootstrap_indices.npy",allow_pickle=False)
        self.saved=load_json(b/"metrics.json");self.starts=load_json(b/"starts.json")
        self.seeds=load_json(b/"seed-record.json")
    def metrics(self):
        p,t,ix=self.p,self.t,self.indices;n=len(np.unique(t["field_index"]))
        self.check(np.array_equal(p["row_ids"],t["row_id"]),"metrics:row-alignment")
        self.check(np.isfinite(p["estimate_uT"]).all(),"metrics:finite-predictions")
        self.check(ix.shape==(5000,n) and np.issubdtype(ix.dtype,np.integer),"bootstrap:shape-type")
        self.check(np.all((ix>=0)&(ix<n)),"bootstrap:bounds")
        wanted=np.random.default_rng(BOOT).integers(0,n,size=(5000,n))
        self.check(np.array_equal(ix,wanted),"bootstrap:registered-draws")
        out={"partition_fields":n,"bootstrap_seed":BOOT,"bootstrap_resamples":5000,"quantile_method":"linear","cells":{}}
        for cell in CELLS:
            arms={};take={}
            for bias in (0,250):
                positions=np.flatnonzero((t["cell"]==cell)&(self.i["bias_uT"]==bias))
                positions=positions[np.argsort(t["field_index"][positions])]
                self.check(np.array_equal(t["field_index"][positions],np.arange(n)),f"pair:{cell}:{bias}")
                y=t["field_uT"][positions];e=p["estimate_uT"][positions]
                fail=p["failed"][positions];bd=p["boundary"][positions];tim=p["elapsed_seconds"][positions]
                take[bias]=(positions,y,e,fail,bd,tim)
                arms[str(bias)]=summarize(e-y,fail,bd,tim)
                arms[str(bias)]["constant45"]=summarize(45-y,np.zeros(n,bool),np.zeros(n,bool),np.zeros(n))
            pos,y,e,fail,bd,tim=take[250];_,y0,e0,f0,b0,t0=take[0]
            self.check(np.array_equal(y,y0),"labels:paired-"+cell)
            contrasts={}
            for name,diff in [("biased_minus_zero",np.abs(e-y)-np.abs(e0-y)),("biased_minus_constant45",np.abs(e-y)-np.abs(45-y))]:
                means=np.sum(diff[ix],axis=1)/n
                contrasts[name]={"mean_uT":float(np.sum(diff)/n),"ci95_uT":[percentile(means,.025),percentile(means,.975)]}
            temp=t["temperature_K"][pos];bins=[]
            for lo,hi in [(-math.inf,288.15),(288.15,293.15),(293.15,298.15),(298.15,math.inf)]:
                mask=(temp>=lo)&(temp<hi)
                bins.append({"lower_K":None if not math.isfinite(lo) else lo,"upper_K":None if not math.isfinite(hi) else hi,"n":int(mask.sum()),
                    "biased":summarize((e-y)[mask],fail[mask],bd[mask],tim[mask]) if mask.any() else None,
                    "zero_bias":summarize((e0-y)[mask],f0[mask],b0[mask],t0[mask]) if mask.any() else None})
            sensitivity={str(delta):summarize(np.where(fail,45,e-delta)-y,fail,bd,tim) for delta in (-5,-1,0,1,5)}
            thermal=np.abs((temp-293.15)*.0742/GAMMA)
            out["cells"][cell]={"arms":arms,"paired_contrasts":contrasts,"temperature_bins":bins,
                "calibration_shift_uT":sensitivity,"single_line_temperature_error_uT":{"reference_K":293.15,"mean":float(thermal.mean()),"p95":percentile(thermal,.95),"max":float(thermal.max())}}
        a=out["cells"]["realistic_anchor"];biased=a["arms"]["250"];c=a["paired_contrasts"]
        conditions={"beats_zero":c["biased_minus_zero"]["ci95_uT"][1]<-.5,
            "beats_constant":c["biased_minus_constant45"]["ci95_uT"][1]<-.5,
            "mae":biased["mae_uT"]<=2,"p90":biased["p90_abs_uT"]<=5,"failure":biased["failure_fraction"]<=.01}
        out["gate"]={"conditions":conditions,"pass":all(conditions.values()),"claim":"Conditional simulated known-axis measurement-design comparison only."}
        self.report["recomputed_metrics"]=out
        self.compare(self.saved,out,"saved-metrics")
        self.check(self.cache["metric_receipt"]["gate_pass"]==out["gate"]["pass"],"receipt:gate")
    def structure(self):
        p,t,i=self.p,self.t,self.i;n=self.cache["input_manifest"]["fields"];rows=n*6
        self.check(set(i)=={"spectra","frequencies_mhz","bias_uT","row_ids"},"inputs:truth-exclusion")
        self.check(set(p)=={"row_ids","estimate_uT","failed","boundary","elapsed_seconds"},"predictions:keys")
        truth_keys={"mean","noise_standard_normal","field_index","field_uT","cell","temperature_K","mw_scale","gradient",
            "field_seed","nuisance_seed","noise_seed","trajectory_seed","trajectory_index","width_mhz","reference_snr","row_id"}
        self.check(set(t)==truth_keys,"truth:keys")
        expected_ids=[f"field{f:04d}:{cell}:bias{bias}" for f in range(n) for cell in CELLS for bias in (0,250)]
        for label,ids in [("input",i["row_ids"]),("truth",t["row_id"]),("prediction",p["row_ids"])]:
            self.check(ids.tolist()==expected_ids,label+":registered-order")
        self.check(np.array_equal(i["frequencies_mhz"],np.linspace(2820,2920,100)),"inputs:frequencies")
        self.check(np.array_equal(i["bias_uT"],np.tile([0.,250.],3*n)),"inputs:bias")
        self.check(np.array_equal(t["field_index"],np.repeat(np.arange(n),6)),"truth:field-index")
        self.check(np.array_equal(t["cell"],np.tile(np.repeat(CELLS,2),n)),"truth:registered-cell-order")
        for name in ("estimate_uT","failed","boundary","elapsed_seconds"):
            self.check(p[name].shape==(rows,),"predictions:shape-"+name)
        for name,width,snr in zip(CELLS,WIDTHS,SNRS):
            mask=t["cell"]==name
            self.check(np.all(t["width_mhz"][mask]==width) and np.all(t["reference_snr"][mask]==snr),"truth:cell-"+name)
        for name in ("spectra",):self.check(i[name].shape==(rows,100) and np.isfinite(i[name]).all(),"inputs:"+name)
        for name in ("mean","noise_standard_normal"):
            self.check(t[name].shape==(rows,100) and np.isfinite(t[name]).all(),"truth:"+name)
        self.check(np.all(t["mean"]>0),"truth:positive-mean")
        photons=(t["reference_snr"]/(.30*.015))**2
        formula=t["mean"]+np.sqrt(t["mean"]/photons[:,None])*t["noise_standard_normal"]
        self.check(np.allclose(i["spectra"],formula,rtol=0,atol=2e-15),"inputs:saved-noise-formula")
        shared=["field_uT","temperature_K","mw_scale","gradient","field_seed","nuisance_seed","noise_seed","trajectory_seed","trajectory_index","noise_standard_normal"]
        for name in shared:
            a=t[name].reshape((n,6)+t[name].shape[1:])
            self.check(np.array_equal(a,np.broadcast_to(a[:,0:1],a.shape)),"paired:"+name)
        self.check(np.all((t["field_uT"]>=20)&(t["field_uT"]<=70)),"truth:field-range")
        self.check(np.all((t["gradient"]>=.046875)&(t["gradient"]<=.346875)),"truth:gradient-range")
        self.check(np.all((t["trajectory_index"]>=0)&(t["trajectory_index"]<40000)),"truth:trajectory-index")
        self.check(np.all(t["temperature_K"]>=.001) and np.all(t["mw_scale"]>=.000001),"truth:positive-latents")
        for name in ("failed","boundary"):self.check(p[name].dtype==np.bool_,"predictions:boolean-"+name)
        self.check(np.all(p["estimate_uT"][p["failed"]]==45),"predictions:failed-fallback45")
        self.check(np.isfinite(p["elapsed_seconds"]).all() and np.all(p["elapsed_seconds"]>=0),"predictions:recorded-time")
        self.check(self.seeds["seed_audit_sha256"]==sha(self.a.seed_audit),"seeds:audit-hash")
        self.check(self.seeds["draw_order"]==["field_gradient","nuisance_index","noise"],"seeds:draw-order")
        for name,draws in zip(("field_seed","nuisance_seed","noise_seed"),self.seeds["draws"]):
            self.check(t[name][::6].tolist()==draws,"seeds:draw-to-row-"+name)
        self.check(len(self.seeds["draws"])==3,"seeds:three-streams")
        unique=set()
        for name in ("field_seed","nuisance_seed","noise_seed","trajectory_seed"):
            vals=t[name][::6]
            self.check(np.issubdtype(vals.dtype,np.integer) and np.all((vals>=LOW)&(vals<HIGH)),"seeds:namespace-"+name)
            unique.update(int(x) for x in vals)
        self.check(len(unique)==4*n and sorted(unique)==self.seeds["all_new_seeds"],"seeds:unique-accounted")
        audit=self.cache["seed_audit"]
        self.check(all(isinstance(v,int) and 0<=v<LOW for v in audit["old_seed_values"]),"seeds:old-range")
        self.check(bool(audit["old_seed_values"]) or bool(audit["old_seed_ranges"]),"seeds:old-evidence-present")
        for item in audit["old_seed_ranges"]:
            self.check(0<=item["lower"]<item["upper_exclusive"]<=LOW and len(item["source_sha256"])==64,"seeds:old-range-certificate")
        self.check(not unique.intersection(audit.get("new_used_seeds",[])) and BOOT not in unique,"seeds:no-prior-fresh-collision")
        self.report["rows_checked"]=rows
    def start_records(self):
        p,i=self.p,self.i
        self.check(len(self.starts)==len(p["row_ids"]),"starts:row-count")
        for row,answer in enumerate(self.starts):
            tag=f"starts:row{row}";records=answer["starts"];observed=i["spectra"][row]
            self.check(answer["estimate_uT"]==p["estimate_uT"][row] and answer["failed"]==bool(p["failed"][row])
                and answer["boundary"]==bool(p["boundary"][row]) and answer["elapsed_seconds"]==p["elapsed_seconds"][row],tag+":output")
            self.check(math.isfinite(answer["elapsed_seconds"]) and answer["elapsed_seconds"]>=0,tag+":elapsed")
            if not np.isfinite(observed).all():
                self.check(not records and answer["failed"] and answer["estimate_uT"]==45,tag+":invalid-observation")
                continue
            self.check(len(records)==6,tag+":six-starts")
            if len(records)==6:self.check(records[1]["initial"][1]==records[3]["initial"][1]==records[5]["initial"][1],tag+":shared-centroid-start")
            good=[]
            for j,record in enumerate(records):
                label=tag+f":start{j}";initial=np.array(record["initial"])
                self.check(initial.shape==(6,) and np.isfinite(initial).all(),label+":initial")
                self.check(initial[0]==(25,45,65)[j//2] and np.array_equal(initial[2:],[5,.015,1,.02]),label+":fixed-start")
                self.check(initial[1]==2871.50827 if j%2==0 else 2868<=initial[1]<=2875,label+":center-start")
                self.check(math.isfinite(record["elapsed_seconds"]) and record["elapsed_seconds"]>=0,label+":elapsed")
                self.check(isinstance(record["message"],str) and record["message"]!="",label+":termination-message")
                if record["parameters"] is None:
                    self.check(record["success"] is False and record["objective"] is None,label+":failed-start")
                else:
                    v=np.asarray(record["parameters"]);objective=record["objective"];mask=record["active_mask"]
                    self.check(v.shape==(6,) and np.isfinite(v).all() and np.all(v>=PARAM_LOW) and np.all(v<=PARAM_HIGH),label+":parameter-bounds")
                    self.check(math.isfinite(objective) and objective>=0,label+":finite-objective")
                    self.check(len(mask)==6 and all(x in (-1,0,1) for x in mask),label+":active-mask")
                    self.check(record["status"] in (-1,0,1,2,3,4) and record["success"]==(record["status"]>0),label+":status")
                    self.check(1<=record["nfev"]<=120 and 0<=record["njev"]<=record["nfev"],label+":evaluation-count")
                    if record["success"]:good.append(record)
            self.check(answer["elapsed_seconds"]+1e-12>=sum(r["elapsed_seconds"] for r in records),tag+":timing-components")
            if good:
                winner=min(good,key=lambda r:r["objective"])
                self.check(not answer["failed"] and answer["parameters"]==winner["parameters"]
                    and answer["estimate_uT"]==winner["parameters"][0],tag+":minimum-successful-objective")
                self.check(answer["boundary"]==bool(any(winner["active_mask"])),tag+":selected-boundary")
            else:
                self.check(answer["failed"] and answer["estimate_uT"]==45 and not answer["boundary"]
                    and answer["parameters"] is None,tag+":all-failed-fallback")
        elapsed=self.cache["prediction_receipt"]["total_process_seconds"]
        self.check(math.isfinite(elapsed) and elapsed+1e-12>=float(np.sum(p["elapsed_seconds"])),"timing:recorded-process-total")
        self.report["start_scope"]="Selection and boundary flags checked against saved start records; residual objectives and optimizer optimality were not recomputed."
    def provenance(self):
        a=self.a;n=self.cache["input_manifest"]["fields"];partition=self.cache["input_manifest"]["partition"];t=self.t
        if partition=="development":
            entropy=int(hashlib.sha256(b"tychon/scalar-information-limit/2026-10-15/dev").hexdigest(),16)
        else:
            self.check(a.reveal is not None and a.retired is not None,"provenance:retired-public-reveal-required")
            if a.reveal is None or a.retired is None:return
            self.check(a.reveal.name=="reveal.json" and a.retired.name=="retired.json","provenance:public-record-names")
            reveal=load_json(a.reveal);retired=load_json(a.retired)
            self.check({k:v for k,v in reveal.items() if k!="secret_hex"}==retired,"provenance:retired-record")
            self.check(bool(retired.get("retired_utc")) and retired.get("report_status") in ("complete","failed"),"provenance:terminal-retirement")
            secret=bytes.fromhex(reveal["secret_hex"])
            self.check(len(secret)==32 and hashlib.sha256(secret).hexdigest()==self.cache["freeze"]["commitment_sha256"],"provenance:revealed-commitment")
            self.check(reveal["freeze_sha256"]==sha(a.freeze) and reveal["access_sha256"]==sha(a.access),"provenance:reveal-binding")
            entropy=int.from_bytes(secret,"big")
        audit=self.cache["seed_audit"];used=set(audit["old_seed_values"])|set(audit.get("new_used_seeds",[]))|{BOOT}
        draws=[];reject=[]
        for label,child in zip(("field_gradient","nuisance_index","noise"),np.random.SeedSequence(entropy).spawn(3)):
            rng=np.random.default_rng(child);values=[]
            while len(values)<n:
                value=int(rng.integers(LOW,HIGH,dtype=np.int64))
                if value in used:reject.append({"stream":label,"position":len(values),"seed":value})
                else:values.append(value);used.add(value)
            draws.append(values)
        self.compare(self.seeds["draws"],draws,"provenance:master-streams")
        self.check(self.seeds["draw_order"]==["field_gradient","nuisance_index","noise"],"provenance:draw-order")
        maximum_temperature_error=maximum_mw_error=0.
        for field,(fs,ns,zs) in enumerate(zip(*draws)):
            row=field*6;rng=np.random.default_rng(fs)
            self.check(t["field_uT"][row]==rng.uniform(20,70) and t["gradient"][row]==rng.uniform(.046875,.346875),"provenance:field-gradient",field)
            ci,ct=np.random.SeedSequence(ns).spawn(2)
            index=int(np.random.default_rng(ci).integers(0,40000));rng=np.random.default_rng(ct)
            while True:
                trajectory=int(rng.integers(LOW,HIGH,dtype=np.int64))
                if trajectory not in used:used.add(trajectory);break
                reject.append({"stream":"derived_trajectory","parent_seed":ns,"seed":trajectory})
            self.check(index==t["trajectory_index"][row] and trajectory==t["trajectory_seed"][row],"provenance:trajectory-key",field)
            self.check(np.array_equal(np.random.default_rng(zs).standard_normal(100),t["noise_standard_normal"][row]),"provenance:noise-draw",field)
            child_t,child_m=np.random.SeedSequence(trajectory).spawn(2)
            nt=np.random.default_rng(child_t).standard_normal(index);nm=np.random.default_rng(child_m).standard_normal(index)
            if index:
                dt=math.exp(-.001);dm=math.exp(-10);steps=np.arange(1,index+1,dtype=float)
                forcing=(1-dt)*(293.15+15*np.sin(2*np.pi*(steps-1)/5400))+.05*math.sqrt((1-dt*dt)/.002)*nt
                temperatures=np.exp(-.001*steps)*(293.15+np.cumsum(np.exp(.001*steps)*forcing))
                ages=index-steps
                m=float(math.exp(-10*index)+np.sum(np.exp(-10*ages)*((1-dm)*(1-.0035*(temperatures-293.15))+.006*math.sqrt((1-dm*dm)/20)*nm)))
                temp=max(float(temperatures[-1]),.001);mw=max(m,.000001)
            else:temp,mw=293.15,1.
            te=abs(temp-t["temperature_K"][row]);me=abs(mw-t["mw_scale"][row])
            maximum_temperature_error=max(maximum_temperature_error,te);maximum_mw_error=max(maximum_mw_error,me)
            self.check(te<=1e-8 and me<=1e-10,"provenance:OU-closed-form-endpoint",{"field_index":field,"temperature_abs_error":te,"mw_abs_error":me})
        self.compare(self.seeds["rejected_collisions"],reject,"provenance:collision-order")
        self.report["optional_provenance"]={"fields":n,"maximum_temperature_abs_error_K":maximum_temperature_error,
            "maximum_mw_abs_error":maximum_mw_error,"method":"Closed-form OU recurrence, no renderer or fit."}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("bundle","protocol","registration","code-root","code-manifest","seed-audit","output"):
        p.add_argument("--"+name,type=Path,required=True)
    for name in ("expected-manifest-sha256","expected-commitment-revision","commitment-relative-path"):
        p.add_argument("--"+name,required=True)
    for name in ("freeze","access","secret-commitment","reveal","retired"):p.add_argument("--"+name,type=Path)
    p.add_argument("--check-provenance",action="store_true")
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);started=time.monotonic();audit=Audit(a)
    audit.phase("hashes-and-custody",audit.bindings);audit.phase("load-saved-arrays",audit.load)
    audit.phase("primary-metrics",audit.metrics);audit.phase("paired-rows-noise-and-flags",audit.structure)
    audit.phase("saved-start-selection",audit.start_records)
    if a.check_provenance:audit.phase("optional-revealed-seed-and-OU",audit.provenance)
    audit.report["status"]="pass" if not audit.report["failures"] else "fail"
    audit.report["verifier_wall_seconds"]=time.monotonic()-started
    audit.report["verifier_sha256"]=sha(Path(__file__))
    audit.report["expected_bundle_manifest_sha256"]=a.expected_manifest_sha256
    audit.report["limitations"]=["No forward renderer, spectrum generation, fit, inference or old consumed dataset was run.",
        "Saved start objectives are accepted as recorded values; only selection logic and flags are independently checked.",
        "No proof of procedural custody against the machine owner is claimed.",
        "Primary metrics remain in the report even if an independent provenance phase fails."]
    def safe_json(value):
        if isinstance(value,np.generic):value=value.item()
        if isinstance(value,float) and not math.isfinite(value):return {"nonfinite":repr(value)}
        if isinstance(value,dict):return {k:safe_json(v) for k,v in value.items()}
        if isinstance(value,(tuple,list)):return [safe_json(v) for v in value]
        return value
    (a.output/"verification.json").write_text(json.dumps(safe_json(audit.report),indent=2,allow_nan=False)+"\n")
    print(json.dumps({"status":audit.report["status"],"failure_count":len(audit.report["failures"]),
        "phases":audit.report["phases"],"report":str(a.output/"verification.json")}))
    raise SystemExit(0 if audit.report["status"]=="pass" else 1)
if __name__=="__main__":main()
