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


from experiments.sparse_acquisition_screen.accounting import authorize_stage, sha


def authorize(gate_path, cases_path):
    gate = authorize_stage(gate_path, "ROOT_APPROVED_DEVELOPMENT_SCREEN")
    if gate.get("maximum_cases") not in range(1,9):
        raise RuntimeError("development screen is capped at eight cases")
    evidence = Path(gate["qualification_verification_path"])
    if sha(evidence) != gate["qualification_verification_sha256"]:
        raise RuntimeError("qualification verification digest mismatch")
    verdict = json.loads(evidence.read_text())
    if (verdict.get("status") != "qualification_pass"
            or verdict.get("source_files") != gate["source_files"]
            or verdict.get("specification_sha256") != gate["qualification_spec_sha256"]):
        raise RuntimeError("Bayesian/grid qualification absent or stale")
    if sha(cases_path) != gate["cases_sha256"]:
        raise RuntimeError("fresh-case manifest mismatch")
    audit = json.loads(Path(gate["seed_audit_path"]).read_text())
    if sha(gate["seed_audit_path"]) != gate["seed_audit_sha256"] or audit.get("status") != "pass":
        raise RuntimeError("fresh-seed audit missing")
    if (audit.get("cases_sha256") != gate["cases_sha256"]
            or audit.get("all_consumed_campaigns_checked") is not True):
        raise RuntimeError("seed audit does not cover frozen cases and prior campaigns")
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
    (a.out/"cases.json").write_bytes(a.cases.read_bytes())
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
            for policy_type in (UniformPolicy, CoarseToFinePolicy, FisherPolicy, BayesianPolicy):
                before = time.perf_counter()
                policy = policy_type()
                policy_setup_seconds = time.perf_counter()-before
                row = simulate_episode(point, case["noise_seed"], policy, prior, config)
                row["policy_setup_seconds"] = policy_setup_seconds
                row["modeled_total_seconds"] += policy_setup_seconds
                row.update(case_id=case["case_id"], truth_uT=point.field_uT,
                    absolute_error_uT=abs(row["estimate_uT"]-point.field_uT),
                    interval_contains_truth=bool(row["lower_uT"] <= point.field_uT <= row["upper_uT"]))
                rows.append(row)
                (a.out/"partial-results.json").write_text(json.dumps(rows, indent=2)+"\n")
        result = {"status":"development-only", "setup_seconds":setup_seconds,
            "acquisition":asdict(config), "gate_sha256":sha(a.gate),
            "cases_sha256":sha(a.cases), "source_commit":gate["source_commit"],
            "source_files":gate["source_files"],
            "qualification_verification_sha256":gate["qualification_verification_sha256"], "rows":rows}
        (a.out/"results.json").write_text(json.dumps(result, indent=2)+"\n")
    except Exception as exc:
        (a.out/"failure.json").write_text(json.dumps({"error":repr(exc),"completed_rows":len(rows)}))
        raise
    print(json.dumps({"status":"development-only","rows":len(rows),"results":str(a.out/"results.json")}))


if __name__ == "__main__":
    main()
