"""Development-only driver. Default registration refuses numerical execution."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def authorize(gate_path, cases_path):
    gate = json.loads(Path(gate_path).read_text())
    if gate.get("status") != "ROOT_APPROVED_DEVELOPMENT_SCREEN":
        raise RuntimeError("numerical screen is unregistered; root accounting gate required")
    if gate.get("allow_training") is not False or gate.get("allow_final_evaluation") is not False:
        raise RuntimeError("only classical development screening is implemented")
    required = {
        "experiments/sparse_acquisition_screen/core.py",
        "experiments/sparse_acquisition_screen/run_screen.py",
        "experiments/sparse_acquisition_screen/PROTOCOL.md",
        "experiments/scalar_information_limit/forward.py",
        "tests/test_sparse_acquisition_screen.py",
    }
    if not required.issubset(gate["source_files"]):
        raise RuntimeError("incomplete source/protocol freeze")
    if gate.get("maximum_cases") not in range(1, 9):
        raise RuntimeError("development screen is capped at eight cases")
    if not gate.get("preflight_passed"):
        raise RuntimeError("registered numerical preflight must pass first")
    for relative, digest in gate["source_files"].items():
        candidate = (ROOT / relative).resolve(strict=True)
        candidate.relative_to(ROOT)
        if sha(candidate) != digest:
            raise RuntimeError("frozen source mismatch: "+relative)
    if sha(cases_path) != gate["cases_sha256"]:
        raise RuntimeError("fresh-case manifest mismatch")
    audit = json.loads(Path(gate["seed_audit_path"]).read_text())
    if sha(gate["seed_audit_path"]) != gate["seed_audit_sha256"] or audit.get("status") != "pass":
        raise RuntimeError("fresh-seed audit missing")
    if (audit.get("cases_sha256") != gate["cases_sha256"]
            or audit.get("all_consumed_campaigns_checked") is not True):
        raise RuntimeError("seed audit does not cover frozen cases and prior campaigns")
    # Root owns the shared lock, campaign ledgers, and resource accounting.
    receipt_path = os.environ.get("TYCHON_ACTIVE_NUMERICAL_CONTEXT")
    if not receipt_path:
        raise RuntimeError("run through the registered accounting wrapper")
    receipt = json.loads(Path(receipt_path).read_text())
    if (receipt.get("status") != "running" or receipt.get("parent_pid") != os.getppid()
            or receipt.get("gate_sha256") != sha(gate_path)):
        raise RuntimeError("accounting context does not bind this child")
    import fcntl
    with open(receipt["shared_lock_path"], "r+") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            raise RuntimeError("accounting wrapper does not hold shared numerical lock")
    cases = json.loads(Path(cases_path).read_text())
    if (cases.get("partition") != "fresh-development"
            or not 1 <= len(cases["cases"]) <= gate["maximum_cases"]):
        raise RuntimeError("unregistered partition or case count")
    seeds = [x["noise_seed"] for x in cases["cases"]]
    if any(type(s) is not int or not (2**40 <= s < 2**63) for s in seeds):
        raise RuntimeError("screen seeds must use the audited 64-bit development namespace")
    if len(seeds) != len(set(seeds)) or any(s in audit["excluded_seeds"] for s in seeds):
        raise RuntimeError("duplicate or consumed seed")
    if set(seeds) != set(audit["approved_noise_seeds"]):
        raise RuntimeError("cases do not match approved seed inventory")
    ids = [x["case_id"] for x in cases["cases"]]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate case identifier")
    fixed = {"theta":0., "phi":0., "bias_uT":250., "slope":.02,
             "contrast":.015, "temperature_K":293.15, "mw_scale":1.,
             "gradient":.196875}
    ranges = {"field_uT":(20.,70.), "center_mhz":(0.,.6), "width_mhz":(4.,6.)}
    import math
    for case in cases["cases"]:
        point = case["point"]
        if set(point) != set(fixed) | set(ranges):
            raise RuntimeError("case must declare exactly the registered Point fields")
        if any(point[k] != v for k,v in fixed.items()):
            raise RuntimeError("case changed a fixed calibration or known-axis parameter")
        if any(not math.isfinite(point[k]) or not lo <= point[k] <= hi
               for k,(lo,hi) in ranges.items()):
            raise RuntimeError("case outside declared prior")
    return gate, cases


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gate", type=Path, required=True)
    p.add_argument("--cases", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    gate, cases = authorize(a.gate, a.cases)
    # Importing numerical modules occurs only after the accounting gate.
    from experiments.sparse_acquisition_screen.core import (
        Acquisition, GridBelief, UniformPolicy, CoarseToFinePolicy,
        FisherPolicy, BayesianPolicy, Point, simulate_episode,
    )
    a.out.mkdir(parents=True, exist_ok=False)
    (a.out/"started.json").write_text(json.dumps({"gate_sha256":sha(a.gate)}))
    config = Acquisition(**gate["acquisition"])
    config.validate()
    if (config.maximum_actions > 32 or config.primary_actions > 24
            or config.recovery_actions > 8):
        raise RuntimeError("registered action budgets exceed this preparation scope")
    start = time.perf_counter()
    prior = GridBelief()
    setup_seconds = time.perf_counter()-start
    rows = []
    try:
        for case in cases["cases"]:
            point = Point(**case["point"])
            for policy in (UniformPolicy(), CoarseToFinePolicy(), FisherPolicy(), BayesianPolicy()):
                row = simulate_episode(point, case["noise_seed"], policy, prior, config)
                row.update(case_id=case["case_id"], truth_uT=point.field_uT,
                    absolute_error_uT=abs(row["estimate_uT"]-point.field_uT),
                    interval_contains_truth=bool(row["lower_uT"] <= point.field_uT <= row["upper_uT"]))
                rows.append(row)
                (a.out/"partial-results.json").write_text(json.dumps(rows, indent=2)+"\n")
        result = {"status":"development-only", "setup_seconds":setup_seconds,
            "acquisition":asdict(config), "gate_sha256":sha(a.gate),
            "cases_sha256":sha(a.cases), "rows":rows}
        (a.out/"results.json").write_text(json.dumps(result, indent=2)+"\n")
    except Exception as exc:
        (a.out/"failure.json").write_text(json.dumps({"error":repr(exc),"completed_rows":len(rows)}))
        raise
    print(json.dumps({"status":"development-only","rows":len(rows),"results":str(a.out/"results.json")}))


if __name__ == "__main__":
    main()
