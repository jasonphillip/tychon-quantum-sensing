"""Independent arithmetic on saved artifacts; never calls models or policies."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def near(actual, expected, label, absolute=1e-7, relative=1e-10):
    require(math.isfinite(actual) and math.isfinite(expected), label+": nonfinite")
    require(abs(actual-expected) <= absolute + relative*abs(expected), label+": mismatch")


def quantile(values, q):
    values = sorted(values)
    pos = (len(values)-1)*q
    lo, hi = math.floor(pos), math.ceil(pos)
    return values[lo]*(hi-pos)+values[hi]*(pos-lo) if lo!=hi else values[lo]


def posterior(table, observations):
    states, rates = table["states"], table["rates"]
    # Likelihood ratios avoid subtracting large Poisson constants.
    reference = rates[0]
    logw = []
    for row in rates:
        value = 0.
        for observation in observations:
            i, count, exposure = (observation[k] for k in ("index","count","exposure_photons"))
            value += count*math.log(row[i]/reference[i])-exposure*(row[i]-reference[i])
        logw.append(value)
    maximum = max(logw)
    weights = [math.exp(v-maximum) for v in logw]
    total = math.fsum(weights)
    weights = [v/total for v in weights]
    grouped = {}
    for state, weight in zip(states, weights):
        grouped.setdefault(state[0],[]).append(weight)
    marginal = [(field,math.fsum(parts)) for field,parts in sorted(grouped.items())]
    mean = math.fsum(field*mass for field,mass in marginal)
    variance = math.fsum((field-mean)**2*mass for field,mass in marginal)
    def qtile(q):
        running=0.
        for field,mass in marginal:
            running += mass
            if running >= q:
                return field
        return marginal[-1][0]
    return {"weights":weights,"marginal":marginal,"mean_uT":mean,"variance_uT2":variance,
            "estimate_uT":qtile(.5),"lower_uT":qtile(.025),"upper_uT":qtile(.975),
            "boundary_mass":marginal[0][1]+marginal[-1][1]}


def wasserstein(a,b):
    ma,mb=dict(a),dict(b)
    points=sorted(set(ma)|set(mb))
    ca=cb=total=0.
    for j,point in enumerate(points[:-1]):
        ca+=ma.get(point,0.)
        cb+=mb.get(point,0.)
        total+=abs(ca-cb)*(points[j+1]-point)
    return total


def verify_qualification(folder):
    manifest=json.loads((folder/"artifact_manifest.json").read_text())
    for name,digest in manifest["files"].items():
        require(Path(name).name==name,"manifest path escaped artifact folder")
        require(sha(folder/name)==digest,"artifact digest mismatch: "+name)
    artifact=json.loads((folder/"qualification.json").read_text())
    spec=json.loads((folder/"specification.json").read_text())
    require(sha(folder/"specification.json")==sha(
        ROOT/"experiments/sparse_acquisition_screen/qualification_spec.json"),
        "saved specification differs from frozen source")
    for relative,digest in artifact["source_files"].items():
        path=(ROOT/relative).resolve(strict=True)
        path.relative_to(ROOT)
        require(sha(path)==digest,"qualification source mismatch: "+relative)
    require(artifact["status"]=="qualification-output-complete-unadjudicated","incomplete output")
    require(artifact["specification_sha256"]==sha(folder/"specification.json"),"spec hash mismatch")
    require(artifact["calibration_sha256"]==sha(folder/"calibration.json.gz"),"table hash mismatch")
    with gzip.open(folder/"calibration.json.gz","rt") as handle:
        tables=json.load(handle)
    recipes={r["id"]:r for r in spec["beliefs"]}
    require([r["id"] for r in artifact["records"]]==list(recipes),"missing/reordered beliefs")
    require(json.loads((folder/"unit-tests.json").read_text())["pass"] is True,"unit preflight did not pass")
    tolerance=spec["tolerances"]
    config=spec["acquisition"]
    results=[]
    all_pass=True
    for record in artifact["records"]:
        recipe=recipes[record["id"]]
        observations=record["observations"]
        require([o["index"] for o in observations]==recipe["indices"],"manufactured frequency mismatch")
        mean=record["manufactured_mean"]
        require(len(mean)==100 and all(math.isfinite(x) and x>0 for x in mean),"invalid manufactured mean")
        for j,observation in enumerate(observations):
            require(observation["exposure_photons"]==config["photon_rate"]*config["dwell_seconds"],"manufactured exposure mismatch")
            lam=observation["exposure_photons"]*mean[observation["index"]]
            z=recipe["residual_sigma"][j%len(recipe["residual_sigma"])]
            require(observation["count"]==round(lam+z*math.sqrt(lam)),"manufactured count mismatch")
        post={}
        failures=[]
        for grid_name,table in tables.items():
            value=posterior(table,observations)
            saved=record["posteriors"][grid_name]
            require(len(saved["weights"])==len(value["weights"]),"posterior size mismatch")
            discrepancy=max(abs(x-y) for x,y in zip(saved["weights"],value["weights"]))
            require(discrepancy<=tolerance["posterior_reconstruction_max_abs"],
                    "posterior reconstruction mismatch")
            for name in ("mean_uT","estimate_uT","lower_uT","upper_uT","boundary_mass"):
                near(saved["estimate"][name],value[name],"saved "+name,
                     absolute=.000001 if name in ("mean_uT","boundary_mass") else 0.)
            post[grid_name]=value
        coarse,fine=post["coarse"],post["fine"]
        grid_metrics={
            "field_wasserstein_uT":wasserstein(coarse["marginal"],fine["marginal"]),
            "field_mean_uT":abs(coarse["mean_uT"]-fine["mean_uT"]),
            "field_median_uT":abs(coarse["estimate_uT"]-fine["estimate_uT"]),
            "interval_endpoint_uT":max(abs(coarse[k]-fine[k]) for k in ("lower_uT","upper_uT")),
            "variance_difference_uT2":abs(coarse["variance_uT2"]-fine["variance_uT2"])}
        for name in ("field_wasserstein_uT","field_mean_uT","field_median_uT","interval_endpoint_uT"):
            if grid_metrics[name]>tolerance[name]:
                failures.append(name)
        variance_limit=max(tolerance["variance_absolute_uT2"],
                           tolerance["variance_relative"]*fine["variance_uT2"])
        if grid_metrics["variance_difference_uT2"]>variance_limit:
            failures.append("variance_difference_uT2")
        last=observations[-1]["index"] if observations else None
        costs=[config["dwell_seconds"]+(0. if i==last else config["settling_seconds"])
               for i in range(100)]
        utilities={}
        for design_name,design in spec["designs"].items():
            saved=record["designs"][design_name]
            expected=saved["expected_variance_uT2"]
            require(len(expected)==100,"invalid utility spectrum")
            variance=post[design["grid"]]["variance_uT2"]
            raw=[variance-v for v in expected]
            if min(expected)<-tolerance["gain_absolute_uT2"]:
                failures.append(design_name+":negative_expected_variance")
            if min(raw)<-tolerance["gain_absolute_uT2"]:
                failures.append(design_name+":negative_expected_gain")
            utility=[max(v,0.)/cost for v,cost in zip(raw,costs)]
            for actual,check in zip(saved["utility_uT2_per_second"],utility):
                near(actual,check,"utility")
            selected=max(range(100),key=utility.__getitem__)
            # A floating tie may select either index; enforce equivalent utility.
            chosen=saved["selected_index"]
            require(type(chosen) is int and 0<=chosen<100,"invalid selected action")
            near(utility[chosen],utility[selected],"saved action optimality",absolute=1e-6)
            utilities[design_name]=utility
        comparisons=[]
        for candidate,reference in (("coarse_low","coarse_high"),("coarse_high","fine_high"),
                                    ("coarse_low","fine_high")):
            a,b=utilities[candidate],utilities[reference]
            best=max(b)
            absolute=tolerance["gain_absolute_uT2"]/min(costs)
            utility_limit=tolerance["utility_relative"]*best+absolute
            difference=max(abs(x-y) for x,y in zip(a,b))
            chosen=record["designs"][candidate]["selected_index"]
            regret=best-b[chosen]
            regret_limit=tolerance["action_regret_relative"]*best+absolute
            passed=difference<=utility_limit and regret<=regret_limit
            if not passed:
                failures.append(candidate+"_versus_"+reference)
            comparisons.append({"candidate":candidate,"reference":reference,
                "max_utility_difference":difference,"utility_limit":utility_limit,
                "selected_action_regret":regret,"regret_limit":regret_limit,
                "candidate_index":chosen,"reference_index":record["designs"][reference]["selected_index"],
                "pass":passed})
        passed=not failures
        all_pass=all_pass and passed
        results.append({"id":record["id"],"pass":passed,"failures":failures,
                        "grid_metrics":grid_metrics,"variance_limit":variance_limit,
                        "comparisons":comparisons})
    return {"status":"qualification_pass" if all_pass else "qualification_fail",
        "qualification_sha256":sha(folder/"qualification.json"),
        "manifest_sha256":sha(folder/"artifact_manifest.json"),
        "specification_sha256":sha(folder/"specification.json"),
        "source_commit":artifact["source_commit"],"source_files":artifact["source_files"],
        "beliefs":results,"development_authorized":False,
        "scope":"saved-table reconstruction and arithmetic; no forward model or policy execution"}


def verify_development(folder):
    result=json.loads((folder/"results.json").read_text())
    cases=json.loads((folder/"cases.json").read_text())
    require(result["status"]=="development-only","wrong result stage")
    require(sha(folder/"cases.json")==result["cases_sha256"],"case hash mismatch")
    require(cases.get("partition")=="fresh-development" and 1<=len(cases["cases"])<=8,"invalid development partition")
    config=result["acquisition"]
    expected_policies={"uniform","coarse_to_fine","nuisance_fisher","bayesian_variance"}
    truth={c["case_id"]:c["point"]["field_uT"] for c in cases["cases"]}
    rows=result["rows"]
    require(len(rows)==len(truth)*4,"missing policy/case row")
    require({(r["case_id"],r["policy"]) for r in rows}
            =={(c,p) for c in truth for p in expected_policies},"duplicate or wrong row")
    scores={p:[] for p in expected_policies}
    for row in rows:
        target=truth[row["case_id"]]
        near(row["truth_uT"],target,"truth")
        trace=row["trace"]
        require(0<len(trace)<=config["maximum_actions"],"invalid action count")
        last=None
        for j,entry in enumerate(trace):
            index=entry["index"]
            require(type(index) is int and 0<=index<100,"invalid frequency")
            require(type(entry["count"]) is int and entry["count"]>=0,"invalid count")
            require(entry["recovered"]==(j>=config["primary_actions"]),"recovery flag mismatch")
            near(entry["dwell_seconds"],config["dwell_seconds"],"dwell")
            near(entry["exposure_photons"],config["photon_rate"]*config["dwell_seconds"],"photons")
            near(entry["settling_seconds"],config["settling_seconds"] if index!=last else 0.,"settling")
            for key in ("decision_seconds","update_seconds"):
                require(math.isfinite(entry[key]) and entry[key]>=0,"invalid measured timing")
            stopped=(entry["upper_uT"]-entry["lower_uT"])/2<=config["credible_half_width_uT"]
            require(entry["internal_precision_stop"]==stopped,"precision stop mismatch")
            require(not stopped or j==len(trace)-1,"continued after stopping")
            last=index
        for key in ("estimate_uT","lower_uT","upper_uT","mean_uT","boundary_mass"):
            near(row[key],trace[-1][key],"last trace "+key)
        near(row["absolute_error_uT"],abs(row["estimate_uT"]-target),"absolute error")
        require(row["interval_contains_truth"]==(row["lower_uT"]<=target<=row["upper_uT"]),"coverage")
        require(row["failed_precision"]==(not trace[-1]["internal_precision_stop"]),"failure flag")
        require(row["actions"]==len(trace),"action count")
        require(row["recovery_actions"]==sum(t["recovered"] for t in trace),"recovery count")
        for key in ("dwell_seconds","settling_seconds","decision_seconds","update_seconds"):
            near(row[key],math.fsum(t[key] for t in trace),key)
        near(row["normalized_exposure_photons"],math.fsum(t["exposure_photons"] for t in trace),"total exposure")
        require(row["detected_photons"]==sum(t["count"] for t in trace),"total detected photons")
        parts=("dwell_seconds","settling_seconds","decision_seconds","update_seconds",
               "episode_setup_seconds","policy_setup_seconds")
        require(all(math.isfinite(row[k]) and row[k]>=0 for k in parts),"invalid timing part")
        near(row["modeled_total_seconds"],math.fsum(row[k] for k in parts),"total time")
        scores[row["policy"]].append(row)
    metrics={}
    for name,group in sorted(scores.items()):
        errors=[r["absolute_error_uT"] for r in group]
        metrics[name]={"n":len(group),"mae_uT":statistics.fmean(errors),"p90_uT":quantile(errors,.9),
            "max_uT":max(errors),"precision_failures":sum(r["failed_precision"] for r in group),
            "interval_misses":sum(not r["interval_contains_truth"] for r in group),
            "median_total_seconds":statistics.median(r["modeled_total_seconds"] for r in group),
            "median_exposure_photons":statistics.median(r["normalized_exposure_photons"] for r in group),
            "recovery_actions":sum(r["recovery_actions"] for r in group)}
    return {"status":"saved_development_verified","results_sha256":sha(folder/"results.json"),
            "cases_sha256":sha(folder/"cases.json"),"metrics":metrics,
            "scope":"eight-case development arithmetic only; no population or superiority verdict"}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--kind",choices=("qualification","development"),required=True)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--gate",type=Path)
    args=parser.parse_args()
    if args.gate:
        from experiments.sparse_acquisition_screen.accounting import authorize_stage
        authorize_stage(args.gate,"ROOT_APPROVED_SPARSE_SAVED_VERIFICATION")
    # Without a private gate this remains a portable saved-artifact recomputation.
    # Active campaign jobs must still use root's accounting wrapper.
    verdict=verify_qualification(args.input) if args.kind=="qualification" else verify_development(args.input)
    with args.out.open("x") as handle:
        json.dump(verdict,handle,indent=2,allow_nan=False)
        handle.write("\n")
    print(json.dumps({"status":verdict["status"],"out":str(args.out)}))
    if verdict["status"]=="qualification_fail":
        raise SystemExit(2)


if __name__=="__main__":
    main()
