"""Dispatch-7 — re-select the per-family re-decode policy on the v6 checkpoints (PRE-HOC).

TVW dispatch 7 (`dispatch-7-v6-default-2026-07-08.md`), issued from the increment-6 SUCCESS
verdict (`docs/increment6_results.md`, main b102cf3) and the TVW deploy ruling
(`audit-dwell-program-2026-07-07.md` Addendum D). Zero-retrain, evaluation-and-config only:
the deployed re-decode policy (A3 on OU/reversal, baseline on held) was selected from **v2's**
2c matrix and does NOT automatically transfer to the coverage-retrained v6 weights — re-select
before the default flip. This is the dispatch-7 policy flip, NOT increment-7 (the
identity-recovery retrain is dispatch-8, branch `increment-7-identity-recovery`, not issued).

The rules below are declared PRE-HOC — this file is committed before `matrix_6_redecode.json`
and the dwell menu exist (same discipline as `increment6_verdict.py`, committed at 6074f41
before any increment-6 result). Run it AFTER the matrices are produced; it self-guards on
missing inputs and returns 1 with the rules still on record.

STANDING MENU (no new decoders — the 2c/increment-4 menu):
  baseline  – deployed per-slot readout ``track_pos``
  A1        = ``physics``  – physics-anchored decode from ``b_est`` (no scores)
  A3        = ``stack5``   – A2 smoothed scores biased by A1's physics prior + physics fallback,
                            latency 5 frames.  A3 and "stack5" are the SAME decode (the dispatch
                            lists both as menu members; they collapse to one).
The field estimate ``b_est`` is untouched by every decode, so FIELD / lock metrics are identical
across the menu (``identity_redecode.py`` asserts this at build). A re-decode can only move
identity, never the lock/vector claim.

V2-ERA DEPLOYED POLICY (the continuity baseline — what a tie keeps):
  standing eval:  held -> baseline ;  ou -> A3(stack5) ;  reversal -> A3(stack5)
  dwell through-merge identity claim (finding b):  A3(stack5)

SELECTION RULE (pre-hoc, fixed) — surface (a), the deployable per-family policy:
  Metric = misassoc (in-collision mis-assignment rate; lower better), idsw_opp reported
  alongside. Pool the 3 v6 seeds; Wilson 95% CI. For family F with v2-era default decode d0:
  a candidate decode d != d0 SWITCHES F iff
    (i)  d is CI-disjoint BELOW d0 AND every individual seed improves (sign-consistent),
         at BOTH clean and snr30 — the identity-measurable regime where the 2c policy was
         chosen (increment-4 `survives()` used exactly clean+snr30); AND
    (ii) d does NOT CI-regress vs d0 at ANY of the four rungs {clean,snr30,snr10,snr3}.
  If several candidates qualify, take the lowest pooled clean+snr30 misassoc. Ties / nothing
  qualifying -> KEEP d0 (continuity with the v2-era policy).

SURFACES (b) dwell in-coverage and (c) off-cone dwell (report which decode wins there):
  Menu evaluated on exit identity (idsw_opp) per dwell population; CI-disjoint + every-seed to
  name a winner over the v2-era dwell decode A3. Because every menu decode shares the same
  per-sequence lock (b_est identical), conditioning-on-lock would filter the same sequences for
  all three, so the relative winner is invariant to conditioning — the unconditioned idsw_opp
  comparison is used for the menu winner. The A3-vs-KF finding-(b) claim (KF conditioned-on-lock)
  is a separate, already-established increment-6 result and is quoted, not recomputed.

STOP-AND-REPORT (do not flip if any fires):
  1. LOCK/FIELD guard: a standing family F x rung where NO menu decode is CI-neutral-or-better
     vs the v2-era default on lock. Lock is decode-invariant, so this reduces to: v6 checkpoint
     field lock (pooled) CI-regressed vs v2 checkpoint field lock at that F x rung. Equivalent
     to increment-6 Part 1b (which passed CI-neutral on all 12 cells); re-asserted here.
  2. Integrity: `matrix_6_redecode.json` decode:baseline must reproduce the learned column of
     `matrix_6_coverage.json` EXACTLY (fixed-seed noise) — a mismatch is an eval-path surprise.
  3. (v6 checkpoint md5s vs the increment-6 run record — checked in the flip doc, not here.)

    python experiments/v6_redecode_policy.py
Writes `artifacts/increment6/v6_redecode_policy.{json,md}`.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import h5py
import numpy as np
import torch

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "experiments"))

import identity_redecode as ir  # noqa: E402
import noise_matrix_report as nmr  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.data.contract import validate_dataset_dir  # noqa: E402
from odmr_vector_tracking.tracking import redecode as rd  # noqa: E402
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8  # noqa: E402

MATRIX_REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_6_redecode.json"
MATRIX_V6_COV = _REPO / "artifacts" / "noise_matrix" / "matrix_6_coverage.json"
MATRIX_2C = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_final.json"
COVSPLIT = _REPO / "artifacts" / "increment6" / "coverage_split_v6.json"
OUT_JSON = _REPO / "artifacts" / "increment6" / "v6_redecode_policy.json"
OUT_MD = _REPO / "artifacts" / "increment6" / "v6_redecode_policy.md"

DWELL = _REPO / "data" / "sequence_dwell_v1"
V1_DIR = _REPO / "data" / "sequence_train_v1"

V6_SEEDS = ("v3_gated_linear_snr10", "v3_gated_linear_snr10_s20260711",
            "v3_gated_linear_snr10_s20260721")
V2_SEEDS = ir.BASELINE_SEEDS
V6_RUNS = _REPO / "artifacts" / "increment6" / "runs"

MENU = ("baseline", "physics", "stack5")  # baseline / A1=physics / A3=stack5
NAME = {"baseline": "baseline", "physics": "A1(physics)", "stack5": "A3(stack5)"}
V2_ERA_STANDING = {"held": "baseline", "ou": "stack5", "reversal": "stack5"}
V2_ERA_DWELL = "stack5"
FAMILIES = ("held", "ou", "reversal")
ALL_RUNGS = ("clean", "snr30", "snr10", "snr3")
SELECT_RUNGS = ("clean", "snr30")
IN_COVERAGE_TEMPLATES = (0, 1)
DWELL_RUNGS = (("clean", None), ("snr30", 30.0))


def cmp_ci(a: tuple[int, int], b: tuple[int, int]) -> str:
    """a vs b, lower better: improve / regress / neutral by Wilson-CI disjointness."""
    alo, ahi = wilson_ci(*a)
    blo, bhi = wilson_ci(*b)
    if ahi < blo:
        return "improve"
    if alo > bhi:
        return "regress"
    return "neutral"


def pool_std(cells: dict, seeds: tuple[str, ...], decode: str, rung: str, fam: str,
             key: str) -> tuple[int, int]:
    """Pool a standing-eval re-decode cell (matrix_6_redecode) over seeds."""
    k = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][0]) for s in seeds)
    n = sum(int(cells[rung][f"decode:{decode}"][s][fam][key][1]) for s in seeds)
    return k, n


def per_seed_rates(cells: dict, seeds: tuple[str, ...], decode: str, rung: str, fam: str,
                   key: str) -> list[float]:
    out = []
    for s in seeds:
        k, n = cells[rung][f"decode:{decode}"][s][fam][key][:2]
        out.append(k / n if n else float("nan"))
    return out


def rate(kn: tuple[int, int]) -> float:
    k, n = kn
    return k / n if n else float("nan")


def cell_win(cells: dict, cand: str, d0: str, rung: str, fam: str) -> tuple[bool, str, bool]:
    """Candidate vs d0 at (rung, fam) on misassoc: (win, ci_verdict, every_seed_improves)."""
    a = pool_std(cells, V6_SEEDS, cand, rung, fam, "misassoc")
    b = pool_std(cells, V6_SEEDS, d0, rung, fam, "misassoc")
    ci = cmp_ci(a, b)
    ca = per_seed_rates(cells, V6_SEEDS, cand, rung, fam, "misassoc")
    cb = per_seed_rates(cells, V6_SEEDS, d0, rung, fam, "misassoc")
    seed_ok = all(x <= y + 1e-9 for x, y in zip(ca, cb))
    return ci == "improve" and seed_ok, ci, seed_ok


def select_family(cells: dict, fam: str) -> dict:
    """Apply the pre-hoc selection rule to one standing-eval family."""
    d0 = V2_ERA_STANDING[fam]
    detail: dict = {"v2_era": d0, "candidates": {}}
    qualifying: list[tuple[float, str]] = []
    for cand in MENU:
        if cand == d0:
            continue
        wins = {r: cell_win(cells, cand, d0, r, fam) for r in ALL_RUNGS}
        win_select = all(wins[r][0] for r in SELECT_RUNGS)
        no_regress = all(wins[r][1] != "regress" for r in ALL_RUNGS)
        pooled_sel = tuple(
            sum(pool_std(cells, V6_SEEDS, cand, r, fam, "misassoc")[i] for r in SELECT_RUNGS)
            for i in (0, 1))
        detail["candidates"][cand] = {
            "win_both_select_rungs": win_select, "no_regress_any_rung": no_regress,
            "qualifies": win_select and no_regress,
            "per_rung": {r: {"win": wins[r][0], "ci": wins[r][1],
                             "every_seed": wins[r][2]} for r in ALL_RUNGS},
            "pooled_select_misassoc": [pooled_sel[0], pooled_sel[1]],
        }
        if win_select and no_regress:
            qualifying.append((rate(pooled_sel), cand))
    if qualifying:
        qualifying.sort()
        detail["selected"] = qualifying[0][1]
        detail["switched"] = qualifying[0][1] != d0
    else:
        detail["selected"] = d0
        detail["switched"] = False
    return detail


def dwell_menu() -> dict:
    """Compute the standing menu (baseline/A1/A3) on the dwell populations for the v6 seeds.

    Mirrors `increment6_coverage_split.py` exactly for baseline & stack5 (cross-checked against
    the committed coverage_split_v6.json) and adds A1(physics) to complete the menu on
    surfaces (b) in-coverage and (c) off-cone. Identity metric: idsw_opp (exit identity).
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    m = validate_dataset_dir(DWELL)
    lw = float(m["linewidth_Hz"])
    cap = nmr.CAPTURE_RADIUS_LW * lw
    v1_depths = np.asarray(validate_dataset_dir(V1_DIR)["line_depths"])
    faintest = float(v1_depths.min())
    clean = SequenceDatasetLoader(DWELL).load_split("test")
    with h5py.File(DWELL / "dataset.h5", "r") as f:
        tmpl = f["test/template_idx"][:]
        topo = f["test/exit_topology"][:]
    labels = [f"{'cov' if t in IN_COVERAGE_TEMPLATES else 'offcone'}/"
              f"{'cross' if x == 0 else 'bounce'}" for t, x in zip(tmpl, topo)]
    pops = sorted(set(labels))
    T = clean.spectra.shape[1]
    pred_axis = np.broadcast_to(LINE_AXIS_8, (T, 8))
    budgets = {tag: (None if snr is None else float(nmr.photons_for_dip_snr(faintest, snr)))
               for tag, snr in DWELL_RUNGS}

    out: dict = {"populations": pops, "rungs": list(budgets), "seeds": list(V6_SEEDS),
                 "cells": {}}
    t0 = time.time()
    for tag, photons in budgets.items():
        ds = nmr.noisy_copy(clean, photons)
        cells = out["cells"].setdefault(tag, {})
        for seed in V6_SEEDS:
            seqs, _ = ir.run_ckpt_outputs(V6_RUNS / seed / "best.pt", ds, device)
            for kind in MENU:
                rows = [nmr._row(ir.decode_tracked(kind, s, cap, lw), pred_axis,
                                 s["b_est"], ds, n, m) for n, s in enumerate(seqs)]
                agg = nmr.aggregate(rows, labels)
                cells.setdefault(f"decode:{kind}", {})[seed] = {
                    p: {"idsw_opp": agg[p]["idsw_opp"][:2],
                        "lock_loss": agg[p]["lock_loss"][:2]} for p in pops}
            print(f"[dwell:{tag}] {seed} done ({time.time() - t0:.0f}s)", flush=True)
    return out


