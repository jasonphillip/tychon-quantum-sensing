"""Pre-flight parity gate for increment-4 (environment-drift STOP condition).

The overlay-decoder experiment only means something if the ws2-regenerated zero-retrain
re-decode reproduces the archived ws1 reference EXACTLY on the standing eval — otherwise a
"win" could be environment drift (a different torch/cuDNN moving a boundary argmax) rather than
the decoder. This gate asserts three things and exits non-zero on any mismatch:

  (1) ``decode:baseline`` in-collision misassoc (and IDSW/opportunity, and field lock-loss)
      reproduces ``matrix_2c_final.json``'s learned-baseline column for every seed x rung x
      family — exact integer counts. This is the check the dispatch names.
  (2) The per-sequence post-crossing angular error (``ae_post_all``) of the baseline decode is
      byte-identical to the final matrix's learned column (the ``b_est`` path is untouched, so a
      float mismatch here is drift, not decode).
  (3) The full ws2 re-decode (all six variants) matches the archived reference
      ``matrix_2c_redecode.json`` cell-for-cell (a stronger, decoder-inclusive reproduction).

Exit 0 = parity holds -> proceed. Exit 1 = drift -> STOP-AND-REPORT (dispatch condition 1).

    python experiments/increment4_parity_gate.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
NM = _REPO / "artifacts" / "noise_matrix"
LOCAL_REDECODE = NM / "matrix_2c_redecode.json"            # ws2-regenerated (this run)
ARCHIVED_REDECODE = NM / "matrix_2c_redecode.archived.json"  # ws1 reference copy
FINAL = NM / "matrix_2c_final.json"                        # ws1 reference (learned baseline + KF/NLS)

RUNGS = ("clean", "snr30", "snr10", "snr3")
DECODES = ("baseline", "greedy", "smooth5", "smooth15", "physics", "stack5")
COUNT_KEYS = ("misassoc", "idsw_opp", "lock_loss")  # [k, n, ci_lo, ci_hi]; compare [k, n] exactly
FINAL_LABEL = "learned-gated+linear+aug[{seed}]"    # matrix_2c_final learned column per seed


def _counts(cell: dict, key: str) -> tuple[int, int]:
    v = cell[key]
    return int(v[0]), int(v[1])


def check_baseline_vs_final(local: dict, final_cells: dict) -> list[str]:
    """decode:baseline (ws2) == learned-baseline column (matrix_2c_final) — exact."""
    seeds = local["seeds"]
    fails: list[str] = []
    n_cmp = 0
    for rung in RUNGS:
        base = local["cells"][rung]["decode:baseline"]
        for seed in seeds:
            label = FINAL_LABEL.format(seed=seed)
            fcell = final_cells[rung][label]
            dcell = base[seed]
            for fam in sorted(fcell.keys()):
                for key in COUNT_KEYS:
                    dk, dn = _counts(dcell[fam], key)
                    fk, fn = _counts(fcell[fam], key)
                    n_cmp += 1
                    if (dk, dn) != (fk, fn):
                        fails.append(
                            f"[baseline!=final] {rung}/{seed}/{fam}/{key}: "
                            f"ws2 {dk}/{dn} vs final {fk}/{fn}")
                # field: per-sequence post-crossing angular error must be byte-identical
                if dcell[fam]["ae_post_all"] != fcell[fam]["ae_post_all"]:
                    fails.append(f"[baseline!=final] {rung}/{seed}/{fam}/ae_post_all: float drift")
                if dcell[fam]["lost_all"] != fcell[fam]["lost_all"]:
                    fails.append(f"[baseline!=final] {rung}/{seed}/{fam}/lost_all: lock drift")
    print(f"  (1) baseline-vs-final: {n_cmp} count comparisons over "
          f"{len(RUNGS)} rungs x {len(seeds)} seeds x 3 families")
    return fails


def check_redecode_reproduction(local: dict, archived: dict) -> list[str]:
    """Full ws2 re-decode == archived reference, every variant/seed/rung/family."""
    seeds = local["seeds"]
    if archived["seeds"] != seeds:
        return [f"[redecode] seed list differs: {archived['seeds']} vs {seeds}"]
    fails: list[str] = []
    n_cmp = 0
    for rung in RUNGS:
        for dec in DECODES:
            lcells = local["cells"][rung][f"decode:{dec}"]
            acells = archived["cells"][rung][f"decode:{dec}"]
            for seed in seeds:
                for fam in sorted(lcells[seed].keys()):
                    for key in COUNT_KEYS:
                        lk = _counts(lcells[seed][fam], key)
                        ak = _counts(acells[seed][fam], key)
                        n_cmp += 1
                        if lk != ak:
                            fails.append(
                                f"[redecode drift] {rung}/{dec}/{seed}/{fam}/{key}: "
                                f"ws2 {lk[0]}/{lk[1]} vs archived {ak[0]}/{ak[1]}")
                    if lcells[seed][fam]["ae_post_all"] != acells[seed][fam]["ae_post_all"]:
                        fails.append(f"[redecode drift] {rung}/{dec}/{seed}/{fam}/ae_post_all")
    print(f"  (3) redecode reproduction: {n_cmp} count comparisons over "
          f"{len(RUNGS)} rungs x {len(DECODES)} decodes x {len(seeds)} seeds x 3 families")
    return fails


def main() -> int:
    for p in (LOCAL_REDECODE, ARCHIVED_REDECODE, FINAL):
        if not p.exists():
            print(f"[parity] MISSING input: {p}")
            return 1
    local = json.load(open(LOCAL_REDECODE))
    archived = json.load(open(ARCHIVED_REDECODE))
    final_cells = json.load(open(FINAL))["datasets"]["v1"]["cells"]

    print("[parity] increment-4 pre-flight gate (environment drift)")
    fails = check_baseline_vs_final(local, final_cells)
    fails += check_redecode_reproduction(local, archived)

    # Report the headline held numbers so the gate's evidence is visible in the log.
    print("\n[parity] held in-collision misassoc, decode:baseline (ws2) — pooled 3 seeds:")
    for rung in RUNGS:
        base = local["cells"][rung]["decode:baseline"]
        k = sum(base[s]["held"]["misassoc"][0] for s in local["seeds"])
        n = sum(base[s]["held"]["misassoc"][1] for s in local["seeds"])
        fk = sum(final_cells[rung][FINAL_LABEL.format(seed=s)]["held"]["misassoc"][0]
                 for s in local["seeds"])
        fn = sum(final_cells[rung][FINAL_LABEL.format(seed=s)]["held"]["misassoc"][1]
                 for s in local["seeds"])
        print(f"    {rung:>5}: ws2 {k}/{n}={k/n:.4f}  final {fk}/{fn}={fk/fn:.4f}")

    if fails:
        print(f"\n[parity] FAIL — {len(fails)} mismatch(es); environment drift. STOP-AND-REPORT.")
        for f in fails[:40]:
            print("   ", f)
        if len(fails) > 40:
            print(f"    ... and {len(fails) - 40} more")
        return 1
    print("\n[parity] PASS — ws2 reproduces the ws1 reference exactly. Proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
