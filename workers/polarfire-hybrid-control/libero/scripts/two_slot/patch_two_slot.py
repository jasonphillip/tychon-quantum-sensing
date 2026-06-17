#!/usr/bin/env python3
"""patch_two_slot.py — clean two-slot PID integration (Verilog netlist patch).

Production path of docs/smartdesign_two_slot_canvas_runbook.md, applied at the
generated-netlist level (the proven, byte-deterministic mechanism in this
project; see patch_smartdesign_top.py / patch_smartdesign_watchdog.py). Unlike
the Phase-I eavesdropper, this produces a real, fully-decoded two-slot design:

  SLOT A  nv_pid_top.axi4target  -> FIC0_INITIATOR SLAVE0  @ 0x60001000
          (gains Kp/Ki/Kd/out_min/out_max/inner_clamp; clean read+write; the
           connection drives the previously-undriven SLAVE0 response nets, which
           is what removes the 0x60001000 read-wedge.)
  SLOT B  pid_csr_axi4_wrap      -> FIC0_INITIATOR SLAVE3  @ 0x60040000
          (liveness/version + error/u_ai injection + actuator readback;
           AXI4(64)->AXI4-Lite(32) thin bridge around the validated pid_csr_block.)

Datapath (defeats Synplify constant-folding; real drivers + real consumer):
  pid_csr_block.error_shadow_out -> nv_pid_top.error
  pid_csr_block.u_ai_shadow_out  -> nv_pid_top.u_AI_in
  nv_pid_top.actuator_out_write_data -> pid_csr_block.tap_post_clamp_out
Safety:
  CoreVectorBlox output_valid -> vbx_pulse_gen -> watchdog_timer
  watchdog_timer.timeout -> nv_pid_top.ai_watchdog_timeout + pid_csr tap

Touches three SmartDesign-generated files:
  - Vectorblox_ss.v            : expose core output_valid as output_valid_o
  - FIC_0_PERIPHERALS.v        : add 4 datapath ports; instantiate the wrap +
                                 watchdog + pulse_gen; drive the SLAVE3 response
                                 channel; tap output_valid
  - MPFS_ICICLE_KIT_BASE_DESIGN.v : connect nv_pid_top.axi4target<->AXI4mslave0,
                                 wire datapath, declare top nets

Each edit is anchored and count-checked; a missing/duplicate anchor aborts the
run with no writes. Backups: <file>.pre_two_slot.bak. Idempotent (marker guard).

Usage:
  patch_two_slot.py --top <top.v> --fic <FIC_0_PERIPHERALS.v> --vbx <Vectorblox_ss.v>
  patch_two_slot.py ... --check     # dry run; report anchor matches, write nothing
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

MARKER = "// two_slot PID integration"

# Fabric clock (FIC_0 / ACLK / watchdog) = 125 MHz (8 ns), CONFIRMED from the
# seed_7 PF_CCC_C0 OUT0 = REF_CLK(50 MHz) x 5/2 (constraint/...derived_constraints.sdc).
# Watchdog timeout is a PARAMETER (watchdog_timer.v WATCHDOG_TIMEOUT_CYCLES) so we
# build two clearly-labeled bitstreams from the same netlist:
#   --watchdog-cycles 125000     => SAFETY-SPEC build:  1 ms @ 125 MHz (the real bound)
#   --watchdog-cycles 62500000   => DASHBOARD-DEMO build: 500 ms @ 125 MHz (host-paced;
#                                   stops a software/host-paced replay from spuriously
#                                   tripping between rows). NOT the 1 ms safety bound.
DEMO_WATCHDOG_CYCLES   = 62_500_000   # 500 ms @ 125 MHz  (host-paced demo timeout)
SAFETY_WATCHDOG_CYCLES = 125_000      # 1 ms   @ 125 MHz  (safety-spec bound)
WDOG_PLACEHOLDER = "__WATCHDOG_TIMEOUT_CYCLES__"


class PatchError(RuntimeError):
    pass


def _sub_once(text: str, pattern: str, repl: str, desc: str, flags=0) -> str:
    # NOTE: string-based sub so regex backreferences (\g<1>) expand. None of the
    # replacement blocks contain backslashes, so literal insertion is unaffected.
    rx = re.compile(pattern, flags)
    n = len(rx.findall(text))
    if n != 1:
        raise PatchError(f"anchor {desc!r} matched {n} times, expected 1")
    return rx.sub(repl, text, count=1)


# ---------------------------------------------------------------------------
# 1. Vectorblox_ss.v — expose core_vectorblox_C0_0.output_valid
# ---------------------------------------------------------------------------
def patch_vbx(text: str) -> str:
    if MARKER in text:
        raise PatchError("Vectorblox_ss.v already patched (marker present)")
    # 1a. add port name to the module port list (after the last port s_axi_wready)
    text = _sub_once(
        text,
        r"    s_axi_wready\n\);",
        "    s_axi_wready,\n    output_valid_o\n);",
        "vbx port-list tail",
    )
    # 1b. declare the output port (anchor on the now-unique port-list close)
    text = _sub_once(
        text,
        r"    output_valid_o\n\);\n",
        "    output_valid_o\n);\noutput        output_valid_o;  " + MARKER + "\n",
        "vbx output_valid_o decl",
    )
    # 1c. connect the core's output_valid to the new port
    text = _sub_once(
        text,
        r"\.output_valid  \(  \),",
        ".output_valid  ( output_valid_o ),  " + MARKER,
        "vbx core output_valid",
    )
    return text


# ---------------------------------------------------------------------------
# 2. FIC_0_PERIPHERALS.v
# ---------------------------------------------------------------------------
FIC_NEW_PORTS_NAMES = (
    "    VBX_ACLK,\n"
    "    pid_error_out,\n"
    "    pid_u_ai_out,\n"
    "    pid_watchdog_timeout_out,\n"
    "    pid_actuator_in   " + MARKER + "\n"
    ");"
)

FIC_NEW_PORT_DECLS = (
    "input         ARESETN;\n"
    "output [63:0] pid_error_out;            " + MARKER + "\n"
    "output [31:0] pid_u_ai_out;             " + MARKER + "\n"
    "output        pid_watchdog_timeout_out; " + MARKER + "\n"
    "input  [31:0] pid_actuator_in;          " + MARKER + "\n"
)

FIC_NEW_WIRES = (
    "// " + MARKER + " — slot-B (SLAVE3) bridge + watchdog nets\n"
    "wire        w_s3_awready;\n"
    "wire        w_s3_wready;\n"
    "wire        w_s3_bvalid;\n"
    "wire        w_s3_arready;\n"
    "wire        w_s3_rlast;\n"
    "wire        w_s3_rvalid;\n"
    "wire [8:0]  w_s3_bid;\n"
    "wire [1:0]  w_s3_bresp;\n"
    "wire [8:0]  w_s3_rid;\n"
    "wire [63:0] w_s3_rdata;\n"
    "wire [1:0]  w_s3_rresp;\n"
    "wire [63:0] w_pid_error;\n"
    "wire [31:0] w_pid_u_ai;\n"
    "wire        w_watchdog_timeout;\n"
    "wire        w_vbx_output_valid;\n"
    "wire        w_vbx_pulse;\n"
)

FIC_INSTANCES = """
//-------- """ + MARKER + """ — slot-B clean CSR slave on FIC0_INITIATOR SLAVE3 (0x60040000)
pid_csr_axi4_wrap u_pid_csr_axi4_wrap (
        .s_axi_aclk     ( ACLK ),
        .s_axi_aresetn  ( ARESETN ),
        .s_axi_awid     ( FIC0_INITIATOR_AXI4mslave3_AWID ),
        .s_axi_awaddr   ( FIC0_INITIATOR_AXI4mslave3_AWADDR ),
        .s_axi_awlen    ( FIC0_INITIATOR_AXI4mslave3_AWLEN ),
        .s_axi_awsize   ( FIC0_INITIATOR_AXI4mslave3_AWSIZE ),
        .s_axi_awburst  ( FIC0_INITIATOR_AXI4mslave3_AWBURST ),
        .s_axi_awlock   ( FIC0_INITIATOR_AXI4mslave3_AWLOCK ),
        .s_axi_awcache  ( FIC0_INITIATOR_AXI4mslave3_AWCACHE ),
        .s_axi_awprot   ( FIC0_INITIATOR_AXI4mslave3_AWPROT ),
        .s_axi_awqos    ( FIC0_INITIATOR_AXI4mslave3_AWQOS ),
        .s_axi_awregion ( FIC0_INITIATOR_AXI4mslave3_AWREGION ),
        .s_axi_awuser   ( FIC0_INITIATOR_AXI4mslave3_AWUSER ),
        .s_axi_awvalid  ( FIC0_INITIATOR_AXI4mslave3_AWVALID ),
        .s_axi_awready  ( w_s3_awready ),
        .s_axi_wdata    ( FIC0_INITIATOR_AXI4mslave3_WDATA ),
        .s_axi_wstrb    ( FIC0_INITIATOR_AXI4mslave3_WSTRB ),
        .s_axi_wlast    ( FIC0_INITIATOR_AXI4mslave3_WLAST ),
        .s_axi_wuser    ( FIC0_INITIATOR_AXI4mslave3_WUSER ),
        .s_axi_wvalid   ( FIC0_INITIATOR_AXI4mslave3_WVALID ),
        .s_axi_wready   ( w_s3_wready ),
        .s_axi_bid      ( w_s3_bid ),
        .s_axi_bresp    ( w_s3_bresp ),
        .s_axi_buser    (  ),
        .s_axi_bvalid   ( w_s3_bvalid ),
        .s_axi_bready   ( FIC0_INITIATOR_AXI4mslave3_BREADY ),
        .s_axi_arid     ( FIC0_INITIATOR_AXI4mslave3_ARID ),
        .s_axi_araddr   ( FIC0_INITIATOR_AXI4mslave3_ARADDR ),
        .s_axi_arlen    ( FIC0_INITIATOR_AXI4mslave3_ARLEN ),
        .s_axi_arsize   ( FIC0_INITIATOR_AXI4mslave3_ARSIZE ),
        .s_axi_arburst  ( FIC0_INITIATOR_AXI4mslave3_ARBURST ),
        .s_axi_arlock   ( FIC0_INITIATOR_AXI4mslave3_ARLOCK ),
        .s_axi_arcache  ( FIC0_INITIATOR_AXI4mslave3_ARCACHE ),
        .s_axi_arprot   ( FIC0_INITIATOR_AXI4mslave3_ARPROT ),
        .s_axi_arqos    ( FIC0_INITIATOR_AXI4mslave3_ARQOS ),
        .s_axi_arregion ( FIC0_INITIATOR_AXI4mslave3_ARREGION ),
        .s_axi_aruser   ( FIC0_INITIATOR_AXI4mslave3_ARUSER ),
        .s_axi_arvalid  ( FIC0_INITIATOR_AXI4mslave3_ARVALID ),
        .s_axi_arready  ( w_s3_arready ),
        .s_axi_rid      ( w_s3_rid ),
        .s_axi_rdata    ( w_s3_rdata ),
        .s_axi_rresp    ( w_s3_rresp ),
        .s_axi_rlast    ( w_s3_rlast ),
        .s_axi_ruser    (  ),
        .s_axi_rvalid   ( w_s3_rvalid ),
        .s_axi_rready   ( FIC0_INITIATOR_AXI4mslave3_RREADY ),
        .error_shadow_out  ( w_pid_error ),
        .u_ai_shadow_out   ( w_pid_u_ai ),
        .tap_post_clamp_in ( pid_actuator_in ),
        .tap_watchdog_in   ( w_watchdog_timeout )
        );

