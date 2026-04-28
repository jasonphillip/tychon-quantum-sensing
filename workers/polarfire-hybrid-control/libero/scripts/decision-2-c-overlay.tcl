# decision-2-c-overlay.tcl — Overlay the decision-2-option-c HLS Verilog onto
# the April 2 Microchip Icicle reference design and rerun the P&R pipeline.
#
# RUN ON BEELINK ONLY. Source this from the Libero Tcl console while the
# MPFS_ICICLE_Vectorblox project is the working project.
#
# Why: the fresh-scaffold path (libero/scripts/00..04) is blocked because
# Beelink's Libero install does not have the MPFS250T device libraries
# installed at the project-create level. The April 2 reference design at
#   C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/
#     Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox
# already targets MPFS250T with VectorBlox V1000 + Icicle SoC fabric and
# closed timing on April 2 at +0.165 ns / 24.72% LUT / 20.92% DSP /
# 11.82% LSRAM / 75.74% MSS I/O / 2,664 mW fabric.
#
# File mapping (old PID Verilog → new):
#   OLD: ~/dev/projects/tychon-polarfire-control/hls/hls_output/
#        rtl/nv_pid_top_nv_pid_top.v                      [araddr [4:0], 6 AXI regs, addr range 0x20]
#   NEW: ~/dev/projects/polarfire-hybrid-control/hls/hls_output/
#        rtl/nv_pid_top_nv_pid_top.v                      [araddr [5:0], 7 AXI regs, addr range 0x24]
#
# The new module adds inner_clamp_setpoint at offset 0x20 (Decision 2 Option C
# hybrid sector clamp: hardcoded outer + AXI-tightening inner).

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set NEW_HLS_TCL     "~/dev/projects/polarfire-hybrid-control/hls/hls_output/scripts/libero/create_hdl_plus.tcl"
set NEW_RTL_DIR     "~/dev/projects/polarfire-hybrid-control/hls/hls_output/rtl"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

puts "==> Opening reference design project"
open_project -file $REF_PROJECT

# Re-import HDL+ from the new SmartHLS output. This regenerates the
# User:Private:nv_pid_top_top:1.0 component XML with the wider 6-bit araddr
# and links the new Verilog from our path. Old tychon-polarfire-control
# Verilog references are superseded but not removed (unused after rebuild).
puts "==> Re-importing HDL+ core from decision-2-option-c HLS output"
puts "==>   $NEW_HLS_TCL"
source $NEW_HLS_TCL

puts "==> Rebuilding design hierarchy"
build_design_hierarchy

# Regenerate the SmartDesign top so its internal connections reflect the
# updated nv_pid_top_top port widths (araddr/awaddr widened by 1 bit).
puts "==> Regenerating SmartDesign top: $REF_TOP"
if {[catch {generate_component -component_name $REF_TOP} err]} {
    puts "WARNING: generate_component returned: $err"
    puts "         Continuing — Libero may auto-regen during synthesis."
}

build_design_hierarchy
save_project

# Synthesize + P&R + Timing + Power, mirroring the April 2 baseline flow.
puts "==> SYNTHESIZE"
run_tool -name {SYNTHESIZE}
puts "==> PLACEROUTE"
run_tool -name {PLACEROUTE}
puts "==> VERITIMING (post-P&R STA)"
run_tool -name {VERITIMING}
puts "==> POWERANALYSIS (SmartPower post-P&R)"
run_tool -name {POWERANALYSIS}

save_project

puts "==> OVERLAY PIPELINE COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
puts "    Synthesis log: $REF_PROJECT_DIR/synthesis/${REF_TOP}.srr"
