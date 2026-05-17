# sim/modelsim_pid_workload.do — ModelSim/QuestaSim driver for workload VCD generation
#
# STATUS (2026-05-17, DLOG-047): INFRASTRUCTURE PREP — not yet runnable end-to-end.
# Real SmartHLS 2025.2 output (verified via `shls hw` on Beelink against the
# Kd·s/(1+s·Tf) filtered nv_pid_top) differs from earlier speculative assumptions:
#   - Module name:   nv_pid_top_top    (not nv_pid_top)
#   - RTL filename:  nv_pid_top_nv_pid_top.v   (doubled prefix)
#   - Reset port:    `reset` active-HIGH   (not `ap_rst_n` active-low)
#   - error:         direct 64-bit input  (no `_V` suffix)
#   - u_AI_in:       direct 32-bit input  (no `_V` suffix)
#   - Kp/Ki/Kd/etc:  BEHIND AXI4-target interface — NOT scalar ports
#     The previous `force -freeze sim:/nv_pid_top/Kp_V 32'd6` style WILL FAIL.
#     Internal regs (Kp_reg, Ki_reg, Kd_reg, out_min_reg, out_max_reg,
#     inner_clamp_setpoint_reg) exist at nv_pid_top_nv_pid_top.v:1649-1674
#     inside a generated nv_pid_top_axi4slv_register `ram` instance. Driving
#     them via hierarchical force is the simplest path but the instance path
#     traverses a generate block (genReg) — name must be confirmed in ModelSim
#     after elaboration with `find signals sim:/...*reg*` or via vsim wave.
#   - actuator_out:  HANDSHAKE-style write-port pair (actuator_out_write_en +
#                     actuator_out_write_data), not a scalar memory port.
#
# Drives the SmartHLS-generated nv_pid_top_top RTL with a representative
# ODMR-PID activity trace and dumps a VCD covering the full hierarchy. The
# VCD is then ingested by libero/scripts/05_smartpower_workload.tcl as the
# activity source for SmartPower (replacing the default-toggle baseline used
# in the r6_s25 closure).
#
# Usage from a Beelink Git Bash shell (NOT YET PRODUCTION-VALIDATED):
#   ssh bee
#   cd ~/dev/projects/polarfire-hybrid-control
#   shls hw            # produce hls_output/ RTL (or verify already current)
#   vsim -c -do sim/modelsim_pid_workload.do
#
# Known remaining gaps before this script will produce a SmartPower-ready VCD:
#   1. Hierarchical force path for Kp_reg / Ki_reg / Kd_reg (search after vsim
#      elaboration; the AXI register `ram` instance is inside a generate block).
#   2. SmartPower Tcl form to consume the VCD against the r6_s25 placed
#      netlist — see libero/scripts/05_smartpower_workload.tcl `catch` fallback.
#   3. The r6_s25 closure is on the Microchip reference design at
#      C:/Microchip/.../MPFS_ICICLE_Vectorblox; 05_smartpower_workload.tcl
#      currently opens libero/work/polarfire_hybrid_control.prjx — project
#      path needs realignment before SmartPower can attach to the real netlist.
#   4. VCD signal naming must align with placed netlist after Synplify+P&R
#      register renaming — may need adjustment after first run.

# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
set RTL_DIR "hls/hls_output/rtl"
set TRACE_CSV "sim/stimulus/odmr_representative_trace.csv"
set VCD_OUT "sim/output/pid_workload.vcd"
set CLK_PERIOD_PS 5000  ;# 200 MHz
set HALF_PERIOD_PS [expr {$CLK_PERIOD_PS / 2}]

# Total cycles to simulate per CSV row (1 by default — one PID iteration per
# row of the trace). Increase to amplify activity time per row.
set CYCLES_PER_ROW 1

# Q16.16 conversion of representative gains (would be loaded via AXI write
# in production; held below as forced internal-register values pending
# resolution of the AXI register hierarchy path).
#   Kp  = 0.0001  → Q16.16 = 7   (round(0.0001 * 65536) = 6.5536 → 7)
#   Ki  = 0.00002 → Q16.16 = 1
#   Kd  = 0.001   → Q16.16 = 66  (bump from earlier Kd=0.00001 which rounds to 0)
#   out_min = 0.0      → Q16.16 = 0
#   out_max = 5.0      → Q16.16 = 327680
#   inner_clamp_setpoint = 0.045 → Q16.16 = 2950 (OUTER_SECTOR_CLAMP_FRACTION)

# ---------------------------------------------------------------------------
# Compile RTL — SmartHLS 2025.2 emits nv_pid_top_nv_pid_top.v under hls_output/rtl/.
# ---------------------------------------------------------------------------
puts "INFO: compiling SmartHLS-generated RTL from $RTL_DIR"

if {[file exists "$RTL_DIR/nv_pid_top_nv_pid_top.v"]} {
    vlog "$RTL_DIR/nv_pid_top_nv_pid_top.v"
} else {
    puts "FATAL: nv_pid_top_nv_pid_top.v not found under $RTL_DIR — re-run `shls hw`"
    exit 1
}

