"""Fresh paired known-axis spectra. Evaluation entropy comes only from custody."""
import argparse,hashlib,json,os,sys
from pathlib import Path
import numpy as np
from budget import approved,sha,write_json,BOOTSTRAP_SEED
from custody import safe
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scalar_information_limit"))
from forward import Point,forward,FREQUENCIES_MHZ
from fit import FACTOR

CELLS=(("realistic_anchor",5.,10.),("wide_lines",7.,10.),("low_snr",5.,3.))
LOW_SEED,HIGH_SEED=2**40,2**63
DEV_LABEL="tychon/scalar-information-limit/2026-10-15/dev"

def seed_values(value,key=""):
    found=set()
    if isinstance(value,dict):
        for child_key,child in value.items():found.update(seed_values(child,child_key.lower()))
    elif "seed" in key and isinstance(value,int) and not isinstance(value,bool):found.add(value)
    elif "seed" in key and isinstance(value,list):
        found.update(x for x in value if isinstance(x,int) and not isinstance(x,bool))
    elif isinstance(value,list):
        for child in value:found.update(seed_values(child,key))
    return found

def audit_metadata(certificate,expected,metadata,new_records,out,sanitized,private_map):
    certificate=safe(certificate).resolve(strict=True)
    if sha(certificate)!=expected:raise ValueError("seed certificate hash mismatch")
    cert=json.loads(Path(certificate).read_text())
    required={safe(x["path"]).resolve(strict=True):x for x in cert["files"]}
    supplied={safe(x).resolve(strict=True) for x in metadata}
    if not set(required)<=supplied:raise ValueError("missing certificate metadata source")
    if cert.get("all_sha256_match") is not True or cert.get("all_known_bounds_lt_2^40") is not True:
        raise ValueError("range certificate not passed")
    found=set(cert["excluded_master_seeds"]);found.add(cert["old_reserved_final"]["master_seed"])
    sources=[];mapping={}
    for i,path in enumerate(sorted(supplied)):
        if path.suffix!=".json":raise ValueError("metadata JSON only")
        digest=sha(path);values=seed_values(json.loads(path.read_text()))
        if path in required:
            item=required[path]
            if digest!=item["sha256"] or len(values)!=item["explicit_seed_count"]:
                raise ValueError("prior metadata certificate mismatch")
        if any(not 0<=x<LOW_SEED for x in values):raise ValueError("old seed reaches new namespace")
        found.update(values);opaque=f"prior-metadata-{i:03d}"
        sources.append({"source_id":opaque,"sha256":digest,"seed_count":len(values)})
        mapping[opaque]=str(path)
    bootstrap=cert["other_prior_masters"]["repair_bootstrap_namespace"]
    found.update(range(bootstrap[0],bootstrap[1]+1))
    found.update(v for v in cert["other_prior_masters"].values() if isinstance(v,int))
    new=[]
    for path in new_records:
        record=json.loads(safe(path).read_text());values=record["all_new_seeds"]
        if any(not LOW_SEED<=x<HIGH_SEED for x in values):raise ValueError("invalid fresh seed namespace")
        new.extend(values)
    if len(set(new))!=len(new):raise ValueError("prior fresh partitions share seeds")
    clean=json.loads(json.dumps(cert));clean["roots"]={k:k for k in clean["roots"]}
    for item in clean["files"]:item["path"]=item["root_label"]+"/"+item["relative_path"]
    clean["original_certificate_sha256"]=expected
    write_json(sanitized,clean);write_json(private_map,mapping)
    write_json(out,{"status":"pass","old_seed_values":sorted(found),
        "old_seed_ranges":[{"lower":0,"upper_exclusive":2**32,"source_sha256":expected}],
        "new_used_seeds":sorted(new),"reserved_bootstrap_seed":BOOTSTRAP_SEED,"sources":sources,"certificate_sha256":expected,
        "sanitized_certificate_sha256":sha(sanitized),
        "range_note":"Certificate covers omitted holdout rows and never-generated old final; no reconstruction."})

