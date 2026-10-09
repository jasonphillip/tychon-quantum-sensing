"""Increment-4 overlay-decoder verdict — deterministic survival rule + guards.

Compares each overlay decoder (matrix_4_overlay.json) against the deployed baseline decode and the
current default decode policy (A3=stack5 on OU/reversal, baseline on held; matrix_2c_redecode.json),
with CV-KF and NLS references (matrix_2c_final.json), pooling the 3 wave-2 seeds. Mirrors
leverB_verdict.py.

SURVIVAL (primary): a decoder survives iff, at BOTH clean AND snr30, its held in-collision
misassoc is (a) CI-disjoint below the baseline decode (Wilson 95%, pooled 3 seeds) AND (b) strictly
better on every individual seed (clears the seed spread).

GUARDS (any trip => the decoder FAILS): no CI-disjoint regression at any family x rung versus the
default decode policy; field metrics byte-identical (asserted at matrix build); KF SNR3 identity is
reported conditioned-on-lock only.

Decision: keep-what-survives. If nothing survives, report the per-family evidence and stop.

    python experiments/increment4_verdict.py
"""

from __future__ import annotations

import json
from pathlib import Path

from odmr_vector_tracking.evaluation.metrics import wilson_ci

_REPO = Path(__file__).resolve().parent.parent
NM = _REPO / "artifacts" / "noise_matrix"
OVERLAY = json.load(open(NM / "matrix_4_overlay.json"))
O = OVERLAY["cells"]
W = json.load(open(NM / "matrix_2c_redecode.json"))["cells"]
KF = json.load(open(NM / "matrix_2c_final.json"))["datasets"]["v1"]["cells"]
OUT_MD = _REPO / "artifacts" / "increment4" / "increment4_verdict.md"
OUT_JSON = NM / "increment4_verdict.json"

SEEDS = OVERLAY["seeds"]
LATENCY = OVERLAY["latency_frames"]
DECODERS = [d for d in OVERLAY["decodes"] if d != "baseline"]
RUNGS = ("clean", "snr30", "snr10", "snr3")
FAMS = ("held", "ou", "reversal")


def pool(cells: dict, dec: str, rung: str, fam: str, key: str) -> tuple[int, int]:
    k = sum(cells[rung][f"decode:{dec}"][s][fam][key][0] for s in SEEDS)
    n = sum(cells[rung][f"decode:{dec}"][s][fam][key][1] for s in SEEDS)
    return k, n


def cmp_ci(dk: int, dn: int, bk: int, bn: int) -> str:
    """decode d vs reference b, lower misassoc = better, by Wilson-CI disjointness."""
    dlo, dhi = wilson_ci(dk, dn)
    blo, bhi = wilson_ci(bk, bn)
    if dhi < blo:
        return "improve"
    if dlo > bhi:
        return "regress"
    return "neutral"


def default_policy(rung: str, fam: str, key: str) -> tuple[int, int]:
    """Current deployed decode policy: A3 (stack5) on OU/reversal, baseline on held."""
    dec = "stack5" if fam in ("ou", "reversal") else "baseline"
    return pool(W, dec, rung, fam, key)


def per_seed(cells: dict, dec: str, rung: str, fam: str, key: str) -> list[float]:
    return [round(cells[rung][f"decode:{dec}"][s][fam][key][0]
                  / cells[rung][f"decode:{dec}"][s][fam][key][1], 3) for s in SEEDS]


def survives(dec: str) -> tuple[bool, dict]:
    detail = {}
    ok = True
    for rung in ("clean", "snr30"):
        dk, dn = pool(O, dec, rung, "held", "misassoc")
        bk, bn = pool(O, "baseline", rung, "held", "misassoc")
        ci = cmp_ci(dk, dn, bk, bn)
        seed_ok = all(
            O[rung][f"decode:{dec}"][s]["held"]["misassoc"][0]
            / O[rung][f"decode:{dec}"][s]["held"]["misassoc"][1]
            < O[rung]["decode:baseline"][s]["held"]["misassoc"][0]
            / O[rung]["decode:baseline"][s]["held"]["misassoc"][1]
            for s in SEEDS)
        detail[rung] = {"ci": ci, "every_seed_improves": seed_ok,
                        "pooled": [dk, dn], "baseline": [bk, bn]}
        ok = ok and ci == "improve" and seed_ok
    return ok, detail


def guard_trips(dec: str) -> list[str]:
    trips = []
    for rung in RUNGS:
        for fam in FAMS:
            dk, dn = pool(O, dec, rung, fam, "misassoc")
            pk, pn = default_policy(rung, fam, "misassoc")
            if cmp_ci(dk, dn, pk, pn) == "regress":
                trips.append(f"{rung}/{fam}")
    return trips


