#!/usr/bin/env python3
"""patch_smartdesign_axi_target_experiment.py — discriminating experiment.

Hypothesis under test: the post-Tasks-1+2 closure produced resource numbers
indistinguishable from the pre-integration baseline because nv_pid_top's
AXI4-target inputs (Kp/Ki/Kd/out_min/out_max/inner_clamp_setpoint) are still
tied to literal zero, so Synplify constant-folds the entire multiplier chain
to zero regardless of error/u_AI_in being driven by non-constant taps.

This patcher rewires the highest-impact axi4target inputs from constants
to non-constant FIC_0 AXI master signals, sufficient for Synplify to see
"writes to gain registers might happen with non-zero data."

If the gain-fold hypothesis is correct: after re-synth, `nv_pid_top_0` will
appear in MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv
with non-trivial LUT/DFF counts (multipliers + state preserved). If the
hypothesis is wrong, the hier-CSV will still be empty for nv_pid_top_0.

Either result is informative.

This is a SYNTH-ONLY EXPERIMENT. The rewires use the same FIC_0 master
signals as pid_io_block's tap, so the AXI traffic isn't address-decoded
properly — gain-register writes won't be reliably software-controllable.
That's fine for the discriminating test. Follow-on proper wiring is a
separate effort.

Usage:
  python3 patch_smartdesign_axi_target_experiment.py \\
      <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_axi_target_experiment.py --check <path>

Backup: overwrites <path>.pre_axi_experiment.bak.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ALREADY_APPLIED_MARKER = "// axi4target experiment rewires"

# Each tuple: (anchor_regex, replacement, description, expected_count)
PATCHES: list[tuple[re.Pattern[str], str, str, int]] = [
    # 1. Replace const_net_0 assigns for the W channel data path.
    (
        re.compile(
            r"^assign axi4target_awaddr_const_net_0\s*=\s*6'h00\s*;\s*$",
            re.MULTILINE,
        ),
        "// axi4target experiment rewires (gain-fold discriminating test)\n"
        "assign axi4target_awaddr_const_net_0             = "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[5:0];",
        "rewire axi4target_awaddr <- FIC_0 master AWADDR[5:0]",
        1,
    ),
    (
        re.compile(
            r"^assign axi4target_wdata_const_net_0\s*=\s*64'h0+\s*;\s*$",
            re.MULTILINE,
        ),
        "assign axi4target_wdata_const_net_0              = "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[63:0];",
        "rewire axi4target_wdata <- FIC_0 master WDATA[63:0]",
        1,
    ),
    (
        re.compile(
            r"^assign axi4target_wstrb_const_net_0\s*=\s*8'h00\s*;\s*$",
            re.MULTILINE,
        ),
        "assign axi4target_wstrb_const_net_0              = 8'hFF;",
        "set axi4target_wstrb to all-ones (writes always strobe all bytes)",
        1,
    ),
    # 2. Rewire direct GND_net ties on the nv_pid_top_0 instance to
    #    non-constant FIC_0 signals.
    (
        re.compile(r"\.axi4target_awvalid\s*\(\s*GND_net\s*\)"),
        ".axi4target_awvalid      ( "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID )",
        "rewire .axi4target_awvalid <- FIC_0 master AWVALID",
        1,
    ),
    (
        re.compile(r"\.axi4target_wvalid\s*\(\s*GND_net\s*\)"),
        ".axi4target_wvalid       ( "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID )",
        "rewire .axi4target_wvalid <- FIC_0 master WVALID",
        1,
    ),
    (
        re.compile(r"\.axi4target_bready\s*\(\s*GND_net\s*\)"),
        ".axi4target_bready       ( 1'b1 )",
        "rewire .axi4target_bready <- 1'b1 (always ready)",
        1,
    ),
]


def patch_file(text: str) -> tuple[str, list[str]]:
    if ALREADY_APPLIED_MARKER in text:
        raise ValueError(
            f"already-applied marker {ALREADY_APPLIED_MARKER!r} found. "
            "Restore from .pre_axi_experiment.bak if you want to re-patch."
        )

    log: list[str] = []
    for pattern, replacement, desc, expected_count in PATCHES:
        matches = pattern.findall(text)
        if len(matches) != expected_count:
            raise ValueError(
                f"anchor '{desc}' matched {len(matches)} times, "
                f"expected exactly {expected_count}"
            )
        text = pattern.sub(replacement, text, count=expected_count)
        log.append(f"  ok: {desc}")

    return text, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1

    original = args.path.read_text()
    try:
        patched, log = patch_file(original)
    except ValueError as exc:
        print(f"PATCH FAILED: {exc}", file=sys.stderr)
        return 1

    if args.check:
        print("dry run — patch applies cleanly:")
        for line in log:
            print(line)
        return 0

    backup = args.path.with_suffix(args.path.suffix + ".pre_axi_experiment.bak")
    shutil.copy2(args.path, backup)
    args.path.write_text(patched)
    print(f"patched {args.path}")
    print(f"backup at {backup}")
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
