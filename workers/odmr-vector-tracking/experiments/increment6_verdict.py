"""Increment-6 coverage-retrain verdict — rules declared PRE-HOC, before any result is read.

TVW dispatch 6 §2 (`dispatch-6-coverage-retrain-2026-07-07.md`), GO per audit Addendum C.
House pattern: Wilson 95% CI-disjoint, pooled 3 seeds, every-seed consistency, per-seed spread
reported, no single-seed claims. KF identity is reported conditioned-on-lock alongside
unconditioned (2c house rule as patched into increment-5 by dispatch-6 §1).

Inputs (produced AFTER this file is committed):
- `artifacts/noise_matrix/matrix_6_coverage.json` — tri-eval 1: the immutable v1 standing eval
  (`noise_matrix_report.py --only v1 --v1-runs artifacts/increment6/runs`), scoring pid/kf/nls
  + the three v6 checkpoints. v2 baseline cells come from the committed
  `artifacts/noise_matrix/matrix_2c_final.json` (fixed-seed noise makes cross-file comparison
  exact; increment-4's parity gate proved the reproduction).
- `artifacts/increment6/coverage_split_v6.json` — tri-eval 2 (PRIMARY) + finding (b):
  the increment-5 dwell coverage split re-scored at clean AND snr30 for v2 + v6 checkpoints
  and CV-KF, with per-sequence idsw/lock arrays retained for lock-conditioning.
  cells[rung][decode][gen/seed][pop] (learned) and cells[rung]["kf"][pop].
- `artifacts/increment6/fieldcone_v6.json` — tri-eval 3: per-sequence lock/acquisition arrays
  over `sequence_eval_fieldcone_v1` for v2 + v6 checkpoints and CV-KF at clean AND snr30,
  alongside the per-sequence bucket arrays (bucket_class 0 failure / 1 control / 2 beyond).

RULES (pre-hoc, fixed):

Part 1 — REGRESSION GUARD (immutable v1 standing eval).
  a) Classical parity gate: pid/kf/nls pooled counts (misassoc, idsw_opp, lock_loss, n_seq)
     must equal matrix_2c_final.json EXACTLY at every rung x family — any mismatch is an
     eval-path surprise = STOP-AND-REPORT (not a tunable).
  b) GUARD: for every rung in {clean,snr30,snr10,snr3} x family in {held,reversal,ou}:
     v6 pooled(3-seed) field lock_loss vs v2 pooled(3-seed) lock_loss must be CI-improve or
     CI-neutral. Any CI-disjoint regression = GUARD TRIP = stop-and-report (dispatch rule).
  c) Identity (misassoc, idsw_opp) at the same cells: REPORTED with CI verdicts both ways +
     per-seed spread; not a guard (dispatch scopes the guard to lock).

Part 2 — PRIMARY (dwell coverage split; the increment-5 discovery is the target).
  SUCCESS iff for BOTH off-cone populations (offcone/cross, offcone/bounce) at clean AND
  snr30: (i) v6 pooled(3-seed) lock_loss is CI-disjoint BELOW v2 pooled (v2 = 216/216 per
  population at clean), AND (ii) EVERY v6 seed individually is CI-disjoint below its v2
  per-seed counterpart (72/72). The new in/out-of-coverage split is reported honestly
  whatever it is. In-coverage lock (v2 baseline 0/216 per population) is reported with a CI
  verdict; any CI-disjoint in-coverage regression is FLAGGED in the decision (the formal stop
  guard remains Part 1, per the dispatch).

Part 3 — FIELDCONE boundary (report-only chart + one pre-hoc claim rule).
  Chart: pooled lock-loss (+ acquisition failure for cold starts) per bucket_class and per
  (target angle x target |B|) cell, v6 vs v2 vs KF-reference, per-seed spread. KF keeps its
  GT t=0 init (standing convention) — reference only, not a cold-acquisition comparator.
  CLAIM RULE: the widened-envelope claim ("v6 acquires/holds where v2 could not, inside the
  v3 envelope") is quotable iff, separately on bucket_class 0 (failure geometries) and
  bucket_class 1 (in-envelope control), pooled v6 lock-loss is CI-disjoint below pooled v2
  AND every v6 seed's rate is strictly below every v2 seed's rate, at clean AND snr30.
  bucket_class 2 (beyond-envelope probes: theta 66-70 deg, |B| 2.0-2.5 mT) is the
  generalization statement: REPORTED separately, NO claim pre-committed either way.

Part 4 — finding (b) re-measure (checkpoint-specific until reconfirmed).
  On the in-coverage dwell populations: exit identity (IDSW/opp) for v6 baseline + stack5(A3)
  vs CV-KF — KF both unconditioned and conditioned-on-lock (per-sequence arrays). The
  increment-5 balanced-topology claim RECONFIRMS on v6 iff at clean: (i) bounce: v6-A3 pooled
  CI-disjoint below KF conditioned-on-lock; (ii) topologies-pooled: same; (iii) every v6 seed
  individually CI-disjoint below the KF conditioned pooled figure on (i) and (ii). The cross
  margin is reported, NO claim (retracted at dispatch-6 §1; it stays retracted unless it
  clears the same CI-disjoint + every-seed bar vs KF conditioned). If Part 2 = SUCCESS,
  off-cone exit identity is reported as new territory (report-only, no pre-hoc claim).

DECISION:
  - Part 1a mismatch or Part 1b trip -> verdict = STOP-AND-REPORT (guard tripped).
  - else Part 2 SUCCESS -> increment SUCCEEDS; Part 3 claim per its rule; Part 4 status.
  - else -> coverage retrain FAILED to clear the acquisition gap; report everything honestly.
  Keep-what-survives: no defaults change in this increment either way; adoption is a
  separate, later decision (main promotion carries the verdict doc, not a default flip).

    python experiments/increment6_verdict.py
"""

