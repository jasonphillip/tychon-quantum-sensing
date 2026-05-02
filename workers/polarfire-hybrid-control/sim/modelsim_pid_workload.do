# sim/modelsim_pid_workload.do — ModelSim/QuestaSim driver for workload VCD generation
#
# Drives the SmartHLS-generated nv_pid_top RTL with a representative ODMR-PID
# activity trace and dumps a VCD covering the full nv_pid_top hierarchy. The
# VCD is then ingested by libero/scripts/05_smartpower_workload.tcl as the
# activity source for SmartPower (replacing the default-toggle baseline used
# in the r6_s25 closure).
#
# Usage from a Beelink Git Bash shell:
#   ssh bee
#   cd ~/dev/projects/polarfire-hybrid-control
#   shls hw            # produce hls_output/ RTL (or verify already current)
#   vsim -c -do sim/modelsim_pid_workload.do
#
# The ModelSim wrapper expects the SmartHLS-generated RTL to live at
# hls/hls_output/. If the actual location is hls/output/, adjust the
# RTL_DIR variable below.
#
# CRITICAL: SmartHLS may mangle port names (e.g. `_V` suffix for the
# std_logic_vector serialization of ap_fixpt types). Verify the actual
# port names in the generated nv_pid_top.v after `shls hw` runs and adjust
# the force commands. Comments below document the C++ → RTL mapping.

# ---------------------------------------------------------------------------
# Paths and configuration
# ---------------------------------------------------------------------------
set RTL_DIR "hls/hls_output"
set TRACE_CSV "sim/stimulus/odmr_representative_trace.csv"
set VCD_OUT "sim/output/pid_workload.vcd"
set CLK_PERIOD_PS 5000  ;# 200 MHz
set HALF_PERIOD_PS [expr {$CLK_PERIOD_PS / 2}]

# Total cycles to simulate per CSV row (1 by default — one PID iteration per
# row of the trace). Increase to amplify activity time per row.
set CYCLES_PER_ROW 1

# ---------------------------------------------------------------------------
# Compile RTL
# ---------------------------------------------------------------------------
puts "INFO: compiling SmartHLS-generated RTL from $RTL_DIR"

# Top-level wrapper from SmartHLS. The exact filename varies by tool version;
# common patterns: nv_pid_top.v, nv_pid_top_top.v, or rtl/nv_pid_top.v.
# Edit if needed.
if {[file exists "$RTL_DIR/nv_pid_top.v"]} {
    vlog "$RTL_DIR/nv_pid_top.v"
} elseif {[file exists "$RTL_DIR/rtl/nv_pid_top.v"]} {
    vlog "$RTL_DIR/rtl/nv_pid_top.v"
} else {
    puts "FATAL: nv_pid_top.v not found under $RTL_DIR — verify SmartHLS output path"
    exit 1
}

# Companion modules (clamps, watchdog, etc.) — pull anything else SmartHLS
# emits. -nologo silences banner; -reportprogress runs cleaner in batch mode.
foreach v [glob -nocomplain "$RTL_DIR/*.v"] {
    if {[file tail $v] ne "nv_pid_top.v"} { vlog $v }
}

# ---------------------------------------------------------------------------
# Elaborate
# ---------------------------------------------------------------------------
vsim -t ps -voptargs="+acc" work.nv_pid_top

# ---------------------------------------------------------------------------
# VCD dump setup — capture the full hierarchy under nv_pid_top so SmartPower
# has activity data for every signal in the design.
# ---------------------------------------------------------------------------
vcd file $VCD_OUT
vcd add -r /nv_pid_top/*

# ---------------------------------------------------------------------------
# Drive clock and reset.
# ---------------------------------------------------------------------------
force -freeze sim:/nv_pid_top/clk 1 0, 0 [format "%d ps" $HALF_PERIOD_PS] -repeat [format "%d ps" $CLK_PERIOD_PS]
# Reset assumed active-low. Adjust signal name + polarity if SmartHLS emits
# a different reset port (some configs use ap_rst_n, rst_n, areset).
force -freeze sim:/nv_pid_top/ap_rst_n 0 0
run 50 ns
force -freeze sim:/nv_pid_top/ap_rst_n 1 50ns
run 50 ns

# ---------------------------------------------------------------------------
# Hold static AXI-target inputs (Kp, Ki, Kd, out_min, out_max,
# inner_clamp_setpoint) at representative values. SmartHLS exposes these as
# `_V`-suffixed std_logic_vectors when the C++ type is ap_fixpt.
#
# Q16.16 conversion: float * 2^16 → 32-bit signed integer → padded to vector.
# 0.0001 → 6        (0.0001 * 65536 ≈ 6.5536 → round to 6 or 7)
# 0.00002 → 1
# 0.00001 → 0 (rounds to zero — pick a slightly larger Ki for non-trivial activity)
# 0.0 → 0
# 5.0 → 327680
# 0.045 → 2950      (OUTER_SECTOR_CLAMP_FRACTION)
# ---------------------------------------------------------------------------
force -freeze sim:/nv_pid_top/Kp_V                  32'd6
force -freeze sim:/nv_pid_top/Ki_V                  32'd1
force -freeze sim:/nv_pid_top/Kd_V                  32'd0
force -freeze sim:/nv_pid_top/out_min_V             32'd0
force -freeze sim:/nv_pid_top/out_max_V             32'd327680
force -freeze sim:/nv_pid_top/inner_clamp_setpoint_V 32'd2950

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

    force -freeze sim:/nv_pid_top/error_V              [q_pack $error_hz   30 64]
    force -freeze sim:/nv_pid_top/u_AI_in_V            [q_pack $u_ai_volts 16 32]
    force -freeze sim:/nv_pid_top/ai_watchdog_timeout  $wd_flag

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
