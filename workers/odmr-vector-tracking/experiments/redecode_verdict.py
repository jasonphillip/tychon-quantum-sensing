"""Survival verdict for the zero-retrain identity re-decode (increment-2c lever A).

Compares each decode variant against the deployed baseline decode (``track_pos``) over the
re-decode matrix, pooling the 3 baseline seeds. A variant WINS a rung × family cell iff:
  (1) pooled misassoc is CI-disjoint BELOW baseline (Wilson 95%), and
  (2) every individual seed improves (sign-consistent) — this is what clears the known
      in-collision seed spread (0.550/0.592/0.622) that the dispatch flagged.
Symmetric definition for a REGRESSION. FIELD metrics are invariant by construction (asserted
during matrix build). Also emits the CV-KF identity crown (from matrix_2c_final.json) for the
target regime and writes a markdown table to artifacts/increment2c/redecode_report.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
REDECODE = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_redecode.json"
FINAL = _REPO / "artifacts" / "noise_matrix" / "matrix_2c_final.json"
OUT_MD = _REPO / "artifacts" / "increment2c" / "redecode_report.md"
OUT_JSON = _REPO / "artifacts" / "noise_matrix" / "redecode_verdict.json"

VARIANTS = ("greedy", "smooth5", "smooth15", "physics", "stack5")
BASE_LABELS = {  # matrix_2c_final learned-baseline label per seed (for the cross-check)
    "v2_gated_linear_snr10": "learned-gated+linear+aug[v2_gated_linear_snr10]",
    "v2_gated_linear_snr10_s20260711": "learned-gated+linear+aug[v2_gated_linear_snr10_s20260711]",
    "v2_gated_linear_snr10_s20260721": "learned-gated+linear+aug[v2_gated_linear_snr10_s20260721]",
}


def pooled(cells_by_seed: dict, seeds: list[str], fam: str, key: str) -> tuple[int, int]:
    k = sum(cells_by_seed[s][fam][key][0] for s in seeds)
    n = sum(cells_by_seed[s][fam][key][1] for s in seeds)
    return k, n


def cmp_ci(dk: int, dn: int, bk: int, bn: int) -> str:
    """Compare decode (d) vs baseline (b) proportions by Wilson-CI disjointness (lower=better)."""
    dlo, dhi = wilson_ci(dk, dn)
    blo, bhi = wilson_ci(bk, bn)
    if dhi < blo:
        return "improve"
    if dlo > bhi:
        return "regress"
    return "neutral"


def main() -> int:
    rm = json.load(open(REDECODE))
    seeds = rm["seeds"]
    cells = rm["cells"]
    final = json.load(open(FINAL))["datasets"]["v1"]["cells"]

    lines: list[str] = []
    W = lines.append
    W("# Increment-2c identity re-decode — verdict table\n")
    W(f"Pooled over seeds {seeds}. Latency (frames): {rm['latency_frames']}. "
      "FIELD metrics invariant by construction (asserted at build).\n")

    verdict: dict = {"latency_frames": rm["latency_frames"], "cells": {}}

    for rung in ("clean", "snr30", "snr10", "snr3"):
        base = cells[rung]["decode:baseline"]
        fams = sorted(base[seeds[0]].keys())
        W(f"\n## {rung}\n")
        W("| family | metric | baseline | greedy | smooth5 | smooth15 | physics | stack5 | KF |")
        W("|---|---|" + "---|" * 7)
        for fam in fams:
            bk_m, bn_m = pooled(base, seeds, fam, "misassoc")
            bk_s, bn_s = pooled(base, seeds, fam, "idsw_opp")
            kf = final.get(rung, {}).get("kf", {}).get(fam)
            row_m = [f"{bk_m/bn_m:.3f}"]
            row_s = [f"{bk_s/bn_s:.3f}" if bn_s else "nan"]
            cellverd = {}
            for v in VARIANTS:
                dc = cells[rung][f"decode:{v}"]
                dk_m, dn_m = pooled(dc, seeds, fam, "misassoc")
                dk_s, dn_s = pooled(dc, seeds, fam, "idsw_opp")
                vm = cmp_ci(dk_m, dn_m, bk_m, bn_m)
                vs = cmp_ci(dk_s, dn_s, bk_s, bn_s)
                # per-seed sign consistency on misassoc (clears the seed spread)
                seed_ok = all(
                    dc[s][fam]["misassoc"][0] / dc[s][fam]["misassoc"][1]
                    <= base[s][fam]["misassoc"][0] / base[s][fam]["misassoc"][1] + 1e-9
                    for s in seeds
                )
                win = vm == "improve" and seed_ok
                mark = "✅" if win else ("▲" if vm == "improve" else ("✗" if vm == "regress" else "·"))
                row_m.append(f"{dk_m/dn_m:.3f}{mark}")
                row_s.append(f"{dk_s/dn_s:.3f}" if dn_s else "nan")
                cellverd[v] = {"misassoc": vm, "idsw_opp": vs, "seed_consistent": seed_ok,
                               "win": win, "pooled_misassoc": [dk_m, dn_m]}
            kf_m = f"{kf['misassoc'][0]/kf['misassoc'][1]:.3f}" if kf else "—"
            kf_s = f"{kf['idsw_opp'][0]/kf['idsw_opp'][1]:.3f}" if kf else "—"
            W(f"| {fam} | misassoc | {' | '.join(row_m)} | {kf_m} |")
            W(f"| {fam} | idsw_opp | {' | '.join(row_s)} | {kf_s} |")
            verdict["cells"][f"{rung}/{fam}"] = {"baseline_misassoc": [bk_m, bn_m], **cellverd}

    # summary: where does any variant WIN, and specifically the target regime?
    target = {"clean/held", "clean/reversal", "snr30/held", "snr30/reversal"}
    W("\n## Summary\n")
    for v in VARIANTS:
        wins = [c for c, cv in verdict["cells"].items() if cv[v]["win"]]
        regs = [c for c, cv in verdict["cells"].items() if cv[v]["misassoc"] == "regress"]
        tw = sorted(w for w in wins if w in target)
        W(f"- **{v}**: wins {len(wins)}/12 cells (target-regime: {tw or 'none'}); "
          f"regresses {len(regs)} (legend: ✅ CI-win + all-seed-consistent, ▲ CI-win only, "
          f"✗ regress, · neutral)")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n")
    OUT_JSON.write_text(json.dumps(verdict, indent=1))
    print("\n".join(lines))
    print(f"\n[verdict] wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
