"""Recompute every saved development comparison without inference or fitting."""
import argparse
import json
import math
from pathlib import Path
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.localisation_redesign.guard import PACKAGE, check_source, read_json
from experiments.localisation_redesign.run import validate_files


def same(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)
    return a == b


def verify(artifact):
    import numpy as np
    from experiments.localisation_redesign.metrics import errors, summary, validity, evaluate_saved
    from experiments.localisation_redesign.partition import validate_redesign
    manifest = read_json(artifact / "artifact_manifest.json")
    check_source(manifest["source_sha256"])
    validate_files(artifact, manifest["files"])
    for name in ("predictions.npz", "metrics.json", "protocol.json", "partition.json", "selection.json", "verification.json"):
        if name not in manifest["files"]:
            raise ValueError("missing required artifact pin: " + name)
    protocol = read_json(artifact / "protocol.json")
    if protocol != read_json(PACKAGE / "protocol.json"):
        raise ValueError("protocol differs")
    split = read_json(artifact / "partition.json")
    validate_redesign(split, protocol)
    context, selection = [read_json(artifact / name) for name in ("verification.json", "selection.json")]
    confidence = context["stage"] == "held_group"
    if context["stage"] not in ("development", "held_group") or confidence != context["confidence"]:
        raise ValueError("stage/confidence mismatch")
    rows = split["test"] if confidence else split["validation"]
    if (rows != context["expected_row_indices"] or context["small_label_budget"] != split["small_label_budget"]
            or context["full_label_budget"] != split["full_label_budget"]):
        raise ValueError("row/budget mismatch")
    with np.load(artifact / "predictions.npz", allow_pickle=False) as saved:
        labels = saved["labels_um"]
        if (not np.array_equal(saved["row_indices"], rows) or len(set(rows)) != len(rows)
                or not np.array_equal(saved["spatial_groups"], np.asarray(split["spatial_groups"])[rows])):
            raise ValueError("prediction row/group identities differ")
        names = ("small", "full") if confidence and context["selected_path"] == "CLASSICAL_CALIBRATION_EFFICIENCY" else ("candidate", "small", "full") if confidence else ("candidate", "control", "small", "full")
        if confidence and ("control_um" in saved or ("candidate" not in names and "candidate_um" in saved)):
            raise ValueError("unselected model was scored on held data")
        for name in names:
            flags = saved[name + "_valid"]
            if flags.dtype != np.bool_ or not np.array_equal(flags, validity(saved[name + "_um"], labels)):
                raise ValueError("validity flags differ: " + name)
        if not confidence:
            for name in ("small", "full"):
                records = selection["all_classical_" + name]
                predictions = saved["all_" + name + "_um"]
                flags = saved["all_" + name + "_valid"]
                if len(records) != len(protocol["classical_grid"]) or len(predictions) != len(records) or flags.dtype != np.bool_:
                    raise ValueError("classical grid size changed")
                for index, (record, prediction) in enumerate(zip(records, predictions)):
                    if (record["index"] != index or record["config"] != protocol["classical_grid"][index]
                            or not same(summary(errors(prediction, labels)), record["metrics"])
                            or not np.array_equal(flags[index], validity(prediction, labels))
                            or record["valid"] != bool(flags[index].all())):
                        raise ValueError("classical result/configuration mismatch")
                    if record["checkpoint"] is not None and manifest["files"].get(record["checkpoint"]) != record["checkpoint_sha256"]:
                        raise ValueError("classical checkpoint pin mismatch")
                winner = min(range(len(records)), key=lambda i: (records[i]["metrics"]["mean_error_um"] if records[i]["valid"] else float("inf"), i))
                if winner != selection[name + "_winner"] or not np.array_equal(predictions[winner], saved[name + "_um"], equal_nan=True):
                    raise ValueError("classical winner changed")
            for name in ("candidate", "control"):
                if (not same(summary(errors(saved[name + "_um"], labels)), selection[name]["saved_prediction_metrics"])
                        or manifest["files"].get(name + ".npz") != selection[name]["checkpoint_sha256"]):
                    raise ValueError("paired candidate record mismatch")
            complete = all(row["valid"] for name in ("small", "full") for row in selection["all_classical_" + name])
            if complete != selection["benchmark_complete"] or complete != context["benchmark_complete"]:
                raise ValueError("benchmark completeness differs")
        result = evaluate_saved(labels, saved["candidate_um"] if "candidate_um" in saved else None,
                                saved["control_um"] if "control_um" in saved else None, saved["small_um"], saved["full_um"],
                                saved["spatial_groups"], protocol, split["small_label_budget"], split["full_label_budget"],
                                context.get("bootstrap_seed", 0), confidence, context["benchmark_complete"],
                                context["selected_path"] if confidence else None)
        if result["selected_path"] != context["selected_path"] or selection["selected_path"] != context["selected_path"]:
            raise ValueError("saved adoption path differs")
    if not same(result, read_json(artifact / "metrics.json")):
        raise ValueError("saved metrics differ")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args(argv)
    result = verify(Path(args.artifact).resolve())
    print(json.dumps({"artifact_integrity": "pass", "metric_recomputation": "pass",
                      "scientific_gate_passed": result["gate_passed"], "metrics": result}, indent=2))
    return 0 if result["gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