# Companion modules — pull anything else SmartHLS emits.
foreach v [glob -nocomplain "$RTL_DIR/*.v"] {
    if {[file tail $v] ne "nv_pid_top_nv_pid_top.v"} { vlog $v }
}

# ---------------------------------------------------------------------------
# Elaborate. SmartHLS top-level module is nv_pid_top_top.
# ---------------------------------------------------------------------------
vsim -t ps -voptargs="+acc" work.nv_pid_top_top

# ---------------------------------------------------------------------------
# VCD dump setup — capture the full hierarchy so SmartPower has activity data
# for every signal in the design.
# ---------------------------------------------------------------------------
vcd file $VCD_OUT
vcd add -r /nv_pid_top_top/*

# ---------------------------------------------------------------------------
# Drive clock and reset. Reset is ACTIVE-HIGH `reset` (SmartHLS 2025.2 default).
# ---------------------------------------------------------------------------
force -freeze sim:/nv_pid_top_top/clk 1 0, 0 [format "%d ps" $HALF_PERIOD_PS] -repeat [format "%d ps" $CLK_PERIOD_PS]
force -freeze sim:/nv_pid_top_top/reset 1 0
run 50 ns
force -freeze sim:/nv_pid_top_top/reset 0 50ns
run 50 ns

# ---------------------------------------------------------------------------
# GAP: drive AXI4 register block to load Kp/Ki/Kd/out_min/out_max/
#      inner_clamp_setpoint at representative values.
#
# Two implementation options for a future session:
#   (A) Issue real AXI write transactions on axi4target_aw/w/b channels at
#       the addresses from the SmartHLS-generated address map (see
#       hls/hls_output/reports/summary.hls.nv_pid_top.rpt §4 "AXI4 Target
#       Interface Address Map").
#   (B) Hierarchical force on the internal Kp_reg, Ki_reg, Kd_reg, out_min_reg,
#       out_max_reg, inner_clamp_setpoint_reg signals — they exist at
#       nv_pid_top_nv_pid_top.v:1649-1674 inside the
#       nv_pid_top_axi4slv_register `ram` instance. The full hierarchy path
#       needs to be discovered in vsim after elaboration:
#           find signals -recursive sim:/nv_pid_top_top/* | grep _reg$
#       then add forces of the form:
#           force -freeze <hier>/Kp_reg  32'd7
#           force -freeze <hier>/Ki_reg  32'd1
#           force -freeze <hier>/Kd_reg  32'd66
#           force -freeze <hier>/out_min_reg 32'd0
#           force -freeze <hier>/out_max_reg 32'd327680
#           force -freeze <hier>/inner_clamp_setpoint_reg 32'd2950
#
# Until one of (A) or (B) is wired, the gains remain at reset value (zero) and
# the resulting VCD has near-zero datapath activity — SmartPower would
# under-report dynamic power. Surfaced as a known gap in
# docs/workload_smartpower_2026-05-17.md.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Drive the dynamic inputs (error, u_AI_in, ai_watchdog_timeout) from CSV.
#
# error is freq_t (ap_fixpt<64, 34>) → 64-bit signed. Q34.30 means 30
# fractional bits. Conversion: float Hz × 2^30 → 64-bit signed integer.
# u_AI_in is out_t (ap_fixpt<32, 16>) → 32-bit signed. Q16.16. Conversion:
# float V × 2^16 → 32-bit signed integer.
# ---------------------------------------------------------------------------

proc q_pack {value frac_bits width} {
    # Convert float to fixed-point and emit a Verilog-style signed bit vector.
    set scaled [expr {round($value * (1 << $frac_bits))}]
    # Mask into width-bit two's complement.
    set mask [expr {(1 << $width) - 1}]
    set packed [expr {$scaled & $mask}]
    return [format "%d'd%d" $width $packed]
}

set fp [open $TRACE_CSV r]
# Skip header.
gets $fp _hdr

set row_count 0
while {[gets $fp line] >= 0} {
    if {[string trim $line] eq ""} { continue }
    set fields [split $line ","]
    set error_hz   [lindex $fields 1]
    set u_ai_volts [lindex $fields 2]
    set wd_flag    [lindex $fields 3]

    # error: 64-bit Q34.30 (no `_V` suffix on the real RTL); u_AI_in: 32-bit Q16.16.
    force -freeze sim:/nv_pid_top_top/error              [q_pack $error_hz   30 64]
    force -freeze sim:/nv_pid_top_top/u_AI_in            [q_pack $u_ai_volts 16 32]
    force -freeze sim:/nv_pid_top_top/ai_watchdog_timeout  $wd_flag

    run [expr {$CLK_PERIOD_PS * $CYCLES_PER_ROW}] ps
    incr row_count
}
close $fp

puts "INFO: drove $row_count rows from $TRACE_CSV"

# ---------------------------------------------------------------------------
# Flush VCD and exit.
# ---------------------------------------------------------------------------
vcd flush $VCD_OUT
puts "INFO: VCD written to $VCD_OUT"
quit -f
