"""Run a bounded numerical command under cumulative ledger and final-reserve limits."""
import argparse, datetime, fcntl, json, math, os, resource, subprocess, time
from pathlib import Path
def usage(paths):
    cpu=wall=0.;conservative=[]
    for path in set(map(Path,paths)):
        if not path.exists():raise ValueError("budget ledger missing: "+str(path))
        entries=[json.loads(line) for line in path.read_text().splitlines()]
        standard_keys={o["correction_of_utc"] for o in entries if "correction_of_utc" in o}
        entries=[o for o in entries if not ("adjustment_cpu_seconds" in o and o.get("original_completed_utc") in standard_keys)]
        adjustments={}
        for obj in entries:
            key=obj.get("original_completed_utc",obj.get("correction_of_utc"))
            if key:
                amount=obj.get("adjustment_cpu_seconds",obj.get("cpu_seconds"))
                if not isinstance(amount,(int,float)) or not math.isfinite(amount) or amount<0:raise ValueError("invalid CPU adjustment")
                if not any(e.get("completed_utc",e.get("utc"))==key for e in entries):raise ValueError("CPU adjustment lacks original")
                adjustments[key]=adjustments.get(key,0)+amount
        for number,obj in enumerate(entries,1):
            if obj.get("job")=="cpu_adjustment":
                cpu+=obj.get("adjustment_cpu_seconds",obj.get("cpu_seconds"));continue
            w=obj.get("wall_seconds");c=obj.get("cpu_seconds")
            adjusted=adjustments.get(obj.get("completed_utc",obj.get("utc")),0)
            if not isinstance(w,(int,float)) or not math.isfinite(w) or w<0:raise ValueError("invalid wall accounting")
            if c is None:
                if adjusted>=4*w-1e-6:c=0
                else:c=4*w
                conservative.append(f"{path}:{number}: unknown CPU charged four times wall")
            if not isinstance(c,(int,float)) or not math.isfinite(c) or c<0:raise ValueError("invalid CPU accounting")
            # Earlier wrappers measured parent CPU only. Charging at least wall is conservative for this one-thread lane.
            if c<w and not adjusted:conservative.append(f"{path}:{number}: CPU charged at least wall")
            cpu+=c if adjusted else max(c,w);wall+=w
    return dict(cpu_seconds=cpu,wall_seconds=wall,conservative_adjustments=conservative)
def check_budget(total,local,seconds,stage,cpu_cap=14400,wall_cap=7200):
    if not 0<seconds<=900:raise ValueError("job reserve must be 1..900 seconds")
    reserve_cpu,reserve_wall=(0,0) if stage=="final" else (7200,1800)
    if total["cpu_seconds"]+seconds+reserve_cpu>cpu_cap or total["wall_seconds"]+seconds+reserve_wall>wall_cap:
        raise ValueError("shared cap or final reserve would be exceeded")
    if stage=="development" and (local["cpu_seconds"]+seconds>1800 or local["wall_seconds"]+seconds>900):
        raise ValueError("development allocation would be exceeded")
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True);p.add_argument("--budget-ledger",type=Path,action="append",default=[])
    p.add_argument("--budget-lock",type=Path,required=True)
    p.add_argument("--stage",choices=("development","validation","final"),default="development")
    p.add_argument("--seconds",type=int,default=120)
    p.add_argument("command",nargs=argparse.REMAINDER);a=p.parse_args()
    cmd=a.command[1:] if a.command[:1]==["--"] else a.command
    if not cmd:p.error("a command is required")
    a.ledger.parent.mkdir(parents=True,exist_ok=True);a.ledger.touch(exist_ok=True)
    a.budget_lock.parent.mkdir(parents=True,exist_ok=True)
    with a.budget_lock.open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        total=usage([a.ledger,*a.budget_ledger]);local=usage([a.ledger])
        check_budget(total,local,a.seconds,a.stage)
        started=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
        def limits():
            resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
            resource.setrlimit(resource.RLIMIT_CPU,(a.seconds,a.seconds))
        state="complete";rc=124
        try:
            result=subprocess.run(cmd,env={**os.environ,"CUDA_VISIBLE_DEVICES":"-1",
                "OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
                "TF_NUM_INTRAOP_THREADS":"1","TF_NUM_INTEROP_THREADS":"1"},
                timeout=a.seconds,preexec_fn=limits)
            rc=result.returncode
            if rc:state="failed"
        except subprocess.TimeoutExpired:state="timeout"
        finally:
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            receipt=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,
                wall_seconds=time.monotonic()-started,
                cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                peak_memory_bytes=after.ru_maxrss*1024,returncode=rc,status=state,
                stage=a.stage,reserved_seconds=a.seconds,budget_before=total)
            with a.ledger.open("a") as f:f.write(json.dumps(receipt)+"\n")
        print(json.dumps(receipt),flush=True)
    raise SystemExit(rc)
if __name__=="__main__":main()
