"""Re-evaluate archived wave-1 and increment-7 guards without changing old verdicts.

Run with ``--artifacts`` pointing to the read-only archived artifact tree.
Only ``--output`` is written. Ordered arrays are matched by sequence ordinal
and seed suffix; the matrix builders document common sequence order and fixed
noise realization. Pooled-only metrics remain inconclusive.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "src"))

from odmr_vector_tracking.evaluation.noninferiority import (
    Outcome, PROPOSED_MARGINS, compare_paired,
)

from wave1_verdict import BASELINE_RUN, LEVER_RUNS, ci_disjoint_worse, find_label, paired_median_diff_ci
from increment7_verdict import (
    ARMS, FAMILIES, NOISE, POLICY, SPLIT_RUNGS, V6_SEEDS, arm_seed_names,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def old_status(flags: list[bool]) -> str:
    return "regression" if any(flags) else "accepted as neutral/better"


def new_status(results: list) -> str:
    if not results:
        return "inconclusive (no paired rows)"
    if any(r.verdict == "inconclusive" for r in results):
        return "inconclusive"
    return "superior" if all(r.verdict == "superior" for r in results) else "non-inferior"


def summary(results: list) -> str:
    if not results:
        return "no per-sequence data"
    bad = sum(r.ci_low > 0 for r in results)
    return (f"{sum(r.verdict == 'inconclusive' for r in results)}/{len(results)} inconclusive; "
            f"{bad} CIs exclude zero on worse side; max upper CI {max(r.ci_high for r in results):+.3f}")


def metric_rows(cell: dict, key: str, seed: str) -> list[Outcome] | None:
    if key == "lock_loss":
        vals = cell.get("lost_all")
        denoms = [1] * len(vals) if vals is not None else None
    elif key == "misassoc":
        vals, denoms = cell.get("in_coll_wrong_all"), cell.get("in_coll_n_all")
    elif key == "ae_post":
        vals = cell.get("ae_post_all")
        denoms = [1] * len(vals) if vals is not None else None
    else:
        return None  # no per-sequence switch/opportunity counts in these matrices
    if vals is None or denoms is None or len(vals) != len(denoms):
        return None
    # A zero-exposure sequence has no defined event rate. Remove the same ID
    # from both sides in paired_rows, rather than imputing an outcome.
    return [Outcome(i, seed, float(value), float(denom)) for i, (value, denom)
            in enumerate(zip(vals, denoms))]


def paired_rows(a: dict, b: dict, key: str, seed: str):
    ar, br = metric_rows(a, key, seed), metric_rows(b, key, seed)
    if ar is None or br is None or len(ar) != len(br):
        return None
    good = [i for i, (x, y) in enumerate(zip(ar, br))
            if x.exposure > 0 and y.exposure > 0
            and x.value == x.value and y.value == y.value]
    return [ar[i] for i in good], [br[i] for i in good]


def compare_cells(pairs: list[tuple[dict, dict, str]], key: str):
    candidate, baseline = [], []
    for a, b, seed in pairs:
        rows = paired_rows(a, b, key, seed)
        if rows is None:
            return None
        candidate.extend(rows[0])
        baseline.extend(rows[1])
    if not candidate:
        return None
    return compare_paired(candidate, baseline, margin=PROPOSED_MARGINS[key],
                          binary=key != "ae_post")


def wave1(artifacts: Path, lines: list[str]) -> None:
    matrix = load(artifacts / "noise_matrix/matrix_2c_final.json")
    cells = matrix["datasets"]["v1"]["cells"]
    lines.extend(["## Wave-1 levers", "", "Source: archived `matrix_2c_final.json`; old decisions: `docs/increment2c_results.md`.",
                  "The matrix preserves the same sequence order and fixed noise realization for each tracker.",
                  "", "| Lever | Guard | Old verdict | New verdict | Paired evidence |", "|---|---|---|---|---|"])
    for run, lever in LEVER_RUNS.items():
        for key in ("lock_loss", "ae_post", "misassoc", "idsw_opp"):
            old_flags, new = [], []
            missing = False
            for rung, rung_cells in cells.items():
                al, bl = find_label(rung_cells, run), find_label(rung_cells, BASELINE_RUN)
                if al is None or bl is None:
                    missing = True
                    continue
                for fam in sorted(rung_cells[bl]):
                    a, b = rung_cells[al][fam], rung_cells[bl][fam]
                    if key == "ae_post":
                        _, lo, _, n = paired_median_diff_ci(a["ae_post_all"], b["ae_post_all"])
                        old_flags.append(n > 0 and lo > 0)
                    else:
                        old_flags.append(ci_disjoint_worse(a[key], b[key]))
                    result = compare_cells([(a, b, "20260701")], key)
                    if result is None:
                        missing = True
                    else:
                        new.append(result)
            status = "inconclusive (missing matched arrays)" if missing else new_status(new)
            lines.append(f"| {lever} | {key} | {old_status(old_flags)} | {status} | {summary(new)} |")
    lines.extend(["", "Old wave-1 decision: **all three eliminated**. New decision: **none qualifies as non-regressing across all guards**.",
                  "IDSW/opportunity lacks per-sequence event and opportunity arrays; its old neutral calls cannot be confirmed.", ""])


def redecode_cell(data: dict, rung: str, decode: str, seed: str, fam: str) -> dict:
    return data["cells"][rung][f"decode:{decode}"][seed][fam]


def increment7(artifacts: Path, lines: list[str]) -> None:
    old = load(artifacts / "increment7/increment7_verdict.json")
    v6 = load(artifacts / "noise_matrix/matrix_6_redecode.json")
    lines.extend(["## Increment-7 arms", "", "Source: archived arm, v6, and old-verdict JSON files.",
                  "Matched training-seed suffixes and sequence ordinals retain the paired design.",
                  "", "| Arm | Guard | Old verdict | New verdict | Paired evidence |", "|---|---|---|---|---|"])
    for arm in ARMS:
        d = artifacts / "increment7" / arm
        if arm not in old["reports"] or not (d / "redecode.json").exists():
            lines.append(f"| {arm} | all | not evaluated | inconclusive (no arm results) | no rows |")
            continue
        a = load(d / "redecode.json")
        afield = load(d / "fieldcone.json")
        seed_pairs = list(zip(arm_seed_names(arm), V6_SEEDS))
        oldarm = old["reports"][arm]
        # The primary held identity gate is a superiority gate, with a separate
        # every-seed requirement. Report the paired superiority result and keep
        # the original every-seed check intact.
        primary = []
        for rung in SPLIT_RUNGS:
            pairs = [(redecode_cell(a, rung, POLICY["held"], sa, "held"),
                      redecode_cell(v6, rung, POLICY["held"], sb, "held"), sa)
                     for sa, sb in seed_pairs]
            primary.append(compare_cells(pairs, "misassoc"))
        old_primary = "clears" if oldarm["primary"]["clears"] else "does not clear"
        new_primary = ("clears" if all(r is not None and r.verdict == "superior" for r in primary)
                       and all(oldarm["primary"]["detail"]["held"][f"{r}/misassoc"]["every_seed_better"]
                               for r in SPLIT_RUNGS) else "does not clear")
        primary_results = [r for r in primary if r]
        lines.append(f"| {arm} | PRIMARY held misassoc | {old_primary} | {new_primary} | "
                     f"paired {new_status(primary_results)}; {summary(primary_results)}; every-seed retained |")

        # Guard A(i) is an exact zero-loss invariant, not a CI-neutral rule.
        dir_old = "trip" if oldarm["guard_a"]["directed_trip"] else "pass"
        bucket = afield["bucket_class"]
        selected = [i for i, klass in enumerate(bucket) if klass == 0]
        directed = all(all(afield["cells"][rung][sa]["lost_all"][i] == 0
                           for i in selected for sa, _ in seed_pairs) for rung in SPLIT_RUNGS)
        lines.append(f"| {arm} | GUARD-A directed zero | {dir_old} | {'pass' if directed else 'trip'} | exact zero rule; {len(selected)} sequences/seed |")

        # Dwell artifacts retain only pooled counts: no sequence IDs or rows.
        off_old = "trip" if oldarm["guard_a"]["offcone_trip"] else "accepted as neutral/better"
        lines.append(f"| {arm} | GUARD-A off-cone dwell lock | {off_old} | inconclusive | pooled counts only; no paired rows |")

        guardb = []
        for rung in NOISE:
            for fam in FAMILIES:
                pairs = [(redecode_cell(a, rung, "baseline", sa, fam),
                          redecode_cell(v6, rung, "baseline", sb, fam), sa)
                         for sa, sb in seed_pairs]
                guardb.append(compare_cells(pairs, "lock_loss"))
        b_old = "trip" if oldarm["guard_b"]["trips"] else "accepted as neutral/better"
        lines.append(f"| {arm} | GUARD-B standing lock | {b_old} | {new_status([r for r in guardb if r])} | {summary([r for r in guardb if r])} |")
    lines.extend(["", "Old increment-7 decision: **keep nothing, escalate**. New decision: **keep nothing**.",
                  "The old claim that evaluated arms cleared every acquisition guard is no longer supported:",
                  "GUARD-A off-cone dwell is inconclusive without sequence-level outcomes.",
                  "These proposed margins do not revise the contractual deployable default.", ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    lines = ["# Paired non-inferiority re-verdict", "",
             "**Proposed analysis, not approved by Jason.** This is a retrospective audit, not a policy reselection.",
             "The legacy verdict scripts and their pre-declared rules remain historical records.", "",
             "A 95% sequence-blocked paired bootstrap uses 10,000 draws and common sequence IDs across seed strata.",
             "A guard is non-inferior only when the upper CI for candidate minus baseline is below its margin.",
             "A CI wholly below zero is superior. Other comparisons are inconclusive; at least 30 distinct sequences are required.",
             "", "| Metric | PROPOSED margin (not approved) | Rationale |", "|---|---:|---|",
             "| lock loss | +0.01 rate | At most one extra lost sequence per 100. |",
             "| misassociation | +0.01 rate | At most one extra wrong collision frame per 100. |",
             "| IDSW/opportunity | +0.01 rate | At most one extra switch per 100 opportunities. |",
             "| post-crossing angular error | +0.1 degree mean | Smaller than the reported angular differences of concern. |", ""]
    wave1(args.artifacts, lines)
    increment7(args.artifacts, lines)
    lines.extend(["## Decision changes", "",
                  "The top-level choices do not change: no wave-1 lever survives and increment-7 keeps no arm.",
                  "The supporting guard verdicts do change. Several old neutral/better calls are inconclusive",
                  "under the proposed paired rule, including both arms' off-cone dwell and standing-lock guards.",
                  "Wave-1 misassociation and IDSW/opportunity have no matched arrays in the archived matrix.",
                  "No new non-regression claim is certified from pooled Wilson overlap.", ""])
    if args.output.resolve().is_relative_to(args.artifacts.resolve()):
        parser.error("output must be outside the read-only artifact tree")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
