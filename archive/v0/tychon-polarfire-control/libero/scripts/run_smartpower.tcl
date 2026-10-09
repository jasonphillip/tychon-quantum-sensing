# run_smartpower.tcl — Multi-Mode SmartPower Analysis
#
# Standalone SmartPower script for post-P&R power estimation.
# Produces subsystem-level breakdown and multi-mode analysis
# for Phase I KPP validation (total < 12 W).
#
# Prerequisites: scripts 01-03 must have run, and 04_synth_pnr.tcl
# must have completed at least through PLACEROUTE.
#
# Run on Beelink:
#   "C:/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/libero.exe" \
#       SCRIPT:~/dev/projects/tychon-polarfire-control/libero/scripts/run_smartpower.tcl
#
# Or from within an open Libero Tcl console:
#   source run_smartpower.tcl

# ──────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set PROJ_DIR    [file join $REPO_ROOT libero work]
set PROJ_FILE   [file join $PROJ_DIR tychon_polarfire_control.prjx]
set REPORT_DIR  [file join $REPO_ROOT libero reports]

file mkdir $REPORT_DIR

# ──────────────────────────────────────────────────────
# Verify project exists
# ──────────────────────────────────────────────────────
if {![file exists $PROJ_FILE]} {
    puts "ERROR: Project not found at $PROJ_FILE"
    puts "       Run scripts 01-04 first (at least through PLACEROUTE)."
    error "Missing Libero project"
}

puts "INFO: Opening project $PROJ_FILE"
open_project -file $PROJ_FILE

# ──────────────────────────────────────────────────────
# Mode 1: Active — Full operation (PID + VBX inference)
#
# Toggle rate 12.5% is Libero's default conservative
# estimate for designs without VCD. This represents
# typical FPGA fabric switching activity.
# ──────────────────────────────────────────────────────
puts ""
puts "============================================"
puts " Mode 1: ACTIVE (PID + VBX inference)"
puts "============================================"

configure_tool -name {POWERANALYSIS} -params [subst {
    OPERATING_CONDITIONS:Typical \
    AMBIENT_TEMP:25 \
    TOGGLE_RATE:12.5 \
    STATIC_PROBABILITY:0.5
}]

puts "INFO: Running SmartPower — Active mode (toggle=12.5%, 25C typical)..."
run_tool -name {POWERANALYSIS}

set rpt_active [file join $REPORT_DIR smartpower_active.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $rpt_active]

puts "INFO: Active-mode report written to $rpt_active"

# ──────────────────────────────────────────────────────
# Mode 2: Worst-case — Max junction temp, max toggle
#
# Military/industrial worst-case: 85C junction, high
# switching activity. This is the number that must
# stay under 12 W for KPP compliance.
# ──────────────────────────────────────────────────────
puts ""
puts "============================================"
puts " Mode 2: WORST-CASE (85C, high activity)"
puts "============================================"

configure_tool -name {POWERANALYSIS} -params [subst {
    OPERATING_CONDITIONS:Worst \
    AMBIENT_TEMP:85 \
    TOGGLE_RATE:25.0 \
    STATIC_PROBABILITY:0.5
}]

puts "INFO: Running SmartPower — Worst-case mode (toggle=25%, 85C worst)..."
run_tool -name {POWERANALYSIS}

set rpt_worst [file join $REPORT_DIR smartpower_worstcase.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $rpt_worst]

puts "INFO: Worst-case report written to $rpt_worst"

# ──────────────────────────────────────────────────────
# Mode 3: PID-only — VBX idle/sleep
#
# Between AI inference bursts (10-100 Hz duty cycle),
# VBX is idle. Low toggle rate on fabric, PID still
# running at 200 MHz.
# ──────────────────────────────────────────────────────
puts ""
puts "============================================"
puts " Mode 3: PID-ONLY (VBX idle, low activity)"
puts "============================================"

configure_tool -name {POWERANALYSIS} -params [subst {
    OPERATING_CONDITIONS:Typical \
    AMBIENT_TEMP:25 \
    TOGGLE_RATE:5.0 \
    STATIC_PROBABILITY:0.5
}]

puts "INFO: Running SmartPower — PID-only mode (toggle=5%, VBX idle)..."
run_tool -name {POWERANALYSIS}

set rpt_idle [file join $REPORT_DIR smartpower_pid_only.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $rpt_idle]

puts "INFO: PID-only report written to $rpt_idle"

# ──────────────────────────────────────────────────────
# Mode 4: Standby — MSS only, fabric clock-gated
#
# Ultra-low power mode for when control loop is paused.
# Only MSS static power + leakage.
# ──────────────────────────────────────────────────────
puts ""
puts "============================================"
puts " Mode 4: STANDBY (minimal activity)"
puts "============================================"

configure_tool -name {POWERANALYSIS} -params [subst {
    OPERATING_CONDITIONS:Typical \
    AMBIENT_TEMP:25 \
    TOGGLE_RATE:0.5 \
    STATIC_PROBABILITY:0.5
}]

puts "INFO: Running SmartPower — Standby mode (toggle=0.5%)..."
run_tool -name {POWERANALYSIS}