def main() -> int:
    if not MATRIX_REDECODE.exists():
        print(f"[policy] {MATRIX_REDECODE.name} not yet produced. Rules are declared (pre-hoc). "
              "Produce it with:\n  python experiments/identity_redecode.py "
              f"--runs-dir {V6_RUNS} --seeds {' '.join(V6_SEEDS)} --out {MATRIX_REDECODE}\n"
              "then re-run this script.")
        return 1

    red = json.load(open(MATRIX_REDECODE))["cells"]
    covm = json.load(open(MATRIX_V6_COV))["datasets"]["v1"]["cells"]
    m2c = json.load(open(MATRIX_2C))["datasets"]["v1"]["cells"]

    L: list[str] = []
    P = L.append
    verdict: dict = {"menu": list(MENU), "v2_era_standing": V2_ERA_STANDING,
                     "v2_era_dwell": V2_ERA_DWELL}
    P("# Dispatch-7 — v6 per-family re-decode policy selection\n")
    P("Pre-hoc rule (see module docstring). Wilson 95%; pooled 3 v6 seeds; every-seed "
      "consistency; ties keep the v2-era choice. Menu: baseline / A1(physics) / A3(stack5).\n")

    # ---- Stop 2: integrity — redecode baseline reproduces the coverage learned column ----------
    integ: list[str] = []
    for rung in ALL_RUNGS:
        for fam in FAMILIES:
            for key in ("misassoc", "idsw_opp", "lock_loss"):
                a = pool_std(red, V6_SEEDS, "baseline", rung, fam, key)
                bk = sum(int(covm[rung][f"learned-gated+linear+aug[{s}]"][fam][key][0])
                         for s in V6_SEEDS)
                bn = sum(int(covm[rung][f"learned-gated+linear+aug[{s}]"][fam][key][1])
                         for s in V6_SEEDS)
                if a != (bk, bn):
                    integ.append(f"{rung}/{fam}/{key}: redecode {a} != coverage {(bk, bn)}")
    P("## Integrity — decode:baseline == matrix_6_coverage learned column\n")
    P("PASS — the re-decode harness reproduces the standing-eval learned column exactly."
      if not integ else "**FAIL (STOP) — eval-path surprise:**\n"
      + "\n".join(f"- {x}" for x in integ))
    verdict["integrity_mismatches"] = integ

    # ---- Stop 1: lock/field guard (v6 checkpoint lock vs v2 checkpoint lock; decode-invariant) --
    P("\n## Stop-1 guard — standing field lock, v6 vs v2 (decode-invariant)\n")
    P("| rung | family | v2 lock | v6 lock | verdict |")
    P("|---|---|---|---|---|")
    lock_regress: list[str] = []
    for rung in ALL_RUNGS:
        for fam in FAMILIES:
            a = (sum(int(covm[rung][f"learned-gated+linear+aug[{s}]"][fam]["lock_loss"][0])
                     for s in V6_SEEDS),
                 sum(int(covm[rung][f"learned-gated+linear+aug[{s}]"][fam]["lock_loss"][1])
                     for s in V6_SEEDS))
            b = (sum(int(m2c[rung][f"learned-gated+linear+aug[{s}]"][fam]["lock_loss"][0])
                     for s in V2_SEEDS),
                 sum(int(m2c[rung][f"learned-gated+linear+aug[{s}]"][fam]["lock_loss"][1])
                     for s in V2_SEEDS))
            v = cmp_ci(a, b)
            if v == "regress":
                lock_regress.append(f"{rung}/{fam}")
            P(f"| {rung} | {fam} | {b[0]}/{b[1]} | {a[0]}/{a[1]} | "
              f"{v.upper() if v == 'regress' else v} |")
    P(f"\nLock regressions (would damage the field claim -> STOP): **{lock_regress or 'none'}**")
    verdict["lock_regressions"] = lock_regress

    # ---- Surface (a): per-family standing-eval selection ---------------------------------------
    P("\n## Surface (a) — v1 standing eval per-family selection\n")
    selected: dict[str, str] = {}
    verdict["surface_a"] = {}
    for fam in FAMILIES:
        d = select_family(red, fam)
        selected[fam] = d["selected"]
        verdict["surface_a"][fam] = d
        P(f"\n### {fam} — v2-era default {NAME[d['v2_era']]} -> **selected "
          f"{NAME[d['selected']]}**" + ("  *(SWITCHED)*" if d["switched"] else ""))
        P("\n| rung | metric | baseline | A1(physics) | A3(stack5) | v2-era ref |")
        P("|---|---|--:|--:|--:|---|")
        for rung in ALL_RUNGS:
            for key in ("misassoc", "idsw_opp"):
                cellvals = {c: rate(pool_std(red, V6_SEEDS, c, rung, fam, key)) for c in MENU}
                marks = {}
                for c in MENU:
                    if c == d["v2_era"]:
                        marks[c] = "(d0)"
                    else:
                        cv = d["candidates"][c]["per_rung"][rung] if key == "misassoc" else None
                        marks[c] = ("" if key != "misassoc" else
                                    ("✅" if cv["win"] else ("✗" if cv["ci"] == "regress"
                                                            else "·")))
                P(f"| {rung} | {key} | {cellvals['baseline']:.3f}{marks['baseline']} | "
                  f"{cellvals['physics']:.3f}{marks['physics']} | "
                  f"{cellvals['stack5']:.3f}{marks['stack5']} | {NAME[d['v2_era']]} |")
    verdict["selected_standing_policy"] = selected

    # ---- Surfaces (b)+(c): dwell menu ----------------------------------------------------------
    P("\n## Surfaces (b) in-coverage & (c) off-cone dwell — menu winner on exit identity\n")
    dwm = dwell_menu()
    # cross-check baseline & stack5 vs the committed coverage_split_v6.json
    cov = json.load(open(COVSPLIT))["cells"]
    xcheck: list[str] = []
    for tag in dwm["cells"]:
        for kind in ("baseline", "stack5"):
            for seed in V6_SEEDS:
                for pop in dwm["populations"]:
                    a = [int(x) for x in dwm["cells"][tag][f"decode:{kind}"][seed][pop]["idsw_opp"]]
                    b = [int(x) for x in cov[tag][f"decode:{kind}"][seed][pop]["idsw_opp"][:2]]
                    if a != b:
                        xcheck.append(f"{tag}/{kind}/{seed}/{pop}: {a} != covsplit {b}")
    verdict["dwell_xcheck_mismatches"] = xcheck
    P("Cross-check vs coverage_split_v6.json (baseline+A3): "
      + ("**PASS**" if not xcheck else f"**FAIL** {xcheck[:3]}") + ".\n")
    verdict["surface_bc"] = {}
    for tag in dwm["cells"]:
        P(f"\n### rung = {tag}\n")
        P("| population | baseline | A1(physics) | A3(stack5) | winner |")
        P("|---|--:|--:|--:|---|")
        for pop in dwm["populations"]:
            pooled = {}
            for c in MENU:
                k = sum(int(dwm["cells"][tag][f"decode:{c}"][s][pop]["idsw_opp"][0])
                        for s in V6_SEEDS)
                n = sum(int(dwm["cells"][tag][f"decode:{c}"][s][pop]["idsw_opp"][1])
                        for s in V6_SEEDS)
                pooled[c] = (k, n)
            d0 = V2_ERA_DWELL
            best = d0
            for c in MENU:
                if c == d0:
                    continue
                per_seed_ok = all(
                    rate((int(dwm["cells"][tag][f"decode:{c}"][s][pop]["idsw_opp"][0]),
                          int(dwm["cells"][tag][f"decode:{c}"][s][pop]["idsw_opp"][1])))
                    <= rate((int(dwm["cells"][tag][f"decode:{best}"][s][pop]["idsw_opp"][0]),
                             int(dwm["cells"][tag][f"decode:{best}"][s][pop]["idsw_opp"][1])))
                    + 1e-9 for s in V6_SEEDS)
                if cmp_ci(pooled[c], pooled[best]) == "improve" and per_seed_ok:
                    best = c
            P(f"| {pop} | {rate(pooled['baseline']):.3f} | {rate(pooled['physics']):.3f} | "
              f"{rate(pooled['stack5']):.3f} | {NAME[best]}"
              + ("" if best == d0 else " *(beats A3)*") + " |")
            verdict["surface_bc"].setdefault(tag, {})[pop] = {
                "pooled": {c: list(pooled[c]) for c in MENU}, "winner": best}

    # ---- Decision ------------------------------------------------------------------------------
    P("\n## Decision\n")
    stop = bool(integ) or bool(lock_regress)
    if stop:
        P("**STOP-AND-REPORT** — "
          + ("; ".join(filter(None, [
              f"integrity mismatch ({len(integ)})" if integ else "",
              f"lock regression at {lock_regress}" if lock_regress else ""])))
          + ". Do not flip.")
        verdict["decision"] = "stop-and-report"
    else:
        switches = [f"{f}: {NAME[V2_ERA_STANDING[f]]}->{NAME[selected[f]]}"
                    for f in FAMILIES if selected[f] != V2_ERA_STANDING[f]]
        P("**FLIP CLEARED.** Selected standing policy: "
          + ", ".join(f"{f} -> {NAME[selected[f]]}" for f in FAMILIES)
          + (f". Switches vs v2-era: {switches}." if switches
             else ". No family switched — the v2-era per-family policy transfers unchanged "
                  "(ties kept per the continuity rule).")
          + f" Dwell through-merge decode stays {NAME[V2_ERA_DWELL]} (finding b).")
        verdict["decision"] = "flip-cleared"

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps({**verdict, "dwell_menu": dwm}, indent=1))
    OUT_MD.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[policy] decision={verdict['decision']} | wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
