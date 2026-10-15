"""Saved-output metrics; spatial blocks, not individual pixels, are uncertainty units."""
import numpy as np


def compare(targets, row_key, saved, seed, frozen_reference=None, shape_edges=None, frozen_candidate=None):
    methods = sorted(key[:-12] for key in saved if key.endswith("__prediction"))
    if not methods or targets.shape != (len(row_key), 9, 200) or not np.isfinite(targets).all():
        raise ValueError("Invalid measured references")
    groups = np.unique(row_key[:, 1])
    if len(groups) < 16:
        raise ValueError("Insufficient complete spatial groups")
    if shape_edges is None or shape_edges.dtype.kind not in "iu" or shape_edges.shape != (50,):
        raise ValueError("Frozen training-only shape edges required")
    if np.any(shape_edges < 0) or np.any(shape_edges >= 199) or len(np.unique(shape_edges)) != 50:
        raise ValueError("Invalid shape-edge mask")
    if type(seed) is not int or not 0 <= seed < 2 ** 128:
        raise ValueError("Explicit audited bootstrap seed required")
    bootstrap = np.random.Generator(np.random.PCG64(seed)).integers(0, len(groups), size=(10000, len(groups)))
    summaries, blocks = {}, {}
    for method in methods:
        prediction, failed = saved[method + "__prediction"], saved[method + "__failed"]
        seconds, reliable = saved[method + "__seconds"], saved[method + "__fit_reliable"]
        if prediction.shape != (len(row_key), 200) or not np.isfinite(prediction).all():
            raise ValueError("Invalid operational prediction")
        if failed.dtype != np.bool_ or reliable.dtype != np.bool_ or failed.shape != (len(row_key),) or reliable.shape != failed.shape:
            raise ValueError("Invalid failure flags")
        if seconds.shape != failed.shape or not np.isfinite(seconds).all() or np.any(seconds < 0):
            raise ValueError("Invalid recorded timing")
        losses = np.mean((prediction[:, None, :] - targets) ** 2, axis=2)
        derivative_error = (np.diff(prediction, axis=1) - np.diff(targets[:, 0], axis=1))[:, shape_edges]
        derivative_losses = np.mean(derivative_error ** 2, axis=1)
        blocks[method] = np.asarray([losses[row_key[:, 1] == group].mean(axis=0) for group in groups])
        summaries[method] = {"mse": float(blocks[method][:, 0].mean()),
            "shape_derivative_mse": float(np.mean([derivative_losses[row_key[:, 1] == g].mean() for g in groups])),
            "p90_patch_rmse": float(np.quantile(np.sqrt(losses[:, 0]), 0.9)),
            "failure_fraction": float(failed.mean()), "fit_reliable_fraction": float(reliable.mean()),
            "recorded_batch1_p95_seconds": float(np.quantile(seconds, 0.95)),
            "shift_mse": blocks[method].mean(axis=0).tolist(),
            "by_current_file_mse": {str(int(i)): float(losses[row_key[:, 0] == i, 0].mean()) for i in np.unique(row_key[:, 0])}}
    candidates = [name for name in methods if name.startswith("candidate_")]
    classical = [name for name in methods if name not in candidates]
    reference = frozen_reference or min(classical, key=lambda name: (summaries[name]["mse"], name))
    if reference not in classical:
        raise ValueError("Frozen classical reference missing")
    baseline_diagnostic = None
    if "raw" in summaries and "training_mean" in summaries:
        baseline_diagnostic = bool(summaries["raw"]["mse"] > 0 and summaries["training_mean"]["shape_derivative_mse"] > 0
            and summaries[reference]["mse"] <= 0.98 * summaries["raw"]["mse"]
            and summaries[reference]["failure_fraction"] <= 0.01
            and summaries[reference]["shape_derivative_mse"] <= 0.98 * summaries["training_mean"]["shape_derivative_mse"])
    expected = {"raw", "training_mean", "savgol_5", "savgol_11", "savgol_21", "ridge_0.001", "ridge_0.01", "ridge_0.1",
                "pca_wiener_4", "pca_wiener_8", "pca_wiener_16", "robust_lorentzian"}
    result = {"status": "complete", "rows": len(row_key), "groups": len(groups), "reference": reference,
        "methods": summaries, "classical_development_diagnostic": baseline_diagnostic,
        "baseline_execution_valid": expected <= set(classical),
        "uncertainty_scope": "Conditional spatial-block bootstrap from one field of view; no independent acquisitions or calibrated field truth.",
        "candidate_gate": None}
    if candidates:
        if "training_mean" not in summaries:
            raise ValueError("Candidate comparison requires the saved training-mean null")
        registered = {"candidate_16", "candidate_32", "candidate_64"}
        if frozen_candidate:
            if candidates != [frozen_candidate] or frozen_candidate not in registered:
                raise ValueError("Final candidate differs from the frozen winner")
            selected = frozen_candidate
        else:
            if set(candidates) != registered:
                raise ValueError("Development selection requires all three registered configurations")
            selected = min(candidates, key=lambda name: (summaries[name]["mse"], int(name.split("_")[1])))
        result["selected_candidate"] = selected
        result["candidate_selection"] = "Lowest development MSE, ties by fewer parameters; no switch after failed quality gates"
        candidate, ref = summaries[selected], summaries[reference]
        numerator = blocks[selected][bootstrap, 0].mean(axis=1)
        denominator = blocks[reference][bootstrap, 0].mean(axis=1)
        # 0/0 is no demonstrated improvement; positive/0 is worse, never favorable.
        ratios = np.divide(numerator, denominator,
            out=np.where(numerator == 0, 1.0, np.finfo(float).max), where=denominator > 0)
        interval = np.quantile(ratios, (0.025, 0.975))
        conditions = {
            "mse_improvement_at_least_5pct": ref["mse"] > 0 and candidate["mse"] <= 0.95 * ref["mse"],
            "paired_ratio_ci_upper_below_one": interval[1] < 1.0,
            "p90_rmse_no_more_than_2pct_worse": candidate["p90_patch_rmse"] <= 1.02 * ref["p90_patch_rmse"],
            "failure_fraction": candidate["failure_fraction"] <= min(0.01, ref["failure_fraction"] + 0.005),
            "shape_derivative_within_2pct_of_classical": candidate["shape_derivative_mse"] <= 1.02 * ref["shape_derivative_mse"],
            "shape_derivative_5pct_better_than_mean_null": summaries["training_mean"]["shape_derivative_mse"] > 0 and candidate["shape_derivative_mse"] <= 0.95 * summaries["training_mean"]["shape_derivative_mse"],
            "all_registration_shifts_within_2pct": bool(np.all(np.asarray(candidate["shift_mse"]) <= 1.02 * np.asarray(ref["shift_mse"]))),
            "all_current_files_within_2pct": all(candidate["by_current_file_mse"][i] <= 1.02 * ref["by_current_file_mse"][i] for i in ref["by_current_file_mse"])}
        result["candidate_gate"] = {"passed": bool(all(conditions.values())), "conditions": {k: bool(v) for k, v in conditions.items()},
                                    "mse_ratio_ci95": interval.tolist()}
    return result, bootstrap
