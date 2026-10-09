"""Increment-8 B+C-stack verdict — ALL pre-declarations + verdict rules, committed PRE-HOC.

TVW dispatch-9 (`dispatch-9-increment8-bc-stack-2026-07-11.md`). Committed BEFORE any training
result exists (house discipline; same as `increment7_verdict.py`). This module is BOTH the
pre-declaration of the arm specs / hyperparameters (imported by `increment8_train.py`) and the
verdict reader (run after the local eval artifacts exist).

Goal: recover the in-cone line identity v6 lost (v1 held misassoc 0.311 → 0.540) **reliably
across seeds** (increment-7: single-teacher KD recovered it in 2/3 seeds, not every-seed —
reliability-at-fixed-capacity), WITHOUT losing v6's acquisition win and WITHOUT changing the
deployed model shape (frozen v3 data, frozen v6 architecture — 175,790 params, V250 whitelist;
cues OFF; only the training signal + trajectory control change). Baseline-to-beat: the
**`baseline-env` arm** — the unchanged increment-6 v6 recipe rerun ×5 seeds in the SAME AWS L4
environment (the training env is not bitwise-comparable to GB10; see docs/increment8_results.md
§0-ii). Decoders inherited: dispatch-7 policy (held→baseline, ou/reversal→A3=stack5).

=================================  PRE-DECLARATIONS (pre-hoc)  ==============================

Frozen recipe (every arm): `sequence_train_v3`, gated core + linear assoc, epochs 800 / batch 32
/ patience 100 / val_every 5, snr10 shot-noise augmentation, cues OFF, input_gain from the data.

- KD blend / temperature: alpha=0.5, T=2.0 (increment-7 7b verbatim; Hinton 2015).
- Teacher arch: v6 config with feat_dim 32->64, assoc_dim 16->32, state_dim 64->128,
  conv_channels 8->16 (n_lines/n_freq/n_downsample/conv_kernel unchanged so the anchor grid K and
  score shape match the student). Teacher size/patience held at the increment-7 value, NOT grown
  (Cho & Hariharan 1910.01348). Teachers throwaway, never deployed, never shipped outward.
- Ensemble averaging (bc/bc_sam): the k=5 teachers' **responses** are averaged — mean of the
  per-teacher temperature-scaled, logit-standardized softmax probabilities (NOT logit averaging).
  Response averaging is what buys the O(1/k) inter-student variance reduction (2601.18909).
- Logit standardization (bc/bc_sam): per-sample z-score of the association logits over the K-anchor
  class dim (eps 1e-7), applied to teacher AND student **inside the KD/KL soft-target term only**;
  the hard-CE term uses raw student logits, unchanged. Repairs the ~4x teacher/student logit-scale
  mismatch (2403.01427) without altering the hard-label objective.
- Weight-EMA (bc/bc_sam): decay 0.999 per optimizer step; the EMA weights are evaluated for early
  stopping AND are the deployed candidate (2411.18704 churn reduction).
- SAM (bc_sam only): rho=0.05 neighborhood radius; ~2x step cost (Foret 2020, 2010.01412).
- Shared trunk: all bc/bc_sam students warm-start from ONE trunk checkpoint trained (seed
  20260700, baseline recipe) to the branch epoch 40, then resume epochs 41..800 on the SAME
  cosine — a shared early-stability phase so the 5 branches stay in one basin (LMC, 1912.05671),
  which is also what makes the report-only soup valid (2203.05482).
- kd1 distills from `teacher_e1` alone (a single fixed ensemble member; the k=1 ablation point).
- Deployment-neutrality: trainable param count == 175,790 on every candidate; V250 ops-guard
  passes with no new ops.

=================================  VERDICT RULES (pre-hoc)  ================================

PRIMARY — in-cone identity recovery vs `baseline-env`, evaluated at the dispatch-7 policy decode
  per family (held->baseline, ou/reversal->stack5). Metric: in-collision misassoc (headline) +
  exit idsw_opp (reported). A candidate CLEARS PRIMARY iff, on the headline cell (held misassoc),
  it is CI-disjoint BELOW `baseline-env` AND every one of the n=5 seeds is below `baseline-env`,
  at BOTH clean and snr30. Reversal/ou and idsw_opp reported with the same CI+every-seed test.
  MATERIAL iff held clean misassoc recovers >= half the v6 regression:
  held <= base_held - 0.5*(base_held - v2_ref_held)  (~0.425 when base_held~0.540, v2~0.311).
  Report recovered fraction (base-arm)/(base-v2_ref) per family x metric AND per-seed pass counts
  for EVERY arm — the reliability measurement itself.

GUARD-A (HARD; the acquisition win we cannot lose):
  (i)  fieldcone directed geometries (bucket_class 0) stay lost=0 — pooled AND every seed — at
       clean+snr30 (baseline-env directed = 0/72 expected).
  (ii) off-cone dwell lock (offcone/cross + offcone/bounce) CI-neutral-or-better vs baseline-env,
       every seed, clean+snr30.
  Any acquisition regression -> the arm is DROPPED regardless of identity gain.

GUARD-B — in-cone field lock: v1 standing-eval lock CI-neutral vs baseline-env, per family x rung.

Report-only: kd1(k=1) vs bc(k=5) inter-student variance on held misassoc (the O(1/k) check);
  soup vs individual bc students; baseline-env vs GB10 v6 (environment shift — a MATERIAL shift on
  a guard surface is stop-and-report #1); classical parity exact; snr3 leans; deployment-neutrality
  (param count == 175,790 + ops-guard) per candidate; re-chart the fieldcone boundary if a
  candidate survives.

KEEP-WHAT-SURVIVES: candidates clearing PRIMARY with no GUARD-A/B trip survive. Multiple ->
  strongest material recovery; tie -> simpler arm (bc < bc_sam). None clears PRIMARY, OR all trip
  GUARD-A -> keep nothing and STOP: escalate UP to TVW on the options-audit ladder (family F
  collapse-exact expansion, then true capacity). NO default flip inside increment-8.

    python experiments/increment8_verdict.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent

# =====================  PRE-DECLARATIONS (imported by increment8_train.py)  =================
KD_ALPHA = 0.5
KD_TEMP = 2.0
TEACHER_CFG_OVERRIDES = {"feat_dim": 64, "assoc_dim": 32, "state_dim": 128, "conv_channels": 16}
ENSEMBLE_AVERAGE = "response"   # mean of per-teacher temperature-scaled standardized softmaxes
LOGIT_STANDARDIZE = True        # bc/bc_sam: z-score logits inside the KD/KL term only
EMA_DECAY = 0.999               # bc/bc_sam: weight-EMA decay, per optimizer step
SAM_RHO = 0.05                  # bc_sam only: SAM neighborhood radius
TRUNK_BRANCH_EPOCH = 40         # shared-trunk branch point (of the frozen 800-epoch schedule)
STUDENT_PARAMS = 175790         # every candidate must match exactly (deployment-neutrality)

# Frozen recipe (single source of truth for the train script).
EPOCHS = 800
BATCH_SIZE = 32
PATIENCE = 100
VAL_EVERY = 5
TRAIN_SNR = 10.0

TEACHER_SEEDS = (30260701, 30260702, 30260703, 30260704, 30260705)
STUDENT_SEEDS = (20260701, 20260711, 20260721, 20260731, 20260741)
TRUNK_SEED = 20260700
KD1_TEACHER = "teacher_e1"      # kd1's single teacher (first ensemble member; k=1 ablation)
N_TEACHERS = len(TEACHER_SEEDS)

# =====================  Verdict reader  ====================================================
NOISE = ("clean", "snr30", "snr10", "snr3")
SPLIT_RUNGS = ("clean", "snr30")
FAMILIES = ("held", "ou", "reversal")
POLICY = {"held": "baseline", "ou": "stack5", "reversal": "stack5"}  # dispatch-7 re-decode policy
POPS_OFF = ("offcone/cross", "offcone/bounce")

# Arms scored against baseline-env; baseline-env is the baseline, not a candidate. kd1 is
# EVALUATED + reported (the k=1 ablation for the O(1/k) check) but is REPORT-ONLY — only bc and
# bc_sam are adoption candidates that can be "kept" (dispatch-9 arms table).
BASELINE_ARM = "baseline_env"
CANDIDATE_ARMS = ("kd1", "bc", "bc_sam")   # all evaluated + reported
ADOPTION_ARMS = ("bc", "bc_sam")           # only these can survive/be kept
ARM_PREFIX = {"baseline_env": "baseline", "kd1": "kd1", "bc": "bc", "bc_sam": "bc_sam"}
ARM_SIMPLICITY = {"bc": 0, "bc_sam": 1}    # tie-break: simpler wins (bc < bc_sam)

INC8 = _REPO / "artifacts" / "increment8"
V2_REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_redecode.json"   # GB10 v2 id ref
V6_REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_6_redecode.json"    # GB10 v6 (env x-chk)
V2_SEEDS = ("v2_gated_linear_snr10", "v2_gated_linear_snr10_s20260711",
            "v2_gated_linear_snr10_s20260721")
V6_SEEDS = ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
            "v3_gated_linear_snr10_s20260721")


def rate(kn) -> float:
    k, n = kn[0], kn[1]
    return k / n if n else float("nan")


def cmp_ci(a, b) -> str:
    """a vs b, lower better: improve / regress / neutral by Wilson-CI disjointness."""
    alo, ahi = wilson_ci(int(a[0]), int(a[1]))
    blo, bhi = wilson_ci(int(b[0]), int(b[1]))
    if ahi < blo:
        return "improve"
    if alo > bhi:
        return "regress"
    return "neutral"


def arm_run_names(arm: str) -> tuple[str, ...]:
    p = ARM_PREFIX[arm]
    return tuple(f"{p}_s{seed}" for seed in STUDENT_SEEDS)


def pool_redecode(cells, seeds, decode, rung, fam, key):
    k = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][0]) for s in seeds)
    n = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][1]) for s in seeds)
    return k, n


def seed_rates_redecode(cells, seeds, decode, rung, fam, key):
    return [rate((int(cells[rung][f"decode:{decode}"][s][fam][key][0]),
                  int(cells[rung][f"decode:{decode}"][s][fam][key][1]))) for s in seeds]


def _load_arm(arm: str) -> dict | None:
    d = INC8 / arm
    red_p, dwell_p, fc_p = d / "redecode.json", d / "dwell.json", d / "fieldcone.json"
    if not (red_p.exists() and dwell_p.exists() and fc_p.exists()):
        return None
    return {"red": json.load(open(red_p))["cells"], "dwell": json.load(open(dwell_p))["cells"],
            "fc": json.load(open(fc_p))}


def evaluate_candidate(arm: str, base: dict, v2red: dict) -> dict | None:
    """Score one candidate arm against the in-environment baseline-env arm. None if absent."""
    A = _load_arm(arm)
    if A is None:
        return None
    ared, adw, afc = A["red"], A["dwell"], A["fc"]
    bred, bdw, bfc = base["red"], base["dwell"], base["fc"]
    aseeds = arm_run_names(arm)
    bseeds = arm_run_names(BASELINE_ARM)
    res: dict = {"arm": arm, "seeds": list(aseeds)}

    # ---- PRIMARY: in-cone identity recovery (policy decode per family) --------------------
    prim: dict = {}
    for fam in FAMILIES:
        dec = POLICY[fam]
        prim[fam] = {}
        for rung in NOISE:
            for key in ("misassoc", "idsw_opp"):
                a = pool_redecode(ared, aseeds, dec, rung, fam, key)
                b = pool_redecode(bred, bseeds, dec, rung, fam, key)
                v2 = pool_redecode(v2red, V2_SEEDS, dec, rung, fam, key)
                ci = cmp_ci(a, b)
                ar = seed_rates_redecode(ared, aseeds, dec, rung, fam, key)
                br = seed_rates_redecode(bred, bseeds, dec, rung, fam, key)
                every = all(x < y - 1e-12 for x, y in zip(ar, br))
                n_pass = sum(1 for x, y in zip(ar, br) if x < y - 1e-12)
                span = rate(b) - rate(v2)
                recov = (rate(b) - rate(a)) / span if abs(span) > 1e-9 else float("nan")
                prim[fam][f"{rung}/{key}"] = {
                    "arm": rate(a), "base": rate(b), "v2": rate(v2), "ci_vs_base": ci,
                    "every_seed_better": every, "n_seed_pass": n_pass, "arm_seed_rates": ar,
                    "recovered_frac": recov}
    held_ok = all(prim["held"][f"{r}/misassoc"]["ci_vs_base"] == "improve"
                  and prim["held"][f"{r}/misassoc"]["every_seed_better"] for r in SPLIT_RUNGS)
    held_arm_clean = prim["held"]["clean/misassoc"]["arm"]
    base_held = prim["held"]["clean/misassoc"]["base"]
    v2_held = prim["held"]["clean/misassoc"]["v2"]
    material_thresh = base_held - 0.5 * (base_held - v2_held)
    res["primary"] = {"detail": prim, "clears": held_ok,
                      "material": held_arm_clean <= material_thresh,
                      "material_thresh": material_thresh,
                      "held_clean_misassoc": held_arm_clean,
                      "held_recovered_frac_clean": prim["held"]["clean/misassoc"]["recovered_frac"]}

    # ---- GUARD-A(i): fieldcone directed (bucket_class 0) stays 0 --------------------------
    bc_cls = np.asarray(afc["bucket_class"])
    idx0 = np.flatnonzero(bc_cls == 0)
    ga_dir_trip = False
    dir_detail = {}
    for rung in SPLIT_RUNGS:
        a_pool = sum(sum(int(afc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in aseeds)
        b_pool = sum(sum(int(bfc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in bseeds)
        per_seed = [sum(int(afc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in aseeds]
        trip = a_pool > b_pool
        ga_dir_trip = ga_dir_trip or trip
        dir_detail[rung] = {"arm_lost": a_pool, "base_lost": b_pool, "n_geoms": int(len(idx0)),
                            "arm_per_seed": per_seed, "trip": trip}

    # ---- GUARD-A(ii): off-cone dwell lock CI-neutral-or-better vs baseline-env ------------
    ga_off_trip = False
    off_detail = {}
    for rung in SPLIT_RUNGS:
        for pop in POPS_OFF:
            a = (sum(int(adw[rung]["decode:baseline"][s][pop]["lock_loss"][0]) for s in aseeds),
                 sum(int(adw[rung]["decode:baseline"][s][pop]["lock_loss"][1]) for s in aseeds))
            b = (sum(int(bdw[rung]["decode:baseline"][s][pop]["lock_loss"][0]) for s in bseeds),
                 sum(int(bdw[rung]["decode:baseline"][s][pop]["lock_loss"][1]) for s in bseeds))
            ci = cmp_ci(a, b)
            per_ok = []
            for sa, sb in zip(aseeds, bseeds):
                av = (int(adw[rung]["decode:baseline"][sa][pop]["lock_loss"][0]),
                      int(adw[rung]["decode:baseline"][sa][pop]["lock_loss"][1]))
                bv = (int(bdw[rung]["decode:baseline"][sb][pop]["lock_loss"][0]),
                      int(bdw[rung]["decode:baseline"][sb][pop]["lock_loss"][1]))
                per_ok.append(cmp_ci(av, bv) != "regress")
            trip = ci == "regress" or not all(per_ok)
            ga_off_trip = ga_off_trip or trip
            off_detail[f"{rung}/{pop}"] = {"arm": a, "base": b, "ci": ci,
                                           "per_seed_ok": per_ok, "trip": trip}
    res["guard_a"] = {"directed_trip": ga_dir_trip, "offcone_trip": ga_off_trip,
                      "trip": ga_dir_trip or ga_off_trip,
                      "directed": dir_detail, "offcone": off_detail}

    # ---- GUARD-B: v1 standing lock CI-neutral vs baseline-env (decode-invariant) ----------
    gb_trips = []
    lock_detail = {}
    for rung in NOISE:
        for fam in FAMILIES:
            a = pool_redecode(ared, aseeds, "baseline", rung, fam, "lock_loss")
            b = pool_redecode(bred, bseeds, "baseline", rung, fam, "lock_loss")
            ci = cmp_ci(a, b)
            if ci == "regress":
                gb_trips.append(f"{rung}/{fam}")
            lock_detail[f"{rung}/{fam}"] = {"arm": a, "base": b, "ci": ci}
    res["guard_b"] = {"trips": gb_trips, "detail": lock_detail}

    res["survives"] = bool(res["primary"]["clears"]
                           and not res["guard_a"]["trip"] and not gb_trips)
    return res


def _held_seed_rates(arm: str, base: dict | None = None):
    """Per-seed held clean-misassoc rates for an arm (for the O(1/k) variance report)."""
    A = _load_arm(arm)
    if A is None:
        return None
    return seed_rates_redecode(A["red"], arm_run_names(arm), POLICY["held"], "clean",
                               "held", "misassoc")


def report_only(present: dict) -> dict:
    """Report-only measurements (do not gate the verdict): O(1/k), soup, environment shift."""
    rep: dict = {}
    # --- O(1/k): inter-student variance kd1 (k=1) vs bc (k=5) on held clean misassoc ---
    kd1 = _held_seed_rates("kd1")
    bc = _held_seed_rates("bc")
    if kd1 and bc:
        v1, v5 = float(np.var(kd1)), float(np.var(bc))
        rep["ok_variance"] = {"kd1_seed_rates": kd1, "bc_seed_rates": bc,
                              "kd1_var": v1, "bc_var": v5,
                              "var_ratio_kd1_over_bc": (v1 / v5 if v5 > 0 else float("inf")),
                              "oned_over_k_prediction": float(N_TEACHERS),
                              "kd1_std": float(np.std(kd1)), "bc_std": float(np.std(bc))}
    # --- soup vs individual bc students (held clean misassoc) ---
    soup = _load_arm("soup")
    if soup is not None and bc:
        sr = seed_rates_redecode(soup["red"], list(soup["red"]["clean"]["decode:baseline"].keys()),
                                 POLICY["held"], "clean", "held", "misassoc")
        rep["soup"] = {"soup_held_misassoc": sr, "bc_individual_held": bc,
                       "beats_every_individual": (len(sr) == 1 and all(sr[0] < b for b in bc))}
    # --- environment shift: baseline-env vs GB10 v6 (matrix_6_redecode) ---
    base = _load_arm(BASELINE_ARM)
    if base is not None and V6_REDECODE.exists():
        v6 = json.load(open(V6_REDECODE))["cells"]
        bseeds = arm_run_names(BASELINE_ARM)
        shift = {}
        material = False
        for fam in FAMILIES:
            for key in ("misassoc", "lock_loss"):
                a = pool_redecode(base["red"], bseeds, "baseline", "clean", fam, key)
                g = pool_redecode(v6, V6_SEEDS, "baseline", "clean", fam, key)
                ci = cmp_ci(a, g)
                shift[f"{fam}/{key}"] = {"baseline_env": rate(a), "gb10_v6": rate(g), "ci": ci}
                if key == "lock_loss" and ci != "neutral":
                    material = True  # a lock (guard-surface) shift is the material one
        rep["env_shift"] = {"detail": shift, "material_guard_surface_shift": material}
    return rep


def main() -> int:
    if not V2_REDECODE.exists():
        print(f"[verdict] missing v2 reference {V2_REDECODE} — cannot score recovered fraction.")
    v2red = json.load(open(V2_REDECODE))["cells"] if V2_REDECODE.exists() else {}
    base = _load_arm(BASELINE_ARM)
    if base is None:
        print("[verdict] baseline-env artifacts absent under artifacts/increment8/baseline_env/ "
              "— rules + pre-declarations are committed (pre-hoc). Re-run after training + "
              "increment8_eval.py produces every arm's redecode/dwell/fieldcone.json.")
        return 1

    reports = {a: evaluate_candidate(a, base, v2red) for a in CANDIDATE_ARMS}
    present = {a: r for a, r in reports.items() if r is not None}
    rep = report_only(present)

    L: list[str] = []
    P = L.append
    P("# Increment-8 B+C-stack verdict\n")
    P("Pre-hoc rules (module docstring). Baseline: the `baseline-env` arm (increment-6 v6 recipe "
      "rerun x5 seeds in the same AWS L4 environment). Decode: dispatch-7 policy "
      "(held->baseline, ou/reversal->A3/stack5). Wilson 95%; pooled 5 seeds; every-seed (n=5).\n")

    survivors = []
    for arm in CANDIDATE_ARMS:
        r = present.get(arm)
        if r is None:
            P(f"\n## Arm {arm} — (not yet evaluated)\n")
            continue
        pr = r["primary"]
        adoption = arm in ADOPTION_ARMS
        if adoption:
            label = "**SURVIVES**" if r["survives"] else "does not survive"
        else:
            label = "(report-only — k=1 ablation, not an adoption candidate)"
        P(f"\n## Arm {arm} — " + label + "\n")
        P(f"- PRIMARY clears (held misassoc CI-improve + every-seed n=5, clean+snr30): "
          f"**{pr['clears']}** | material (<= {pr['material_thresh']:.3f}): **{pr['material']}** | "
          f"held clean misassoc {pr['held_clean_misassoc']:.3f} "
          f"(recovered {pr['held_recovered_frac_clean']*100:.0f}% toward v2)")
        P(f"- GUARD-A trip: **{r['guard_a']['trip']}** "
          f"(directed {r['guard_a']['directed_trip']}, off-cone {r['guard_a']['offcone_trip']})")
        P(f"- GUARD-B lock trips: **{r['guard_b']['trips'] or 'none'}**")
        P("\n  PRIMARY identity (policy decode) — held/ou/reversal misassoc, arm(pass/5) vs base:")
        P("\n  | family | decode | clean arm/base/v2 (pass/5) | snr30 | snr10 | snr3 | recov% |")
        P("  |---|---|---|---|---|---|--:|")
        for fam in FAMILIES:
            cells = []
            for rung in NOISE:
                c = pr["detail"][fam][f"{rung}/misassoc"]
                mark = "✓" if (c["ci_vs_base"] == "improve" and c["every_seed_better"]) else \
                       ("✗" if c["ci_vs_base"] == "regress" else "·")
                if rung == "clean":
                    cells.append(f"{c['arm']:.3f}/{c['base']:.3f}/{c['v2']:.3f} "
                                 f"({c['n_seed_pass']}/5){mark}")
                else:
                    cells.append(f"{c['arm']:.3f} ({c['n_seed_pass']}/5){mark}")
            rc = pr["detail"][fam]["clean/misassoc"]["recovered_frac"]
            P(f"  | {fam} | {POLICY[fam]} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} "
              f"| {rc*100:.0f}% |")
        if adoption and r["survives"]:
            survivors.append(arm)

    # --- report-only ---
    P("\n## Report-only\n")
    if "ok_variance" in rep:
        ov = rep["ok_variance"]
        P(f"- **O(1/k) inter-student variance (held clean misassoc):** kd1(k=1) var {ov['kd1_var']:.4f} "
          f"(std {ov['kd1_std']:.3f}), bc(k=5) var {ov['bc_var']:.4f} (std {ov['bc_std']:.3f}); "
          f"ratio kd1/bc = {ov['var_ratio_kd1_over_bc']:.2f} (O(1/k) predicts ~{ov['oned_over_k_prediction']:.0f}x).")
        P(f"  - kd1 seed rates {['%.3f' % x for x in ov['kd1_seed_rates']]}; "
          f"bc seed rates {['%.3f' % x for x in ov['bc_seed_rates']]}")
    if "soup" in rep:
        sp = rep["soup"]
        P(f"- **Soup vs individuals (held clean misassoc):** soup {['%.3f' % x for x in sp['soup_held_misassoc']]} "
          f"vs bc {['%.3f' % x for x in sp['bc_individual_held']]} — beats every individual: "
          f"**{sp['beats_every_individual']}** (increment-9 material if True; report, do not adopt).")
    if "env_shift" in rep:
        es = rep["env_shift"]
        P(f"- **Environment shift (baseline-env vs GB10 v6, clean):** "
          f"material guard-surface (lock) shift: **{es['material_guard_surface_shift']}** "
          + ("→ STOP-AND-REPORT #1 (environment problem, not science)."
             if es["material_guard_surface_shift"] else "(within noise)."))
        for k, v in es["detail"].items():
            P(f"  - {k}: env {v['baseline_env']:.3f} vs GB10 {v['gb10_v6']:.3f} ({v['ci']})")

    # --- keep-what-survives ---
    P("\n## Decision (keep-what-survives)\n")
    if not survivors:
        adopt = [a for a in ADOPTION_ARMS if a in present]
        all_ga = bool(adopt) and all(present[a]["guard_a"]["trip"] for a in adopt)
        none_primary = not any(present[a]["primary"]["clears"] for a in adopt)
        P(f"**KEEP NOTHING — STOP-AND-REPORT.** No candidate survives "
          f"(all GUARD-A trip: {all_ga}; none clears PRIMARY: {none_primary}). Escalate UP to TVW "
          "on the options-audit ladder (family F collapse-exact expansion, then true capacity). "
          "NO default flip inside increment-8.")
        decision, kept = "keep-nothing-escalate", None
    else:
        def keyf(a: str):
            return (-present[a]["primary"]["held_recovered_frac_clean"], ARM_SIMPLICITY[a])
        survivors.sort(key=keyf)
        kept = survivors[0]
        P(f"**Survivors: {survivors}.** KEEP **{kept}** "
          + ("(sole survivor)" if len(survivors) == 1 else
             "(strongest material recovery; tie -> simpler arm bc < bc_sam).")
          + " NO default flip inside increment-8 — adoption is a separate TVW ruling.")
        decision, kept = f"keep-{kept}", kept

    out = {"decision": decision, "kept": kept, "survivors": survivors,
           "candidates": present, "report_only": rep}
    INC8.mkdir(parents=True, exist_ok=True)
    (INC8 / "increment8_verdict.json").write_text(json.dumps(out, indent=1, default=float))
    (INC8 / "increment8_verdict.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[verdict] decision={decision} | wrote {INC8 / 'increment8_verdict.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