set rpt_standby [file join $REPORT_DIR smartpower_standby.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $rpt_standby]

puts "INFO: Standby report written to $rpt_standby"

# ──────────────────────────────────────────────────────
# Also export the primary report as the canonical file
# (worst-case is the KPP-relevant number)
# ──────────────────────────────────────────────────────
configure_tool -name {POWERANALYSIS} -params [subst {
    OPERATING_CONDITIONS:Worst \
    AMBIENT_TEMP:85 \
    TOGGLE_RATE:25.0 \
    STATIC_PROBABILITY:0.5
}]

run_tool -name {POWERANALYSIS}

set rpt_main [file join $REPORT_DIR smartpower_report.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $rpt_main]

# ──────────────────────────────────────────────────────
# Generate Markdown summary
#
# SmartPower text reports are verbose; this creates
# a concise deliverable-grade summary. Note: the
# actual power values are parsed from the .rpt files
# after the run. This Tcl section writes the template
# with instructions for the actual numbers.
# ──────────────────────────────────────────────────────
set md_file [file join $REPORT_DIR smartpower_estimate.md]
set fd [open $md_file w]

puts $fd "# SmartPower Analysis — Tychon PolarFire Control"
puts $fd ""
puts $fd "**Device:** MPFS250T-FCSG536 (PolarFire SoC)"
puts $fd "**Date:** [clock format [clock seconds] -format {%Y-%m-%d %H:%M}]"
puts $fd "**Tool:** Libero SoC 2025.2 / SmartPower"
puts $fd "**Method:** Post-P&R toggle-rate estimation (no VCD)"
puts $fd ""
puts $fd "## KPP Requirement"
puts $fd ""
puts $fd "Total payload power **must be < 12 W** to meet Phase I KPP."
puts $fd ""
puts $fd "## Multi-Mode Power Summary"
puts $fd ""
puts $fd "| Mode | Toggle Rate | Temp | Conditions | Report File |"
puts $fd "|------|-------------|------|------------|-------------|"
puts $fd "| Active (PID+VBX) | 12.5% | 25C | Typical | smartpower_active.rpt |"
puts $fd "| Worst-Case | 25.0% | 85C | Worst | smartpower_worstcase.rpt |"
puts $fd "| PID-Only (VBX idle) | 5.0% | 25C | Typical | smartpower_pid_only.rpt |"
puts $fd "| Standby | 0.5% | 25C | Typical | smartpower_standby.rpt |"
puts $fd ""
puts $fd "## Subsystem Power Breakdown"
puts $fd ""
puts $fd "Extract these values from the worst-case .rpt file:"
puts $fd ""
puts $fd "| Subsystem | Static (W) | Dynamic (W) | Total (W) | Notes |"
puts $fd "|-----------|-----------|-------------|-----------|-------|"
puts $fd "| RISC-V MSS (4x RV64GC) | — | — | — | DDR4 controller, MMUART |"
puts $fd "| FPGA Fabric (logic+routing) | — | — | — | PID + glue logic |"
puts $fd "| CoreVectorBlox V250 | — | — | — | AI inference engine |"
puts $fd "| Clock Network (PF_CCC) | — | — | — | 125→200 MHz PLL |"
puts $fd "| I/O Ring | — | — | — | LVCMOS 3.3V |"
puts $fd "| SerDes | — | — | — | Not used (0 W expected) |"
puts $fd "| Memory (LSRAM/uSRAM) | — | — | — | VBX weight storage |"
puts $fd "| **TOTAL** | **—** | **—** | **—** | **Must be < 12 W** |"
puts $fd ""
puts $fd "## Notes"
puts $fd ""
puts $fd "- Toggle-rate estimation is conservative without VCD stimulus"
puts $fd "- VectorBlox duty-cycled at 10-100 Hz; PID-only mode is the steady-state"
puts $fd "- Worst-case 85C numbers are the KPP-binding values"
puts $fd "- MSS power depends on enabled peripherals (configured in MSS Configurator)"
puts $fd "- Actual numbers will be populated from .rpt files after this script completes"
puts $fd ""
puts $fd "## Raw Reports"
puts $fd ""
puts $fd "See accompanying .rpt files in this directory for full SmartPower output."

close $fd

puts ""
puts "INFO: Markdown summary written to $md_file"

# ──────────────────────────────────────────────────────
# Done
# ──────────────────────────────────────────────────────
save_project
close_project

puts ""
puts "========================================="
puts " SmartPower multi-mode analysis complete"
puts ""
puts " Reports in: $REPORT_DIR"
puts "   smartpower_active.rpt     — 25C typical, 12.5% toggle"
puts "   smartpower_worstcase.rpt  — 85C worst, 25% toggle"
puts "   smartpower_pid_only.rpt   — 25C typical, 5% toggle (VBX idle)"
puts "   smartpower_standby.rpt    — 25C typical, 0.5% toggle"
puts "   smartpower_report.rpt     — canonical worst-case (KPP)"
puts "   smartpower_estimate.md    — summary for deliverable"
puts ""
puts " KPP check: total worst-case must be < 12 W"
puts "========================================="
