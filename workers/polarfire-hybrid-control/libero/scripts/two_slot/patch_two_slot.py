#!/usr/bin/env python3
"""patch_two_slot.py — clean two-slot PID integration (Verilog netlist patch).

Production path of docs/smartdesign_two_slot_canvas_runbook.md, applied at the
generated-netlist level (the proven, byte-deterministic mechanism in this
project). All the integration logic lives in a structured HDL module
`pid_subsystem.v` (demux + nv_pid_top + pid_csr + watchdog + pulse_gen); this
patch just drops that one module onto the single free crossbar slot and removes
the now-superseded top-level nv_pid_top instance.

Topology (CONFIRMED, docs/two_slot_integration_notes_2026-06-17.md): the FIC0_INITIATOR
crossbar has exactly one free slot, SLAVE3 @ 0x60040000 (SLAVE0=DMA ctrl, SLAVE1
occupied, SLAVE2=V250). pid_subsystem splits SLAVE3 into:
  0x60040000  nv_pid_top.axi4target (gains)   0x60040800  pid_csr (CSR)

Three SmartDesign-generated files are touched:
  - Vectorblox_ss.v            : expose core output_valid as output_valid_o
  - FIC_0_PERIPHERALS.v        : instantiate pid_subsystem on SLAVE3, drive the
                                 SLAVE3 response channel, tap output_valid
  - MPFS_ICICLE_KIT_BASE_DESIGN.v : delete the dead top-level nv_pid_top instance
                                 (nv_pid_top now lives inside pid_subsystem)

Each edit is anchored and count-checked; backups: <file>.pre_two_slot.bak.
Idempotent (marker guard). Watchdog timeout is parameterized.

Usage:
  patch_two_slot.py --top <top.v> --fic <FIC_0_PERIPHERALS.v> --vbx <Vectorblox_ss.v>
                    [--watchdog-cycles N] [--check]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

MARKER = "// two_slot PID integration"

# Fabric clock (FIC_0 / ACLK / watchdog) = 125 MHz (8 ns), CONFIRMED from the
# seed_7 PF_CCC_C0 OUT0 = REF_CLK(50 MHz) x 5/2.
#   --watchdog-cycles 125000     => SAFETY-SPEC build:  1 ms @ 125 MHz
#   --watchdog-cycles 62500000   => DASHBOARD-DEMO build: 500 ms (host-paced; NOT the 1 ms bound)
DEMO_WATCHDOG_CYCLES   = 62_500_000
SAFETY_WATCHDOG_CYCLES = 125_000
WDOG_PLACEHOLDER = "__WATCHDOG_TIMEOUT_CYCLES__"


class PatchError(RuntimeError):
    pass


def _sub_once(text: str, pattern: str, repl: str, desc: str, flags=0) -> str:
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
        raise PatchError("Vectorblox_ss.v already patched")
    text = _sub_once(text, r"    s_axi_wready\n\);",
                     "    s_axi_wready,\n    output_valid_o\n);", "vbx port-list tail")
    text = _sub_once(text, r"    output_valid_o\n\);\n",
                     "    output_valid_o\n);\noutput        output_valid_o;  " + MARKER + "\n",
                     "vbx output_valid_o decl")
    text = _sub_once(text, r"\.output_valid  \(  \),",
                     ".output_valid  ( output_valid_o ),  " + MARKER, "vbx core output_valid")
    return text


# ---------------------------------------------------------------------------
# 2. FIC_0_PERIPHERALS.v — pid_subsystem on SLAVE3
# ---------------------------------------------------------------------------
FIC_NEW_WIRES = (
    "// " + MARKER + " — SLAVE3 response nets driven by pid_subsystem + V250 output_valid\n"
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
    "wire        w_vbx_output_valid;\n"
)

FIC_INSTANCES = """
//-------- """ + MARKER + """ — clean two-slot PID subsystem on FIC0_INITIATOR SLAVE3 (0x60040000)
pid_subsystem #(
        .WATCHDOG_TIMEOUT_CYCLES(""" + WDOG_PLACEHOLDER + """)
) u_pid_subsystem (
        .clk             ( ACLK ),
        .resetn          ( ARESETN ),
        .vbx_output_valid( w_vbx_output_valid ),
        .s_awid     ( FIC0_INITIATOR_AXI4mslave3_AWID ),
        .s_awaddr   ( FIC0_INITIATOR_AXI4mslave3_AWADDR ),
        .s_awlen    ( FIC0_INITIATOR_AXI4mslave3_AWLEN ),
        .s_awsize   ( FIC0_INITIATOR_AXI4mslave3_AWSIZE ),
        .s_awburst  ( FIC0_INITIATOR_AXI4mslave3_AWBURST ),
        .s_awlock   ( FIC0_INITIATOR_AXI4mslave3_AWLOCK ),
        .s_awcache  ( FIC0_INITIATOR_AXI4mslave3_AWCACHE ),
        .s_awprot   ( FIC0_INITIATOR_AXI4mslave3_AWPROT ),
        .s_awqos    ( FIC0_INITIATOR_AXI4mslave3_AWQOS ),
        .s_awregion ( FIC0_INITIATOR_AXI4mslave3_AWREGION ),
        .s_awuser   ( FIC0_INITIATOR_AXI4mslave3_AWUSER ),
        .s_awvalid  ( FIC0_INITIATOR_AXI4mslave3_AWVALID ),
        .s_awready  ( w_s3_awready ),
        .s_wdata    ( FIC0_INITIATOR_AXI4mslave3_WDATA ),
        .s_wstrb    ( FIC0_INITIATOR_AXI4mslave3_WSTRB ),
        .s_wlast    ( FIC0_INITIATOR_AXI4mslave3_WLAST ),
        .s_wuser    ( FIC0_INITIATOR_AXI4mslave3_WUSER ),
        .s_wvalid   ( FIC0_INITIATOR_AXI4mslave3_WVALID ),
        .s_wready   ( w_s3_wready ),
        .s_bid      ( w_s3_bid ),
        .s_bresp    ( w_s3_bresp ),
        .s_buser    (  ),
        .s_bvalid   ( w_s3_bvalid ),
        .s_bready   ( FIC0_INITIATOR_AXI4mslave3_BREADY ),
        .s_arid     ( FIC0_INITIATOR_AXI4mslave3_ARID ),
        .s_araddr   ( FIC0_INITIATOR_AXI4mslave3_ARADDR ),
        .s_arlen    ( FIC0_INITIATOR_AXI4mslave3_ARLEN ),
        .s_arsize   ( FIC0_INITIATOR_AXI4mslave3_ARSIZE ),
        .s_arburst  ( FIC0_INITIATOR_AXI4mslave3_ARBURST ),
        .s_arlock   ( FIC0_INITIATOR_AXI4mslave3_ARLOCK ),
        .s_arcache  ( FIC0_INITIATOR_AXI4mslave3_ARCACHE ),
        .s_arprot   ( FIC0_INITIATOR_AXI4mslave3_ARPROT ),
        .s_arqos    ( FIC0_INITIATOR_AXI4mslave3_ARQOS ),
        .s_arregion ( FIC0_INITIATOR_AXI4mslave3_ARREGION ),
        .s_aruser   ( FIC0_INITIATOR_AXI4mslave3_ARUSER ),
        .s_arvalid  ( FIC0_INITIATOR_AXI4mslave3_ARVALID ),
        .s_arready  ( w_s3_arready ),
        .s_rid      ( w_s3_rid ),
        .s_rdata    ( w_s3_rdata ),
        .s_rresp    ( w_s3_rresp ),
        .s_rlast    ( w_s3_rlast ),
        .s_ruser    (  ),
        .s_rvalid   ( w_s3_rvalid ),
        .s_rready   ( FIC0_INITIATOR_AXI4mslave3_RREADY )
        );

