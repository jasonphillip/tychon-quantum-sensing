"""Explicit-path entry points; numerical imports occur after authorization."""
import argparse
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.measured_localisation.bundle import inspect_bundle
from experiments.measured_localisation.guard import PACKAGE, authorize, bind_file, read_json, sha256, write_json


def prepare_output(path):
    output = Path(path).resolve()
    output.mkdir(parents=True, exist_ok=False)
    return output


def save_manifest(output, approval, inputs, extras=None):
    record = {"schema_version": 1, "study": approval["study"],
              "approval_sha256": approval["approval_sha256"],
              "source_sha256": approval["source_sha256"], "inputs": inputs,
              "files": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}}
    if extras:
        record.update(extras)
    write_json(output / "artifact_manifest.json", record)


def choose_classical(x, y, xv, yv, protocol):
    import numpy as np
    from experiments.measured_localisation.metrics import errors, summary
    from experiments.measured_localisation.models import Scaling, fit_classical
    scale = Scaling().fit(x, y)
    xx, yy, q = scale.x(x), scale.y(y), scale.x(xv)
    rows, predictions = [], []
    for family, configs in protocol["classical_grid"].items():
        for config in configs:
            start = time.perf_counter()
            predict = fit_classical(family, config, xx, yy)
            prediction = scale.inverse(predict(q))
            rows.append({"family": family, "config": config,
                         "metrics": summary(errors(prediction, yv)),
                         "fit_plus_validation_wall_seconds": time.perf_counter() - start})
            predictions.append(prediction)
    winner = min(range(len(rows)), key=lambda i: rows[i]["metrics"]["mean_error_um"])
    return rows[winner], predictions[winner], rows


def qualify(args, approval, protocol):
    from experiments.measured_localisation.bundle import arrays
    from experiments.measured_localisation.partition import validate_partition
    bind_file(approval, "partition_sha256", args.partition)
    split = read_json(args.partition)
    manifest, metadata = inspect_bundle(args.bundle)
    validate_partition(split, metadata["n"], protocol)
    if split["manifest_sha256"] != sha256(args.bundle):
        raise RuntimeError("partition came from a different custody bundle")
    if manifest.get("physical_baseline_ready") is True:
        raise RuntimeError("a calibrated physical comparator is available and must be implemented before comparison")
    reason = manifest.get("physical_baseline_exclusion_reason")
    if not reason or "REPLACE" in reason:
        raise RuntimeError("custody must resolve physical comparator eligibility")
    indices = sorted(set(split["full_train"]) | set(split["validation"]))
    x, y, _, _ = arrays(args.bundle, indices)
    output = prepare_output(args.output)
    result = {"status": "qualification_pass", "bundle_sha256": sha256(args.bundle),
              "partition_sha256": sha256(args.partition), "development_rows_checked": len(indices),
              "all_development_features_finite_positive": True, "all_development_labels_finite": True,
              "small_label_budget": split["small_label_budget"], "full_label_budget": split["full_label_budget"],
              "physical_baseline_exclusion_reason": reason, "held_out_signal_values_accessed": False}
    result.update({key: split[key] for key in ("label_budget_unit", "small_measurement_rows", "full_measurement_rows",
                                               "partition_unique_positions", "possible_session_overlap", "session_assignment_status")})
    write_json(output / "qualification.json", result)
    save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle), "partition_sha256": sha256(args.partition)})
    print(json.dumps(result, indent=2))
    return 0


