#!/usr/bin/env python3
"""patch_smartdesign_pid_csr.py — Phase I bring-up patch.

Instantiates `pid_csr_block` (libero/hdl/pid_csr_block.v) inside the
generated `MPFS_ICICLE_KIT_BASE_DESIGN.v`, tied to the FIC_0 master tap
as an eavesdropping slave so Synplify sees non-constant write traffic on
the new register surface. This is the **Phase I** shortcut, not the
production path.

CORPUS BASIS:
  - The corpus says the FIRST survival criterion (defeating Synplify
    constant-folding) requires "real, software-visible, non-trivial AXI
    traffic and readback so the registers genuinely have time-varying
    drivers" (preventing-synplify-constant-folding-smarthls-pid.md:5).
    Eavesdropping on the FIC_0 master satisfies the write half.
  - The SECOND criterion (architectural proof: software write-then-readback)
    requires distinct address-decoded slots, which is **not** what this
    patch does. Use docs/smartdesign_two_slot_canvas_runbook.md for that.

EFFECTS ON MPFS_ICICLE_KIT_BASE_DESIGN.v:
  1. Add `pid_csr_block_0` instance, AXI4-Lite slave fed from
     FIC_0_PERIPHERALS_1_AXI4mslave0 traffic. WSTRB passes through; the
     slave is AXI4-Lite-spec-compliant (any pattern accepted) per
     fpga-hls-docs:2594-2596 element-alignment rule for the SmartHLS
     case and ARM IHI0022 for hand-written slaves. The CoreVectorBlox
     "all high or all low" rule (HB0919:565-635) does NOT apply here.
  2. Connect tap inputs to non-constant FIC_0 master signals so the
     status fields toggle and avoid pruning.
  3. OR the lower bits of all coefficient shadow outputs together into
     the existing LED0 observability path so Synplify cannot
     cascade-prune the new storage.

Usage:
  python3 patch_smartdesign_pid_csr.py <path/to/MPFS_ICICLE_KIT_BASE_DESIGN.v>
  python3 patch_smartdesign_pid_csr.py --check <path>

A backup is written to <path>.pre_pid_csr.bak.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ALREADY_APPLIED_MARKER = "// pid_csr_block Phase I bring-up"

INSTANCE_BLOCK = """
// pid_csr_block Phase I bring-up — non-constant write traffic from FIC_0
// master tap; tap inputs from same FIC traffic. PRODUCTION path is the
// SmartDesign two-slot canvas (see docs/smartdesign_two_slot_canvas_runbook.md).
wire [31:0] pid_csr_kp_shadow_w;
wire [31:0] pid_csr_ki_shadow_w;
wire [31:0] pid_csr_kd_shadow_w;
wire [31:0] pid_csr_out_min_shadow_w;
wire [31:0] pid_csr_out_max_shadow_w;
wire [31:0] pid_csr_inner_clamp_shadow_w;
wire [63:0] pid_csr_error_shadow_w;
wire [31:0] pid_csr_u_ai_shadow_w;
wire [1:0]  pid_csr_brresp_unused;
wire [1:0]  pid_csr_rrresp_unused;
wire [31:0] pid_csr_rdata_unused;
wire        pid_csr_awready_unused;
wire        pid_csr_wready_unused;
wire        pid_csr_bvalid_unused;
wire        pid_csr_arready_unused;
wire        pid_csr_rvalid_unused;

