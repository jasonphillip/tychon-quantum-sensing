"""Saved-output metrics. No model fitting or hidden target construction."""
import numpy as np


def errors(prediction, target):
    if prediction.shape != target.shape or prediction.ndim != 2 or prediction.shape[1] != 2:
        raise ValueError("prediction and stage-label shapes differ")
    if not np.isfinite(prediction).all() or not np.isfinite(target).all():
        raise ValueError("nonfinite output; no failed rows may disappear")
    return np.linalg.norm(prediction - target, axis=1)


def summary(error):
    return {"mean_error_um": float(np.mean(error)), "median_error_um": float(np.median(error)),
            "p95_error_um": float(np.quantile(error, 0.95)), "count": int(len(error)), "coverage": 1.0}


def ratio(numerator, denominator):
    # A perfect classical reference cannot be beaten by treating 0/0 as success.
    if denominator <= 0:
        return None
    return float(numerator / denominator)


def block_ratio_upper(a, b, groups, replicates, seed):
    unique = np.unique(groups)
    total_a = np.array([a[groups == group].sum() for group in unique])
    total_b = np.array([b[groups == group].sum() for group in unique])
    rng = np.random.default_rng(seed)
    chosen = rng.integers(0, len(unique), size=(replicates, len(unique)))
    denominators = total_b[chosen].sum(1)
    if (denominators <= 0).any():
        return None
    return float(np.quantile(total_a[chosen].sum(1) / denominators, 0.95))


def evaluate_saved(labels, candidate, classical, full_classical, groups, protocol, small_budget, full_budget, seed, confidence=True):
    ec, eb, ef = [errors(x, labels) for x in (candidate, classical, full_classical)]
    gate = protocol["primary_gate"]
    result = {"candidate": summary(ec), "classical_small": summary(eb), "classical_full": summary(ef),
              "small_label_budget": int(small_budget), "full_label_budget": int(full_budget),
              "candidate_to_classical_mean_ratio": ratio(ec.mean(), eb.mean()),
              "candidate_to_classical_p95_ratio": ratio(np.quantile(ec, .95), np.quantile(eb, .95)),
              "candidate_to_full_classical_mean_ratio": ratio(ec.mean(), ef.mean()),
              "label_budget_ratio": ratio(small_budget, full_budget),
              "spatial_block_count": int(len(np.unique(groups)))}
    def under(key, threshold):
        return result[key] is not None and result[key] <= threshold
    criteria = {
        "same_budget_useful_advantage": under("candidate_to_classical_mean_ratio", gate["maximum_candidate_to_classical_mean_ratio"]),
        "tail_safeguard": under("candidate_to_classical_p95_ratio", gate["maximum_candidate_to_classical_p95_ratio"]),
        "matched_full_pool_quality": under("candidate_to_full_classical_mean_ratio", gate["maximum_candidate_to_full_classical_mean_ratio"]),
        "label_reduction": under("label_budget_ratio", gate["maximum_small_to_full_label_budget_ratio"]),
    }
    if confidence:
        upper_small = block_ratio_upper(ec, eb, groups, protocol["uncertainty"]["bootstrap_replicates"], seed)
        upper_full = block_ratio_upper(ec, ef, groups, protocol["uncertainty"]["bootstrap_replicates"], seed + 1)
        result.update({"one_sided_95pct_small_ratio": upper_small, "one_sided_95pct_full_ratio": upper_full})
        criteria.update({"small_ratio_uncertainty": upper_small is not None and upper_small < gate["maximum_one_sided_95pct_block_bootstrap_ratio"],
                         "full_ratio_uncertainty": upper_full is not None and upper_full <= gate["maximum_one_sided_95pct_full_classical_ratio"],
                         "test_size": len(ec) >= gate["minimum_test_samples"],
                         "test_groups": len(np.unique(groups)) >= gate["minimum_test_spatial_blocks"]})
    result["criteria"] = criteria
    result["gate_passed"] = all(criteria.values())
    result["scope"] = "measured_motor_stage_labels_fixed_geometry_conditional_spatial_test"
    return result
