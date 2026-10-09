"""Increment-3 lever-B verdict: appearance-fingerprint model vs the wave-2 baseline.

Compares the 3-seed lever-B re-decode matrix (matrix_3_redecode.json) against the wave-2
baseline (matrix_2c_redecode.json, same 3 seeds) and CV-KF (matrix_2c_final.json), pooling
seeds, on the PRIMARY target (held clean/snr30 in-collision misassoc + IDSW/opp) and the
GUARDS (OU/reversal identity under the A3 decode; the field lock-loss/ae_post claim). Verdict
is CI-disjoint (Wilson 95%) with per-seed spread reported — no single-seed claims. Writes a
markdown table to artifacts/increment3/leverB_verdict.md.
"""
from __future__ import annotations

import json
from pathlib import Path

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
B = json.load(open(_REPO / "artifacts/noise_matrix/matrix_3_redecode.json"))["cells"]
W = json.load(open(_REPO / "artifacts/noise_matrix/matrix_2c_redecode.json"))["cells"]
KF = json.load(open(_REPO / "artifacts/noise_matrix/matrix_2c_final.json"))["datasets"]["v1"]["cells"]
OUT = _REPO / "artifacts/increment3/leverB_verdict.md"
BS = ["appfp_snr10_s20260701", "appfp_snr10_s20260711", "appfp_snr10_s20260721"]
WS = ["v2_gated_linear_snr10", "v2_gated_linear_snr10_s20260711", "v2_gated_linear_snr10_s20260721"]


def pool(c, dec, seeds, rung, fam, key):
    k = sum(c[rung][f"decode:{dec}"][s][fam][key][0] for s in seeds)
    n = sum(c[rung][f"decode:{dec}"][s][fam][key][1] for s in seeds)
    return k, n


def verdict(bk, bn, wk, wn):
    lo1, hi1 = wilson_ci(bk, bn)
    lo2, hi2 = wilson_ci(wk, wn)
    return "B-BETTER" if hi1 < lo2 else ("B-WORSE" if lo1 > hi2 else "~overlap")


def per_seed(c, dec, seeds, rung, fam, key):
    return [round(c[rung][f"decode:{dec}"][s][fam][key][0] / c[rung][f"decode:{dec}"][s][fam][key][1], 3)
            for s in seeds]


def main():
    L = []
    P = L.append
    P("# Increment-3 lever-B verdict (appearance-fingerprint branch, 3 seeds)\n")
    P("Pooled over 3 paired seeds vs wave-2 baseline (same seeds) and CV-KF. CI-disjoint (Wilson 95%).\n")

    P("## PRIMARY — held in-collision misassoc\n")
    P("| rung/decode | wave-2 | lever-B | verdict | KF | per-seed lever-B |")
    P("|---|---|---|---|---|---|")
    for rung in ("clean", "snr30"):
        kf = KF[rung]["kf"]["held"]["misassoc"]
        for dec in ("baseline", "greedy", "stack5"):
            wk, wn = pool(W, dec, WS, rung, "held", "misassoc")
            bk, bn = pool(B, dec, BS, rung, "held", "misassoc")
            P(f"| {rung}/{dec} | {wk/wn:.3f} | {bk/bn:.3f} | {verdict(bk,bn,wk,wn)} | "
              f"{kf[0]/kf[1]:.3f} | {per_seed(B,dec,BS,rung,'held','misassoc')} |")

    P("\n## held IDSW/opportunity (through-crossing switches)\n")
    P("| rung/decode | wave-2 | lever-B | verdict | KF |")
    P("|---|---|---|---|---|")
    for rung in ("clean", "snr30"):
        kf = KF[rung]["kf"]["held"]["idsw_opp"]
        for dec in ("baseline", "stack5"):
            wk, wn = pool(W, dec, WS, rung, "held", "idsw_opp")
            bk, bn = pool(B, dec, BS, rung, "held", "idsw_opp")
            P(f"| {rung}/{dec} | {wk/wn:.3f} | {bk/bn:.3f} | {verdict(bk,bn,wk,wn)} | {kf[0]/kf[1]:.3f} |")

    P("\n## GUARDS\n")
    P("| guard | wave-2 | lever-B | verdict |")
    P("|---|---|---|---|")
    for rung in ("clean", "snr30"):
        for fam in ("ou", "reversal"):
            wk, wn = pool(W, "stack5", WS, rung, fam, "misassoc")
            bk, bn = pool(B, "stack5", BS, rung, fam, "misassoc")
            P(f"| {rung}/{fam} misassoc (A3 decode) | {wk/wn:.3f} | {bk/bn:.3f} | {verdict(bk,bn,wk,wn)} |")
    for rung in ("clean", "snr30", "snr10", "snr3"):
        wl = sum(W[rung]["decode:baseline"][s][f]["lock_loss"][0] for s in WS for f in ("held", "ou", "reversal"))
        bl = sum(B[rung]["decode:baseline"][s][f]["lock_loss"][0] for s in BS for f in ("held", "ou", "reversal"))
        tot = sum(W[rung]["decode:baseline"][s][f]["lock_loss"][1] for s in WS for f in ("held", "ou", "reversal"))
        v = verdict(bl, tot, wl, tot)
        P(f"| {rung} field lock-loss | {wl}/{tot} | {bl}/{tot} | {v} |")

    OUT.write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\n[verdict] wrote {OUT}")


if __name__ == "__main__":
    main()
