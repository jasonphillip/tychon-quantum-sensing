"""Saved-output metrics; invalid rows stay in the denominator and fail gates."""
import numpy as np

NEURAL = "NEURAL_CALIBRATION_EFFICIENCY"
CLASSICAL = "CLASSICAL_CALIBRATION_EFFICIENCY"


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
    if a is None or b is None or not np.isfinite(a).all() or not np.isfinite(b).all():
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
                   small_budget, full_budget, seed, confidence, benchmark_complete, frozen_path=None):
    if confidence and frozen_path not in (NEURAL, CLASSICAL):
        raise ValueError("held evaluation requires exactly one frozen adoption path")
    values = {name: errors(prediction, labels) if prediction is not None else None for name, prediction in
              (("candidate", candidate), ("old_loss_control", control), ("classical_small", small), ("classical_full", full))}
    result = {name: summary(value) if value is not None else None for name, value in values.items()}
    def metric(name, key):
        return result[name][key] if result[name] is not None else None
    def r(a, b, key="mean_error_um"):
        return ratio(metric(a, key), metric(b, key))
    result.update({"candidate_to_classical_mean_ratio": r("candidate", "classical_small"),
                   "candidate_to_classical_p95_ratio": r("candidate", "classical_small", "p95_error_um"),
                   "candidate_to_full_classical_mean_ratio": r("candidate", "classical_full"),
                   "candidate_to_old_loss_control_mean_ratio": r("candidate", "old_loss_control"),
                   "small_to_full_classical_mean_ratio": r("classical_small", "classical_full"),
                   "small_to_full_classical_p95_ratio": r("classical_small", "classical_full", "p95_error_um"),
                   "label_budget_ratio": ratio(small_budget, full_budget),
                   "small_label_budget": small_budget, "full_label_budget": full_budget,
                   "label_budget_unit": "unique_stage_xy_positions_including_validation",
                   "evaluated_measurement_rows": len(labels),
                   "evaluated_unique_stage_positions": len(np.unique(labels, axis=0)),
                   "spatial_block_count": len(np.unique(groups)),
                   "benchmark_complete": bool(benchmark_complete)})
    gate, classical_gate = protocol["primary_gate"], protocol["classical_adoption_gate"]
    def under(key, limit):
        return result[key] is not None and result[key] <= limit
    def coverage(names):
        return all(result[name] is not None and result[name]["coverage"] == 1.0 for name in names)
    common = {"label_reduction": under("label_budget_ratio", gate["maximum_small_to_full_label_budget_ratio"]),
              "complete_classical_comparison": bool(benchmark_complete)}
    neural = {**common,
        "same_budget_useful_advantage": under("candidate_to_classical_mean_ratio", gate["maximum_candidate_to_classical_mean_ratio"]),
        "tail_safeguard": under("candidate_to_classical_p95_ratio", gate["maximum_candidate_to_classical_p95_ratio"]),
        "matched_full_pool_quality": under("candidate_to_full_classical_mean_ratio", gate["maximum_candidate_to_full_classical_mean_ratio"]),
        "full_coverage": coverage(("candidate", "classical_small", "classical_full") + (() if confidence else ("old_loss_control",)))}
    classical = {**common,
        "matched_full_pool_quality": under("small_to_full_classical_mean_ratio", classical_gate["maximum_mean_ratio"]),
        "tail_safeguard": under("small_to_full_classical_p95_ratio", classical_gate["maximum_p95_ratio"]),
        "full_coverage": coverage(("classical_small", "classical_full"))}
    if confidence:
        size = {"test_size": len(np.unique(labels, axis=0)) >= gate["minimum_test_samples"],
                "test_groups": len(np.unique(groups)) >= gate["minimum_test_spatial_blocks"]}
        if frozen_path == NEURAL:
            upper_small = block_ratio_upper(values["candidate"], values["classical_small"], groups, protocol["uncertainty"]["bootstrap_replicates"], seed)
            upper_full = block_ratio_upper(values["candidate"], values["classical_full"], groups, protocol["uncertainty"]["bootstrap_replicates"], seed + 1)
            result.update(one_sided_95pct_small_ratio=upper_small, one_sided_95pct_full_ratio=upper_full)
            neural.update(**size, small_ratio_uncertainty=upper_small is not None and upper_small < gate["maximum_one_sided_95pct_block_bootstrap_ratio"],
                          full_ratio_uncertainty=upper_full is not None and upper_full <= gate["maximum_one_sided_95pct_full_classical_ratio"])
        else:
            upper = block_ratio_upper(values["classical_small"], values["classical_full"], groups, protocol["uncertainty"]["bootstrap_replicates"], seed)
            result["one_sided_95pct_classical_full_ratio"] = upper
            classical.update(**size, full_ratio_uncertainty=upper is not None and upper <= classical_gate["maximum_one_sided_95pct_mean_ratio"])
    neural_pass = all(neural.values()) if not confidence or frozen_path == NEURAL else False
    classical_pass = all(classical.values()) if not confidence or frozen_path == CLASSICAL else False
    selected = frozen_path if confidence else NEURAL if neural_pass else CLASSICAL if classical_pass else None
    result.update(neural_criteria=neural, classical_criteria=classical,
                  neural_gate_passed=neural_pass, classical_gate_passed=classical_pass,
                  selected_path=selected, gate_passed=(neural_pass if selected == NEURAL else classical_pass if selected == CLASSICAL else False),
                  selection_rule="neural_if_all_gates_pass_else_classical_if_all_gates_pass_else_close",
                  unselected_path_confirmed=False)
    comparison = result["candidate_to_old_loss_control_mean_ratio"]
    result["loss_change_improved_error"] = comparison is not None and comparison < 1.0
    result["control_role"] = "diagnostic_attribution_only_never_alternative_candidate"
    result["scope"] = protocol["scope"]
    return result
