# 04_synth_pnr.tcl — Synthesis, Place & Route, Report Extraction
#
# Runs the full back-end flow and extracts the three deliverable reports:
#   1. SmartTime XML  — proves Fmax >= 200 MHz, PID latency < 150 µs
#   2. SmartPower XML — proves total power < 12 W
#   3. Resource utilization — LUTs, LSRAM, Math Blocks, DSPs
#
# Reports are written to libero/reports/ and committed from Beelink.
# Analysis happens on DGX Spark after git pull.
#
# Run on Beelink after 03_smartdesign.tcl:
#   cd <repo>/libero/scripts
#   source 04_synth_pnr.tcl

# ──────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set PROJ_DIR    [file join $REPO_ROOT libero work]
set PROJ_FILE   [file join $PROJ_DIR tychon_polarfire_control.prjx]
set REPORT_DIR  [file join $REPO_ROOT libero reports]

# Ensure report output directory exists
file mkdir $REPORT_DIR

# ──────────────────────────────────────────────────────
# Open project
# ──────────────────────────────────────────────────────
puts "INFO: Opening project..."
open_project -file $PROJ_FILE

# ──────────────────────────────────────────────────────
# Step 1: Synthesis (Synplify Pro ME)
# ──────────────────────────────────────────────────────
puts "INFO: Running synthesis..."
run_tool -name {SYNTHESIZE}

# Check synthesis status
set synth_status [run_tool -name {SYNTHESIZE} -script {REPORT}]
puts "INFO: Synthesis complete."

# ──────────────────────────────────────────────────────
# Step 2: Place and Route
# ──────────────────────────────────────────────────────
puts "INFO: Running place and route..."
run_tool -name {PLACEROUTE}
puts "INFO: Place and route complete."

# ──────────────────────────────────────────────────────
# Step 3: SmartTime — Static Timing Analysis
#
# Verifies timing closure at 200 MHz (5 ns period).
# The XML report contains worst-case slack, Fmax, and
# per-path timing detail for the Final Technical Report.
# ──────────────────────────────────────────────────────
puts "INFO: Running SmartTime timing analysis..."
run_tool -name {VERITIMING}

# Export timing report
set timing_xml [file join $REPORT_DIR smarttime_timing.xml]
export_prog_job -job_file_name $timing_xml -export_dir $REPORT_DIR

# SmartTime detailed text report
set timing_rpt [file join $REPORT_DIR smarttime_timing.rpt]
report \
    -type {timing} \
    -format {text} \
    -max_paths {50} \
    [list -file $timing_rpt]

puts "INFO: Timing report written to $REPORT_DIR"

# ──────────────────────────────────────────────────────
# Step 4: SmartPower — Power Estimation
#
# Estimates static + dynamic power. Dynamic accuracy
# depends on activity factors — without a VCD file,
# SmartPower uses toggle-rate estimates (conservative).
# For Phase I deliverable, this is sufficient. A VCD
# from co-simulation would improve accuracy (future).
# ──────────────────────────────────────────────────────
puts "INFO: Running SmartPower analysis..."
run_tool -name {POWERANALYSIS}

set power_rpt [file join $REPORT_DIR smartpower_report.rpt]
report \
    -type {power} \
    -format {text} \
    [list -file $power_rpt]

puts "INFO: Power report written to $REPORT_DIR"

# ──────────────────────────────────────────────────────
# Step 5: Resource Utilization
#
# Extracts LUT, FF, LSRAM, µSRAM, Math Block, and DSP
# usage. Critical for verifying MPFS250T has headroom
# for CoreVectorBlox V250 + PID. If utilization > 85%,
# consider fallback to MPFS460T.
# ──────────────────────────────────────────────────────
set resource_rpt [file join $REPORT_DIR resource_utilization.rpt]
report \
    -type {pin} \
    -format {text} \
    [list -file [file join $REPORT_DIR pin_report.rpt]]

report \
    -type {status} \
    -format {text} \
    [list -file $resource_rpt]

puts "INFO: Resource report written to $REPORT_DIR"

# ──────────────────────────────────────────────────────
# Step 6: Export programming job file (.job)
#
# The .job file is the bitstream for board programming
# via FlashPro. Not strictly needed for Phase I timing/
# power analysis, but useful for Icicle Kit eval.
# ──────────────────────────────────────────────────────
puts "INFO: Generating programming job file..."
run_tool -name {GENERATEPROGRAMMINGDATA}

set job_file [file join $REPORT_DIR tychon_polarfire_control.job]
export_prog_job \
    -job_file_name {tychon_polarfire_control} \
    -export_dir $REPORT_DIR

puts "INFO: Programming job exported to $REPORT_DIR"

# ──────────────────────────────────────────────────────
# Save and summary
# ──────────────────────────────────────────────────────
save_project
close_project

puts ""
puts "========================================="
puts " Synthesis + P&R complete"
puts ""
puts " Reports in: $REPORT_DIR"
puts "   smarttime_timing.rpt  — Fmax, slack, critical paths"
puts "   smartpower_report.rpt — Static + dynamic power"
puts "   resource_utilization.rpt — LUT/FF/LSRAM/DSP usage"
puts "   pin_report.rpt        — I/O assignment status"
puts "   *.job                 — Programming bitstream"
puts ""
puts " Deliverable checks:"
puts "   [ ] Fmax >= 200 MHz (5 ns period)"
puts "   [ ] Total power < 12 W"
puts "   [ ] Resource utilization < 85% (or fallback to MPFS460T)"
puts "========================================="
puts ""
puts "Next: git add libero/reports/ && git commit && git push"
puts "Then pull on Spark for analysis."