def develop(args, approval, protocol):
    import numpy as np
    from experiments.measured_localisation.bundle import arrays
    from experiments.measured_localisation.metrics import evaluate_saved
    from experiments.measured_localisation.models import Scaling, train_candidate, predict_candidate
    from experiments.measured_localisation.partition import validate_partition
    bind_file(approval, "partition_sha256", args.partition)
    bind_file(approval, "qualification_sha256", args.qualification)
    qualification = read_json(args.qualification)
    if (qualification.get("status") != "qualification_pass"
            or qualification.get("bundle_sha256") != sha256(args.bundle)
            or qualification.get("partition_sha256") != sha256(args.partition)):
        raise RuntimeError("qualified development inputs differ")
    split = read_json(args.partition)
    _, metadata = inspect_bundle(args.bundle)
    validate_partition(split, metadata["n"], protocol)
    if split["manifest_sha256"] != sha256(args.bundle):
        raise RuntimeError("partition came from a different custody bundle")
    x, y, manifest, _ = arrays(args.bundle, split["train"])
    xv, yv, _, _ = arrays(args.bundle, split["validation"])
    xf, yf, _, _ = arrays(args.bundle, split["full_train"])
    if manifest.get("physical_baseline_ready") is True:
        raise RuntimeError("physical calibration is available: root must add/freeze its strong inverse baseline before comparison")
    if not manifest.get("physical_baseline_exclusion_reason"):
        raise RuntimeError("record the metadata-only reason calibrated physical inversion is unavailable")
    output = prepare_output(args.output)
    best, pred, records = choose_classical(x, y, xv, yv, protocol)
    full, pred_full, full_records = choose_classical(xf, yf, xv, yv, protocol)
    scale = Scaling().fit(x, y)
    candidate_records, candidate_states, candidate_predictions = [], [], []
    for config in protocol["candidate_grid"]:
        weights, candidate_info = train_candidate(scale.x(x), scale.y(y), scale.x(xv), yv,
                                                   config, scale, approval["random_seed"])
        prediction = scale.inverse(predict_candidate(scale.x(xv), weights))
        if not np.isfinite(prediction).all():
            raise RuntimeError("a registered candidate produced nonfinite predictions")
        candidate_info["saved_prediction_validation_mean_error_um"] = float(np.linalg.norm(prediction - yv, axis=1).mean())
        candidate_info["config"] = config
        candidate_records.append(candidate_info)
        candidate_states.append(weights)
        candidate_predictions.append(prediction)
        np.savez(output / f"candidate_width_{config['hidden']}.npz", **{"weight." + k: v for k, v in weights.items()},
                 **{"scale." + k: v for k, v in scale.saved().items()})
        np.savez(output / f"validation_width_{config['hidden']}.npz", labels_um=yv, candidate_um=prediction,
                 row_indices=np.asarray(split["validation"], dtype=np.int64), valid=np.ones(len(yv), dtype=bool))
    winner = min(range(len(candidate_records)), key=lambda i: (
        candidate_records[i]["saved_prediction_validation_mean_error_um"], candidate_records[i]["parameters"]))
    weights, candidate_info, candidate = candidate_states[winner], candidate_records[winner], candidate_predictions[winner]
    metrics = evaluate_saved(yv, candidate, pred, pred_full, np.asarray(split["spatial_groups"])[split["validation"]],
                             protocol, split["small_label_budget"], split["full_label_budget"],
                             approval["random_seed"], confidence=False)
    np.savez(output / "candidate.npz", **{"weight." + k: v for k, v in weights.items()},
             **{"scale." + k: v for k, v in scale.saved().items()})
    np.savez(output / "validation_predictions.npz", labels_um=yv, candidate_um=candidate,
             classical_small_um=pred, classical_full_um=pred_full,
             row_indices=np.asarray(split["validation"], dtype=np.int64),
             spatial_groups=np.asarray(split["spatial_groups"])[split["validation"]],
             valid=np.ones(len(yv), dtype=bool))
    selection = {"schema_version": 1, "stage": "development", "development_gate_passed": metrics["gate_passed"],
                 "candidate": candidate_info, "classical_small": best, "classical_full": full,
                 "all_candidates": candidate_records,
                 "candidate_selection_rule": "lowest_validation_mean_error_then_fewer_parameters_before_any_gate",
                 "all_classical_small": records, "all_classical_full": full_records,
                 "metrics": metrics, "partition_sha256": sha256(args.partition),
                 "bundle_sha256": sha256(args.bundle), "candidate_sha256": sha256(output / "candidate.npz"),
                 "physical_baseline_exclusion_reason": manifest["physical_baseline_exclusion_reason"],
                 "held_out_signal_values_accessed": False,
                 "claim": "development_only_not_a_held_group_result"}
    write_json(output / "selection.json", selection)
    write_json(output / "partition.json", split)
    write_json(output / "metrics.json", metrics)
    write_json(output / "protocol.json", protocol)
    write_json(output / "verification.json", {"stage": "development", "confidence": False,
               "saved_partition_file": "partition.json",
               "prediction_file": "validation_predictions.npz",
               "expected_row_indices": split["validation"],
               "small_label_budget": split["small_label_budget"], "full_label_budget": split["full_label_budget"],
               "dataset_doi": manifest["dataset_doi"], "archive_sha256": manifest["archive_sha256"],
               "calibration_count_includes_validation": True})
    save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle), "partition_sha256": sha256(args.partition)})
    print(json.dumps({"development_gate_passed": metrics["gate_passed"], "output": str(output)}))
    return 0 if metrics["gate_passed"] else 2


