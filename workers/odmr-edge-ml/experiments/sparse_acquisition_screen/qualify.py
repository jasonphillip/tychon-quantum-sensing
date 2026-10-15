"""Generate preregistered approximation evidence, only inside a reserved job."""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.sparse_acquisition_screen.accounting import authorize_stage, sha, PACKAGE


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    gate = authorize_stage(args.gate, "ROOT_APPROVED_SPARSE_QUALIFICATION")
    spec_path = PACKAGE / "qualification_spec.json"
    spec = json.loads(spec_path.read_text())
    # Numerical dependencies load only after reservation and source checks.
    import numpy as np
    from experiments.sparse_acquisition_screen.core import (
        Acquisition, GridBelief, BayesianPolicy, Observation, Point, forward, FACTOR)
    args.out.mkdir(parents=True, exist_ok=False)
    write_json(args.out / "specification.json", spec)
    write_json(args.out / "started.json", {"gate_sha256":sha(args.gate),
        "source_commit":gate["source_commit"], "source_files":gate["source_files"]})
    begun = time.perf_counter()
    import io
    import unittest
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"),pattern="test_sparse*.py")
    result = unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (args.out/"unit-tests.txt").write_text(stream.getvalue())
    write_json(args.out/"unit-tests.json",{"tests":result.testsRun,"pass":result.wasSuccessful()})
    if not result.wasSuccessful():
        raise RuntimeError("registered unit preflight failed; qualification stopped")
    config = Acquisition(**spec["acquisition"])
    config.validate()
    priors = {}
    for name, grid in spec["grids"].items():
        write_json(args.out/"progress.json",{"stage":"building_calibration","grid":name})
        axes = tuple(np.linspace(*grid[k]) for k in ("field","center","width"))
        priors[name] = GridBelief(axes=axes)
    # These calibrated likelihood tables allow verification without the forward model.
    tables = {name:{"axes":[a.tolist() for a in prior.axes],
                   "states":prior.states.tolist(), "rates":prior.rates.tolist()}
              for name,prior in priors.items()}
    with gzip.open(args.out / "calibration.json.gz", "wt") as handle:
        json.dump(tables, handle, allow_nan=False)
    records = []
    try:
        for recipe in spec["beliefs"]:
            truth = Point(**spec["fixed_point"], **recipe["truth"])
            mean, _ = forward(truth, "fixed_amplitude", FACTOR)
            observations = []
            last = None
            for j,index in enumerate(recipe["indices"]):
                lam = config.exposure_photons * float(mean[index])
                z = recipe["residual_sigma"][j % len(recipe["residual_sigma"])]
                count = int(np.rint(lam + z*np.sqrt(lam)))
                observations.append(Observation(index,count,config.exposure_photons,
                    config.dwell_seconds,config.settling_seconds if index!=last else 0.,False))
                last = index
            record = {"id":recipe["id"], "manufactured_mean":mean.tolist(), "observations":[asdict(x) for x in observations],
                      "posteriors":{}, "designs":{}}
            posteriors = {}
            for grid_name, prior in priors.items():
                belief = prior.clone_prior()
                for observation in observations:
                    belief.update(observation)
                posteriors[grid_name] = belief
                record["posteriors"][grid_name] = {
                    "weights":belief.weights.tolist(), "estimate":belief.estimate()}
            for design_name, design in spec["designs"].items():
                write_json(args.out/"progress.json",{"stage":"design","belief":recipe["id"],"design":design_name})
                before = time.perf_counter()
                policy = BayesianPolicy(design["representatives"],design["nodes"])
                evidence = policy.design(posteriors[design["grid"]],config,tuple(observations))
                record["designs"][design_name] = {
                    "expected_variance_uT2":evidence["expected_variance_uT2"].tolist(),
                    "utility_uT2_per_second":evidence["utility_uT2_per_second"].tolist(),
                    "selected_index":int(np.argmax(evidence["utility_uT2_per_second"])),
                    "seconds":time.perf_counter()-before}
                write_json(args.out/"in-progress-belief.json",record)
            records.append(record)
            write_json(args.out / "partial-qualification.json", records)
            if time.perf_counter()-begun > spec["budgets"]["qualification"]["wall_seconds"]:
                raise RuntimeError("qualification soft wall limit exceeded; stop without retry")
        artifact = {"status":"qualification-output-complete-unadjudicated",
            "specification_sha256":sha(args.out/"specification.json"),
            "calibration_sha256":sha(args.out/"calibration.json.gz"),
            "gate_sha256":sha(args.gate), "source_commit":gate["source_commit"],
            "source_files":gate["source_files"], "elapsed_seconds":time.perf_counter()-begun,
            "numpy_version":np.__version__, "records":records}
        write_json(args.out / "qualification.json", artifact)
        write_json(args.out / "artifact_manifest.json", {
            "files":{name:sha(args.out/name) for name in
                     ("specification.json","calibration.json.gz","qualification.json","started.json","unit-tests.json","unit-tests.txt")},
            "purpose":"saved-output-only qualification verification"})
    except Exception as exc:
        write_json(args.out/"failure.json",{"error":repr(exc),"completed_beliefs":len(records)})
        raise
    print(json.dumps({"status":"unadjudicated","beliefs":len(records),"out":str(args.out)}))


if __name__ == "__main__":
    main()
