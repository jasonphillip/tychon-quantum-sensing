#!/usr/bin/env python3
"""Independent saved-output verification; never imports the evaluator or reads spectra.

Definitions inspected at frozen commit c6229d52279af38792023de48ec0747d93d720bb.
Only validation predictions/labels/flags and their reporting metadata are inputs.
Recorded pipeline timing is trusted for tie-breaking, not remeasured.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import traceback
import numpy as np

COMMIT = "c6229d52279af38792023de48ec0747d93d720bb"
CELLS = ("clean", "realistic_anchor", "wide_lines", "low_snr", "negative_slope", "negative_offset", "higher_contrast")
PRIMARY = ("clean", "realistic_anchor")
SEEDS = (42, 20261014, 20261015)
POLICIES = ("identity", "edge_ols", "joint_fit")
PRECISIONS = ("fp32", "int8")
CLASSICAL = ("robust_prior_fit", "conditional_likelihood")
BASES = ("training_mean", "training_median")
MEDIAN = 44.90404360960018
MEAN = 45.064080128749545
DRAWS = 10000
ANALYSIS_SEED = 202610152001
ATOL = 1e-9
RTOL = 1e-10
MODEL_NAMES = tuple(f"{p}__C_direct_seed{s}__{q}" for p in POLICIES for s in SEEDS for q in PRECISIONS)
METHODS = (*BASES, "unchanged_PID", "robust_prior_fit", "original_prior_fit", "conditional_likelihood", *MODEL_NAMES)
FLAG_METHODS = tuple(k for k in METHODS if k not in BASES)
FAMILIES = tuple(f"{p}__{q}" for p in POLICIES[1:] for q in PRECISIONS)
CHECKS = 0


def require(condition, label):
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(label)


def same(actual, expected, label):
    """Strict structure and integer/bool matching; explicit tolerance for floats."""
    if isinstance(expected, dict):
        require(isinstance(actual, dict) and set(actual) == set(expected), label + ": keys")
        for k, v in expected.items():
            same(actual[k], v, label + "." + k)
    elif isinstance(expected, (list, tuple)):
        require(isinstance(actual, (list, tuple)) and len(actual) == len(expected), label + ": length")
        for i, v in enumerate(expected):
            same(actual[i], v, label + f"[{i}]")
    elif isinstance(expected, bool):
        require(type(actual) is bool and actual == expected, label)
    elif isinstance(expected, int):
        require(type(actual) is int and actual == expected, label)
    elif isinstance(expected, float):
        require(type(actual) in (int, float) and math.isfinite(actual)
                and math.isclose(actual, expected, abs_tol=ATOL, rel_tol=RTOL),
                label + f": reported={actual!r}, recomputed={expected!r}")
    else:
        require(actual == expected, label)


def safe(path):
    p = Path(path).absolute()
    require(not any(q.is_symlink() for q in (p, *p.parents)), "symlink refused: " + str(p))
    return p


def digest(path):
    h = hashlib.sha256()
    with safe(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(safe(path).read_text())


def error_summary(pred, truth):
    require(pred.ndim == 1 and pred.shape == truth.shape and len(pred) > 0, "metric dimensions")
    signed = pred.astype(np.float64) - truth.astype(np.float64)
    require(np.isfinite(signed).all(), "nonfinite all-row errors")
    absolute = np.abs(signed)
    return {"n": len(pred), "mae_uT": float(np.mean(absolute)),
            "rmse_uT": float(np.sqrt(np.dot(signed, signed) / len(signed))),
            "median_abs_uT": float(np.quantile(absolute, .5, method="linear")),
            "p90_abs_uT": float(np.quantile(absolute, .9, method="linear")),
            "worst_uT": float(np.max(absolute)), "bias_uT": float(np.mean(signed))}


def bootstrap_many(contrasts, groups):
    """Independent frequency-weight implementation of paired cluster bootstrap.

    Use the registered RNG draws, but aggregate draw multiplicities and matrix
    multiply grouped losses. No evaluator functions or summation code are used.
    Each draw retains all rows belonging to a sampled nuisance group.
    """
    keys = list(contrasts)
    differences = np.column_stack([contrasts[k] for k in keys])
    unique, inverse, counts = np.unique(groups, return_inverse=True, return_counts=True)
    g = len(unique)
    require(g >= 2 and np.isfinite(differences).all(), "bootstrap groups/losses")
    grouped = np.zeros((g, len(keys)), dtype=np.float64)
    np.add.at(grouped, inverse, differences)
    rng = np.random.default_rng(ANALYSIS_SEED)
    samples = np.empty((DRAWS, len(keys)), dtype=np.float64)
    for offset in range(0, DRAWS, 100):
        size = min(100, DRAWS - offset)
        drawn = rng.integers(0, g, size=(size, g))
        multiplicity = np.zeros((size, g), dtype=np.float64)
        np.add.at(multiplicity, (np.repeat(np.arange(size), g), drawn.ravel()), 1.)
        samples[offset:offset + size] = (multiplicity @ grouped) / (multiplicity @ counts)[:, None]
    endpoints = np.quantile(samples, [.025, .975], axis=0, method="linear")
    return {k: {"mean_difference_uT": float(np.mean(differences[:, j])),
                "ci95_uT": endpoints[:, j].tolist(), "groups": g,
                "draws": DRAWS, "seed": ANALYSIS_SEED} for j, k in enumerate(keys)}


def load_arrays(path, n):
    allowed = {"truth_uT", "group_ids", "field_ids", "sample_seeds", "common_hard_invalid",
               "common_ambiguous", "raw_projection_robust_fit", "raw_projection_original_fit",
               "likelihood_interval90_uT"}
    allowed.update("pred__" + k for k in METHODS)
    allowed.update(prefix + k for k in FLAG_METHODS for prefix in ("raw__", "fallback__", "reliable_valid__"))
    with np.load(safe(path), allow_pickle=False) as archive:
        require(set(archive.files) == allowed and len(archive.files) == len(allowed), "prediction archive keys")
        # Conditional likelihood intervals are not needed and are never loaded.
        arrays = {k: archive[k] for k in sorted(allowed - {"likelihood_interval90_uT"})}
    for k, v in arrays.items():
        require(v.shape == (n,), k + ": retained row count")
        if k.startswith(("fallback__", "reliable_valid__", "common_")):
            require(v.dtype == np.dtype(bool), k + ": boolean flags")
        elif k in ("field_ids", "group_ids"):
            require(v.dtype.kind in "US", k + ": string identifiers")
        elif k == "sample_seeds":
            require(v.dtype.kind in "iu", "integer sample seeds")
        else:
            require(v.dtype.kind == "f", k + ": floating values")
    return arrays


def check_timing(timing):
    required = {*CLASSICAL, *(k for k in MODEL_NAMES if not k.startswith("identity__"))}
    require(set(timing) == required, "pipeline timing candidate set")
    for k, t in timing.items():
        for key, val in {"n": 16, "warmup": 4, "warmup_source": "frozen development", "batch_size": 1, "threads": 1}.items():
            same(t[key], val, "timing." + k + "." + key)
        require(math.isfinite(t["median_pipeline_seconds"]) and t["median_pipeline_seconds"] >= 0,
                "finite nonnegative recorded median timing")
        require(math.isfinite(t["p95_pipeline_seconds"]) and t["p95_pipeline_seconds"] >= t["median_pipeline_seconds"],
                "recorded p95 timing")


def verify_cell(name, data, reported, n):
    truth = data["truth_uT"]
    hard, ambiguous = data["common_hard_invalid"], data["common_ambiguous"]
    require(np.isfinite(truth).all() and ((truth >= 20) & (truth <= 70)).all(), "finite supported labels")
    require(not (hard & ambiguous).any(), "hard/ambiguity exclusivity")
    require(len(np.unique(data["field_ids"])) == n, "unique retained field IDs")
    require(len(np.unique(data["sample_seeds"])) == n, "unique retained sample seeds")
    same(reported["n"], n, name + ".n")
    pred = {k: data["pred__" + k] for k in METHODS}
    require(np.array_equal(pred["training_mean"], np.full(n, MEAN)), "original training mean")
    require(np.array_equal(pred["training_median"], np.full(n, MEDIAN)), "original training median")
    metrics = {k: error_summary(v, truth) for k, v in pred.items()}
    same(reported["metrics"], metrics, name + ".metrics")
    flags, coverage = {}, {}
    for k in FLAG_METHODS:
        raw, fallback = data["raw__" + k], data["fallback__" + k]
        nonfinite = ~np.isfinite(raw)
        outside = np.isfinite(raw) & ((raw < 20) | (raw > 70))
        invalid = nonfinite | outside
        projection = {}
        if k in ("robust_prior_fit", "original_prior_fit"):
            pk = "raw_projection_robust_fit" if k == "robust_prior_fit" else "raw_projection_original_fit"
            p = data[pk]
            p_nonfinite = ~np.isfinite(p)
            p_outside = np.isfinite(p) & ((p < 0) | (p > 70))
            invalid |= p_nonfinite | p_outside
            projection = {"nonfinite_raw_projection_count": int(p_nonfinite.sum()),
                          "raw_projection_support_violations": int(p_outside.sum())}
        if k == "robust_prior_fit":
            expected_fallback = hard
        elif k == "conditional_likelihood":
            expected_fallback = hard | nonfinite
        elif k == "original_prior_fit":
            expected_fallback = nonfinite | p_nonfinite | p_outside
        elif k == "unchanged_PID" or k.startswith("identity__"):
            expected_fallback = nonfinite
        else:
            expected_fallback = hard | invalid
        require(np.array_equal(fallback, expected_fallback), name + ".fallback." + k)
        require(np.allclose(pred[k], np.where(fallback, MEDIAN, raw), atol=ATOL, rtol=RTOL),
                name + ".fallback prediction." + k)
        valid = ~(fallback | hard | ambiguous | invalid)
        require(np.array_equal(data["reliable_valid__" + k], valid), name + ".reliable_valid." + k)
        flags[k] = {"fallback_count": int(fallback.sum()), "common_input_hard_invalid_count": int(hard.sum()),
                    "method_invalid_count": int(invalid.sum()), "nonfinite_raw_count": int(nonfinite.sum()),
                    "raw_output_support_violations": int(outside.sum()), "ambiguous_count": int(ambiguous.sum()),
                    "reliable_valid_count": int(valid.sum()), "n": n,
                    "accepted_only": error_summary(pred[k][valid], truth[valid]) if valid.any() else None,
                    **projection}
        coverage[k] = float(valid.mean())
    same(reported["flags"], flags, name + ".flags")
    disagreement = {}
    for policy in POLICIES:
        disagreement[policy] = {}
        for seed in SEEDS:
            fp, qi = (data[f"raw__{policy}__C_direct_seed{seed}__{q}"] for q in PRECISIONS)
            finite = np.isfinite(fp) & np.isfinite(qi)
            delta = np.abs(fp[finite] - qi[finite])
            disagreement[policy][str(seed)] = {"finite_pairs": int(finite.sum()), "n": n,
                "mean_abs_uT": float(delta.mean()) if len(delta) else None,
                "p95_abs_uT": float(np.quantile(delta, .95, method="linear")) if len(delta) else None,
                "max_abs_uT": float(delta.max()) if len(delta) else None}
    same(reported["fp32_int8_disagreement"], disagreement, name + ".fp32_int8_disagreement")
    check_timing(reported["pipeline_timing"])
    losses = {k: np.abs(v - truth) for k, v in pred.items()}
    decision_metrics = {}
    for k in CLASSICAL:
        decision_metrics[k] = {"mae_uT": metrics[k]["mae_uT"], "p90_abs_uT": metrics[k]["p90_abs_uT"],
            "hard_invalid_fraction": float(data["fallback__" + k].mean()),
            "valid_fraction": float((~(data["fallback__" + k] | hard | ambiguous)).mean()),
            "median_pipeline_seconds": reported["pipeline_timing"][k]["median_pipeline_seconds"]}
    for policy in POLICIES[1:]:
        for precision in PRECISIONS:
            k = policy + "__" + precision
            names = [f"{policy}__C_direct_seed{s}__{precision}" for s in SEEDS]
            losses[k] = np.stack([losses[v] for v in names]).mean(axis=0)
            valid = [float((~(data["fallback__" + v] | hard | ambiguous)).mean()) for v in names]
            decision_metrics[k] = {"mae_uT": float(losses[k].mean()),
                "p90_abs_uT": float(np.quantile(losses[k], .9, method="linear")),
                "hard_invalid_fraction": float(np.mean([data["fallback__" + v].mean() for v in names])),
                "valid_fraction": float(np.mean(valid)), "all_seeds_reliable": all(v >= .95 for v in valid),
                "median_pipeline_seconds": float(np.mean([reported["pipeline_timing"][v]["median_pipeline_seconds"] for v in names]))}
    # Full error/flag summaries are verified for all cells. Bootstrap is bounded to the two primary cells.
    if name not in PRIMARY:
        for k, values in decision_metrics.items():
            for field, value in values.items():
                if field != "all_seeds_reliable":
                    same(reported["decision_metrics"][k][field], value, name + ".decision_metrics." + k + "." + field)
        return {"n": n, "methods": len(metrics), "flag_methods": len(flags), "decision_metrics": decision_metrics,
                "bootstrap_checked": False, "raw_disagreement_checked": True}
    contrasts = {}
    for k in FAMILIES:
        for b in (*BASES, *CLASSICAL):
            contrasts[k + "_minus_" + b] = losses[k] - losses[b]
    for k in CLASSICAL:
        for b in BASES:
            contrasts[k + "_minus_" + b] = losses[k] - losses[b]
    for p in POLICIES[1:]:
        for s in SEEDS:
            contrasts[f"{p}_seed{s}_int8_minus_fp32"] = losses[f"{p}__C_direct_seed{s}__int8"] - losses[f"{p}__C_direct_seed{s}__fp32"]
        contrasts[p + "_mean_int8_minus_fp32"] = losses[p + "__int8"] - losses[p + "__fp32"]
    pair_keys = set(contrasts)
    for k in MODEL_NAMES:
        if not k.startswith("identity__"):
            for b in BASES:
                contrasts["seed::" + k + "::" + b] = losses[k] - losses[b]
    intervals = bootstrap_many(contrasts, data["group_ids"])
    paired = {k: intervals[k] for k in pair_keys}
    same(reported["paired_comparisons"], paired, name + ".paired_comparisons")
    seed_gates = {}
    for k in MODEL_NAMES:
        if k.startswith("identity__"):
            continue
        pairs = {b: intervals["seed::" + k + "::" + b] for b in BASES}
        seed_gates[k] = {"prediction_passed": bool(metrics[k]["p90_abs_uT"] <= 25 and
            all(v["ci95_uT"][1] < -.5 for v in pairs.values())),
            "paired_constants": pairs, "reliable_valid_fraction": coverage[k]}
    same(reported["seed_gates"], seed_gates, name + ".seed_gates")
    for p in POLICIES[1:]:
        for q in PRECISIONS:
            k = p + "__" + q
            decision_metrics[k]["all_seeds_reliable"] &= all(seed_gates[f"{p}__C_direct_seed{s}__{q}"]["prediction_passed"] for s in SEEDS)
    same(reported["decision_metrics"], decision_metrics, name + ".decision_metrics")
    return {"n": n, "methods": len(metrics), "flag_methods": len(flags), "decision_metrics": decision_metrics,
            "paired_comparisons": paired, "seed_gates": seed_gates,
            "bootstrap_checked": True, "bootstrap_contrasts": len(contrasts), "raw_disagreement_checked": True}


def selection_from_recomputed(cells):
    eligible = (*CLASSICAL, "edge_ols__int8", "joint_fit__int8")
    gates = {}
    for k in eligible:
        checks = {}
        for cell in PRIMARY:
            c = cells[cell]
            checks[cell] = bool(c["decision_metrics"][k]["p90_abs_uT"] <= 25 and all(
                c["paired_comparisons"][k + "_minus_" + b]["ci95_uT"][1] < -.5 for b in BASES))
        gates[k] = {"passed": all(checks.values()), "conditions": checks}
    anchor = cells["realistic_anchor"]["decision_metrics"]
    def winner(candidates):
        minimum = min(anchor[k]["mae_uT"] for k in candidates)
        near = [k for k in candidates if anchor[k]["mae_uT"] < minimum + .1]
        return sorted(near, key=lambda k: (anchor[k]["hard_invalid_fraction"], anchor[k]["median_pipeline_seconds"], k))[0]
    classical = winner(CLASSICAL)
    neural = winner(("edge_ols__int8", "joint_fit__int8"))
    return {"classical": classical, "neural": neural, "primary_implementation": "int8", "claim_route": "accuracy",
            "gates": gates, "can_proceed": gates[classical]["passed"] or gates[neural]["passed"]}


def verify(args):
    root = safe(args.results)
    require(root.name == "results-val", "only canonical validation output directory supported")
    require(digest(root / "SUMMARY.json") == args.summary_sha256, "pinned summary hash")
    require(digest(root / "RECEIPT.json") == args.receipt_sha256, "pinned receipt hash")
    report, receipt = read_json(root / "SUMMARY.json"), read_json(root / "RECEIPT.json")
    access = read_json(root.parent / "VAL_EVALUATOR_ACCESS.json")
    for label, obj in (("summary", report), ("receipt", receipt), ("access", access)):
        for key, value in {"status": "complete", "partition": "val", "freeze_sha256": args.freeze_sha256,
                           "manifest_sha256": args.manifest_sha256}.items():
            same(obj[key], value, label + "." + key)
    same(receipt["summary_sha256"], args.summary_sha256, "receipt summary binding")
    same(access["summary_sha256"], args.summary_sha256, "exclusive access summary binding")
    require(set(report["cells"]) == set(CELLS), "exact condition set")
    hashes, recomputed, identity = {}, {}, None
    for cell in CELLS:
        pred_file = root / (cell + "_predictions.npz")
        checksum = digest(pred_file)
        same(report["cells"][cell]["predictions_sha256"], checksum, cell + ".predictions_sha256")
        hashes[pred_file.name] = checksum
        saved_cell = read_json(root / (cell + "_metrics.json"))
        require(saved_cell == report["cells"][cell], cell + ": duplicate metric JSON equality")
        same(saved_cell["warmup_manifest_sha256"], receipt["warmup_manifest_sha256"], cell + ".warmup_manifest_sha256")
        data = load_arrays(pred_file, 512)
        current = {k: data[k] for k in ("truth_uT", "field_ids", "group_ids", "sample_seeds")}
        if identity is None:
            identity = current
        else:
            for k in current:
                require(np.array_equal(identity[k], current[k]), cell + ": paired identity " + k)
        recomputed[cell] = verify_cell(cell, data, saved_cell, 512)
    selection = selection_from_recomputed(recomputed)
    same(report["selection"], selection, "selection")
    same(report["validation_can_proceed"], selection["can_proceed"], "validation continuation")
    same(report["final_decision"], None, "no final decision on validation")
    same(report["timing"]["rows"], 3584, "complete row total")
    # Recheck input hashes after verification to detect concurrent artifact mutation.
    for filename, checksum in hashes.items():
        require(digest(root / filename) == checksum, "input drift: " + filename)
    require(digest(root / "SUMMARY.json") == args.summary_sha256, "summary drift")
    require(digest(root / "RECEIPT.json") == args.receipt_sha256, "receipt drift")
    return {"status": "PASS", "verification_scope": "saved validation arrays only; independent formulas",
            "definition_commit": COMMIT, "results_root": str(root), "summary_sha256": args.summary_sha256,
            "receipt_sha256": args.receipt_sha256, "freeze_sha256": args.freeze_sha256,
            "manifest_sha256": args.manifest_sha256, "prediction_hashes": hashes,
            "rows": 3584, "methods_per_cell": 24, "method_condition_combinations": 168,
            "flag_methods_per_cell": 22, "primary_bootstrap_contrasts": 104,
            "bootstrap_draws": DRAWS, "bootstrap_seed": ANALYSIS_SEED,
            "absolute_tolerance": ATOL, "relative_tolerance": RTOL,
            "selection": selection, "cells": recomputed,
            "limitations": ["Recorded timing metadata supplies selection tie-breaks; no timing remeasurement.",
                "Common quality/ambiguity flags are accepted saved inputs, not rederived from spectra.",
                "Label provenance and payload-to-prediction correspondence remain with custody; no spectra were read.",
                "Quantization input/endpoint counts are not reconstructed from saved magnitude predictions.",
                "Secondary-condition bootstrap intervals and per-seed prediction gates are outside this verification.",
                "Conditional likelihood intervals remain uncalibrated and are not opened.",
                "Frozen source identity is the reviewed definition commit; custody verifies Freeze 1 membership."]}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "summary-sha256", "receipt-sha256", "freeze-sha256", "manifest-sha256", "out"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    output = safe(a.out)
    require(safe(a.results) not in output.parents, "verification output must be outside frozen result directory")
    require(not output.exists(), "refuse overwrite of verification report")
    output.parent.mkdir(parents=True, exist_ok=True)
    for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        require(os.environ.get(var) == "1", "one-thread wrapper required: " + var)
    try:
        result = verify(a)
        exit_code = 0
    except Exception as exc:
        result = {"status": "FAIL", "definition_commit": COMMIT, "error_type": type(exc).__name__,
                  "error": str(exc), "traceback": traceback.format_exc()}
        exit_code = 1
    result.update(completed_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  verifier_sha256=digest(Path(__file__)), checks=CHECKS)
    with output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "report": str(output), "checks": CHECKS,
                      "selection": result.get("selection"), "error": result.get("error")}))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
