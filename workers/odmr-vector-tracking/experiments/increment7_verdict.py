"""Increment-7 identity-recovery verdict — rules + arm specs declared PRE-HOC.

TVW dispatch-8 (`dispatch-8-increment7-identity-recovery-2026-07-08.md`). Committed BEFORE any
training result exists (house discipline; same as `increment6_verdict.py` at 6074f41). Goal: buy
back the in-cone identity v6 lost (v1 held misassoc 0.311→0.540) WITHOUT losing v6's acquisition
win and WITHOUT changing the deployed model's shape (frozen v3 data, frozen v6 architecture —
175,790 params, V250 whitelist; cues OFF; only the training signal changes). Baseline-to-beat:
**v6 @ 2f52d69 with the dispatch-7 re-decode policy** (held→baseline, ou/reversal→A3), inherited.

This module is BOTH the pre-declaration of the arm specs (imported by `increment7_train.py`) and
the verdict reader (run after the eval artifacts exist).

=================================  ARM SPECS (pre-hoc)  =================================

7a — geometry-weighted ("foveated") identity loss. Per-sequence multiplier on the association
term, keyed on `max_offbias_angle_deg`, then normalized so the TRAIN-set mean weight == 1.0 (the
assoc-vs-field balance is preserved; ONLY the angular distribution of identity gradient shifts).
Bins (lo_deg, hi_deg, raw_factor):
    (0, 30, 2.0)   — historic in-cone: 2x identity gradient (where identity was lost)
    (30, 45, 1.0)  — transition: unchanged
    (45, inf, 0.5) — wide angle: 0.5x (v6's acquisition win lives here; identity never the goal)
Field-lock/projection loss untouched.

7b — knowledge distillation. Unconstrained FP32 teacher (wider, off-target, throwaway, never
deployed): v6 config with feat_dim 32→64, assoc_dim 16→32, state_dim 64→128, conv_channels 8→16
(n_lines/n_freq/n_downsample/conv_kernel unchanged so the anchor grid K and score shape match the
student). Teacher trained on v3, same wave-2 recipe (snr10 aug, epochs 800, patience 100), seed
20260701, cues OFF. Student is byte-identical in shape to v6 (175,790 params); the association CE
is blended with the temperature-scaled KD soft target: assoc = (1−α)·CE + α·T²·KL(teacher‖student),
α = 0.5, T = 2.0 (Hinton 2015). One teacher distilled into 3 seeded students (20260701/11/21) —
student seed variation (init, minibatch order, per-epoch noise) stays genuine; the shared teacher
is noted as a mild correlation across the every-seed check.

7c — PCGrad (OPTIONAL). Two-task gradient projection: identity task = w_assoc·association, field
task = w_proj·projection; shared position/track added plain. Project on gradient conflict (Yu
2020). Students byte-identical to v6; seeds 20260701/11/21.

=================================  VERDICT RULES (pre-hoc)  ==============================

Roles are INVERTED vs increment-6: identity recovery is PRIMARY, acquisition is the HARD guard.

PRIMARY — in-cone identity recovery on the immutable v1 standing eval, evaluated at the
  dispatch-7 policy decode per family (held→baseline, ou/reversal→A3). Metric: in-collision
  misassoc (primary) + exit idsw_opp (reported). An arm CLEARS PRIMARY iff, on the headline
  regressed cell (held misassoc), it is CI-disjoint BELOW v6 AND every seed is below v6, at BOTH
  clean and snr30. Reversal/ou and idsw_opp are reported with the same CI+every-seed test.
  MATERIAL (vs marginal) iff held misassoc recovers ≥ half the v6 regression → ≤ ~0.425 (the
  0.311→0.540 slide). Recovered fraction (v6−arm)/(v6−v2_ref) reported per family × metric.

GUARD-A (HARD; the acquisition win we cannot lose):
  (i)  fieldcone directed geometries (bucket_class 0) stay lost=0 — pooled AND every seed — at
       clean+snr30 (v6 = 0/72).
  (ii) off-cone dwell lock (offcone/cross + offcone/bounce) is CI-neutral-or-better vs v6, every
       seed, clean+snr30 (v6 = 1–2/216 per population).
  Any acquisition regression → the arm is DROPPED regardless of identity gain.

GUARD-B — in-cone field lock: v1 standing-eval lock CI-neutral vs v6, per family × rung
  (decode-invariant; b_est untouched). A CI-disjoint lock regression trips it.

Report-only: classical parity (pid/kf/nls reproduce matrix_2c_final exactly — checkpoint-
  independent, asserted); snr3 leans; re-chart the fieldcone boundary if an arm survives.

Deployment-neutrality (every surviving candidate): trainable param count == 175,790 and the
  ops-guard passes with no new ops (asserted in `increment7_eval.py` / here via `assert_shape`).

KEEP-WHAT-SURVIVES: arms clearing PRIMARY with no GUARD-A/B trip survive. Multiple → strongest
  material identity recovery; tie → simpler arm (7a < 7c < 7b). None clears PRIMARY, OR all trip
  GUARD-A → keep nothing and STOP: escalate UP to TVW as the increment-8 capacity-tension trigger
  (do NOT start a capacity bump here).

    python experiments/increment7_verdict.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent

# ---------- Arm specs (pre-hoc; imported by increment7_train.py) ----------------------------
FOVEATED_BINS: tuple[tuple[float, float, float], ...] = (
    (0.0, 30.0, 2.0), (30.0, 45.0, 1.0), (45.0, float("inf"), 0.5),
)
TEACHER_CFG_OVERRIDES = {"feat_dim": 64, "assoc_dim": 32, "state_dim": 128, "conv_channels": 16}
KD_ALPHA = 0.5
KD_TEMP = 2.0
SEEDS = (20260701, 20260711, 20260721)
STUDENT_PARAMS = 175790  # v6 trainable param count — every candidate must match exactly


def foveated_weights(angles_deg: np.ndarray) -> np.ndarray:
    """Per-sequence foveated association weight, normalized to TRAIN-set mean 1.0 (arm 7a)."""
    a = np.asarray(angles_deg, dtype=np.float64)
    raw = np.ones_like(a)
    for lo, hi, factor in FOVEATED_BINS:
        raw[(a >= lo) & (a < hi)] = factor
    return (raw / raw.mean()).astype(np.float32)


# ---------- Verdict reader ------------------------------------------------------------------
NOISE = ("clean", "snr30", "snr10", "snr3")
SPLIT_RUNGS = ("clean", "snr30")
FAMILIES = ("held", "ou", "reversal")
POLICY = {"held": "baseline", "ou": "stack5", "reversal": "stack5"}  # dispatch-7 re-decode policy
POPS_OFF = ("offcone/cross", "offcone/bounce")
V6_SEEDS = ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
            "v3_gated_linear_snr10_s20260721")
V2_SEEDS = ("v2_gated_linear_snr10", "v2_gated_linear_snr10_s20260711",
            "v2_gated_linear_snr10_s20260721")
ARMS = ("7a", "7b", "7c")
ARM_PREFIX = {"7a": "fov", "7b": "kd", "7c": "pcgrad"}
ARM_SIMPLICITY = {"7a": 0, "7c": 1, "7b": 2}  # tie-break: simpler wins

INC7 = _REPO / "artifacts" / "increment7"
V6_REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_6_redecode.json"
V2_REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_redecode.json"
V6_DWELL = _REPO / "artifacts" / "increment6" / "coverage_split_v6.json"
V6_FIELDCONE = _REPO / "artifacts" / "increment6" / "fieldcone_v6.json"


def rate(kn: tuple[int, int]) -> float:
    k, n = kn
    return k / n if n else float("nan")


def cmp_ci(a: tuple[int, int], b: tuple[int, int]) -> str:
    """a vs b, lower better: improve / regress / neutral by Wilson-CI disjointness."""
    alo, ahi = wilson_ci(*a)
    blo, bhi = wilson_ci(*b)
    if ahi < blo:
        return "improve"
    if alo > bhi:
        return "regress"
    return "neutral"


def pool_redecode(cells: dict, seeds, decode: str, rung: str, fam: str, key: str) -> tuple[int, int]:
    k = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][0]) for s in seeds)
    n = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][1]) for s in seeds)
    return k, n


def seed_rates_redecode(cells: dict, seeds, decode: str, rung: str, fam: str, key: str) -> list[float]:
    return [rate((int(cells[rung][f"decode:{decode}"][s][fam][key][0]),
                  int(cells[rung][f"decode:{decode}"][s][fam][key][1]))) for s in seeds]


def arm_seed_names(arm: str) -> tuple[str, ...]:
    p = ARM_PREFIX[arm]
    return (f"{p}_gated_linear_snr10", f"{p}_gated_linear_snr10_s20260711",
            f"{p}_gated_linear_snr10_s20260721")


def evaluate_arm(arm: str) -> dict | None:
    """Read one arm's eval artifacts and score it against v6. None if artifacts absent."""
    d = INC7 / arm
    red_p, dwell_p, fc_p = d / "redecode.json", d / "dwell.json", d / "fieldcone.json"
    if not (red_p.exists() and dwell_p.exists() and fc_p.exists()):
        return None
    ared = json.load(open(red_p))["cells"]
    adw = json.load(open(dwell_p))["cells"]
    afc = json.load(open(fc_p))
    v6red = json.load(open(V6_REDECODE))["cells"]
    v2red = json.load(open(V2_REDECODE))["cells"]
    v6dw = json.load(open(V6_DWELL))["cells"]
    v6fc = json.load(open(V6_FIELDCONE))
    aseeds = arm_seed_names(arm)

    res: dict = {"arm": arm, "seeds": list(aseeds)}

    # ---- PRIMARY: in-cone identity recovery (policy decode per family) --------------------
    prim: dict = {}
    for fam in FAMILIES:
        dec = POLICY[fam]
        prim[fam] = {}
        for rung in NOISE:
            for key in ("misassoc", "idsw_opp"):
                a = pool_redecode(ared, aseeds, dec, rung, fam, key)
                v6 = pool_redecode(v6red, V6_SEEDS, dec, rung, fam, key)
                v2 = pool_redecode(v2red, V2_SEEDS, dec, rung, fam, key)
                ci = cmp_ci(a, v6)
                ar = seed_rates_redecode(ared, aseeds, dec, rung, fam, key)
                vr = seed_rates_redecode(v6red, V6_SEEDS, dec, rung, fam, key)
                every = all(x < y - 1e-12 for x, y in zip(ar, vr))
                span = rate(v6) - rate(v2)
                recov = (rate(v6) - rate(a)) / span if abs(span) > 1e-9 else float("nan")
                prim[fam][f"{rung}/{key}"] = {
                    "arm": rate(a), "v6": rate(v6), "v2": rate(v2), "ci_vs_v6": ci,
                    "every_seed_better": every, "recovered_frac": recov}
    # headline gate: held misassoc CI-improve + every-seed at clean AND snr30
    held_ok = all(prim["held"][f"{r}/misassoc"]["ci_vs_v6"] == "improve"
                  and prim["held"][f"{r}/misassoc"]["every_seed_better"] for r in SPLIT_RUNGS)
    held_arm_clean = prim["held"]["clean/misassoc"]["arm"]
    material = held_arm_clean <= 0.425
    res["primary"] = {"detail": prim, "clears": held_ok, "material": material,
                      "held_clean_misassoc": held_arm_clean,
                      "held_recovered_frac_clean": prim["held"]["clean/misassoc"]["recovered_frac"]}

    # ---- GUARD-A(i): fieldcone directed (bucket_class 0) stays 0 --------------------------
    bc = np.asarray(afc["bucket_class"])
    idx0 = np.flatnonzero(bc == 0)
    ga_dir_trip = False
    dir_detail = {}
    for rung in SPLIT_RUNGS:
        a_pool = sum(sum(int(afc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in aseeds)
        v6_pool = sum(sum(int(v6fc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in V6_SEEDS)
        per_seed = [sum(int(afc["cells"][rung][s]["lost_all"][i]) for i in idx0) for s in aseeds]
        n = len(idx0)
        # v6 directed = 0 → require arm pooled 0 and every seed 0
        trip = a_pool > v6_pool
        ga_dir_trip = ga_dir_trip or trip
        dir_detail[rung] = {"arm_lost": a_pool, "v6_lost": v6_pool, "n_per_seed": n,
                            "arm_per_seed": per_seed, "trip": trip}

    # ---- GUARD-A(ii): off-cone dwell lock CI-neutral-or-better vs v6 ----------------------
    ga_off_trip = False
    off_detail = {}
    for rung in SPLIT_RUNGS:
        for pop in POPS_OFF:
            a = (sum(int(adw[rung]["decode:baseline"][s][pop]["lock_loss"][0]) for s in aseeds),
                 sum(int(adw[rung]["decode:baseline"][s][pop]["lock_loss"][1]) for s in aseeds))
            v6 = (sum(int(v6dw[rung]["decode:baseline"][s][pop]["lock_loss"][0]) for s in V6_SEEDS),
                  sum(int(v6dw[rung]["decode:baseline"][s][pop]["lock_loss"][1]) for s in V6_SEEDS))
            ci = cmp_ci(a, v6)
            per_ok = []
            for sa, sv in zip(aseeds, V6_SEEDS):
                av = (int(adw[rung]["decode:baseline"][sa][pop]["lock_loss"][0]),
                      int(adw[rung]["decode:baseline"][sa][pop]["lock_loss"][1]))
                vv = (int(v6dw[rung]["decode:baseline"][sv][pop]["lock_loss"][0]),
                      int(v6dw[rung]["decode:baseline"][sv][pop]["lock_loss"][1]))
                per_ok.append(cmp_ci(av, vv) != "regress")
            trip = ci == "regress" or not all(per_ok)
            ga_off_trip = ga_off_trip or trip
            off_detail[f"{rung}/{pop}"] = {"arm": a, "v6": v6, "ci": ci,
                                           "per_seed_ok": per_ok, "trip": trip}
    res["guard_a"] = {"directed_trip": ga_dir_trip, "offcone_trip": ga_off_trip,
                      "trip": ga_dir_trip or ga_off_trip,
                      "directed": dir_detail, "offcone": off_detail}

    # ---- GUARD-B: v1 standing lock CI-neutral vs v6 (decode-invariant) --------------------
    gb_trips = []
    lock_detail = {}
    for rung in NOISE:
        for fam in FAMILIES:
            a = pool_redecode(ared, aseeds, "baseline", rung, fam, "lock_loss")
            v6 = pool_redecode(v6red, V6_SEEDS, "baseline", rung, fam, "lock_loss")
            ci = cmp_ci(a, v6)
            if ci == "regress":
                gb_trips.append(f"{rung}/{fam}")
            lock_detail[f"{rung}/{fam}"] = {"arm": a, "v6": v6, "ci": ci}
    res["guard_b"] = {"trips": gb_trips, "detail": lock_detail}

    res["survives"] = bool(res["primary"]["clears"]
                           and not res["guard_a"]["trip"] and not gb_trips)
    return res


def main() -> int:
    reports = {arm: evaluate_arm(arm) for arm in ARMS}
    present = {a: r for a, r in reports.items() if r is not None}
    if not present:
        print("[verdict] no arm eval artifacts under artifacts/increment7/<arm>/ yet — rules "
              "and arm specs are declared (pre-hoc). Re-run after training + increment7_eval.py.")
        return 1

    L: list[str] = []
    P = L.append
    P("# Increment-7 identity-recovery verdict\n")
    P("Pre-hoc rules (module docstring). Baseline-to-beat: v6 @ 2f52d69 + dispatch-7 policy "
      "(held→baseline, ou/reversal→A3). Wilson 95%; pooled 3 seeds; every-seed consistency.\n")

    survivors = []
    for arm in ARMS:
        r = present.get(arm)
        if r is None:
            P(f"\n## Arm {arm} — (not yet evaluated)\n")
            continue
        pr = r["primary"]
        P(f"\n## Arm {arm} ({ARM_PREFIX[arm]}) — "
          + ("**SURVIVES**" if r["survives"] else "does not survive") + "\n")
        P(f"- PRIMARY clears (held misassoc CI-improve + every-seed, clean+snr30): "
          f"**{pr['clears']}** | material (≤0.425): **{pr['material']}** | held clean misassoc "
          f"{pr['held_clean_misassoc']:.3f} (v6 0.540, v2 0.311; recovered "
          f"{pr['held_recovered_frac_clean']*100:.0f}%)")
        P(f"- GUARD-A trip: **{r['guard_a']['trip']}** "
          f"(directed {r['guard_a']['directed_trip']}, off-cone {r['guard_a']['offcone_trip']})")
        P(f"- GUARD-B lock trips: **{r['guard_b']['trips'] or 'none'}**")
        P("\n  PRIMARY identity (policy decode), held/ou/reversal misassoc by rung:")
        P("\n  | family | decode | clean arm/v6/v2 | snr30 | snr10 | snr3 | recov%(clean) |")
        P("  |---|---|---|---|---|---|--:|")
        for fam in FAMILIES:
            cells = []
            for rung in NOISE:
                c = pr["detail"][fam][f"{rung}/misassoc"]
                mark = "✓" if (c["ci_vs_v6"] == "improve" and c["every_seed_better"]) else \
                       ("✗" if c["ci_vs_v6"] == "regress" else "·")
                cells.append(f"{c['arm']:.3f}{mark}" if rung != "clean"
                             else f"{c['arm']:.3f}/{c['v6']:.3f}/{c['v2']:.3f}{mark}")
            rc = pr["detail"][fam]["clean/misassoc"]["recovered_frac"]
            P(f"  | {fam} | {POLICY[fam]} | {cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} "
              f"| {rc*100:.0f}% |")
        if r["survives"]:
            survivors.append(arm)

    # keep-what-survives
    P("\n## Decision (keep-what-survives)\n")
    if not survivors:
        all_ga = all((present[a]["guard_a"]["trip"] for a in present))
        none_primary = not any(present[a]["primary"]["clears"] for a in present)
        P(f"**KEEP NOTHING — STOP-AND-REPORT.** No arm survives "
          f"(all GUARD-A trip: {all_ga}; none clears PRIMARY: {none_primary}). This is the "
          "capacity-tension evidence → escalate UP to TVW as the increment-8 capacity-bump "
          "trigger. Do NOT start a capacity bump inside increment-7.")
        decision = "keep-nothing-escalate"
        kept = None
    else:
        def keyf(a: str) -> tuple:
            # strongest material recovery first (higher recovered frac), then simpler arm
            rc = present[a]["primary"]["held_recovered_frac_clean"]
            return (-rc, ARM_SIMPLICITY[a])
        survivors.sort(key=keyf)
        kept = survivors[0]
        P(f"**Survivors: {survivors}.** KEEP **{kept}** "
          + ("(sole survivor)" if len(survivors) == 1 else
             "(strongest material recovery; tie → simpler arm 7a<7c<7b).")
          + " NO default flip inside increment-7 — adoption is a separate TVW ruling.")
        decision = f"keep-{kept}"

    out = {"decision": decision, "kept": kept, "survivors": survivors,
           "reports": present}
    (INC7).mkdir(parents=True, exist_ok=True)
    (INC7 / "increment7_verdict.json").write_text(json.dumps(out, indent=1, default=float))
    (INC7 / "increment7_verdict.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[verdict] decision={decision} | wrote {INC7 / 'increment7_verdict.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
