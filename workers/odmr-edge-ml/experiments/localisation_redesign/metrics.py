"""Saved-output metrics; invalid rows stay in the denominator and fail gates."""
import numpy as np


def validity(prediction, labels):
    if prediction.shape != labels.shape or labels.ndim != 2 or labels.shape[1] != 2:
        raise ValueError("prediction/label shape mismatch")
    if not np.isfinite(labels).all():
        raise ValueError("nonfinite reference labels")
    return np.isfinite(prediction).all(axis=1)


def errors(prediction, labels):
    valid = validity(prediction, labels)
    result = np.full(len(labels), np.inf)
    result[valid] = np.linalg.norm(prediction[valid] - labels[valid], axis=1)
    return result


def summary(error):
    complete = bool(np.isfinite(error).all())
    return {"mean_error_um": float(np.mean(error)) if complete else None,
            "median_error_um": float(np.median(error)) if complete else None,
            "p95_error_um": float(np.quantile(error, .95)) if complete else None,
            "count": len(error), "invalid_rows": int((~np.isfinite(error)).sum()),
            "coverage": float(np.isfinite(error).mean())}


def ratio(a, b):
    if a is None or b is None or not np.isfinite(a) or not np.isfinite(b) or b <= 0:
        return None
    return float(a / b)


def block_ratio_upper(a, b, groups, replicates, seed):
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        return None
    unique = np.unique(groups)
    numerator = np.array([a[groups == g].sum() for g in unique])
    denominator = np.array([b[groups == g].sum() for g in unique])
    selected = np.random.default_rng(seed).integers(0, len(unique), size=(replicates, len(unique)))
    totals = denominator[selected].sum(1)
    if (totals <= 0).any():
        return None
    return float(np.quantile(numerator[selected].sum(1) / totals, .95))


def evaluate_saved(labels, candidate, control, small, full, groups, protocol,
                   small_budget, full_budget, seed, confidence, benchmark_complete):
    values = {name: errors(prediction, labels) for name, prediction in
              (("candidate", candidate), ("old_loss_control", control), ("classical_small", small), ("classical_full", full))}
    result = {name: summary(value) for name, value in values.items()}
    c, b, f, control_metrics = [result[k] for k in ("candidate", "classical_small", "classical_full", "old_loss_control")]
    result.update({"candidate_to_classical_mean_ratio": ratio(c["mean_error_um"], b["mean_error_um"]),
                   "candidate_to_classical_p95_ratio": ratio(c["p95_error_um"], b["p95_error_um"]),
                   "candidate_to_full_classical_mean_ratio": ratio(c["mean_error_um"], f["mean_error_um"]),
                   "candidate_to_old_loss_control_mean_ratio": ratio(c["mean_error_um"], control_metrics["mean_error_um"]),
                   "small_to_full_classical_mean_ratio": ratio(b["mean_error_um"], f["mean_error_um"]),
                   "label_budget_ratio": ratio(small_budget, full_budget),
                   "small_label_budget": small_budget, "full_label_budget": full_budget,
                   "label_budget_unit": "unique_stage_xy_positions_including_validation",
                   "evaluated_measurement_rows": len(labels),
                   "evaluated_unique_stage_positions": len(np.unique(labels, axis=0)),
                   "spatial_block_count": len(np.unique(groups)),
                   "benchmark_complete": bool(benchmark_complete)})
    gate = protocol["primary_gate"]
    def under(key, limit):
        return result[key] is not None and result[key] <= limit
    criteria = {
        "same_budget_useful_advantage": under("candidate_to_classical_mean_ratio", gate["maximum_candidate_to_classical_mean_ratio"]),
        "tail_safeguard": under("candidate_to_classical_p95_ratio", gate["maximum_candidate_to_classical_p95_ratio"]),
        "matched_full_pool_quality": under("candidate_to_full_classical_mean_ratio", gate["maximum_candidate_to_full_classical_mean_ratio"]),
        "label_reduction": under("label_budget_ratio", gate["maximum_small_to_full_label_budget_ratio"]),
        "full_coverage": all(m["coverage"] == 1.0 for m in (c, b, f, control_metrics)),
        "complete_classical_comparison": bool(benchmark_complete),
    }
    if confidence:
        upper_small = block_ratio_upper(values["candidate"], values["classical_small"], groups, protocol["uncertainty"]["bootstrap_replicates"], seed)
        upper_full = block_ratio_upper(values["candidate"], values["classical_full"], groups, protocol["uncertainty"]["bootstrap_replicates"], seed + 1)
        result.update(one_sided_95pct_small_ratio=upper_small, one_sided_95pct_full_ratio=upper_full)
        criteria.update(small_ratio_uncertainty=upper_small is not None and upper_small < gate["maximum_one_sided_95pct_block_bootstrap_ratio"],
                        full_ratio_uncertainty=upper_full is not None and upper_full <= gate["maximum_one_sided_95pct_full_classical_ratio"],
                        test_size=len(np.unique(labels, axis=0)) >= gate["minimum_test_samples"],
                        test_groups=len(np.unique(groups)) >= gate["minimum_test_spatial_blocks"])
    result["criteria"] = criteria
    result["gate_passed"] = all(criteria.values())
    comparison = result["candidate_to_old_loss_control_mean_ratio"]
    result["loss_change_improved_error"] = comparison is not None and comparison < 1.0
    result["control_role"] = "diagnostic_attribution_only_never_alternative_candidate"
    result["scope"] = protocol["scope"]
    return result
