"""Public saved-output verification. NumPy/stdlib only; no inference or approvals."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.measured_widefield.io import validate_rows
from experiments.measured_widefield.metrics import compare

SCHEMA = "measured-widefield-saved-verification-v1"
CLASSICAL = {"raw", "training_mean", "savgol_5", "savgol_11", "savgol_21",
             "ridge_0.001", "ridge_0.01", "ridge_0.1", "pca_wiener_4",
             "pca_wiener_8", "pca_wiener_16", "robust_lorentzian"}
CANDIDATES = {"candidate_16", "candidate_32", "candidate_64"}
SOURCE_NAMES = ("verify_saved.py", "metrics.py", "io.py", "protocol.json")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paths_for(targets, predictions, model, metrics, bootstrap):
    paths = {"metrics": Path(metrics), "bootstrap": Path(bootstrap)}
    bundles = {"targets": Path(targets), "model": Path(model)}
    bundles.update({"prediction_" + str(i): Path(value) for i, value in enumerate(predictions)})
    for name, root in bundles.items():
        paths[name + "_manifest"] = root / "manifest.json"
        paths[name + "_arrays"] = root / "arrays.npz"
    return paths


def publication_manifest(targets, predictions, model, metrics, bootstrap, consumed_bootstrap_seed):
    """Build the public hash inventory; caller must independently publish its resulting hash."""
    paths = paths_for(targets, predictions, model, metrics, bootstrap)
    return {"schema": SCHEMA, "bootstrap_seed": consumed_bootstrap_seed,
            "files": {key: sha(path) for key, path in paths.items()},
            "sources": {name: sha(Path(__file__).parent / name) for name in SOURCE_NAMES},
            "seed_scope": "Consumed bootstrap seed only; no unused training or evaluation seed"}


def verify(*, targets, predictions, model, metrics, bootstrap, manifest, expected_manifest_sha256):
    checks = 0

    def require(condition, message):
        nonlocal checks
        checks += 1
        if not condition:
            raise ValueError(message)

    def equal(actual, expected, path):
        if isinstance(expected, dict):
            require(isinstance(actual, dict) and set(actual) == set(expected), path + ": fields differ")
            for key in expected:
                equal(actual[key], expected[key], path + "." + key)
        elif isinstance(expected, list):
            require(isinstance(actual, list) and len(actual) == len(expected), path + ": list differs")
            for i, value in enumerate(expected):
                equal(actual[i], value, path + "[" + str(i) + "]")
        elif type(expected) is bool:
            require(type(actual) is bool and actual == expected, path + ": Boolean differs")
        elif type(expected) is int:
            require(type(actual) is int and actual == expected, path + ": integer differs")
        elif type(expected) is float:
            require(type(actual) in (int, float) and math.isfinite(actual)
                    and math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-15), path + ": metric differs")
        else:
            require(type(actual) is type(expected) and actual == expected, path + ": value differs")

    require(sha(manifest) == expected_manifest_sha256, "Verification manifest hash differs from published pin")
    inventory = json.loads(Path(manifest).read_text())
    require(inventory.get("schema") == SCHEMA, "Unknown verification schema")
    paths = paths_for(targets, predictions, model, metrics, bootstrap)
    require(set(inventory["files"]) == set(paths), "Artifact roles differ")
    for key, path in paths.items():
        require(path.is_file() and not path.is_symlink() and sha(path) == inventory["files"][key], "Artifact hash differs: " + key)
    require(set(inventory["sources"]) == set(SOURCE_NAMES), "Verifier source inventory differs")
    for name in SOURCE_NAMES:
        require(sha(Path(__file__).parent / name) == inventory["sources"][name], "Verifier source changed: " + name)

    def load(role):
        record = json.loads(paths[role + "_manifest"].read_text())
        require(record["arrays_sha256"] == inventory["files"][role + "_arrays"], "Bundle array hash differs: " + role)
        with np.load(paths[role + "_arrays"], allow_pickle=False) as source:
            return record, {key: source[key] for key in source.files}

    target_record, target = load("targets")
    split = target_record.get("split")
    require(target_record.get("kind") == "targets" and split in ("development", "final"), "Invalid target split/kind")
    require(set(target) == {"targets", "repeat_difference", "target_storage_extrema", "row_key"}, "Target array names differ")
    validate_rows(target["row_key"], split)
    rows = len(target["row_key"])
    require(target_record["rows"] == rows and target_record["repeats"] == ([3] if split == "development" else [4]), "Target repeat/row count differs")
    require(target_record["shifts_yx"] == [[0, 0], [-1, 0], [1, 0], [0, -1], [0, 1], [-2, 0], [2, 0], [0, -2], [0, 2]], "Target shifts differ")
    require(target["repeat_difference"].shape == (rows, 200) and np.all(target["repeat_difference"] == 0), "Unexpected held-reference difference")
    require(target["target_storage_extrema"].dtype == np.bool_ and target["target_storage_extrema"].shape == (rows,), "Target flags differ")
    model_record, fitted = load("model")
    require(model_record.get("kind") == "classical_model" and model_record.get("training_only") is True, "Shape mask is not a training artifact")
    require(fitted["shape_edge_training_energy"].shape == (199,) and np.isfinite(fitted["shape_edge_training_energy"]).all(), "Invalid training mask energy")
    derived_mask = np.sort(np.lexsort((np.arange(199), -fitted["shape_edge_training_energy"]))[:50])
    require(np.array_equal(derived_mask, fitted["shape_edges"]), "Shape mask differs from saved training-only rule")
    combined, prediction_hashes = {}, []
    for index in range(len(predictions)):
        role = "prediction_" + str(index)
        record, saved = load(role)
        require(record.get("kind") == "predictions" and record.get("split") == split, "Prediction kind/split differs")
        require(record["inputs_manifest_sha256"] == target_record["inputs_manifest_sha256"], "Prediction/reference observation differs")
        require(record.get("label_values_read") is False, "Prediction metadata reports reference access")
        require(np.array_equal(saved.pop("row_key"), target["row_key"]), "Prediction/reference row identities differ")
        names = record["methods"]
        require(len(names) == len(set(names)) and set(names) <= CLASSICAL | CANDIDATES, "Unknown or duplicated method identity")
        expected = {method + suffix for method in names for suffix in ("__prediction", "__failed", "__fit_reliable", "__seconds")}
        require(set(saved) == expected and not (set(saved) & set(combined)), "Prediction array names overlap or differ")
        combined.update(saved)
        prediction_hashes.append(inventory["files"][role + "_manifest"])
    report = json.loads(Path(metrics).read_text())
    method_names = {key[:-12] for key in combined if key.endswith("__prediction")}
    if split == "development":
        require(method_names == CLASSICAL or method_names == CLASSICAL | CANDIDATES, "Development method coverage differs")
        frozen_candidate = None
    else:
        frozen_candidate = report.get("selected_candidate")
        require(frozen_candidate in CANDIDATES and report["reference"] in CLASSICAL, "Unregistered frozen final methods")
        require(method_names == {frozen_candidate, report["reference"], "training_mean"}, "Final method coverage differs")
    expected, regenerated_indices = compare(target["targets"], target["row_key"], combined,
        inventory["bootstrap_seed"], report["reference"] if split == "final" else None,
        fitted["shape_edges"], frozen_candidate)
    with np.load(bootstrap, allow_pickle=False) as saved_bootstrap:
        require(saved_bootstrap.files == ["groups"], "Bootstrap array names differ")
        groups = saved_bootstrap["groups"]
        require(groups.dtype.kind in "iu" and np.array_equal(groups, regenerated_indices), "Published seed does not reproduce committed resampling indices")
    metadata = {"split", "target_manifest_sha256", "prediction_manifest_sha256", "classical_model_manifest_sha256",
                "shape_edges", "approval_sha256", "accounting_run_id", "bootstrap_sha256"}
    require(set(report) == set(expected) | metadata, "Metric report has missing or unchecked fields")
    for key in expected:
        equal(report[key], expected[key], key)
    equal(report["shape_edges"], fitted["shape_edges"].tolist(), "shape_edges")
    require(report["split"] == split, "Report split differs")
    require(report["target_manifest_sha256"] == inventory["files"]["targets_manifest"], "Report target identity differs")
    require(report["prediction_manifest_sha256"] == prediction_hashes, "Report prediction identities differ")
    require(report["classical_model_manifest_sha256"] == inventory["files"]["model_manifest"], "Report shape model identity differs")
    require(report["bootstrap_sha256"] == inventory["files"]["bootstrap"], "Report bootstrap identity differs")
    return {"status": "PASS", "checks": checks, "rows": rows, "methods": sorted(method_names),
            "metrics_sha256": inventory["files"]["metrics"], "verification_manifest_sha256": expected_manifest_sha256,
            "scope": "Saved-output and metadata verification only; no model inference or independent field-truth validation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("targets", "model", "metrics", "bootstrap", "manifest", "expected-manifest-sha256"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--predictions", nargs="+", required=True)
    parser.add_argument("--out")
    args = vars(parser.parse_args())
    output = args.pop("out")
    try:
        result = verify(**args)
    except (ValueError, KeyError, OSError, TypeError) as error:
        result = {"status": "FAIL", "error": str(error)}
    text = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if output:
        with Path(output).open("x") as stream:
            stream.write(text)
    print(text, end="")
    raise SystemExit(result["status"] != "PASS")


if __name__ == "__main__":
    main()
