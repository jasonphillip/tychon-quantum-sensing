#!/usr/bin/env python3
"""Launch wave 2 of the 2c retrain from the wave-1 survival verdicts.

Reads ``survivors.json`` (written by ``experiments/wave1_verdict.py``) and launches the
seeded final runs on the frozen reference recipe via ``scripts/train_run_2c.sh``:

- survivor combo x seeds {20260701, 20260711, 20260721} — minus any (config, seed) that
  already exists as a wave-1 run (a single-survivor combo IS that wave-1 run at 20260701);
- plus one extra baseline seed (20260711) for baseline seed-variance context;
- no survivors -> baseline x the two missing seeds (wave-1 A covers 20260701).

Placement alternates spark1 (local) / spark2 (ssh). Dry-run with --dry-run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
SEEDS = (20260701, 20260711, 20260721)
BASELINE_EXTRA_SEED = 20260711

LEVER_FLAGS = {
    "soft_targets": "--soft-targets",
    "sinkhorn": "--sinkhorn",
    "scheduled_sampling": "--scheduled-sampling",
}
LEVER_SUFFIX = {
    "soft_targets": "soft",
    "sinkhorn": "sinkhorn",
    "scheduled_sampling": "ss",
}
# Wave-1 runs (all at seed 20260701) keyed by their lever set.
WAVE1_BY_LEVERS = {
    frozenset(): "v2_gated_linear_snr10",
    frozenset({"soft_targets"}): "v2_gated_linear_snr10_soft",
    frozenset({"sinkhorn"}): "v2_gated_linear_snr10_sinkhorn",
    frozenset({"scheduled_sampling"}): "v2_gated_linear_snr10_ss",
}
WAVE1_SEED = 20260701


def run_name(levers: frozenset[str], seed: int) -> str:
    suffix = "".join(
        f"_{LEVER_SUFFIX[lever]}" for lever in sorted(levers, key=list(LEVER_FLAGS).index)
    )
    return f"v2_gated_linear_snr10{suffix}_s{seed}"


def main() -> int:
    ap = argparse.ArgumentParser(description="Launch 2c wave-2 seeded finals")
    ap.add_argument("--survivors", type=Path,
                    default=_REPO_ROOT / "artifacts" / "noise_matrix" / "survivors.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.survivors) as fh:
        sv = json.load(fh)
    combo = frozenset(sv["survivors"])
    print(f"[wave2] survivors: {sorted(combo) or '(none)'}")

    jobs: list[tuple[str, int, list[str]]] = []  # (name, seed, flags)
    flags = [LEVER_FLAGS[lever] for lever in sorted(combo, key=list(LEVER_FLAGS).index)]
    for seed in SEEDS:
        if seed == WAVE1_SEED and combo in WAVE1_BY_LEVERS:
            print(f"[wave2] combo @ {seed} == wave-1 run "
                  f"{WAVE1_BY_LEVERS[combo]} (reused, not relaunched)")
            continue
        jobs.append((run_name(combo, seed), seed, flags))
    # Baseline seed-variance run (skip if the combo IS the baseline — already queued above).
    if combo != frozenset():
        jobs.append((run_name(frozenset(), BASELINE_EXTRA_SEED), BASELINE_EXTRA_SEED, []))

    hosts = ("spark1", "spark2")
    for i, (name, seed, jflags) in enumerate(jobs):
        host = hosts[i % 2]
        cmd = ["bash", "scripts/train_run_2c.sh", name, str(seed), *jflags]
        if host == "spark1":
            full = cmd
        else:
            full = ["ssh", "spark2",
                    "cd ~/projects/odmr-vector-tracking && " + " ".join(cmd)]
        print(f"[wave2] {host}: {name} seed {seed} flags {jflags or '(none)'}")
        if not args.dry_run:
            subprocess.run(full, cwd=_REPO_ROOT, check=True)
    print(f"[wave2] {'DRY RUN — ' if args.dry_run else ''}{len(jobs)} runs dispatched")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