from __future__ import annotations

import json
from pathlib import Path

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
MATRIX_V6 = _REPO / "artifacts" / "noise_matrix" / "matrix_6_coverage.json"
MATRIX_2C = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_final.json"
COVSPLIT = _REPO / "artifacts" / "increment6" / "coverage_split_v6.json"
FIELDCONE = _REPO / "artifacts" / "increment6" / "fieldcone_v6.json"
OUT_MD = _REPO / "artifacts" / "increment6" / "increment6_verdict.md"
OUT_JSON = _REPO / "artifacts" / "increment6" / "increment6_verdict.json"

V2_SEEDS = ("v2_gated_linear_snr10", "v2_gated_linear_snr10_s20260711",
            "v2_gated_linear_snr10_s20260721")
V6_SEEDS = ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
            "v3_gated_linear_snr10_s20260721")
FAMILIES = ("held", "reversal", "ou")
RUNGS = ("clean", "snr30", "snr10", "snr3")
SPLIT_RUNGS = ("clean", "snr30")
POPS_OFF = ("offcone/cross", "offcone/bounce")
POPS_COV = ("cov/cross", "cov/bounce")
CLASSICAL = ("pid", "kf", "nls")
BUCKET_NAMES = {0: "failure", 1: "control", 2: "beyond"}


def cell_key(seed: str) -> str:
    return f"learned-gated+linear+aug[{seed}]"


def rate(kn) -> float:
    k, n = kn
    return k / n if n else float("nan")


def cmp_ci(a: tuple[int, int], b: tuple[int, int]) -> str:
    """a vs b (lower better): improve / regress / neutral by Wilson-CI disjointness."""
    alo, ahi = wilson_ci(*a)
    blo, bhi = wilson_ci(*b)
    if ahi < blo:
        return "improve"
    if alo > bhi:
        return "regress"
    return "neutral"


def pool_matrix(cells: dict, seeds, rung: str, fam: str, key: str) -> tuple[int, int]:
    k = n = 0
    for s in seeds:
        v = cells[rung][cell_key(s)][fam][key]
        k += v[0]
        n += v[1]
    return int(k), int(n)