def evaluate(args, approval, protocol):
    import numpy as np
    from experiments.measured_localisation.bundle import arrays
    from experiments.measured_localisation.metrics import evaluate_saved
    from experiments.measured_localisation.models import Scaling, fit_classical, predict_candidate
    from experiments.measured_localisation.partition import validate_partition
    for key, path in (("partition_sha256", args.partition), ("selection_sha256", args.selection),
                      ("candidate_sha256", args.candidate)):
        bind_file(approval, key, path)
    selection, split = read_json(args.selection), read_json(args.partition)
    if selection.get("development_gate_passed") is not True:
        raise RuntimeError("development failed; no final comparison is permitted")
    if selection["bundle_sha256"] != sha256(args.bundle) or selection["partition_sha256"] != sha256(args.partition):
        raise RuntimeError("development inputs differ")
    if selection["candidate_sha256"] != sha256(args.candidate):
        raise RuntimeError("candidate checkpoint differs")
    _, metadata = inspect_bundle(args.bundle)
    validate_partition(split, metadata["n"], protocol)
    output = prepare_output(args.output)
    xt, yt, manifest, _ = arrays(args.bundle, split["test"])
    predictions = []
    for name, indices in (("classical_small", split["train"]), ("classical_full", split["full_train"])):
        x, y, _, _ = arrays(args.bundle, indices)
        scale = Scaling().fit(x, y)
        chosen = selection[name]
        predict = fit_classical(chosen["family"], chosen["config"], scale.x(x), scale.y(y))
        predictions.append(scale.inverse(predict(scale.x(xt))))
    with np.load(args.candidate, allow_pickle=False) as checkpoint:
        weights = {k.removeprefix("weight."): checkpoint[k] for k in checkpoint.files if k.startswith("weight.")}
        scale = Scaling()
        for k in ("x_mean", "x_scale", "y_mean", "y_scale"):
            setattr(scale, k, checkpoint["scale." + k])
    candidate = scale.inverse(predict_candidate(scale.x(xt), weights))
    groups = np.asarray(split["spatial_groups"])[split["test"]]
    metrics = evaluate_saved(yt, candidate, predictions[0], predictions[1], groups, protocol,
                             split["small_label_budget"], split["full_label_budget"], approval["random_seed"])
    np.savez(output / "predictions.npz", labels_um=yt, candidate_um=candidate,
             classical_small_um=predictions[0], classical_full_um=predictions[1],
             row_indices=np.asarray(split["test"], dtype=np.int64), spatial_groups=groups,
             valid=np.ones(len(yt), dtype=bool))
    write_json(output / "partition.json", split)
    write_json(output / "metrics.json", metrics)
    write_json(output / "protocol.json", protocol)
    # The seed is used by this published metric recomputation, not an unused held-out seed.
    write_json(output / "verification.json", {"stage": "held_group", "confidence": True,
               "saved_partition_file": "partition.json",
               "prediction_file": "predictions.npz", "bootstrap_seed": approval["random_seed"],
               "expected_row_indices": split["test"],
               "small_label_budget": split["small_label_budget"], "full_label_budget": split["full_label_budget"],
               "dataset_doi": manifest["dataset_doi"], "archive_sha256": manifest["archive_sha256"],
               "calibration_count_includes_validation": True})
    save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle), "partition_sha256": sha256(args.partition),
                                      "selection_sha256": sha256(args.selection), "candidate_sha256": sha256(args.candidate)})
    print(json.dumps({"held_group_gate_passed": metrics["gate_passed"], "output": str(output)}))
    return 0 if metrics["gate_passed"] else 2