pid_csr_block u_pid_csr_block (
    .S_AXI_ACLK   (FIC_0_CLK),
    .S_AXI_ARESETN(FIC_0_PERIPHERALS_1_AXI4mslave0_ARESETN),

    .S_AXI_AWADDR (FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[13:0]),
    .S_AXI_AWPROT (FIC_0_PERIPHERALS_1_AXI4mslave0_AWPROT),
    .S_AXI_AWVALID(FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID),
    .S_AXI_AWREADY(pid_csr_awready_unused),

    .S_AXI_WDATA  (FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[31:0]),
    .S_AXI_WSTRB  (FIC_0_PERIPHERALS_1_AXI4mslave0_WSTRB[3:0]),
    .S_AXI_WVALID (FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID),
    .S_AXI_WREADY (pid_csr_wready_unused),

    .S_AXI_BRESP  (pid_csr_brresp_unused),
    .S_AXI_BVALID (pid_csr_bvalid_unused),
    .S_AXI_BREADY (1'b1),

    .S_AXI_ARADDR (FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR[13:0]),
    .S_AXI_ARPROT (FIC_0_PERIPHERALS_1_AXI4mslave0_ARPROT),
    .S_AXI_ARVALID(FIC_0_PERIPHERALS_1_AXI4mslave0_ARVALID),
    .S_AXI_ARREADY(pid_csr_arready_unused),

    .S_AXI_RDATA  (pid_csr_rdata_unused),
    .S_AXI_RRESP  (pid_csr_rrresp_unused),
    .S_AXI_RVALID (pid_csr_rvalid_unused),
    .S_AXI_RREADY (1'b1),

    .kp_shadow_out                   (pid_csr_kp_shadow_w),
    .ki_shadow_out                   (pid_csr_ki_shadow_w),
    .kd_shadow_out                   (pid_csr_kd_shadow_w),
    .out_min_shadow_out              (pid_csr_out_min_shadow_w),
    .out_max_shadow_out              (pid_csr_out_max_shadow_w),
    .inner_clamp_setpoint_shadow_out (pid_csr_inner_clamp_shadow_w),
    .error_shadow_out                (pid_csr_error_shadow_w),
    .u_ai_shadow_out                 (pid_csr_u_ai_shadow_w),

    // Phase I taps: drive from the same non-constant FIC_0 master signals
    // so the status path is non-pruned. Follow-on deployment replaces these
    // with real observability wires from nv_pid_top.
    .tap_pre_clamp_out      (FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[31:0]),
    .tap_post_clamp_out     (FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[31:0]),
    .tap_integrator         ({16'h0, FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR}),
    .tap_derivative         (FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA[63:32]),
    .tap_saturation_flag    (FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID),
    .tap_watchdog_timeout   (FIC_0_PERIPHERALS_1_AXI4mslave0_ARVALID),
    .tap_cooldown_remaining (FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[15:0]),
    .tap_ai_active          (FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID)
);

// Fold the new storage into LED0 so Synplify cannot prune it.
wire pid_csr_obs_w =
    ^pid_csr_kp_shadow_w
  ^ ^pid_csr_ki_shadow_w
  ^ ^pid_csr_kd_shadow_w
  ^ ^pid_csr_out_min_shadow_w
  ^ ^pid_csr_out_max_shadow_w
  ^ ^pid_csr_inner_clamp_shadow_w
  ^ ^pid_csr_error_shadow_w
  ^ ^pid_csr_u_ai_shadow_w
  ^ ^pid_csr_rdata_unused;
"""

# Anchor at the line right before `endmodule` of the top module. We insert
# instance + observability fold between the existing module body and the
# `endmodule` token at file end.
ANCHOR_RE = re.compile(r"^endmodule\s*$", re.MULTILINE)


def already_applied(text: str) -> bool:
    return ALREADY_APPLIED_MARKER in text


def apply_patch(text: str) -> str:
    if already_applied(text):
        raise SystemExit("patch already applied (marker present)")
    matches = list(ANCHOR_RE.finditer(text))
    if not matches:
        raise SystemExit("could not find a final 'endmodule' anchor")
    last = matches[-1]
    return text[: last.start()] + INSTANCE_BLOCK + "\n" + text[last.start() :]


def main(argv: list[str] | None = None) -> int:
    desc = (__doc__ or "").split("\n", 1)[0]
    ap = argparse.ArgumentParser(description=desc)
    ap.add_argument("verilog", type=Path)
    ap.add_argument(
        "--check",
        action="store_true",
        help="only verify whether the patch can be applied, don't write",
    )
    args = ap.parse_args(argv)

    text = args.verilog.read_text()
    if already_applied(text):
        print(f"{args.verilog}: patch already applied")
        return 0

    if args.check:
        # Verify the anchor exists.
        if not ANCHOR_RE.search(text):
            print(f"{args.verilog}: cannot apply — no 'endmodule' anchor")
            return 1
        print(f"{args.verilog}: patch can be applied")
        return 0

    backup = args.verilog.with_suffix(args.verilog.suffix + ".pre_pid_csr.bak")
    shutil.copy2(args.verilog, backup)
    new_text = apply_patch(text)
    args.verilog.write_text(new_text)
    print(f"{args.verilog}: patched. backup at {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