def main() -> int:
    missing = [p.name for p in (MATRIX_V6, COVSPLIT, FIELDCONE) if not p.exists()]
    if missing:
        print(f"[verdict] artifacts not yet produced: {missing} — rules are declared; "
              "re-run after the tri-eval.")
        return 1

    mv6 = json.load(open(MATRIX_V6))["datasets"]["v1"]["cells"]
    m2c = json.load(open(MATRIX_2C))["datasets"]["v1"]["cells"]
    cov = json.load(open(COVSPLIT))
    fc = json.load(open(FIELDCONE))

    L: list[str] = []
    P = L.append
    verdict: dict = {"parts": {}}
    P("# Increment-6 coverage-retrain verdict\n")
    P("Rules pre-hoc (committed before results; see module docstring). Wilson 95%; pooled "
      "3 seeds; every-seed consistency; KF identity conditioned-on-lock alongside "
      "unconditioned.\n")

    # ---- Part 1a: classical parity gate -------------------------------------------------------
    parity_bad: list[str] = []
    for rung in RUNGS:
        for kind in CLASSICAL:
            for fam in FAMILIES:
                for key in ("misassoc", "idsw_opp", "lock_loss"):
                    a = mv6[rung][kind][fam][key][:2]
                    b = m2c[rung][kind][fam][key][:2]
                    if [int(x) for x in a] != [int(x) for x in b]:
                        parity_bad.append(f"{kind}@{rung}/{fam}/{key} {a} != 2c {b}")
    P("## Part 1a — classical parity gate (pid/kf/nls must reproduce 2c exactly)\n")
    P("PASS — all classical cells reproduce matrix_2c_final.json exactly." if not parity_bad
      else "**FAIL — eval-path surprise (STOP)**:\n" + "\n".join(f"- {x}" for x in parity_bad))
    verdict["parts"]["parity"] = parity_bad

    # ---- Part 1b: lock regression guard -------------------------------------------------------
    P("\n## Part 1b — REGRESSION GUARD: v1 standing eval field lock, v6 vs v2\n")
    P("| rung | family | v2 lock | v6 lock | verdict | v6 per-seed |")
    P("|---|---|---|---|---|---|")
    guard_trips: list[str] = []
    for rung in RUNGS:
        for fam in FAMILIES:
            a = pool_matrix(mv6, V6_SEEDS, rung, fam, "lock_loss")
            b = pool_matrix(m2c, V2_SEEDS, rung, fam, "lock_loss")
            v = cmp_ci(a, b)
            if v == "regress":
                guard_trips.append(f"{rung}/{fam}")
            spread = [round(rate(mv6[rung][cell_key(s)][fam]["lock_loss"][:2]), 3)
                      for s in V6_SEEDS]
            P(f"| {rung} | {fam} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | "
              f"{v.upper() if v == 'regress' else v} | {spread} |")
    P(f"\nGuard trips: **{guard_trips or 'none'}**")
    verdict["parts"]["guard_trips"] = guard_trips

    # ---- Part 1c: identity on the standing eval (report-only) ---------------------------------
    P("\n## Part 1c — standing-eval identity (report-only)\n")
    P("| rung | family | metric | v2 | v6 | verdict |")
    P("|---|---|---|--:|--:|---|")
    for rung in RUNGS:
        for fam in FAMILIES:
            for key in ("misassoc", "idsw_opp"):
                a = pool_matrix(mv6, V6_SEEDS, rung, fam, key)
                b = pool_matrix(m2c, V2_SEEDS, rung, fam, key)
                P(f"| {rung} | {fam} | {key} | {rate(b):.3f} | {rate(a):.3f} | "
                  f"{cmp_ci(a, b)} |")

    # ---- Part 2: PRIMARY — dwell coverage split ------------------------------------------------
    P("\n## Part 2 — PRIMARY: dwell coverage split (off-cone acquisition must clear)\n")
    cc = cov["cells"]
    success = True
    P("| rung | pop | v2 lock (pooled) | v6 lock (pooled) | CI | per-seed CI-clears |")
    P("|---|---|---|---|---|---|")
    for rung in SPLIT_RUNGS:
        for pop in POPS_OFF:
            def pool_gen(gen_seeds, dec="decode:baseline"):
                k = n = 0
                for s in gen_seeds:
                    v = cc[rung][dec][s][pop]["lock_loss"]
                    k += v[0]
                    n += v[1]
                return int(k), int(n)
            a, b = pool_gen(V6_SEEDS), pool_gen(V2_SEEDS)
            ci = cmp_ci(a, b)
            seed_clears = []
            for s6, s2 in zip(V6_SEEDS, V2_SEEDS):
                av = cc[rung]["decode:baseline"][s6][pop]["lock_loss"][:2]
                bv = cc[rung]["decode:baseline"][s2][pop]["lock_loss"][:2]
                seed_clears.append(cmp_ci((int(av[0]), int(av[1])),
                                          (int(bv[0]), int(bv[1]))) == "improve")
            ok = ci == "improve" and all(seed_clears)
            success = success and ok
            P(f"| {rung} | {pop} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | {ci} | {seed_clears} |")
    P("\nIn-coverage lock (regression watch; v2 baseline 0 per population):")
    P("| rung | pop | v2 | v6 | verdict |")
    P("|---|---|---|---|---|")
    incov_flags: list[str] = []
    for rung in SPLIT_RUNGS:
        for pop in POPS_COV:
            def pool_gen2(gen_seeds):
                k = n = 0
                for s in gen_seeds:
                    v = cc[rung]["decode:baseline"][s][pop]["lock_loss"]
                    k += v[0]
                    n += v[1]
                return int(k), int(n)
            a, b = pool_gen2(V6_SEEDS), pool_gen2(V2_SEEDS)
            v = cmp_ci(a, b)
            if v == "regress":
                incov_flags.append(f"{rung}/{pop}")
            P(f"| {rung} | {pop} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | {v} |")
    P(f"\nPart 2 SUCCESS (pre-hoc rule): **{success}** | in-coverage flags: "
      f"{incov_flags or 'none'}")
    verdict["parts"]["primary_success"] = success
    verdict["parts"]["incov_flags"] = incov_flags

    # ---- Part 3: fieldcone boundary ------------------------------------------------------------
    P("\n## Part 3 — fieldcone boundary (v6 vs v2 vs KF-reference)\n")
    bc = fc["bucket_class"]
    claim_ok = True
    for rung in SPLIT_RUNGS:
        P(f"\n### rung = {rung}\n")
        P("| bucket | n | v2 lock (pooled) | v6 lock (pooled) | CI | v6 per-seed | kf (ref) |")
        P("|---|--:|---|---|---|---|---|")
        for cls in (0, 1, 2):
            idx = [i for i, c in enumerate(bc) if c == cls]
            def lost(gen_seeds):
                k = 0
                for s in gen_seeds:
                    la = fc["cells"][rung][s]["lost_all"]
                    k += sum(int(la[i]) for i in idx)
                return int(k), len(idx) * len(gen_seeds)
            a, b = lost(V6_SEEDS), lost(V2_SEEDS)
            kf_la = fc["cells"][rung]["kf"]["lost_all"]
            kf = (sum(int(kf_la[i]) for i in idx), len(idx))
            ci = cmp_ci(a, b)
            per6 = [round(sum(int(fc['cells'][rung][s]['lost_all'][i]) for i in idx)
                          / len(idx), 3) for s in V6_SEEDS]
            per2 = [round(sum(int(fc['cells'][rung][s]['lost_all'][i]) for i in idx)
                          / len(idx), 3) for s in V2_SEEDS]
            if cls in (0, 1):
                every = all(x < min(per2) for x in per6)
                claim_ok = claim_ok and ci == "improve" and every
            P(f"| {BUCKET_NAMES[cls]} | {len(idx)} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | {ci} | "
              f"{per6} | {kf[0]}/{kf[1]} |")
    P(f"\nWidened-envelope claim quotable (pre-hoc rule, classes 0+1, both rungs): "
      f"**{claim_ok}** — class 2 (beyond) is the generalization statement, no claim.")
    verdict["parts"]["fieldcone_claim"] = claim_ok

    # ---- Part 4: finding (b) re-measure --------------------------------------------------------
    P("\n## Part 4 — finding (b) balanced-topology identity on v6 (clean, in-coverage)\n")
    def pool_idsw(dec: str, seeds, pops, rung="clean") -> tuple[int, int]:
        k = n = 0
        for s in seeds:
            for pop in pops:
                v = cc[rung][dec][s][pop]["idsw_opp"]
                k += v[0]
                n += v[1]
        return int(k), int(n)

    def kf_idsw(pops, conditioned: bool, rung="clean") -> tuple[int, int]:
        k = n = 0
        for pop in pops:
            c = cc[rung]["kf"][pop]
            if not conditioned:
                v = c["idsw_opp"]
                k += v[0]
                n += v[1]
            else:
                for lost_flag, sw, op in zip(c["lost_all"], c["idsw_opp_switches_all"],
                                             c["idsw_opp_n_all"]):
                    if not lost_flag:
                        k += sw
                        n += op
        return int(k), int(n)

    recon = {}
    for label, pops in (("bounce", ["cov/bounce"]), ("pooled", list(POPS_COV)),
                        ("cross", ["cov/cross"])):
        a3 = pool_idsw("decode:stack5", V6_SEEDS, pops)
        kfu = kf_idsw(pops, conditioned=False)
        kfc = kf_idsw(pops, conditioned=True)
        ci = cmp_ci(a3, kfc)
        per_seed = [cmp_ci(pool_idsw("decode:stack5", [s], pops), kfc) == "improve"
                    for s in V6_SEEDS]
        recon[label] = {"a3": list(a3), "kf_uncond": list(kfu), "kf_cond": list(kfc),
                        "ci_vs_cond": ci, "seeds_clear": per_seed}
        P(f"- **{label}**: v6-A3 {a3[0]}/{a3[1]} = {rate(a3):.3f} vs KF uncond "
          f"{rate(kfu):.3f} / cond {rate(kfc):.3f} → vs-cond {ci}, seeds {per_seed}")
    reconfirmed = (recon["bounce"]["ci_vs_cond"] == "improve"
                   and all(recon["bounce"]["seeds_clear"])
                   and recon["pooled"]["ci_vs_cond"] == "improve"
                   and all(recon["pooled"]["seeds_clear"]))
    P(f"\nFinding (b) reconfirmed on v6 (pre-hoc rule; cross stays no-claim): "
      f"**{reconfirmed}**")
    verdict["parts"]["finding_b"] = {"reconfirmed": reconfirmed, "detail": recon}

    # ---- Decision -----------------------------------------------------------------------------
    P("\n## Decision\n")
    if parity_bad or guard_trips:
        P("**STOP-AND-REPORT: guard tripped** "
          f"(parity: {len(parity_bad)} mismatches; lock guard: {guard_trips}). "
          "Per dispatch: do not tune past a tripped guard.")
        decision = "guard-tripped"
    elif success:
        P("**Increment SUCCEEDS**: the off-cone acquisition failure clears per the pre-hoc "
          f"rule. Fieldcone claim quotable: {claim_ok}. Finding (b) reconfirmed: "
          f"{reconfirmed}. No defaults change in this increment (adoption is a separate "
          "decision).")
        decision = "success"
    else:
        P("**Coverage retrain FAILED to clear the acquisition gap** per the pre-hoc rule; "
          "the split above stands as the honest report.")
        decision = "failed-primary"
    verdict["decision"] = decision

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n")
    OUT_JSON.write_text(json.dumps(verdict, indent=1))
    print("\n".join(L))
    print(f"\n[verdict] decision={decision} | wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