def reproduce(args, approval):
    """Score published saved predictions only; do not execute supplied models."""
    import numpy as np
    from experiments.measured_localisation.bundle import checked_path
    from experiments.measured_localisation.metrics import errors, summary
    manifest, _ = inspect_bundle(args.bundle)
    root = Path(args.bundle).resolve().parent
    entry = manifest["published_test_predictions"]
    label_entry = manifest["published_test_labels"]
    if (entry.get("units") != "um" or entry.get("order") != "paired_published_labels"
            or label_entry.get("units") != "um" or label_entry.get("order") != "paired_published_predictions"):
        raise ValueError("published prediction units/order must be independently established by custody")
    prediction = np.load(checked_path(root, entry), allow_pickle=False)
    y = np.asarray(np.load(checked_path(root, label_entry), allow_pickle=False), dtype=float)
    if y.ndim != 2 or y.shape[1] != 2 or prediction.shape != y.shape:
        raise ValueError("published prediction/label shape mismatch")
    published_rows = list(range(len(y)))
    result = {"stage": "published_split_reproduction", "metrics": summary(errors(prediction, y)),
              "new_confirmation": False, "training_or_inference_run": False,
              "expected_row_indices": published_rows,
              "row_identity": "published_prediction_rows_not_new_bundle_indices",
              "published_label_sha256": label_entry["sha256"],
              "published_prediction_sha256": entry["sha256"], "custody_bundle_sha256": sha256(args.bundle)}
    output = prepare_output(args.output)
    np.savez(output / "reproduction_predictions.npz", labels_um=y, predictions_um=prediction,
             row_indices=np.asarray(published_rows, dtype=np.int64), valid=np.ones(len(y), dtype=bool))
    write_json(output / "reproduction.json", result)
    save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle)})
    print(json.dumps(result, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspector = sub.add_parser("inspect", help="custody hashes and NPY headers only")
    inspector.add_argument("--bundle", required=True)
    for name in ("partition", "qualify", "reproduce", "develop", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("--approval", required=True)
        command.add_argument("--bundle", required=True)
        command.add_argument("--output", required=True)
        if name in ("qualify", "develop", "evaluate"):
            command.add_argument("--partition", required=True)
        if name == "develop":
            command.add_argument("--qualification", required=True)
        if name == "evaluate":
            command.add_argument("--selection", required=True)
            command.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)
    if args.command == "inspect":
        _, metadata = inspect_bundle(args.bundle)
        print(json.dumps(metadata, indent=2))
        return 0
    approval = authorize(args.approval, args.command)
    bind_file(approval, "bundle_sha256", args.bundle)
    protocol = read_json(PACKAGE / "protocol.json")
    if args.command == "reproduce":
        return reproduce(args, approval)
    if args.command == "qualify":
        return qualify(args, approval, protocol)
    if args.command == "partition":
        from experiments.measured_localisation.partition import make_partition
        split = make_partition(args.bundle, protocol, approval["partition_salt"])
        output = prepare_output(args.output)
        write_json(output / "partition.json", split)
        save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle)})
        print(json.dumps({"partition_status": split["status"], "problems": split["problems"]}))
        return 0 if split["status"] == "qualified" else 2
    return develop(args, approval, protocol) if args.command == "develop" else evaluate(args, approval, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
