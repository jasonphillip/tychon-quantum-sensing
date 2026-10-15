"""Additional stage/study budget gate, run INSIDE the existing shared-lock wrapper."""
import argparse,importlib.util,json,os,sys
from pathlib import Path
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registration",type=Path,required=True)
    p.add_argument("--reserve-seconds",type=int,required=True)
    p.add_argument("--accounting-module",type=Path,required=True)
    p.add_argument("command",nargs=argparse.REMAINDER)
    a=p.parse_args();r=json.loads(a.registration.read_text());limits=r["limits"]
    spec=importlib.util.spec_from_file_location("accounting",a.accounting_module)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    own=m.usage([Path(r["ledger"])])
    total=m.usage([Path(r["ledger"]),*map(Path,r["peer_ledgers"])])
    for key,stagecap,studycap,sharedcap in [
        ("cpu_seconds","stage_cpu_seconds","study_cpu_seconds","shared_cpu_seconds"),
        ("wall_seconds","stage_cumulative_wall_seconds","study_cumulative_wall_seconds","shared_cumulative_wall_seconds")]:
        if own[key]+a.reserve_seconds>min(limits[stagecap],limits[studycap]):
            raise RuntimeError("stage/study cumulative reservation cap")
        if total[key]+a.reserve_seconds>limits[sharedcap]:
            raise RuntimeError("shared cumulative reservation cap")
    cmd=a.command[1:] if a.command[:1]==["--"] else a.command
    if not cmd:raise ValueError("command missing")
    if any(os.environ.get(name)!="1" for name in ("OMP_NUM_THREADS","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")):
        raise RuntimeError("thread controls absent; use accounting wrapper")
    print(json.dumps({"event":"new_information_diagnostic_budget_gate","own_before":own,
       "shared_before":total,"reserved_seconds":a.reserve_seconds,
       "accounting_label":"validation is only a legacy wrapper label, not old validation access"}),flush=True)
    os.execv(cmd[0],cmd)
if __name__=="__main__":main()
