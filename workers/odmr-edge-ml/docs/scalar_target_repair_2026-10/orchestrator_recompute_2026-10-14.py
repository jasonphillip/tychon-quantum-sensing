import json, sys, numpy as np
D = sys.argv[1]
z = np.load(f"{D}/evaluation/fresh_synthetic_holdout_predictions.npz", allow_pickle=False)
R = json.load(open(f"{D}/report/RESULTS.json"))["fresh_holdout"]
t = z["truth"].astype(np.float64); n = len(t)
def mae(k): return float(np.mean(np.abs(z[k].astype(np.float64) - t)))
rows = {"deployed__int8__bounded": mae("deployed__int8__bounded"), "deployed__fp32__bounded": mae("deployed__fp32__bounded"),
        "training_mean": mae("training_mean"), "training_median": mae("training_median"), "PID": mae("PID")}
seeds = ["42", "20261014", "20261015"]
arm_err = {}
for arm in ("A_clipped", "B_full_residual", "C_direct"):
    for prec in ("fp32", "int8"):
        errs = np.stack([np.abs(z[f"{arm}_seed{s}__{prec}"].astype(np.float64) - t) for s in seeds])
        per_seed = errs.mean(axis=1)
        rows[f"{arm}__{prec} (mean of seed MAEs)"] = float(per_seed.mean())
        for s, m in zip(seeds, per_seed): rows[f"  {arm}_seed{s}__{prec}"] = float(m)
        arm_err[(arm, prec)] = errs.mean(axis=0)   # seed-averaged per-row abs error
print("== recomputed MAE (uT) vs RESULTS.json")
rep_models = R["models"]; rep_base = R["baselines"]; rep_arm = R["arm_summary"]
def rep(k):
    if k in rep_models: return rep_models[k].get("mae_uT", rep_models[k].get("unbounded", {}).get("mae_uT"))
    if k in rep_base: return rep_base[k].get("mae_uT")
    return None
for k, v in rows.items():
    kk = k.strip().replace(" (mean of seed MAEs)", "")
    r = rep(kk)
    if r is None and kk in rep_arm:
        r = rep_arm[kk].get("mae_uT_mean_over_seeds", rep_arm[kk].get("mae_uT", rep_arm[kk]))
    print(f"{k:48s} {v:12.6f}   reported: {str(r)[:60]}")
print("== paired bootstrap CIs (fp32; seed-averaged per-row errors; seed 20261014; 10,000 resamples)")
const = np.abs(z["training_mean"].astype(np.float64) - t)
diffs = {"B_minus_A": arm_err[("B_full_residual","fp32")] - arm_err[("A_clipped","fp32")],
         "B_minus_training_mean": arm_err[("B_full_residual","fp32")] - const,
         "C_minus_B": arm_err[("C_direct","fp32")] - arm_err[("B_full_residual","fp32")],
         "C_minus_training_mean": arm_err[("C_direct","fp32")] - const}
for method in ("integers", "choice"):
    rng = np.random.default_rng(20261014)
    out = {}
    for name, d in diffs.items():
        if method == "integers": idx = rng.integers(0, n, size=(10000, n))
        else: idx = rng.choice(n, size=(10000, n), replace=True)
        means = d[idx].mean(axis=1)
        out[name] = (float(d.mean()), float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))
    print(f"-- method {method}")
    for name, (m, lo, hi) in out.items():
        r = R["paired_comparisons_fp32"].get(name, {})
        print(f"{name:24s} mean {m:10.6f}  CI [{lo:10.6f}, {hi:10.6f}]   reported: {str({k: (round(v,6) if isinstance(v,float) else v) for k,v in r.items() if k in ('mean_uT','ci_low_uT','ci_high_uT','mean','low','high','ci95')})[:90]}")
print("== B INT8 output range and endpoint occupancy")
for s in seeds:
    corr = z[f"B_full_residual_seed{s}__int8"].astype(np.float64) - z["pid"].astype(np.float64)
    print(f"seed {s}: correction range {corr.min():8.3f} .. {corr.max():8.3f} uT; at min {np.mean(np.isclose(corr, corr.min())):.3f}, at max {np.mean(np.isclose(corr, corr.max())):.3f}")
