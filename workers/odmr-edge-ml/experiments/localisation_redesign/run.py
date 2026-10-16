"""Explicit-path phases; no feature decoding before source/accounting approval."""
import argparse
import json
from pathlib import Path
import sys
import time

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.localisation_redesign.guard import PACKAGE, authorize, bind_file, read_json, sha256, write_json


def output_directory(path):
    output = Path(path).resolve()
    output.mkdir(parents=True, exist_ok=False)
    return output


def save_manifest(output, approval, inputs):
    write_json(output / "artifact_manifest.json", {
        "schema_version": 1, "study": approval["study"], "approval_sha256": approval["approval_sha256"],
        "source_sha256": approval["source_sha256"], "inputs": inputs,
        "files": {p.name: sha256(p) for p in sorted(output.iterdir()) if p.is_file()}})


def validate_files(root, hashes):
    root = Path(root).resolve()
    for name, digest in hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha256(root / relative) != digest:
            raise ValueError("artifact hash mismatch: " + name)


def save_model(path, state, scale):
    import numpy as np
    np.savez(path, **{"state." + k: v for k, v in state.items()}, **{"scale." + k: v for k, v in scale.saved().items()})


def load_model(path):
    import numpy as np
    from experiments.localisation_redesign.models import Scaling
    with np.load(path, allow_pickle=False) as saved:
        state = {k.removeprefix("state."): saved[k] for k in saved.files if k.startswith("state.")}
        scale = Scaling()
        for key in ("x_mean", "x_scale", "y_mean", "y_scale"):
            setattr(scale, key, saved["scale." + key])
    return state, scale


def classical_grid(x, y, xv, yv, protocol, output, budget):
    import numpy as np
    from experiments.localisation_redesign.metrics import errors, summary, validity
    from experiments.localisation_redesign.models import Scaling, fit_classical, predict_classical
    scale = Scaling().fit(x, y)
    xx, yy, q = scale.x(x), scale.y(y), scale.x(xv)
    records, predictions = [], []
    for index, config in enumerate(protocol["classical_grid"]):
        start = time.perf_counter()
        checkpoint = f"classical_{budget}_{index:02d}.npz"
        error = None
        info = {}
        try:
            state, info = fit_classical(config, xx, yy)
            prediction = scale.inverse(predict_classical(config, state, q))
            save_model(output / checkpoint, state, scale)
        except (ValueError, RuntimeError, np.linalg.LinAlgError, FloatingPointError) as exc:
            prediction = np.full(yv.shape, np.nan)
            error = type(exc).__name__ + ": " + str(exc)
            checkpoint = None
        predictions.append(prediction)
        records.append({"index": index, "config": config, "metrics": summary(errors(prediction, yv)),
                        "valid": bool(validity(prediction, yv).all()), "failure": error,
                        "checkpoint": checkpoint, "checkpoint_sha256": sha256(output / checkpoint) if checkpoint else None,
                        "optimizer": info, "fit_plus_validation_wall_seconds": time.perf_counter() - start})
    winner = min(range(len(records)), key=lambda i: (
        records[i]["metrics"]["mean_error_um"] if records[i]["valid"] else float("inf"), i))
    return records, np.stack(predictions), winner


def load_split(args, approval, protocol):
    from experiments.localisation_redesign.bundle import inspect_bundle
    from experiments.localisation_redesign.partition import validate_redesign
    bind_file(approval, "partition_sha256", args.partition)
    split = read_json(args.partition)
    if args.phase == "develop":
        from experiments.localisation_redesign.bundle import inspect_development
        bind_file(approval, "development_bundle_sha256", args.development_bundle)
        derived, indices = inspect_development(args.development_bundle, sha256(args.bundle))
        metadata = {"n": derived["original_n"]}
        if (indices != sorted(set(split["full_train"]) | set(split["validation"]))
                or derived["partition_sha256"] != sha256(args.partition)):
            raise ValueError("development subset differs from frozen nonheld rows")
    else:
        _, metadata = inspect_bundle(args.bundle)
    if split["n"] != metadata["n"] or split["manifest_sha256"] != sha256(args.bundle):
        raise ValueError("partition/bundle mismatch")
    validate_redesign(split, protocol)
    return split


