#!/usr/bin/env python3
"""patch_smartdesign_watchdog.py — apply watchdog_timer integration patches
to the SmartDesign-generated MPFS_ICICLE_KIT_BASE_DESIGN.v.

Runs AFTER patch_smartdesign_top.py (Task 1). Applies three edits:
  1. Declare wire watchdog_timer_0_timeout near other Phase I wires.
  2. Insert watchdog_timer_0 instantiation immediately after the
     pid_io_block_0 instance.
  3. Rewire nv_pid_top_0.ai_watchdog_timeout from GND_net to
     watchdog_timer_0_timeout.

Heartbeat source: MSS_WRAPPER_1_GPIO_2_M2F_28 (Approach B, test stimulus).
HB0919-documented Approach A (CoreVectorBlox output_valid interrupt port,
mirror of Control Register bit 3 at offset 0x00) is the Phase II target;
the IP exports the signal correctly but the existing SmartDesign canvas
leaves Vectorblox_ss.v line 467 with `.output_valid ( )` and the parent
FIC_0_PERIPHERALS sub-component does not propagate it up. Wiring it
properly requires patching both Microchip-shipped sub-components, which
is deferred — see Phase II TODO in libero/hdl/watchdog_timer.v.

Usage:
  python3 patch_smartdesign_watchdog.py <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_watchdog.py --check <path>   # dry run

Backup: overwrites <path>.pre_watchdog.bak on each run.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# --- Sentinel: this patch requires Task 1 to already be applied -----------
TASK1_REQUIRED_MARKER = "pid_io_block pid_io_block_0"

# --- Already-applied marker (idempotency guard) ---------------------------
ALREADY_APPLIED_MARKER = "watchdog_timer watchdog_timer_0"

# --- New wire (just before `// AXI4-Lite slave response signals`) ---------
NEW_WIRE = "wire        watchdog_timer_0_timeout;\n"

# --- watchdog_timer_0 instantiation ---------------------------------------
WATCHDOG_INSTANCE = """\

//--------watchdog_timer (Phase I integration: replaces GND_net binding on
//        nv_pid_top_0.ai_watchdog_timeout. Heartbeat source is currently
//        MSS_WRAPPER_1_GPIO_2_M2F_28 as test stimulus — defeats Synplify
//        constant-folding so the watchdog instance and downstream timeout
//        propagation are preserved. Phase II will replace the heartbeat
//        with CoreVectorBlox output_valid (HB0919 Table 5-4) once the
//        Vectorblox_ss / FIC_0_PERIPHERALS canvas wiring exposes it.)
watchdog_timer #(
    .WATCHDOG_TIMEOUT_CYCLES(200000)
) watchdog_timer_0 (
        .clk          ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .resetn       ( CLOCKS_AND_RESETS_RESETN_FIC_0_CLK ),
        .ai_heartbeat ( MSS_WRAPPER_1_GPIO_2_M2F_28 ),
        .timeout      ( watchdog_timer_0_timeout )
        );

"""


def patch_file(text: str) -> tuple[str, list[str]]:
    log: list[str] = []

    if TASK1_REQUIRED_MARKER not in text:
        raise ValueError(
            f"Task 1 marker {TASK1_REQUIRED_MARKER!r} not found — "
            "apply patch_smartdesign_top.py first"
        )
    if ALREADY_APPLIED_MARKER in text:
        raise ValueError(
            f"already-applied marker {ALREADY_APPLIED_MARKER!r} found. "
            "Restore from .pre_watchdog.bak if you want to re-patch."
        )

    # 1. Insert the new wire before the existing AXI4-Lite slave response
    #    signal block (anchored to the comment line written by Task 1).
    anchor = re.compile(
        r"^// AXI4-Lite slave response signals \(drained by tying", re.MULTILINE
    )
    matches = anchor.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"wire-insertion anchor matched {len(matches)} times, expected 1"
        )
    text = anchor.sub(
        NEW_WIRE + "// AXI4-Lite slave response signals (drained by tying",
        text,
        count=1,
    )
    log.append("  ok: inserted watchdog_timer_0_timeout wire declaration")

    # 2. Rewire nv_pid_top_0.ai_watchdog_timeout from GND_net.
    aw_pat = re.compile(r"\.ai_watchdog_timeout\s*\(\s*GND_net\s*\)")
    aw_matches = aw_pat.findall(text)
    if len(aw_matches) != 1:
        raise ValueError(
            f"ai_watchdog_timeout anchor matched {len(aw_matches)} times, expected 1"
        )
    text = aw_pat.sub(
        ".ai_watchdog_timeout     ( watchdog_timer_0_timeout )",
        text,
        count=1,
    )
    log.append("  ok: rewired nv_pid_top_0.ai_watchdog_timeout <- watchdog_timer_0")

    # 3. Insert watchdog_timer_0 instantiation right after pid_io_block_0's
    #    closing `);`. The block was placed by patch_smartdesign_top.py.
    pid_io_end = re.compile(
        r"(pid_io_block pid_io_block_0\(.*?\n\s*\);)",
        re.DOTALL,
    )
    m = pid_io_end.search(text)
    if not m:
        raise ValueError("could not locate pid_io_block_0 instantiation block")
    insertion_point = m.end()
    text = (
        text[:insertion_point]
        + "\n"
        + WATCHDOG_INSTANCE
        + text[insertion_point:]
    )
    log.append("  ok: inserted watchdog_timer_0 instantiation")

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

    backup = args.path.with_suffix(args.path.suffix + ".pre_watchdog.bak")
    shutil.copy2(args.path, backup)
    args.path.write_text(patched)
    print(f"patched {args.path}")
    print(f"backup at {backup}")
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
