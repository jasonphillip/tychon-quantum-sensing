"""Wave-1 survival verdicts: lever vs baseline over the standing v1-test matrix (2c).

Implements the deterministic survival rule from the 2c parallel amendment — no judgment
calls, so wave 2 can launch unattended:

  A lever SURVIVES iff, at every noise rung x trajectory family of the v1-test matrix,
    (a) FIELD does not regress beyond CI:
        - lock_loss: the lever's Wilson-CI lower bound does not exceed the baseline's
          upper bound (CI-disjoint worsening = regression), and
        - post-crossing angular error: a paired per-sequence bootstrap (identical
          sequences + identical fixed-seed noise for every tracker) of the median
          difference (lever - baseline) has a 95% CI entirely above zero = regression;
    (b) IDENTITY (misassoc, sw/opp) improves or is neutral: no CI-disjoint worsening.

Run after the wave-1 matrix:
    python experiments/noise_matrix_report.py --only v1 \
        --v1-runs artifacts/increment2c --out artifacts/noise_matrix/matrix_2c_wave1.json
    python experiments/wave1_verdict.py --matrix artifacts/noise_matrix/matrix_2c_wave1.json

Writes ``survivors.json`` next to the matrix (consumed by the wave-2 launcher) and prints
the per-cell comparison table, including the CV-KF crown columns for the report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

BOOT_N = 10_000
BOOT_SEED = 0  # deterministic verdicts

# Wave-1 run-dir names (checkpoint labels embed them) and the lever each carries.
BASELINE_RUN = "v2_gated_linear_snr10"
LEVER_RUNS = {
    "v2_gated_linear_snr10_soft": "soft_targets",
    "v2_gated_linear_snr10_sinkhorn": "sinkhorn",
    "v2_gated_linear_snr10_ss": "scheduled_sampling",
}


def find_label(cells: dict, run_name: str) -> str | None:
    """Match a tracker label like ``learned-gated+linear+aug[<run_name>]`` in a cell dict."""
    for label in cells:
        if label.endswith(f"[{run_name}]"):
            return label
    return None


def ci_disjoint_worse(lever: list, base: list) -> bool:
    """[k, n, lo, hi] proportions: lever regressed beyond CI iff its lo exceeds base hi."""
    return float(lever[2]) > float(base[3])


def paired_median_diff_ci(
    lever_vals: list[float], base_vals: list[float]
) -> tuple[float, float, float, int]:
    """Bootstrap 95% CI of median(lever - base) over paired non-NaN sequences."""
    a = np.asarray(lever_vals, dtype=float)
    b = np.asarray(base_vals, dtype=float)
    ok = ~(np.isnan(a) | np.isnan(b))
    d = (a - b)[ok]
    if d.size == 0:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(BOOT_SEED)
    idx = rng.integers(0, d.size, size=(BOOT_N, d.size))
    boots = np.median(d[idx], axis=1)
    return float(np.median(d)), float(np.percentile(boots, 2.5)), float(
        np.percentile(boots, 97.5)
    ), int(d.size)


def main() -> int:
    ap = argparse.ArgumentParser(description="Wave-1 survival verdicts (2c amendment rule)")
    ap.add_argument("--matrix", type=Path, required=True)
    ap.add_argument("--dataset", type=str, default="v1",
                    help="matrix dataset key holding the standing eval (default v1)")
    args = ap.parse_args()

    with open(args.matrix) as fh:
        matrix = json.load(fh)
    rungs = matrix["datasets"][args.dataset]["cells"]

    verdicts: dict[str, dict] = {}
    for run_name, lever in LEVER_RUNS.items():
        failures: list[str] = []
        details: list[str] = []
        seen = False
        for rung, cells in rungs.items():
            base_label = find_label(cells, BASELINE_RUN)
            lever_label = find_label(cells, run_name)
            if base_label is None or lever_label is None:
                continue
            seen = True
            for fam in sorted(cells[base_label]):
                b, lv = cells[base_label][fam], cells[lever_label][fam]
                cell = f"{rung}/{fam}"
                # (a) field: lock-loss CI-disjoint regression
                if ci_disjoint_worse(lv["lock_loss"], b["lock_loss"]):
                    failures.append(f"{cell}: lock_loss {lv['lock_loss'][:2]} vs "
                                    f"{b['lock_loss'][:2]} (CI-disjoint)")
                # (a) field: paired post-crossing angular error
                med, lo, hi, n = paired_median_diff_ci(lv["ae_post_all"], b["ae_post_all"])
                if n > 0 and lo > 0.0:
                    failures.append(f"{cell}: ae_post paired Δmed {med:+.2f}° "
                                    f"CI [{lo:+.2f}, {hi:+.2f}] (n={n}, regression)")
                details.append(f"    {cell}: ae_post Δmed {med:+.2f}° [{lo:+.2f},{hi:+.2f}]")
                # (b) identity: no CI-disjoint worsening
                for key in ("misassoc", "idsw_opp"):
                    if ci_disjoint_worse(lv[key], b[key]):
                        failures.append(
                            f"{cell}: {key} {lv[key][0]}/{lv[key][1]} vs "
                            f"{b[key][0]}/{b[key][1]} (CI-disjoint)"
                        )
        if not seen:
            print(f"[warn] {run_name}: not found in matrix — no verdict")
            continue
        verdicts[run_name] = {
            "lever": lever,
            "survives": not failures,
            "failures": failures,
        }
        print(f"\n=== {lever} ({run_name}): "
              f"{'SURVIVES' if not failures else 'ELIMINATED'} ===")
        for f in failures:
            print(f"  FAIL {f}")
        for d in details:
            print(d)

    survivors = [v["lever"] for v in verdicts.values() if v["survives"]]
    out = {
        "baseline_run": BASELINE_RUN,
        "verdicts": verdicts,
        "survivors": survivors,
        "combo": survivors if survivors else None,  # None => wave 2 = baseline x 3 seeds
    }
    out_path = args.matrix.parent / "survivors.json"
    with open(out_path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\n[survivors] {survivors or '(none — wave 2 = baseline x 3 seeds)'}")
    print(f"[verdict] saved {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
