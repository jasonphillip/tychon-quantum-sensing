#!/usr/bin/env python3
"""CLI to materialize a synthetic v1 dataset (``dataset.h5`` + ``manifest.json``).

A thin wrapper over ``tests/fixtures/synthetic.write_synthetic_h5`` for smoke runs and manual
inspection. The output is a hand-scripted MOCK (not physics) that conforms to the v1 data
contract; it lets downstream code run before the real ``nv-sensor-sim`` data exists.

Usage:
    python scripts/make_fixture.py <out_dir> [--n-timesteps T] [--n-freq F] \
        [--train N] [--val N] [--test N] [--seed S]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make the repo root importable so ``tests.fixtures`` resolves when run as a script.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from odmr_vector_tracking.data.contract import validate_dataset_dir
from tests.fixtures.synthetic import write_synthetic_h5


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("out_dir", type=Path, help="Output directory for the fixture dataset")
    parser.add_argument("--n-timesteps", type=int, default=200)
    parser.add_argument("--n-freq", type=int, default=400)
    parser.add_argument("--train", type=int, default=4)
    parser.add_argument("--val", type=int, default=2)
    parser.add_argument("--test", type=int, default=2)
    parser.add_argument("--seed", type=int, default=0, help="master seed")
    args = parser.parse_args(argv)

    out = write_synthetic_h5(
        args.out_dir,
        split_sizes={"train": args.train, "val": args.val, "test": args.test},
        master_seed=args.seed,
        n_timesteps=args.n_timesteps,
        n_freq=args.n_freq,
    )
    # Validate what we just wrote — the fixture is only useful if it passes the contract.
    manifest = validate_dataset_dir(out)
    print(f"Wrote synthetic v1 fixture to {out}/ (dataset.h5 + manifest.json)")
    print(
        f"  splits: train={manifest['n_spectra_train']} "
        f"val={manifest['n_spectra_val']} test={manifest['n_spectra_test']} | "
        f"T={manifest['n_timesteps']} F={manifest['n_freq_points']} L={manifest['n_lines']}"
    )
    print("  contract validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
