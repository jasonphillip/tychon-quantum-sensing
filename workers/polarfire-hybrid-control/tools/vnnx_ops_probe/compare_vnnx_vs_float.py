#!/usr/bin/env python3
"""Compare VNNX-simulator output to the float reference for one op-probe model.

Runs on bee (or anywhere with numpy) after the SDK simulator has produced per-sample outputs
for the fixed input set. Reports max / mean abs error vs the FLOAT reference saved by
export_ops_probe.py. If the sim output is int8, pass --out-scale/--out-zp (from
ops_probe_manifest.json) to dequantize first; if it is already float, omit them.

Usage:
  python3 compare_vnnx_vs_float.py --fixed gru_cell_onestep_fixed_io.npz \
      --sim gru_cell_onestep_sim_out.npy [--out-scale S --out-zp Z] --model gru_cell_onestep
"""
from __future__ import annotations

import argparse

import numpy as np


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixed", required=True, help="*_fixed_io.npz with a 'ref' float array")
    ap.add_argument("--sim", required=True, help="simulator output (.npy), same shape as ref")
    ap.add_argument("--model", default="")
    ap.add_argument("--out-scale", type=float, default=None, help="int8 output scale (dequantize)")
    ap.add_argument("--out-zp", type=int, default=None, help="int8 output zero-point")
    args = ap.parse_args()

    ref = np.load(args.fixed)["ref"].astype(np.float64)
    sim = np.load(args.sim).astype(np.float64)
    if args.out_scale is not None and args.out_zp is not None:
        sim = (sim - args.out_zp) * args.out_scale  # dequantize int8 sim output

    if sim.shape != ref.shape:
        # allow flattened comparison if the element count matches
        if sim.size == ref.size:
            sim = sim.reshape(ref.shape)
        else:
            raise SystemExit(f"shape mismatch: sim {sim.shape} vs ref {ref.shape}")

    err = np.abs(sim - ref)
    print(f"model={args.model or args.fixed}")
    print(f"  n={ref.size}  max_abs_err={err.max():.6f}  mean_abs_err={err.mean():.6f}  "
          f"ref_range=[{ref.min():.4f},{ref.max():.4f}]")
    # An INT8 model at ~1/128 resolution should land in the low-1e-2 range; a gross mismatch
    # (>~0.1 for these ranges) means the op was mis-compiled, not merely requantized.
    verdict = "SMALL (op behaves)" if err.max() < 0.1 else "LARGE (investigate op mapping)"
    print(f"  verdict: max_abs_err is {verdict}")


if __name__ == "__main__":
    main()
