#!/usr/bin/env python3
"""patch_smartdesign_top.py — apply pid_io_block integration patches to
the SmartDesign-generated MPFS_ICICLE_KIT_BASE_DESIGN.v.

This is a hand-rolled patch because the Phase I integration deliberately
avoids SmartDesign canvas surgery (which would require GUI work or extensive
Tcl that isn't worth the risk inside the time budget). The patch is
deterministic: each edit is anchored to a specific regex; a missing anchor
aborts the run.

Effects:
  1. Declare wires for the new nv_pid_top_0 outputs and pid_io_block_0 outputs.
  2. Replace the assigns of error_const_net_0 / u_AI_in_const_net_0 so they
     come from pid_io_block_0 outputs (defeats Synplify constant-folding).
  3. Replace the unbound nv_pid_top_0 .actuator_out_write_en/_data ports
     with named nets feeding pid_io_block_0.
  4. Insert pid_io_block_0 instantiation immediately after the nv_pid_top_0
     instantiation, with its AXI master-side tapped from non-constant
     MSS-driven FIC_0 AXI signals (test stimulus only — Phase II will route
     a dedicated AXI4-Lite interconnect branch to this slave).

Usage:
  python3 patch_smartdesign_top.py <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_top.py --check <path>   # dry run, exit 0 if clean

Backup: overwrites <path>.pre_pid_io.bak on each run.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

# --- New wire declarations to add (just before the first 'assign' block) ---
NEW_WIRES = """\
// ----- pid_io_block_0 integration (Phase I) -----------------------------
wire [31:0] nv_pid_top_0_actuator_out_write_data;
wire        nv_pid_top_0_actuator_out_write_en;
wire [63:0] pid_io_block_0_error_out;
wire [31:0] pid_io_block_0_u_ai_out;
// AXI4-Lite slave response signals (drained by tying *_RREADY=1, *_BREADY=1)
wire        pid_io_block_0_AWREADY;
wire        pid_io_block_0_WREADY;
wire [1:0]  pid_io_block_0_BRESP;
wire        pid_io_block_0_BVALID;
wire        pid_io_block_0_ARREADY;
wire [31:0] pid_io_block_0_RDATA;
wire [1:0]  pid_io_block_0_RRESP;
wire        pid_io_block_0_RVALID;
// ------------------------------------------------------------------------
"""

# --- pid_io_block_0 instantiation -----------------------------------------
PID_IO_BLOCK_INSTANCE = """\