endmodule"""

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
        raise PatchError("FIC_0_PERIPHERALS.v already patched")
    # wires (anchor on the unique, late 'assign VBX_ACLK_net_1')
    text = _sub_once(text, r"^assign VBX_ACLK_net_1",
                     FIC_NEW_WIRES + "assign VBX_ACLK_net_1", "fic wire-insert", re.MULTILINE)
    # SLAVE3 response channel -> pid_subsystem outputs
    for pat, net, desc in FIC_SLAVE3_TIE_REPL:
        text = _sub_once(text, pat, r"\g<1>" + net + r"\g<2>", "fic " + desc)
    # tap output_valid out of Vectorblox_ss_0
    text = _sub_once(
        text,
        r"\.SLAVE0_ARUSER   \( VBX_AXIM_ARUSER \)\s*\n\s*\);",
        ".SLAVE0_ARUSER   ( VBX_AXIM_ARUSER ),\n"
        "        .output_valid_o  ( w_vbx_output_valid )   " + MARKER + "\n        );",
        "fic Vectorblox_ss_0 output_valid",
    )
    # instantiate pid_subsystem before endmodule
    text = _sub_once(text, r"\nendmodule\s*$", FIC_INSTANCES + "\n", "fic endmodule")
    if WDOG_PLACEHOLDER not in text:
        raise PatchError("watchdog placeholder missing after instance insert")
    text = text.replace(WDOG_PLACEHOLDER, str(watchdog_cycles))
    return text


# ---------------------------------------------------------------------------
# 3. MPFS_ICICLE_KIT_BASE_DESIGN.v — delete the dead top-level nv_pid_top instance
# ---------------------------------------------------------------------------
def patch_top(text: str) -> str:
    if MARKER in text:
        raise PatchError("top already patched")
    # Remove the whole nv_pid_top_0 instance block (nv_pid_top now lives inside
    # pid_subsystem). Its driving const-nets remain (harmless, unused).
    text = _sub_once(
        text,
        r"//--------nv_pid_top_top\nnv_pid_top_top nv_pid_top_0\(.*?\n        \);\n",
        "// nv_pid_top_0 moved into pid_subsystem (FIC_0_PERIPHERALS)   " + MARKER + "\n",
        "top nv_pid_top_0 instance",
        re.DOTALL,
    )
    return text


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n", 1)[0])
    ap.add_argument("--top", type=Path, required=True)
    ap.add_argument("--fic", type=Path, required=True)
    ap.add_argument("--vbx", type=Path, required=True)
    ap.add_argument("--check", action="store_true", help="dry run; write nothing")
    ap.add_argument("--watchdog-cycles", type=int, default=DEMO_WATCHDOG_CYCLES,
                    help=f"watchdog timeout in 125 MHz cycles (default {DEMO_WATCHDOG_CYCLES} "
                         f"= 500 ms demo; {SAFETY_WATCHDOG_CYCLES} = 1 ms safety-spec)")
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
        try:
            patched = fn(path.read_text())
        except PatchError as exc:
            print(f"PATCH FAILED ({path.name}): {exc}", file=sys.stderr)
            return 1
        results.append((path, patched))
        print(f"  ok: {path.name}")

    if args.check:
        print("dry run — all anchors matched, no files written")
        return 0
    for path, patched in results:
        shutil.copy2(path, path.with_suffix(path.suffix + ".pre_two_slot.bak"))
        path.write_text(patched)
        print(f"  wrote {path.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