def main() -> int:
    L: list[str] = []
    P = L.append
    # parity sanity: overlay baseline must equal the wave-2 baseline it is compared against
    parity = all(pool(O, "baseline", r, f, "misassoc") == pool(W, "baseline", r, f, "misassoc")
                 for r in RUNGS for f in FAMS)
    P("# Increment-4 overlay-decoder verdict\n")
    P(f"Pooled over 3 seeds {SEEDS}. CI-disjoint (Wilson 95%). Field metrics invariant by "
      f"construction (asserted at build). Overlay/​wave-2 baseline parity: "
      f"{'OK' if parity else 'MISMATCH'}. JV penalty {OVERLAY.get('jv_penalty')}.\n")

    verdict = {"seeds": SEEDS, "baseline_parity": parity, "decoders": {}, "survivors": []}

    # PRIMARY — held in-collision misassoc vs baseline, clean & snr30
    P("## PRIMARY — held in-collision misassoc (survival rule)\n")
    P("| decoder | lat | clean pooled | clean vs base | snr30 pooled | snr30 vs base | seeds(clean) | SURVIVES |")
    P("|---|--:|--:|---|--:|--:|---|---|")
    kf_c = KF["clean"]["kf"]["held"]["misassoc"]
    base_c = pool(O, "baseline", "clean", "held", "misassoc")
    for dec in DECODERS:
        ok, det = survives(dec)
        dk_c, dn_c = det["clean"]["pooled"]
        dk_s, dn_s = det["snr30"]["pooled"]
        lat = LATENCY.get(dec)
        lats = ">seq" if lat is None else str(lat)
        P(f"| {dec} | {lats} | {dk_c}/{dn_c}={dk_c/dn_c:.3f} | {det['clean']['ci']}"
          f"{'+seeds' if det['clean']['every_seed_improves'] else ''} | "
          f"{dk_s}/{dn_s}={dk_s/dn_s:.3f} | {det['snr30']['ci']}"
          f"{'+seeds' if det['snr30']['every_seed_improves'] else ''} | "
          f"{per_seed(O, dec, 'clean', 'held', 'misassoc')} | {'✅ YES' if ok else '—'} |")
        verdict["decoders"][dec] = {"survives": ok, "detail": det, "guard_trips": guard_trips(dec)}
        if ok and not verdict["decoders"][dec]["guard_trips"]:
            verdict["survivors"].append(dec)
    P(f"\nReference (held clean): baseline {base_c[0]}/{base_c[1]}={base_c[0]/base_c[1]:.3f} · "
      f"CV-KF {kf_c[0]}/{kf_c[1]}={kf_c[0]/kf_c[1]:.3f} · "
      f"NLS {KF['clean']['nls']['held']['misassoc'][0]}/{KF['clean']['nls']['held']['misassoc'][1]}="
      f"{KF['clean']['nls']['held']['misassoc'][0]/KF['clean']['nls']['held']['misassoc'][1]:.3f}\n")

    # GUARDS
    P("## GUARDS — CI-disjoint regression vs default policy (A3 on OU/reversal, baseline on held)\n")
    P("| decoder | regressions (rung/family) |")
    P("|---|---|")
    for dec in DECODERS:
        tr = verdict["decoders"][dec]["guard_trips"]
        P(f"| {dec} | {', '.join(tr) if tr else 'none'} |")

    # KF SNR3 conditioned-on-lock caveat
    kf3 = KF["snr3"]["kf"]["held"]
    P("\n## KF SNR3 identity (conditioned-on-lock)\n")
    P(f"- CV-KF held snr3 misassoc {kf3['misassoc'][0]}/{kf3['misassoc'][1]}="
      f"{kf3['misassoc'][0]/kf3['misassoc'][1]:.3f}, but KF loses field lock on "
      f"{kf3['lock_loss'][0]}/{kf3['lock_loss'][1]} held sequences at snr3 — the identity number "
      "is conditioned on the frames where lock survives and is not a clean win.\n")

    # DECISION
    P("## Decision\n")
    if verdict["survivors"]:
        P(f"**KEEP-WHAT-SURVIVES:** {verdict['survivors']} clear the survival rule AND trip no "
          "guard. Proposed as the identity-decode default for held clean/snr30 (adoption is the "
          "user's call; defaults not flipped here).")
    else:
        P("**NOTHING SURVIVES.** No overlay decoder achieves a CI-disjoint, every-seed held "
          "improvement at both clean and snr30 without tripping a guard. Per the dispatch this is "
          "a stop-and-report outcome — the coalescence-aware overlay menu does not close the held "
          "gap on this eval; the per-family evidence is tabulated above and in matrix_4_overlay.json.")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(L) + "\n")
    OUT_JSON.write_text(json.dumps(verdict, indent=1))
    print("\n".join(L))
    print(f"\n[verdict] survivors={verdict['survivors']} | wrote {OUT_MD} and {OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