//--------pid_io_block (Phase I integration: defeats Synplify constant-folding
//        of nv_pid_top inputs and provides actuator_out readback register
//        block. AXI master-side is tapped from MSS-driven FIC_0 AXI signals
//        as test stimulus; Phase II will route a dedicated AXI4-Lite
//        interconnect branch here. Register map — see libero/hdl/pid_io_block.v.)
pid_io_block pid_io_block_0(
        // AXI4-Lite slave clock/reset
        .S_AXI_ACLK              ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .S_AXI_ARESETN           ( CLOCKS_AND_RESETS_RESETN_FIC_0_CLK ),
        // Write address (tap from MSS->FIC_0 AXI master traffic)
        .S_AXI_AWADDR            ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[11:0] ),
        .S_AXI_AWPROT            ( 3'b000 ),
        .S_AXI_AWVALID           ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID ),
        .S_AXI_AWREADY           ( pid_io_block_0_AWREADY ),
        // Write data
        .S_AXI_WDATA             ( FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[31:0] ),
        .S_AXI_WSTRB             ( 4'b1111 ),
        .S_AXI_WVALID            ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID ),
        .S_AXI_WREADY            ( pid_io_block_0_WREADY ),
        // Write response (drained)
        .S_AXI_BRESP             ( pid_io_block_0_BRESP ),
        .S_AXI_BVALID            ( pid_io_block_0_BVALID ),
        .S_AXI_BREADY            ( 1'b1 ),
        // Read address
        .S_AXI_ARADDR            ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR[11:0] ),
        .S_AXI_ARPROT            ( 3'b000 ),
        .S_AXI_ARVALID           ( MSS_WRAPPER_1_GPIO_2_M2F_16 ),
        .S_AXI_ARREADY           ( pid_io_block_0_ARREADY ),
        // Read data (drained)
        .S_AXI_RDATA             ( pid_io_block_0_RDATA ),
        .S_AXI_RRESP             ( pid_io_block_0_RRESP ),
        .S_AXI_RVALID            ( pid_io_block_0_RVALID ),
        .S_AXI_RREADY            ( 1'b1 ),
        // Connections to nv_pid_top
        .error_out               ( pid_io_block_0_error_out ),
        .u_ai_out                ( pid_io_block_0_u_ai_out ),
        .actuator_capture_in     ( nv_pid_top_0_actuator_out_write_data ),
        .actuator_capture_strobe ( nv_pid_top_0_actuator_out_write_en )
        );

"""

# --- Patch operations -----------------------------------------------------
# Each tuple: (anchor_regex, replacement, description, expected_count)
PATCHES = [
    # 1. Insert new wire declarations before the first 'assign axi4target_'
    (
        re.compile(r"^assign axi4target_araddr_const_net_0", re.MULTILINE),
        NEW_WIRES + "assign axi4target_araddr_const_net_0",
        "insert pid_io_block wire declarations",
        1,
    ),
    # 2. Rewrite error_const_net_0 assign to drive from pid_io_block
    (
        re.compile(r"^assign error_const_net_0\s*=\s*64'h0+\s*;\s*$", re.MULTILINE),
        "assign error_const_net_0                         = pid_io_block_0_error_out;",
        "rewire error_const_net_0 <- pid_io_block error_out",
        1,
    ),
    # 3. Rewrite u_AI_in_const_net_0 assign
    (
        re.compile(r"^assign u_AI_in_const_net_0\s*=\s*32'h0+\s*;\s*$", re.MULTILINE),
        "assign u_AI_in_const_net_0                       = pid_io_block_0_u_ai_out;",
        "rewire u_AI_in_const_net_0 <- pid_io_block u_ai_out",
        1,
    ),
    # 4. Bind nv_pid_top_0.actuator_out_write_en
    (
        re.compile(r"\.actuator_out_write_en\s*\(\s*\)"),
        ".actuator_out_write_en   ( nv_pid_top_0_actuator_out_write_en )",
        "bind nv_pid_top_0.actuator_out_write_en",
        1,
    ),
    # 5. Bind nv_pid_top_0.actuator_out_write_data
    (
        re.compile(r"\.actuator_out_write_data\s*\(\s*\)"),
        ".actuator_out_write_data ( nv_pid_top_0_actuator_out_write_data )",
        "bind nv_pid_top_0.actuator_out_write_data",
        1,
    ),
]

# --- Sentinels indicating the patch is already applied ---------------------
ALREADY_APPLIED_MARKERS = (
    "pid_io_block pid_io_block_0",
    "pid_io_block_0_error_out",
)


def patch_file(text: str) -> tuple[str, list[str]]:
    """Apply the patch sequence to text. Returns (new_text, log_lines).
    Raises ValueError on missing anchors."""
    log: list[str] = []
    for marker in ALREADY_APPLIED_MARKERS:
        if marker in text:
            raise ValueError(
                f"already-applied marker found: {marker!r}. "
                "Restore from .pre_pid_io.bak if you want to re-patch."
            )

    # Apply each pattern with strict count check
    for pattern, replacement, desc, expected_count in PATCHES:
        matches = pattern.findall(text)
        if len(matches) != expected_count:
            raise ValueError(
                f"anchor '{desc}' matched {len(matches)} times, "
                f"expected exactly {expected_count}"
            )
        text = pattern.sub(replacement, text, count=expected_count)
        log.append(f"  ok: {desc}")

    # Insert pid_io_block_0 instantiation right after nv_pid_top_0 closing );
    # The nv_pid_top_0 block ends with `        );\n`. Insert AFTER that.
    nv_pid_end = re.compile(
        r"(nv_pid_top_top nv_pid_top_0\(.*?\n\s*\);)",
        re.DOTALL,
    )
    m = nv_pid_end.search(text)
    if not m:
        raise ValueError("could not locate nv_pid_top_0 instantiation block")
    insertion_point = m.end()
    text = text[:insertion_point] + "\n" + PID_IO_BLOCK_INSTANCE + text[insertion_point:]
    log.append("  ok: inserted pid_io_block_0 instantiation")

    return text, log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument(
        "--check",
        action="store_true",
        help="dry run; exit 0 if patch would apply cleanly, 1 otherwise",
    )
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

    backup = args.path.with_suffix(args.path.suffix + ".pre_pid_io.bak")
    shutil.copy2(args.path, backup)
    args.path.write_text(patched)
    print(f"patched {args.path}")
    print(f"backup at {backup}")
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
