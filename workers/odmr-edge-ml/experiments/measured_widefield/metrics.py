"""Saved-output metrics; spatial blocks, not individual pixels, are uncertainty units."""
import numpy as np


def compare(targets, row_key, saved, seed, frozen_reference=None):
    methods = sorted(key[:-12] for key in saved if key.endswith("__prediction"))
    if not methods or targets.shape != (len(row_key), 9, 200) or not np.isfinite(targets).all():
        raise ValueError("Invalid measured references")
    groups = np.unique(row_key[:, 1])
    if len(groups) < 16:
        raise ValueError("Insufficient complete spatial groups")
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
        blocks[method] = np.asarray([losses[row_key[:, 1] == group].mean(axis=0) for group in groups])
        summaries[method] = {"mse": float(blocks[method][:, 0].mean()),
            "p90_patch_rmse": float(np.quantile(np.sqrt(losses[:, 0]), 0.9)),
            "failure_fraction": float(failed.mean()), "fit_reliable_fraction": float(reliable.mean()),
            "recorded_batch1_p95_seconds": float(np.quantile(seconds, 0.95)),
            "shift_mse": blocks[method].mean(axis=0).tolist(),
            "by_current_file_mse": {str(int(i)): float(losses[row_key[:, 0] == i, 0].mean()) for i in np.unique(row_key[:, 0])}}
    classical = [name for name in methods if name != "candidate"]
    reference = frozen_reference or min(classical, key=lambda name: (summaries[name]["mse"], name))
    if reference not in classical:
        raise ValueError("Frozen classical reference missing")
    baseline_gate = None
    if "raw" in summaries:
        baseline_gate = bool(summaries[reference]["mse"] <= 0.98 * summaries["raw"]["mse"]
                             and summaries[reference]["failure_fraction"] <= 0.01)
    result = {"status": "complete", "rows": len(row_key), "groups": len(groups), "reference": reference,
        "methods": summaries, "classical_development_gate": baseline_gate,
        "uncertainty_scope": "Conditional spatial-block bootstrap from one field of view; no independent acquisitions or calibrated field truth.",
        "candidate_gate": None}
    if "candidate" in summaries:
        candidate, ref = summaries["candidate"], summaries[reference]
        ratios = blocks["candidate"][bootstrap, 0].mean(axis=1) / np.maximum(blocks[reference][bootstrap, 0].mean(axis=1), 1e-20)
        interval = np.quantile(ratios, (0.025, 0.975))
        conditions = {
            "mse_improvement_at_least_5pct": candidate["mse"] <= 0.95 * ref["mse"],
            "paired_ratio_ci_upper_below_one": interval[1] < 1.0,
            "p90_rmse_no_more_than_2pct_worse": candidate["p90_patch_rmse"] <= 1.02 * ref["p90_patch_rmse"],
            "failure_fraction": candidate["failure_fraction"] <= min(0.01, ref["failure_fraction"] + 0.005),
            "all_registration_shifts_within_2pct": bool(np.all(np.asarray(candidate["shift_mse"]) <= 1.02 * np.asarray(ref["shift_mse"]))),
            "all_current_files_within_2pct": all(candidate["by_current_file_mse"][i] <= 1.02 * ref["by_current_file_mse"][i] for i in ref["by_current_file_mse"])}
        result["candidate_gate"] = {"passed": bool(all(conditions.values())), "conditions": {k: bool(v) for k, v in conditions.items()},
                                    "mse_ratio_ci95": interval.tolist()}
    return result, bootstrap
