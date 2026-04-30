#!/usr/bin/env python3
"""patch_smartdesign_pid_axi.py — P1 fix: real address-decoded AXI4-Lite path
for the nv_pid_top axi4target slave.

This is the production replacement for the discriminating
patch_smartdesign_axi_target_experiment.py. The experiment proved the
gain-fold hypothesis (without non-constant AXI inputs the PID multipliers
constant-fold to zero); this patch promotes the proof-of-hypothesis wiring
to a hand-off-able integration with full read+write channel coverage and
WSTRB tightened to all-or-nothing per CoreVectorBlox HB0919 p.12.

Effects on MPFS_ICICLE_KIT_BASE_DESIGN.v:

  WRITE CHANNEL — same as the experiment:
   * axi4target_awaddr  <- FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[5:0]
   * axi4target_wdata   <- FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[63:0]
   * axi4target_wstrb   <- 8'hFF  (full-width writes only — corpus rule)
   * axi4target_awvalid <- FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID
   * axi4target_wvalid  <- FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID
   * axi4target_bready  <- 1'b1   (drained — see RESIDUAL ISSUES)

  READ CHANNEL (NEW vs experiment):
   * axi4target_araddr  <- FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR[5:0]
   * axi4target_arvalid <- FIC_0_PERIPHERALS_1_AXI4mslave0_ARVALID
   * axi4target_rready  <- 1'b1   (drained — see RESIDUAL ISSUES)

  Without the read-channel rewires the SmartHLS slave keeps its read FSM
  parked, and audit gate `--require-status-csrs` cannot prove that a
  software register read returns the value it last wrote.

RESIDUAL ISSUES (deliberately left for Phase II SmartDesign canvas work):

  Both pid_io_block AND nv_pid_top's axi4target slave currently eavesdrop on
  the same FIC_0_PERIPHERALS_1_AXI4mslave0 traffic, with response channels
  drained to constant ready/zero. That is sufficient to keep the Synplify
  optimizer honest and to defeat constant-folding of the PID coefficients.
  It is NOT sufficient to give software a deterministic write-then-read
  contract: with two slaves listening on one bus, the read-data multiplexing
  is undefined.

  The production path requires SmartDesign canvas surgery — adding a
  CoreAXI4Interconnect IP with TWO slave slots (one for nv_pid_top, one for
  pid_io_block) at distinct address bases — which is GUI/Tcl work not
  amenable to a deterministic regex patch. See `docs/corpus_improvement_plan.md`
  Priority 1 acceptance criteria. This script applies the part of the fix
  that IS expressible as text edits and is the prerequisite for the canvas
  change.

ORDER OF OPERATIONS:

  This patch supersedes patch_smartdesign_axi_target_experiment.py — running
  both will fail because the patches share anchor points. If the experiment
  was previously applied, restore from .pre_axi_experiment.bak first.

Usage:
  python3 patch_smartdesign_pid_axi.py <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_pid_axi.py --check <path>

Backup: overwrites <path>.pre_pid_axi.bak.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ALREADY_APPLIED_MARKER = "// pid_axi production rewires"
EXPERIMENT_MARKER = "// axi4target experiment rewires"

# Each tuple: (anchor_regex, replacement, description, expected_count)
PATCHES: list[tuple[re.Pattern[str], str, str, int]] = [
    # 1. Replace const_net_0 assigns for the W channel data path.
    (
        re.compile(
            r"^assign axi4target_awaddr_const_net_0\s*=\s*6'h00\s*;\s*$",
            re.MULTILINE,
        ),
        "// pid_axi production rewires (P1 fix; supersedes experiment)\n"
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
        "set axi4target_wstrb to all-ones (HB0919 p.12: partial-byte writes undefined)",
        1,
    ),
    # 2. NEW vs experiment — the read channel: address (was unconnected) and
    #    arvalid (was GND_net).
    (
        re.compile(
            r"^assign axi4target_araddr_const_net_0\s*=\s*6'h00\s*;\s*$",
            re.MULTILINE,
        ),
        "assign axi4target_araddr_const_net_0             = "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR[5:0];",
        "rewire axi4target_araddr <- FIC_0 master ARADDR[5:0]",
        1,
    ),
    (
        re.compile(r"\.axi4target_arvalid\s*\(\s*GND_net\s*\)"),
        ".axi4target_arvalid      ( "
        "FIC_0_PERIPHERALS_1_AXI4mslave0_ARVALID )",
        "rewire .axi4target_arvalid <- FIC_0 master ARVALID",
        1,
    ),
    (
        re.compile(r"\.axi4target_rready\s*\(\s*GND_net\s*\)"),
        ".axi4target_rready       ( 1'b1 )",
        "rewire .axi4target_rready <- 1'b1 (drained — see RESIDUAL ISSUES)",
        1,
    ),
    # 3. Same write-channel rewires as the experiment.
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
        "rewire .axi4target_bready <- 1'b1 (drained — see RESIDUAL ISSUES)",
        1,
    ),
]


def patch_file(text: str) -> tuple[str, list[str]]:
    if ALREADY_APPLIED_MARKER in text:
        raise ValueError(
            f"already-applied marker {ALREADY_APPLIED_MARKER!r} found. "
            "Restore from .pre_pid_axi.bak if you want to re-patch."
        )
    if EXPERIMENT_MARKER in text:
        raise ValueError(
            "experimental patch marker found "
            f"{EXPERIMENT_MARKER!r} — restore from .pre_axi_experiment.bak "
            "before applying the production patch (the two share anchors)."
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

    backup = args.path.with_suffix(args.path.suffix + ".pre_pid_axi.bak")
    shutil.copy2(args.path, backup)
    args.path.write_text(patched)
    print(f"patched {args.path}")
    print(f"backup at {backup}")
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