def seed_audit(path):
    audit=json.loads(Path(path).read_text())
    if audit.get("status")!="pass":raise ValueError("seed audit not passed")
    if audit.get("certificate_sha256")!="6acd082f907d33f3e84e09156ed05951f720ef3495554ff5098ef5a678c6a081":
        raise ValueError("unregistered seed certificate")
    old=audit["old_seed_values"];ranges=audit["old_seed_ranges"]
    if not old and not ranges:raise ValueError("missing old-seed evidence")
    if any(not isinstance(s,int) or not 0<=s<LOW_SEED for s in old):
        raise ValueError("old seed outside audited low range")
    for item in ranges:
        if not 0<=item["lower"]<item["upper_exclusive"]<=LOW_SEED or not item["source_sha256"]:
            raise ValueError("old seed range certificate invalid")
    used=set(old)|set(audit.get("new_used_seeds",[]))|{BOOTSTRAP_SEED}
    return used

def streams(entropy,n,used):
    draws=[];rejections=[];rngs=[np.random.default_rng(s) for s in np.random.SeedSequence(entropy).spawn(3)]
    for label,rng in zip(("field_gradient","nuisance_index","noise"),rngs):
        values=[]
        while len(values)<n:
            value=int(rng.integers(LOW_SEED,HIGH_SEED,dtype=np.int64))
            if value in used:rejections.append({"stream":label,"position":len(values),"seed":value});continue
            used.add(value);values.append(value)
        draws.append(values)
    return draws,rejections

def nuisance(seed,used,rejections):
    child_index,child_trajectory=np.random.SeedSequence(seed).spawn(2)
    index=int(np.random.default_rng(child_index).integers(0,40000))
    rng=np.random.default_rng(child_trajectory)
    while True:
        trajectory=int(rng.integers(LOW_SEED,HIGH_SEED,dtype=np.int64))
        if trajectory not in used:used.add(trajectory);break
        rejections.append({"stream":"derived_trajectory","parent_seed":seed,"seed":trajectory})
    return index,trajectory

def trajectory_at(index,seed):
    t_seed,m_seed=np.random.SeedSequence(seed).spawn(2)
    nt=np.random.default_rng(t_seed).standard_normal(index)
    nm=np.random.default_rng(m_seed).standard_normal(index)
    dt=np.exp(-.001);dm=np.exp(-10.)
    st=.05*np.sqrt((1-dt*dt)/(.002));sm=.006*np.sqrt((1-dm*dm)/20)
    temperature,mw=293.15,1.
    for i in range(index):
        environment=293.15+15*np.sin(2*np.pi*i/5400)
        temperature=environment+(temperature-environment)*dt+st*nt[i]
        target=1-.0035*(temperature-293.15)
        mw=target+(mw-target)*dm+sm*nm[i]
    return max(temperature,.001),max(mw,.000001)

