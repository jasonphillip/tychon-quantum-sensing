"""Shared accounting, bounded execution, and registration binding for Stage 2."""
import argparse,datetime,hashlib,importlib.util,json,os,platform,subprocess,sys,time
from pathlib import Path

BOOTSTRAP_SEED=2**40+int(hashlib.sha256(
    b"tychon/scalar-information-limit/2026-10-15/bootstrap").hexdigest(),16)%(2**63-2**40)

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write_json(path,value):
    with Path(path).open("x") as stream:json.dump(value,stream,indent=2,allow_nan=False);stream.write("\n")
def approved(registration,protocol):
    record=json.loads(Path(registration).read_text())
    if record.get("stage")!="stage2" or record.get("approved") is not True:
        raise ValueError("Stage 2 is not registered and approved")
    if record.get("protocol_sha256")!=sha(protocol):raise ValueError("protocol binding failed")
    return record

def bindings(args,manifest,phase):
    approved(args.registration,args.protocol)
    record=json.loads(Path(manifest).read_text())
    if record["protocol_sha256"]!=sha(args.protocol):raise ValueError("data/protocol mismatch")
    values={"freeze_sha256":None,"access_sha256":None,"input_manifest_sha256":sha(manifest)}
    if record["partition"]=="evaluation":
        from custody import verify_access,immutable
        if any(getattr(args,k,None) is None for k in ("freeze","access","code_root")):
            raise ValueError("evaluation requires freeze/access bindings")
        verify_access(protocol=args.protocol,registration=args.registration,freeze=args.freeze,
            access=args.access,code_root=args.code_root,data_manifest=manifest)
        values.update(freeze_sha256=sha(args.freeze),access_sha256=sha(args.access))
        immutable(args.access.parent/(phase+".used.json"),{"status":"started",**values})
    return record,values

def cap_check(stage,study,shared,seconds,publication=False):
    if not 0<seconds<=900:raise ValueError("reservation must be 1..900 seconds")
    reserve=0 if publication else 120
    for key,stagecap,studycap,sharedcap in (
        ("cpu_seconds",2700,5400,14400),("wall_seconds",1500,3600,7200)):
        if stage[key]+seconds+reserve>stagecap:raise ValueError("Stage 2 cap/publication reserve")
        if study[key]+seconds+reserve>studycap:raise ValueError("study cap/publication reserve")
        if shared[key]+seconds+reserve>sharedcap:raise ValueError("shared cap/publication reserve")

def runtime():
    import numpy,scipy
    cpu=platform.processor()
    cpuinfo=Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith(("model name","Model")):cpu=line.split(":",1)[-1].strip();break
    return {"cpu":cpu or platform.machine(),"os":platform.platform(),"python":platform.python_version(),
            "numpy":numpy.__version__,"scipy":scipy.__version__,"workers":1}

def main():
    import fcntl,resource
    p=argparse.ArgumentParser()
    for name in ("registration","protocol","stage2-ledger","stage1-ledger","lock","accounting-module"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--prior-ledger",type=Path,action="append",required=True)
    p.add_argument("--seconds",type=int,required=True)
    p.add_argument("--phase",choices=("tests","development","evaluation","metrics","publication"),required=True)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args();approved(a.registration,a.protocol)
    if len(set(a.prior_ledger))!=2:raise ValueError("both original ledgers required")
    if len({p.resolve() for p in (a.stage2_ledger,a.stage1_ledger,*a.prior_ledger)})!=4:
        raise ValueError("four distinct budget ledgers required")
    cmd=a.command[1:] if a.command[:1]==["--"] else a.command
    if not cmd:raise ValueError("missing bounded command")
    spec=importlib.util.spec_from_file_location("prior_accounting",a.accounting_module)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    a.stage2_ledger.parent.mkdir(parents=True,exist_ok=True);a.stage2_ledger.touch(exist_ok=True)
    with a.lock.open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        stage=module.usage([a.stage2_ledger]);study=module.usage([a.stage2_ledger,a.stage1_ledger])
        shared=module.usage([a.stage2_ledger,a.stage1_ledger,*a.prior_ledger])
        cap_check(stage,study,shared,a.seconds,a.phase=="publication")
        module.check_budget(shared,stage,a.seconds,"validation")
        start=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN);rc=124;status="complete"
        def limits():
            resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
            resource.setrlimit(resource.RLIMIT_CPU,(a.seconds,a.seconds))
        try:
            env={**os.environ,"CUDA_VISIBLE_DEVICES":"-1","OMP_NUM_THREADS":"1",
                 "OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1"}
            rc=subprocess.run(cmd,env=env,timeout=a.seconds,preexec_fn=limits).returncode
            if rc:status="failed"
        except subprocess.TimeoutExpired:status="timeout"
        finally:
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            receipt={"utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"command":cmd,
                "status":status,"returncode":rc,"stage":"scalar_bias_design:"+a.phase,
                "wall_seconds":time.monotonic()-start,
                "cpu_seconds":after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                "peak_memory_bytes":after.ru_maxrss*(1 if sys.platform=="darwin" else 1024),
                "reserved_seconds":a.seconds,"protocol_sha256":sha(a.protocol),
                "stage_before":stage,"study_before":study,"budget_before":shared}
            with a.stage2_ledger.open("a") as stream:stream.write(json.dumps(receipt)+"\n")
        print(json.dumps({k:receipt[k] for k in ("status","returncode","cpu_seconds","wall_seconds","peak_memory_bytes")}))
    raise SystemExit(rc)
if __name__=="__main__":main()
