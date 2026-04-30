#!/usr/bin/env python3
"""patch_smartdesign_watchdog.py — apply watchdog_timer integration patches
to the SmartDesign-generated MPFS_ICICLE_KIT_BASE_DESIGN.v.

Runs AFTER patch_smartdesign_top.py (Task 1). Applies these edits:
  1. Declare wire watchdog_timer_0_timeout near other Phase I wires.
  2. Insert watchdog_timer_0 instantiation immediately after the
     pid_io_block_0 instance.
  3. Rewire nv_pid_top_0.ai_watchdog_timeout from GND_net to
     watchdog_timer_0_timeout.
  4. Re-point the nv_pid_top_0_ai_watchdog_timeout_observed assign (declared
     by Task 1) so pid_io_block_0's status CSR sees the live timeout signal
     instead of GND_net. This is what audit gate `--require-status-csrs`
     checks for the watchdog readback path.
  5. (Heartbeat selection) The default heartbeat source is
     MSS_WRAPPER_1_GPIO_2_M2F_28 — non-constant test stimulus that defeats
     Synplify constant-folding so the watchdog instance and downstream
     timeout propagation are preserved. Pass --vbx-output-valid to use the
     CoreVectorBlox output_valid signal through vbx_completion_sync.v
     instead. Per HB0919 §6.4 p.15 / §4.1 p.7-8 the output_valid signal is
     level-held until firmware clears it, so a 2-FF synchronizer + rising-
     edge detector is required between the IP and the watchdog. Use this
     mode only when the SmartDesign canvas exposes Vectorblox_ss.output_valid
     up through FIC_0_PERIPHERALS — see Phase II TODO in
     libero/hdl/watchdog_timer.v.

Usage:
  python3 patch_smartdesign_watchdog.py <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_watchdog.py --check <path>
  python3 patch_smartdesign_watchdog.py --vbx-output-valid <path>

Backup: overwrites <path>.pre_watchdog.bak on each run.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

TASK1_REQUIRED_MARKER = "pid_io_block pid_io_block_0"
ALREADY_APPLIED_MARKER = "watchdog_timer watchdog_timer_0"

NEW_WIRE = "wire        watchdog_timer_0_timeout;\n"

# When --vbx-output-valid is set, declare the synchronizer helper wire.
VBX_SYNC_WIRES = (
    "wire        vbx_output_valid_pulse;  // edge-detected, sync'd to FIC_0_CLK\n"
)

# Default heartbeat — Phase I MSS GPIO test stimulus
WATCHDOG_INSTANCE_GPIO = """\

//--------watchdog_timer (Phase I integration: replaces GND_net binding on
//        nv_pid_top_0.ai_watchdog_timeout. Heartbeat source is currently
//        MSS_WRAPPER_1_GPIO_2_M2F_28 as test stimulus — defeats Synplify
//        constant-folding so the watchdog instance and downstream timeout
//        propagation are preserved. Phase II will replace the heartbeat
//        with CoreVectorBlox output_valid (HB0919 Table 5-4) once the
//        Vectorblox_ss / FIC_0_PERIPHERALS canvas wiring exposes it. Pass
//        --vbx-output-valid to patch_smartdesign_watchdog.py to switch.)
watchdog_timer #(
    .WATCHDOG_TIMEOUT_CYCLES(200000)
) watchdog_timer_0 (
        .clk          ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .resetn       ( CLOCKS_AND_RESETS_RESETN_FIC_0_CLK ),
        .ai_heartbeat ( MSS_WRAPPER_1_GPIO_2_M2F_28 ),
        .timeout      ( watchdog_timer_0_timeout )
        );

"""

# CoreVectorBlox output_valid path — preferred Phase II per corpus.
# vbx_completion_sync ingests the level-held output_valid bit, synchronizes
# it to the watchdog clock domain, and emits a one-cycle rising-edge pulse
# per inference completion.
WATCHDOG_INSTANCE_VBX = """\

//--------vbx_completion_sync (corpus-backed: HB0919 §6.4 p.15 / §4.1 p.7-8.
//        output_valid is level-held until firmware clears it via Control
//        Register bit 3, so each inference completion is a level transition
//        — never a self-clearing pulse. We synchronize to FIC_0_CLK with a
//        2-FF flop chain and convert to a one-cycle rising-edge pulse per
//        completion before driving the watchdog refresh.)
vbx_completion_sync vbx_completion_sync_0 (
        .clk           ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .resetn        ( CLOCKS_AND_RESETS_RESETN_FIC_0_CLK ),
        .output_valid  ( Vectorblox_ss_output_valid ),
        .pulse         ( vbx_output_valid_pulse )
        );