def qualify(args, approval, protocol):
    from experiments.localisation_redesign.bundle import arrays
    split = load_split(args, approval, protocol)
    indices = sorted(set(split["full_train"]) | set(split["validation"]))
    x, y, manifest, _ = arrays(args.bundle, indices)
    if manifest.get("physical_baseline_ready") is True or not manifest.get("physical_baseline_exclusion_reason"):
        raise ValueError("physical comparator eligibility must remain explicitly resolved")
    output = output_directory(args.output)
    result = {"status": "qualification_pass", "bundle_sha256": sha256(args.bundle),
              "partition_sha256": sha256(args.partition), "development_rows_checked": len(indices),
              "all_development_features_finite_positive": True, "held_out_signal_values_accessed": False,
              "physical_baseline_exclusion_reason": manifest["physical_baseline_exclusion_reason"]}
    import numpy as np
    np.save(output / "development_features.npy", x, allow_pickle=False)
    np.save(output / "development_positions.npy", y, allow_pickle=False)
    write_json(output / "development_row_indices.json", indices)
    entries = {}
    for key, filename in (("features", "development_features.npy"), ("positions", "development_positions.npy"),
                          ("row_indices", "development_row_indices.json")):
        entries[key] = {"path": filename, "sha256": sha256(output / filename)}
    derived = {"schema_version": 1, "kind": "qualified_development_rows_only",
               "original_bundle_sha256": sha256(args.bundle), "partition_sha256": sha256(args.partition),
               "original_n": split["n"], "held_feature_rows_included": False,
               "feature_units": "MHz_before_natural_log", "position_units": "um", **entries}
    write_json(output / "development_bundle.json", derived)
    result["development_bundle_sha256"] = sha256(output / "development_bundle.json")
    write_json(output / "qualification.json", result)
    save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle), "partition_sha256": sha256(args.partition)})
    print(json.dumps(result))
    return 0


def save_stage(output, approval, protocol, split, labels, predictions, small_all, full_all, records, stage, seed):
    import numpy as np
    from experiments.localisation_redesign.metrics import evaluate_saved, validity
    confidence = stage == "held_group"
    rows = split["test"] if confidence else split["validation"]
    groups = np.asarray(split["spatial_groups"])[rows]
    complete = records["benchmark_complete"]
    result = evaluate_saved(labels, predictions.get("candidate"), predictions.get("control"), predictions["small"], predictions["full"],
                            groups, protocol, split["small_label_budget"], split["full_label_budget"], seed, confidence, complete,
                            records.get("selected_path") if confidence else None)
    arrays = {"labels_um": labels, "row_indices": np.asarray(rows, dtype=np.int64), "spatial_groups": groups}
    for name, values in predictions.items():
        arrays[name + "_um"] = values
        arrays[name + "_valid"] = validity(values, labels)
    if small_all is not None:
        arrays["all_small_um"], arrays["all_full_um"] = small_all, full_all
        arrays["all_small_valid"] = np.stack([validity(v, labels) for v in small_all])
        arrays["all_full_valid"] = np.stack([validity(v, labels) for v in full_all])
    np.savez(output / "predictions.npz", **arrays)
    write_json(output / "metrics.json", result)
    write_json(output / "protocol.json", protocol)
    write_json(output / "partition.json", split)
    records["selected_path"] = result["selected_path"]
    write_json(output / "selection.json", records)
    context = {"stage": stage, "confidence": confidence, "benchmark_complete": complete,
               "expected_row_indices": rows, "small_label_budget": split["small_label_budget"],
               "full_label_budget": split["full_label_budget"], "prediction_file": "predictions.npz",
               "held_out_signal_values_accessed": confidence, "selected_path": result["selected_path"]}
    if confidence:
        context["bootstrap_seed"] = seed
    write_json(output / "verification.json", context)
    save_manifest(output, approval, {"bundle_sha256": split["manifest_sha256"], "partition_sha256": sha256(output / "partition.json")})
    print(json.dumps({"stage": stage, "scientific_gate_passed": result["gate_passed"], "output": str(output)}))
    return 0 if result["gate_passed"] else 2


def develop(args, approval, protocol):
    from experiments.localisation_redesign.bundle import arrays
    from experiments.localisation_redesign.models import Scaling, train_candidate, predict_candidate
    from experiments.localisation_redesign.metrics import summary, errors
    split = load_split(args, approval, protocol)
    bind_file(approval, "qualification_sha256", args.qualification)
    qualified = read_json(args.qualification)
    if (qualified.get("status") != "qualification_pass" or qualified["bundle_sha256"] != sha256(args.bundle)
            or qualified["partition_sha256"] != sha256(args.partition)):
        raise ValueError("qualification inputs differ")
    from experiments.localisation_redesign.bundle import development_arrays
    if qualified["development_bundle_sha256"] != sha256(args.development_bundle):
        raise ValueError("qualified development subset changed")
    x, y = development_arrays(args.development_bundle, split["train"], sha256(args.bundle))
    xf, yf = development_arrays(args.development_bundle, split["full_train"], sha256(args.bundle))
    xv, yv = development_arrays(args.development_bundle, split["validation"], sha256(args.bundle))
    output = output_directory(args.output)
    small, small_predictions, si = classical_grid(x, y, xv, yv, protocol, output, "small")
    full, full_predictions, fi = classical_grid(xf, yf, xv, yv, protocol, output, "full")
    scale = Scaling().fit(x, y)
    models, predictions = {}, {"small": small_predictions[si], "full": full_predictions[fi]}
    for name, mode in (("candidate", "physical_euclidean"), ("control", "standardized_mse_control")):
        state, info = train_candidate(scale.x(x), scale.y(y), scale.x(xv), yv, protocol["candidate"],
                                      scale, approval["seeds"]["paired_training"], mode)
        predictions[name] = scale.inverse(predict_candidate(scale.x(xv), state))
        save_model(output / (name + ".npz"), state, scale)
        info["saved_prediction_metrics"] = summary(errors(predictions[name], yv))
        info["checkpoint_sha256"] = sha256(output / (name + ".npz"))
        models[name] = info
    records = {"stage": "development", "candidate": models["candidate"], "control": models["control"],
               "all_classical_small": small, "all_classical_full": full, "small_winner": si, "full_winner": fi,
               "classical_selection": "lowest_validation_mean_error_then_registered_index",
               "candidate_selection": "physical_loss_only_control_never_substituted",
               "benchmark_complete": all(r["valid"] for r in small + full),
               "held_out_signal_values_accessed": False, "claim": "consumed_development_only"}
    return save_stage(output, approval, protocol, split, yv, predictions, small_predictions, full_predictions,
                      records, "development", approval["seeds"]["bootstrap"])