def generate(entropy,partition,out,audit_path,context):
    n={"development":32,"evaluation":256}[partition]
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    inputs=[];truth=[];records=[]
    try:
        used=seed_audit(audit_path);prior_used=used.copy();draws,rejected=streams(entropy,n,used)
        for field_index,(field_seed,nuisance_seed,noise_seed) in enumerate(zip(*draws)):
            rng=np.random.default_rng(field_seed)
            field=float(rng.uniform(20,70));gradient=float(rng.uniform(.046875,.346875))
            index,trajectory_seed=nuisance(nuisance_seed,used,rejected)
            temperature,mw=trajectory_at(index,trajectory_seed)
            noise=np.random.default_rng(noise_seed).standard_normal(100)
            for cell,width,snr in CELLS:
                for bias in (0.,250.):
                    row_id=f"field{field_index:04d}:{cell}:bias{int(bias)}"
                    point=Point(field_uT=field,theta=0.,phi=0.,bias_uT=bias,width_mhz=width,
                                temperature_K=temperature,mw_scale=mw,gradient=gradient)
                    mean,_=forward(point,"fixed_amplitude",FACTOR)
                    observed=mean+np.sqrt(mean/(snr/(.30*.015))**2)*noise
                    inputs.append((observed,bias,row_id))
                    truth.append((mean,noise))
                    records.append({"field_index":field_index,"field_uT":field,"cell":cell,
                        "temperature_K":temperature,"mw_scale":mw,"gradient":gradient,
                        "field_seed":field_seed,"nuisance_seed":nuisance_seed,"noise_seed":noise_seed,
                        "trajectory_seed":trajectory_seed,"trajectory_index":index,
                        "width_mhz":width,"reference_snr":snr,"row_id":row_id})
        np.savez_compressed(out/"inputs.npz",spectra=np.stack([r[0] for r in inputs]),
            frequencies_mhz=FREQUENCIES_MHZ,bias_uT=np.array([r[1] for r in inputs]),
            row_ids=np.array([r[2] for r in inputs]))
        values={k:np.array([r[k] for r in records]) for k in records[0]}
        np.savez_compressed(out/"truth.npz",mean=np.stack([r[0] for r in truth]),
            noise_standard_normal=np.stack([r[1] for r in truth]),**values)
        write_json(out/"seed-record.json",{"draw_order":["field_gradient","nuisance_index","noise"],
            "draws":draws,"all_new_seeds":sorted(used-prior_used),
            "rejected_collisions":rejected,"seed_audit_sha256":sha(audit_path)})
        files={name:sha(out/name) for name in ("inputs.npz","truth.npz","seed-record.json")}
        write_json(out/"manifest.json",{"status":"complete","partition":partition,"fields":n,
            "rows":len(inputs),"files":files,**context})
        if partition=="evaluation":
            for p in out.iterdir():p.chmod(0o444)
            out.chmod(0o555)
    except Exception as exc:
        write_json(out/"failure.json",{"status":"failed","error":type(exc).__name__+": "+str(exc),**context})
        raise
    return out/"manifest.json"

def main():
    p=argparse.ArgumentParser()
    for name in ("protocol","registration","seed-audit","out"):p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--partition",choices=("development","evaluation"),required=True)
    for name in ("custody-root","code-root","code-manifest","freeze"):p.add_argument("--"+name,type=Path)
    a=p.parse_args();approved(a.registration,a.protocol)
    context={"protocol_sha256":sha(a.protocol),"registration_sha256":sha(a.registration),
        "freeze_sha256":None,"commitment_sha256":None}
    if a.partition=="development":entropy=int(hashlib.sha256(DEV_LABEL.encode()).hexdigest(),16)
    else:
        if any(getattr(a,x) is None for x in ("custody_root","code_root","code_manifest","freeze")):
            p.error("evaluation requires custody and frozen code")
        from custody import consume_entropy
        audit_relative=a.seed_audit.resolve().relative_to(a.code_root.resolve()).as_posix()
        frozen=json.loads(a.code_manifest.read_text())["files"]
        if frozen.get(audit_relative)!=sha(a.seed_audit):raise ValueError("seed audit is not frozen")
        entropy=consume_entropy(custody_root=a.custody_root,protocol=a.protocol,
            registration=a.registration,code_root=a.code_root,code_manifest=a.code_manifest,
            freeze_sha256=sha(a.freeze),output_root=a.out)
        context.update(freeze_sha256=sha(a.freeze),
            commitment_sha256=json.loads(a.freeze.read_text())["commitment_sha256"])
    result=generate(entropy,a.partition,a.out,a.seed_audit,context)
    print(json.dumps({"manifest":str(result),"manifest_sha256":sha(result),"status":"complete"}))
if __name__=="__main__":
    if len(sys.argv)>1 and sys.argv[1]=="audit":
        p=argparse.ArgumentParser()
        for name in ("certificate","out","sanitized-certificate","private-map"):
            p.add_argument("--"+name,type=Path,required=True)
        p.add_argument("--expected-certificate-sha256",required=True)
        p.add_argument("--metadata",type=Path,action="append",required=True)
        p.add_argument("--new-seed-record",type=Path,action="append",default=[])
        a=p.parse_args(sys.argv[2:])
        audit_metadata(a.certificate,a.expected_certificate_sha256,a.metadata,
            a.new_seed_record,a.out,a.sanitized_certificate,a.private_map)
    else:main()

