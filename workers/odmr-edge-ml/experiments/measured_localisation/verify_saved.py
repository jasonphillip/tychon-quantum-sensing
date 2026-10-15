"""Recompute public metrics from saved labels/predictions only; never infer."""
import argparse
import json
import math
from pathlib import Path
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.measured_localisation.guard import PACKAGE, read_json, sha256


def same_values(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_values(a[k], b[k]) for k in a)
    if isinstance(a, float) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-9)
    return a == b


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    args = parser.parse_args(argv)
    artifact = Path(args.artifact).resolve()
    manifest = read_json(artifact / "artifact_manifest.json")
    required_sources = {str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*.py")} | {"protocol.json"}
    if not required_sources <= set(manifest["source_sha256"]):
        raise ValueError("incomplete frozen source manifest")
    for root, hashes in ((artifact, manifest["files"]), (PACKAGE, manifest["source_sha256"])):
        for name, digest in hashes.items():
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts or sha256(root / relative) != digest:
                raise ValueError("saved artifact/source hash mismatch: " + name)
    import numpy as np
    from experiments.measured_localisation.metrics import evaluate_saved, errors, summary
    if "reproduction.json" in manifest["files"]:
        expected = read_json(artifact / "reproduction.json")
        with np.load(artifact / "reproduction_predictions.npz", allow_pickle=False) as saved:
            if (saved["valid"].dtype != np.bool_ or saved["valid"].shape != (len(saved["labels_um"]),)
                    or not saved["valid"].all()
                    or not np.array_equal(saved["row_indices"], expected["expected_row_indices"])
                    or len(set(saved["row_indices"].tolist())) != len(saved["row_indices"])):
                raise ValueError("invalid reproduction flags or duplicate rows")
            result = summary(errors(saved["predictions_um"], saved["labels_um"]))
        if expected["new_confirmation"] is not False or not same_values(result, expected["metrics"]):
            raise ValueError("published split reproduction mismatch")
        print(json.dumps({"metric_recomputation": "pass", "reproduction_only": True, "metrics": result}, indent=2))
        return 0
    protocol = read_json(artifact / "protocol.json")
    if protocol != read_json(PACKAGE / "protocol.json"):
        raise ValueError("artifact protocol differs from frozen source protocol")
    context = read_json(artifact / "verification.json")
    if "saved_partition_file" in context:
        from experiments.measured_localisation.partition import validate_partition
        if context["saved_partition_file"] != "partition.json" or "partition.json" not in manifest["files"]:
            raise ValueError("unbound public partition")
        partition = read_json(artifact / "partition.json")
        validate_partition(partition, partition["n"], protocol)
        stage_rows = partition["test"] if context["stage"] == "held_group" else partition["validation"]
        if (stage_rows != context["expected_row_indices"]
                or partition["small_label_budget"] != context["small_label_budget"]
                or partition["full_label_budget"] != context["full_label_budget"]):
            raise ValueError("public unique-position budgets or row selection differ")
    prediction_file = context["prediction_file"]
    if prediction_file not in ("predictions.npz", "validation_predictions.npz"):
        raise ValueError("unexpected prediction artifact")
    if context.get("stage") not in ("development", "held_group") or context["confidence"] != (context["stage"] == "held_group"):
        raise ValueError("stage/confidence mismatch")
    with np.load(artifact / prediction_file, allow_pickle=False) as saved:
        if (saved["valid"].dtype != np.bool_ or saved["valid"].shape != (len(saved["labels_um"]),)
                or not saved["valid"].all()
                or not np.array_equal(saved["row_indices"], context["expected_row_indices"])
                or len(set(saved["row_indices"].tolist())) != len(saved["row_indices"])):
            raise ValueError("invalid flags or duplicate test rows")
        result = evaluate_saved(saved["labels_um"], saved["candidate_um"], saved["classical_small_um"],
                                saved["classical_full_um"], saved["spatial_groups"], protocol,
                                context["small_label_budget"], context["full_label_budget"], context.get("bootstrap_seed", 0),
                                confidence=context["confidence"])
    expected = read_json(artifact / "metrics.json")
    if not same_values(result, expected):
        raise ValueError("saved metrics do not match recomputation")
    print(json.dumps({"artifact_integrity": "pass", "metric_recomputation": "pass",
                      "scientific_gate_passed": result["gate_passed"], "metrics": result}, indent=2))
    return 0 if result["gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