def evaluate(args, approval, protocol):
    from experiments.localisation_redesign.bundle import arrays
    from experiments.localisation_redesign.models import predict_candidate, predict_classical
    split = load_split(args, approval, protocol)
    development = Path(args.development).resolve()
    bind_file(approval, "development_manifest_sha256", development / "artifact_manifest.json")
    manifest = read_json(development / "artifact_manifest.json")
    validate_files(development, manifest["files"])
    if manifest["source_sha256"] != approval["source_sha256"]:
        raise ValueError("development source freeze changed")
    if read_json(development / "partition.json") != split or read_json(development / "protocol.json") != protocol:
        raise ValueError("development scientific contract changed")
    development_metrics = read_json(development / "metrics.json")
    if development_metrics["gate_passed"] is not True:
        raise ValueError("failed development closes this formulation")
    selected = read_json(development / "selection.json")
    if (approval.get("selected_path") != development_metrics["selected_path"]
            or selected["selected_path"] != development_metrics["selected_path"]):
        raise ValueError("Freeze B must bind the development-selected adoption path")
    if not selected["benchmark_complete"]:
        raise ValueError("incomplete classical comparison")
    # This is the only entry point allowed to request preserved held feature rows.
    xt, yt, _, _ = arrays(args.bundle, split["test"])
    predictions = {}
    if selected["selected_path"] == "NEURAL_CALIBRATION_EFFICIENCY":
        state, scale = load_model(development / "candidate.npz")
        predictions["candidate"] = scale.inverse(predict_candidate(scale.x(xt), state))
    for name in ("small", "full"):
        record = selected["all_classical_" + name][selected[name + "_winner"]]
        state, scale = load_model(development / record["checkpoint"])
        predictions[name] = scale.inverse(predict_classical(record["config"], state, scale.x(xt)))
    output = output_directory(args.output)
    records = {"stage": "held_group", "benchmark_complete": True, "selected_path": selected["selected_path"],
               "development_manifest_sha256": sha256(development / "artifact_manifest.json"),
               "small_reference": selected["all_classical_small"][selected["small_winner"]],
               "full_reference": selected["all_classical_full"][selected["full_winner"]],
               "checkpoint_refitting": False, "held_out_signal_values_accessed": True}
    return save_stage(output, approval, protocol, split, yt, predictions, None, None, records,
                      "held_group", approval["seeds"]["bootstrap"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("partition", "qualify", "develop", "evaluate"))
    for name in ("approval", "bundle", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--parent-partition")
    parser.add_argument("--partition")
    parser.add_argument("--qualification")
    parser.add_argument("--development")
    parser.add_argument("--development-bundle")
    args = parser.parse_args(argv)
    approval = authorize(args.approval, args.phase)
    bind_file(approval, "bundle_sha256", args.bundle)
    protocol = read_json(PACKAGE / "protocol.json")
    if args.phase == "partition":
        from experiments.localisation_redesign.partition import make_partition
        bind_file(approval, "parent_partition_sha256", args.parent_partition)
        split = make_partition(args.bundle, args.parent_partition, protocol)
        output = output_directory(args.output)
        write_json(output / "partition.json", split)
        save_manifest(output, approval, {"bundle_sha256": sha256(args.bundle), "parent_partition_sha256": sha256(args.parent_partition)})
        print(json.dumps({"status": split["status"], "small_label_budget": split["small_label_budget"]}))
        return 0
    if args.phase == "qualify":
        return qualify(args, approval, protocol)
    if args.phase == "develop":
        return develop(args, approval, protocol)
    return evaluate(args, approval, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
