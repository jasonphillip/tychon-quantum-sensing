"""Increment-5 dwell-lineage verdict — boundary curves, cue robustness, cue exploitation.

No TVW dispatch existed for the consumer side (issued-on-data-exists was deferred); the rules
below are declared here, before reading results, in the house pattern (CI-disjoint Wilson 95%,
pooled 3 seeds, every-seed consistency; report per-seed spread; no single-seed claims).

Part 1 — BOUNDARY (report-only, cues OFF): in-collision misassoc + IDSW/opportunity per
(D, exit-topology) bucket for the deployed decodes and classical references. This is the
recoverability-boundary evidence increment-4 could only infer.

Part 2 — CUE ROBUSTNESS (guard): same tracker/decode on cues-ON vs cues-OFF (seed-paired data).
The physics cues are only deployable if they do not damage the FIELD claim: a CI-disjoint
lock-loss regression on cues-ON = guard trip for the affected tracker. Identity deltas reported.

Part 3 — CUE EXPLOITATION (survival): a cue-aware decode SURVIVES iff, at clean AND snr30,
pooled over all 12 buckets, (a) CI-disjoint below the best non-cue decode on the SAME cues
data AND (b) every seed improves. NET VALUE additionally requires beating the deployed default
(baseline) on the cues-OFF data — i.e. the cues+decode combination must beat the no-cue world,
not merely rescue a cue-degraded one.

    python experiments/increment5_verdict.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
M = json.load(open(_REPO / "artifacts" / "noise_matrix" / "matrix_5_dwell.json"))
OUT_MD = _REPO / "artifacts" / "increment5" / "increment5_verdict.md"
OUT_JSON = _REPO / "artifacts" / "noise_matrix" / "increment5_verdict.json"

SEEDS = M["seeds"]
DS = M["datasets"]
DVALS = (8, 16, 32, 64, 128, 192)
TOPOS = ("cross", "bounce")
BUCKETS = [f"D{d}/{t}" for d in DVALS for t in TOPOS]
NONCUE = ("baseline", "physics", "stack5", "um2")
CUE = ("stack5_strain", "cr_gate", "cr_gate_strain")


def pool(ds: str, dec: str, rung: str, buckets, key: str = "misassoc") -> tuple[int, int]:
    """Pool counts over seeds (learned) or the single run (kf/nls) and the given buckets."""
    cells = DS[ds]["cells"][rung]
    k = n = 0
    if dec in ("kf", "nls"):
        for b in buckets:
            v = cells[dec][b][key]
            k += v[0]; n += v[1]
    else:
        for s in SEEDS:
            for b in buckets:
                v = cells[f"decode:{dec}"][s][b][key]
                k += v[0]; n += v[1]
    return int(k), int(n)


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


def per_seed_rates(ds: str, dec: str, rung: str, buckets, key="misassoc") -> list[float]:
    out = []
    for s in SEEDS:
        k = sum(DS[ds]["cells"][rung][f"decode:{dec}"][s][b][key][0] for b in buckets)
        n = sum(DS[ds]["cells"][rung][f"decode:{dec}"][s][b][key][1] for b in buckets)
        out.append(round(k / n, 3) if n else float("nan"))
    return out


def main() -> int:
    L: list[str] = []
    P = L.append
    P("# Increment-5 dwell-lineage verdict\n")
    P(f"Seeds {SEEDS}, pooled; Wilson 95% CI-disjoint; datasets seed-paired "
      f"(`{DS['off']['dir']}` vs `{DS['cues']['dir']}`). Ladder: {M['ladder_source']}. "
      f"CR marker threshold {M['cr_depth_thresh']:.4f}.\n")
    verdict: dict = {"seeds": SEEDS, "parts": {}}

    # ---- Part 1: boundary curves (cues OFF, clean) -------------------------------------------
    P("## Part 1 — recoverability boundary (cues OFF, clean)\n")
    P("In-collision misassoc per bucket (pooled 3 seeds for learned):\n")
    hdr = "| decode | " + " | ".join(f"D{d}" for d in DVALS) + " |"
    for topo in TOPOS:
        P(f"\n### exit = {topo}\n")
        P(hdr)
        P("|---|" + "--:|" * len(DVALS))
        for dec in ("baseline", "stack5", "um2", "kf", "nls"):
            cells = []
            for d in DVALS:
                b = [f"D{d}/{topo}"]
                try:
                    cells.append(f"{rate(pool('off', dec, 'clean', b)):.3f}")
                except KeyError:
                    cells.append("—")
            P(f"| {dec} | " + " | ".join(cells) + " |")
        P("")
        P("IDSW/opportunity (exit identity):")
        P(hdr)
        P("|---|" + "--:|" * len(DVALS))
        for dec in ("baseline", "stack5", "kf"):
            cells = []
            for d in DVALS:
                b = [f"D{d}/{topo}"]
                cells.append(f"{rate(pool('off', dec, 'clean', b, 'idsw_opp')):.3f}")
            P(f"| {dec} | " + " | ".join(cells) + " |")
    # noise robustness of the boundary (baseline + kf pooled over buckets)
    P("\n### boundary vs noise (pooled all buckets)\n")
    P("| rung | learned baseline | kf |")
    P("|---|--:|--:|")
    for rung in ("clean", "snr30", "snr10", "snr3"):
        P(f"| {rung} | {rate(pool('off', 'baseline', rung, BUCKETS)):.3f} "
          f"| {rate(pool('off', 'kf', rung, BUCKETS)):.3f} |")
    kf3_lock = pool("off", "kf", "snr3", BUCKETS, "lock_loss")
    P(f"\nKF snr3 identity is conditioned-on-lock (KF loses lock {kf3_lock[0]}/{kf3_lock[1]} "
      "dwell sequences at snr3).")
    verdict["parts"]["boundary"] = {
        t: {f"D{d}": {dec: rate(pool("off", dec, "clean", [f"D{d}/{t}"]))
                      for dec in ("baseline", "stack5", "um2", "kf")}
            for d in DVALS} for t in TOPOS}

    # ---- Part 2: cue robustness (guard) -------------------------------------------------------
    P("\n## Part 2 — cue robustness (cues-ON vs cues-OFF, same decode; GUARD)\n")
    P("| tracker/decode | rung | misassoc off→on | verdict | lock-loss off→on | field verdict |")
    P("|---|---|---|---|---|---|")
    guard_trips: list[str] = []
    for dec in ("baseline", "stack5", "kf"):
        for rung in ("clean", "snr30", "snr10", "snr3"):
            mo, mn = pool("off", dec, rung, BUCKETS), pool("cues", dec, rung, BUCKETS)
            lo, ln = pool("off", dec, rung, BUCKETS, "lock_loss"), \
                pool("cues", dec, rung, BUCKETS, "lock_loss")
            vm = cmp_ci(mn, mo)
            vf = cmp_ci(ln, lo)
            if vf == "regress":
                guard_trips.append(f"{dec}@{rung}")
            P(f"| {dec} | {rung} | {rate(mo):.3f}→{rate(mn):.3f} | {vm} | "
              f"{lo[0]}/{lo[1]}→{ln[0]}/{ln[1]} | {vf} |")
    P(f"\nField guard trips (lock-loss regression on cues): {guard_trips or 'none'}")
    verdict["parts"]["robustness_guard_trips"] = guard_trips

    # ---- Part 3: cue exploitation (survival) ---------------------------------------------------
    P("\n## Part 3 — cue exploitation on the cues dataset (SURVIVAL)\n")
    P("Misassoc pooled over all 12 buckets (per-seed spread in brackets):\n")
    P("| decode | clean | snr30 | snr10 | snr3 |")
    P("|---|--:|--:|--:|--:|")
    for dec in NONCUE + CUE:
        row = []
        for rung in ("clean", "snr30", "snr10", "snr3"):
            row.append(f"{rate(pool('cues', dec, rung, BUCKETS)):.3f}")
        P(f"| {dec} | " + " | ".join(row) + " |")
    # best non-cue decode per rung on cues data
    survivors = []
    detail = {}
    for cue_dec in CUE:
        ok = True
        dd = {}
        for rung in ("clean", "snr30"):
            best_nc = min(NONCUE, key=lambda d: rate(pool("cues", d, rung, BUCKETS)))
            c, nc = pool("cues", cue_dec, rung, BUCKETS), pool("cues", best_nc, rung, BUCKETS)
            ci = cmp_ci(c, nc)
            seed_ok = all(
                a < b for a, b in zip(per_seed_rates("cues", cue_dec, rung, BUCKETS),
                                      per_seed_rates("cues", best_nc, rung, BUCKETS)))
            # net value vs the deployed default in the no-cue world (paired sequences)
            off_base = pool("off", "baseline", rung, BUCKETS)
            net = cmp_ci(c, off_base)
            dd[rung] = {"vs_best_noncue": [best_nc, ci, seed_ok], "vs_off_baseline": net,
                        "pooled": list(c)}
            ok = ok and ci == "improve" and seed_ok
        detail[cue_dec] = dd
        if ok:
            survivors.append(cue_dec)
    P("\n**Survival vs best non-cue decode on cues data (clean & snr30, CI-disjoint + every "
      "seed):**\n")
    for cue_dec in CUE:
        dd = detail[cue_dec]
        P(f"- `{cue_dec}`: " + "; ".join(
            f"{r}: vs {dd[r]['vs_best_noncue'][0]} → {dd[r]['vs_best_noncue'][1]}"
            f"{'+seeds' if dd[r]['vs_best_noncue'][2] else ''}, net-vs-off-baseline "
            f"{dd[r]['vs_off_baseline']}" for r in ("clean", "snr30"))
          + f" → {'SURVIVES' if cue_dec in survivors else 'no'}")
    verdict["parts"]["exploitation"] = detail
    verdict["survivors"] = survivors

    # ---- Decision -----------------------------------------------------------------------------
    P("\n## Decision\n")
    if survivors and not guard_trips:
        P(f"**{survivors} survive** the cue-exploitation rule with no field guard trip — "
          "proposed (not adopted) as the identity decode when the physics cues are present. "
          "Net-value column states whether cues+decode beat the no-cue world.")
    elif survivors:
        P(f"{survivors} clear the exploitation rule **but the field guard tripped** "
          f"({guard_trips}) — the cues as rendered damage the field claim for the affected "
          "trackers; not deployable as-is.")
    else:
        P("**No cue decode survives.** Evidence tabulated above; boundary curves stand as the "
          "increment's primary result.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n")
    OUT_JSON.write_text(json.dumps(verdict, indent=1))
    print("\n".join(L))
    print(f"\n[verdict] survivors={survivors} guard_trips={guard_trips} | wrote {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
