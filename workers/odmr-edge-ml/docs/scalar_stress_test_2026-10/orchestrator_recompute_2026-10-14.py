import json, sys, numpy as np
D = sys.argv[1]
Sm = json.load(open(f"{D}/SUMMARY.json"))
cells = ["clean","realistic_anchor","wide_lines","low_snr","negative_slope","negative_offset","higher_contrast"]
z0 = np.load(f"{D}/clean_predictions.npz", allow_pickle=False); keys = sorted(z0.files)
print("prediction keys (clean):", len(keys)); print([k for k in keys if not k.startswith(("A_","B_full")) ][:40])
def truth(z):
    for k in ("truth","truth_uT","b_true_uT","magnitude_uT"):
        if k in z.files: return z[k].astype(np.float64)
    raise KeyError("truth")
def seed_avg_mae(z, prefix, suffix, t):
    ks = [k for k in z.files if k.startswith(prefix) and k.endswith(suffix) and "bounded" not in k]
    if not ks: return None, ks
    return float(np.mean([np.mean(np.abs(z[k].astype(np.float64)-t)) for k in ks])), ks
print(f"{'cell':18s} {'C_INT8':>9s} {'C_FP32':>9s} {'const':>9s} {'prior_fit':>9s} {'B_rankINT8':>10s} {'PID':>9s}   | SUMMARY (C_INT8 / const / prior)")
for c in cells:
    z = np.load(f"{D}/{c}_predictions.npz", allow_pickle=False); t = truth(z)
    ci,_ = seed_avg_mae(z, "pred__C_direct", "__int8", t); cf,_ = seed_avg_mae(z, "pred__C_direct", "__fp32", t)
    bi,_ = seed_avg_mae(z, "pred__B_full_residual", "__int8", t)
    const = float(np.mean(np.abs(z["pred__training_mean"].astype(np.float64)-t))) if "pred__training_mean" in z.files else None
    pk = [k for k in z.files if "prior" in k.lower() and "fit" in k.lower()]; pf = float(np.mean(np.abs(z[pk[0]].astype(np.float64)-t))) if pk else None
    pidk = [k for k in z.files if k.lower() in ("pred__pid","pid")]; pid = float(np.mean(np.abs(z[pidk[0]].astype(np.float64)-t))) if pidk else None
    sc = Sm["cells"].get(c, {}) if isinstance(Sm.get("cells"), dict) else {}
    def g(*path):
        o = sc
        for p in path:
            o = o.get(p, {}) if isinstance(o, dict) else {}
        return o if not isinstance(o, dict) else None
    rep = str({k: (round(v,5) if isinstance(v,(int,float)) else None) for k,v in (sc.items() if isinstance(sc,dict) else []) if isinstance(v,(int,float))})[:120]
    fmt = lambda v: f"{v:9.4f}" if isinstance(v,float) else f"{'n/a':>9s}"
    print(f"{c:18s} {fmt(ci)} {fmt(cf)} {fmt(const)} {fmt(pf)} {fmt(bi) if bi is None else f'{bi:10.3f}'} {fmt(pid)}   | {rep}")
print("primary_criterion_passed:", Sm.get("primary_criterion_passed"))
print("SUMMARY clean cell keys:", list(Sm["cells"]["clean"])[:12] if isinstance(Sm.get("cells"),dict) else type(Sm.get("cells")))