//--------watchdog_timer (Phase II integration: heartbeat is the synchronized
//        rising-edge pulse from CoreVectorBlox output_valid via
//        vbx_completion_sync. The watchdog's internal heartbeat_rising
//        detector still fires on the pulse for consistency with Phase I.)
watchdog_timer #(
    .WATCHDOG_TIMEOUT_CYCLES(200000)
) watchdog_timer_0 (
        .clk          ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .resetn       ( CLOCKS_AND_RESETS_RESETN_FIC_0_CLK ),
        .ai_heartbeat ( vbx_output_valid_pulse ),
        .timeout      ( watchdog_timer_0_timeout )
        );

"""


def patch_file(text: str, *, use_vbx_output_valid: bool) -> tuple[str, list[str]]:
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
    if use_vbx_output_valid and "Vectorblox_ss_output_valid" not in text:
        raise ValueError(
            "--vbx-output-valid requires the SmartDesign canvas to expose "
            "Vectorblox_ss.output_valid up through FIC_0_PERIPHERALS as the "
            "top-level signal `Vectorblox_ss_output_valid`. Not found. "
            "Re-export the port from the Vectorblox_ss / FIC_0_PERIPHERALS "
            "components first, or run without --vbx-output-valid for the "
            "Phase I GPIO heartbeat."
        )

    # 1. Insert the new wire(s) before the existing AXI4-Lite slave response
    #    signal block (anchored to the comment line written by Task 1).
    anchor = re.compile(
        r"^// AXI4-Lite slave response signals \(drained by tying", re.MULTILINE
    )
    matches = anchor.findall(text)
    if len(matches) != 1:
        raise ValueError(
            f"wire-insertion anchor matched {len(matches)} times, expected 1"
        )
    new_wires = NEW_WIRE
    if use_vbx_output_valid:
        new_wires += VBX_SYNC_WIRES
    text = anchor.sub(
        new_wires + "// AXI4-Lite slave response signals (drained by tying",
        text,
        count=1,
    )
    log.append("  ok: inserted watchdog wire declaration(s)")

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

    # 3. Update the observed-watchdog assign so pid_io_block_0 sees the live
    #    timeout net rather than GND_net.
    observed_assign_pat = re.compile(
        r"^assign\s+nv_pid_top_0_ai_watchdog_timeout_observed\s*=\s*GND_net\s*;",
        re.MULTILINE,
    )
    obs_matches = observed_assign_pat.findall(text)
    if len(obs_matches) != 1:
        raise ValueError(
            "nv_pid_top_0_ai_watchdog_timeout_observed anchor matched "
            f"{len(obs_matches)} times, expected 1 (was the patched Task 1 "
            "wire block emitted?)"
        )
    text = observed_assign_pat.sub(
        "assign nv_pid_top_0_ai_watchdog_timeout_observed = "
        "watchdog_timer_0_timeout;",
        text,
        count=1,
    )
    log.append("  ok: rewired nv_pid_top_0_ai_watchdog_timeout_observed <- watchdog_timer_0_timeout")

    # 4. Insert watchdog_timer_0 instantiation right after pid_io_block_0's
    #    closing `);`.
    pid_io_end = re.compile(
        r"(pid_io_block pid_io_block_0\(.*?\n\s*\);)",
        re.DOTALL,
    )
    m = pid_io_end.search(text)
    if not m:
        raise ValueError("could not locate pid_io_block_0 instantiation block")
    insertion_point = m.end()
    instance_block = (
        WATCHDOG_INSTANCE_VBX if use_vbx_output_valid else WATCHDOG_INSTANCE_GPIO
    )
    text = (
        text[:insertion_point]
        + "\n"
        + instance_block
        + text[insertion_point:]
    )
    if use_vbx_output_valid:
        log.append("  ok: inserted vbx_completion_sync_0 + watchdog_timer_0 (Phase II)")
    else:
        log.append("  ok: inserted watchdog_timer_0 instantiation (Phase I GPIO)")

    return text, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument(
        "--vbx-output-valid",
        action="store_true",
        help="Use CoreVectorBlox output_valid via vbx_completion_sync rather "
        "than MSS GPIO test stimulus (requires SmartDesign canvas to "
        "expose Vectorblox_ss_output_valid up to top level).",
    )
    args = ap.parse_args()

    if not args.path.is_file():
        print(f"ERROR: file not found: {args.path}", file=sys.stderr)
        return 1

    original = args.path.read_text()
    try:
        patched, log = patch_file(
            original, use_vbx_output_valid=args.vbx_output_valid
        )
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
