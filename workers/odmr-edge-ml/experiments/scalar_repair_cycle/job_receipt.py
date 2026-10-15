"""Run one bounded numerical command and append a persistent compute receipt."""
import argparse, datetime, json, os, resource, subprocess, time
from pathlib import Path
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ledger",type=Path,required=True);p.add_argument("--seconds",type=int,default=600)
    p.add_argument("command",nargs=argparse.REMAINDER);a=p.parse_args()
    cmd=a.command[1:] if a.command[:1]==["--"] else a.command
    if not cmd: p.error("a command is required")
    a.ledger.parent.mkdir(parents=True,exist_ok=True)
    started=time.monotonic();before=resource.getrusage(resource.RUSAGE_CHILDREN)
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(8*1024**3,8*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(min(a.seconds,900),min(a.seconds,900)))
    state="complete";rc=124
    try:
        result=subprocess.run(cmd,env={**os.environ,"CUDA_VISIBLE_DEVICES":"-1",
            "OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1",
            "TF_NUM_INTRAOP_THREADS":"1","TF_NUM_INTEROP_THREADS":"1"},
            timeout=a.seconds,preexec_fn=limits)
        rc=result.returncode
        if rc:state="failed"
    except subprocess.TimeoutExpired:
        state="timeout"
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    receipt=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),command=cmd,
        wall_seconds=time.monotonic()-started,
        cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
        peak_memory_bytes=after.ru_maxrss*1024,returncode=rc,status=state)
    with a.ledger.open("a") as f:f.write(json.dumps(receipt)+"\n")
    print(json.dumps(receipt),flush=True)
    raise SystemExit(rc)
if __name__=="__main__":main()