//-------- """ + MARKER + """ — V250 output_valid -> pulse -> watchdog
vbx_pulse_gen u_vbx_pulse_gen (
        .clk_i              ( ACLK ),
        .resetn_i           ( ARESETN ),
        .vbx_output_valid_i ( w_vbx_output_valid ),
        .pulse_o            ( w_vbx_pulse )
        );

watchdog_timer #(
        .WATCHDOG_TIMEOUT_CYCLES(""" + WDOG_PLACEHOLDER + """)
) u_watchdog_timer (
        .clk          ( ACLK ),
        .resetn       ( ARESETN ),
        .ai_heartbeat ( w_vbx_pulse ),
        .timeout      ( w_watchdog_timeout )
        );

assign pid_error_out            = w_pid_error;
assign pid_u_ai_out             = w_pid_u_ai;
assign pid_watchdog_timeout_out = w_watchdog_timeout;

endmodule"""

# SLAVE3 response-channel: replace const/GND tie-offs with the bridge outputs.
FIC_SLAVE3_TIE_REPL = [
    (r"(\.SLAVE3_AWREADY   \(\s*)GND_net(\s*\))", "w_s3_awready", "SLAVE3_AWREADY"),
    (r"(\.SLAVE3_WREADY    \(\s*)GND_net(\s*\))", "w_s3_wready", "SLAVE3_WREADY"),
    (r"(\.SLAVE3_BVALID    \(\s*)GND_net(\s*\))", "w_s3_bvalid", "SLAVE3_BVALID"),
    (r"(\.SLAVE3_ARREADY   \(\s*)GND_net(\s*\))", "w_s3_arready", "SLAVE3_ARREADY"),
    (r"(\.SLAVE3_RLAST     \(\s*)GND_net(\s*\))", "w_s3_rlast", "SLAVE3_RLAST"),
    (r"(\.SLAVE3_RVALID    \(\s*)GND_net(\s*\))", "w_s3_rvalid", "SLAVE3_RVALID"),
    (r"(\.SLAVE3_BID       \(\s*)SLAVE3_BID_const_net_0(\s*\))", "w_s3_bid", "SLAVE3_BID"),
    (r"(\.SLAVE3_BRESP     \(\s*)SLAVE3_BRESP_const_net_0(\s*\))", "w_s3_bresp", "SLAVE3_BRESP"),
    (r"(\.SLAVE3_RID       \(\s*)SLAVE3_RID_const_net_0(\s*\))", "w_s3_rid", "SLAVE3_RID"),
    (r"(\.SLAVE3_RDATA     \(\s*)SLAVE3_RDATA_const_net_0(\s*\))", "w_s3_rdata", "SLAVE3_RDATA"),
    (r"(\.SLAVE3_RRESP     \(\s*)SLAVE3_RRESP_const_net_0(\s*\))", "w_s3_rresp", "SLAVE3_RRESP"),
]


def patch_fic(text: str, watchdog_cycles: int) -> str:
    if MARKER in text:
        raise PatchError("FIC_0_PERIPHERALS.v already patched (marker present)")
    # 2a. port name list
    text = _sub_once(text, r"    VBX_ACLK\n\);", FIC_NEW_PORTS_NAMES, "fic port-list tail")
    # 2b. port declarations
    text = _sub_once(text, r"input         ARESETN;\n", FIC_NEW_PORT_DECLS, "fic ARESETN decl")
    # 2c. new wires (anchor: first 'assign VBX_ACLK_net_1' is unique and late)
    text = _sub_once(
        text,
        r"^assign VBX_ACLK_net_1",
        FIC_NEW_WIRES + "assign VBX_ACLK_net_1",
        "fic wire-insert anchor",
        re.MULTILINE,
    )
    # 2d. SLAVE3 response channel -> bridge outputs
    for pat, net, desc in FIC_SLAVE3_TIE_REPL:
        text = _sub_once(text, pat, r"\g<1>" + net + r"\g<2>", "fic " + desc)
    # 2e. tap output_valid out of Vectorblox_ss_0 (add port before its closing ');')
    text = _sub_once(
        text,
        r"(\.SLAVE0_ARUSER   \( VBX_AXIM_ARUSER \) \n        \);)",
        ".SLAVE0_ARUSER   ( VBX_AXIM_ARUSER ),\n"
        "        .output_valid_o  ( w_vbx_output_valid )   " + MARKER + "\n        );",
        "fic Vectorblox_ss_0 output_valid",
    )
    # 2f. instantiate wrap + watchdog + pulse_gen, drive new ports (before endmodule)
    text = _sub_once(text, r"\nendmodule\n?$", FIC_INSTANCES + "\n", "fic endmodule", re.MULTILINE)
    # 2g. bake the watchdog timeout (parameterized: safety-spec vs dashboard-demo)
    if WDOG_PLACEHOLDER not in text:
        raise PatchError("watchdog placeholder missing after instance insert")
    text = text.replace(WDOG_PLACEHOLDER, str(watchdog_cycles))
    return text


# ---------------------------------------------------------------------------
# 3. MPFS_ICICLE_KIT_BASE_DESIGN.v (top)
# ---------------------------------------------------------------------------
TOP_NEW_NVPID_INSTANCE = """nv_pid_top_top nv_pid_top_0(   """ + MARKER + """
        // Clock/reset
        .clk                     ( CLOCKS_AND_RESETS_FIC_0_CLK ),
        .reset                   ( GND_net ),
        // axi4target slave <- FIC0_INITIATOR SLAVE0 (0x60001000), gains R/W
        .axi4target_arvalid      ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARVALID ),
        .axi4target_rready       ( FIC_0_PERIPHERALS_1_AXI4mslave0_RREADY ),
        .axi4target_awvalid      ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWVALID ),
        .axi4target_wvalid       ( FIC_0_PERIPHERALS_1_AXI4mslave0_WVALID ),
        .axi4target_wlast        ( FIC_0_PERIPHERALS_1_AXI4mslave0_WLAST ),
        .axi4target_bready       ( FIC_0_PERIPHERALS_1_AXI4mslave0_BREADY ),
        .ai_watchdog_timeout     ( w_pid_watchdog ),
        .axi4target_araddr       ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARADDR[5:0] ),
        .axi4target_arid         ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARID[0] ),
        .axi4target_arburst      ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARBURST ),
        .axi4target_arlen        ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARLEN ),
        .axi4target_arsize       ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARSIZE ),
        .axi4target_arcache      ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARCACHE ),
        .axi4target_arlock       ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARLOCK ),
        .axi4target_arprot       ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARPROT ),
        .axi4target_arqos        ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARQOS ),
        .axi4target_arregion     ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARREGION ),
        .axi4target_aruser       ( GND_net ),
        .axi4target_awaddr       ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWADDR[5:0] ),
        .axi4target_awid         ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWID[0] ),
        .axi4target_awburst      ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWBURST ),
        .axi4target_awlen        ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWLEN ),
        .axi4target_awsize       ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWSIZE ),
        .axi4target_awcache      ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWCACHE ),
        .axi4target_awlock       ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWLOCK ),
        .axi4target_awprot       ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWPROT ),
        .axi4target_awqos        ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWQOS ),
        .axi4target_awregion     ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWREGION ),
        .axi4target_awuser       ( GND_net ),
        .axi4target_wdata        ( FIC_0_PERIPHERALS_1_AXI4mslave0_WDATA ),
        .axi4target_wstrb        ( FIC_0_PERIPHERALS_1_AXI4mslave0_WSTRB ),
        .axi4target_wuser        ( GND_net ),
        // Real datapath stimulus from the slot-B CSR block
        .error                   ( w_pid_error ),
        .u_AI_in                 ( w_pid_u_ai ),
        // axi4target slave responses -> drive the SLAVE0 nets (fixes the wedge)
        .axi4target_arready      ( FIC_0_PERIPHERALS_1_AXI4mslave0_ARREADY ),
        .axi4target_rvalid       ( FIC_0_PERIPHERALS_1_AXI4mslave0_RVALID ),
        .axi4target_rlast        ( FIC_0_PERIPHERALS_1_AXI4mslave0_RLAST ),
        .axi4target_awready      ( FIC_0_PERIPHERALS_1_AXI4mslave0_AWREADY ),
        .axi4target_wready       ( FIC_0_PERIPHERALS_1_AXI4mslave0_WREADY ),
        .axi4target_bvalid       ( FIC_0_PERIPHERALS_1_AXI4mslave0_BVALID ),
        .actuator_out_write_en   (  ),
        .axi4target_rdata        ( FIC_0_PERIPHERALS_1_AXI4mslave0_RDATA ),
        .axi4target_rid          ( w_nvpid_rid ),
        .axi4target_rresp        ( FIC_0_PERIPHERALS_1_AXI4mslave0_RRESP ),
        .axi4target_ruser        (  ),
        .axi4target_bid          ( w_nvpid_bid ),
        .axi4target_bresp        ( FIC_0_PERIPHERALS_1_AXI4mslave0_BRESP ),
        .axi4target_buser        (  ),
        // Actuator output -> CSR readback tap
        .actuator_out_write_data ( w_pid_actuator )
        );"""

TOP_NEW_WIRES = (
    "wire   [63:0] w_pid_error;          " + MARKER + "\n"
    "wire   [31:0] w_pid_u_ai;           " + MARKER + "\n"
    "wire   [31:0] w_pid_actuator;       " + MARKER + "\n"
    "wire          w_pid_watchdog;       " + MARKER + "\n"
    "wire          w_nvpid_bid;          " + MARKER + "\n"
    "wire          w_nvpid_rid;          " + MARKER + "\n"
)

TOP_NEW_ASSIGNS = (
    "assign FIC_0_PERIPHERALS_1_AXI4mslave0_BID = { 3'b000, w_nvpid_bid };   " + MARKER + "\n"
    "assign FIC_0_PERIPHERALS_1_AXI4mslave0_RID = { 3'b000, w_nvpid_rid };   " + MARKER + "\n"
)

TOP_FIC_NEW_CONNS = (
    "        .AXI4mslave0_SLAVE0_WUSER      ( FIC_0_PERIPHERALS_1_AXI4mslave0_WUSER ),\n"
    "        .pid_error_out                ( w_pid_error ),            " + MARKER + "\n"
    "        .pid_u_ai_out                 ( w_pid_u_ai ),             " + MARKER + "\n"
    "        .pid_watchdog_timeout_out     ( w_pid_watchdog ),         " + MARKER + "\n"
    "        .pid_actuator_in              ( w_pid_actuator ),         " + MARKER
)


def patch_top(text: str) -> str:
    if MARKER in text:
        raise PatchError("top already patched (marker present)")
    # 3a. replace the entire nv_pid_top_0 instance block
    text = _sub_once(
        text,
        r"nv_pid_top_top nv_pid_top_0\(.*?\n        \);",
        TOP_NEW_NVPID_INSTANCE,
        "top nv_pid_top_0 instance",
        re.DOTALL,
    )
    # 3b. new top wires (anchor on the error const-net decl, unique)
    text = _sub_once(
        text,
        r"^wire   \[63:0\] error_const_net_0;\n",
        "wire   [63:0] error_const_net_0;\n" + TOP_NEW_WIRES,
        "top wire-insert anchor",
        re.MULTILINE,
    )
    # 3c. BID/RID width-adaptation assigns (anchor on the existing BID_0 glue)
    text = _sub_once(
        text,
        r"^assign FIC_0_PERIPHERALS_1_AXI4mslave0_BID_0 = \{",
        TOP_NEW_ASSIGNS + "assign FIC_0_PERIPHERALS_1_AXI4mslave0_BID_0 = {",
        "top assign-insert anchor",
        re.MULTILINE,
    )
    # 3d. add the 4 datapath ports to the FIC_0_PERIPHERALS_1 instance
    text = _sub_once(
        text,
        r"        \.AXI4mslave0_SLAVE0_WUSER      \( FIC_0_PERIPHERALS_1_AXI4mslave0_WUSER \),",
        TOP_FIC_NEW_CONNS,
        "top FIC_0_PERIPHERALS_1 new ports",
    )
    return text


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--top", type=Path, required=True)
    ap.add_argument("--fic", type=Path, required=True)
    ap.add_argument("--vbx", type=Path, required=True)
    ap.add_argument("--check", action="store_true", help="dry run; write nothing")
    ap.add_argument(
        "--watchdog-cycles", type=int, default=DEMO_WATCHDOG_CYCLES,
        help=f"watchdog timeout in fabric (125 MHz) cycles. "
             f"default {DEMO_WATCHDOG_CYCLES} (500 ms, dashboard-demo); "
             f"use {SAFETY_WATCHDOG_CYCLES} for the 1 ms safety-spec build.",
    )
    args = ap.parse_args()

    wc = args.watchdog_cycles
    label = "SAFETY-SPEC 1 ms" if wc == SAFETY_WATCHDOG_CYCLES else "host-paced DEMO"
    print(f"watchdog: {wc} cycles @ 125 MHz = {wc / 125e6 * 1e3:.3f} ms  [{label}]")

    jobs = [
        (args.vbx, lambda t: patch_vbx(t)),
        (args.fic, lambda t: patch_fic(t, wc)),
        (args.top, lambda t: patch_top(t)),
    ]
    results = []
    for path, fn in jobs:
        if not path.is_file():
            print(f"ERROR: not found: {path}", file=sys.stderr)
            return 1
        original = path.read_text()
        try:
            patched = fn(original)
        except PatchError as exc:
            print(f"PATCH FAILED ({path.name}): {exc}", file=sys.stderr)
            return 1
        results.append((path, original, patched))
        print(f"  ok: {path.name} ({len(patched) - len(original):+d} bytes)")

    if args.check:
        print("dry run — all anchors matched, no files written")
        return 0

    for path, _original, patched in results:
        backup = path.with_suffix(path.suffix + ".pre_two_slot.bak")
        shutil.copy2(path, backup)
        path.write_text(patched)
        print(f"  wrote {path.name} (backup {backup.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
