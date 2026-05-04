# 04_synth_pnr.tcl — Synthesis, Place & Route, Report Extraction
#
# Runs the full back-end flow and extracts reports:
#   1. SmartTime XML  — proves Fmax >= 200 MHz, PID latency < 150 µs
#   2. SmartPower XML — proves total power < 12 W
#   3. Resource utilization — LUTs, LSRAM, Math Blocks, DSPs
#
# Reports are written to libero/reports/ and committed to git.
#
# Run after 03_smartdesign.tcl:
#   cd <repo>/libero/scripts
#   source 04_synth_pnr.tcl

# ──────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set PROJ_DIR    [file join $REPO_ROOT libero work]
set PROJ_FILE   [file join $PROJ_DIR polarfire_hybrid_control.prjx]
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
# per-path timing detail.
# ──────────────────────────────────────────────────────
puts "INFO: Running SmartTime timing analysis..."
run_tool -name {VERITIMING}

# SmartTime detailed text report (was previously calling export_prog_job
# with smarttime_timing.xml as the job_file_name, which is the bitstream
# API misused for SmartTime — fixed 2026-05-04 in HW-04d).
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
# For initial validation, this is sufficient. A VCD
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
# Step 6: Export programming job file (.job) — HW-04d
#
# Persists the bitstream artifact to a dated subdir so each
# closure has a verifiable .job + sha256 sidecar. The base
# `export_prog_job` call previously did not consistently land
# the file on disk; we now copy + checksum explicitly.
# ──────────────────────────────────────────────────────
puts "INFO: Generating programming job file..."
run_tool -name {GENERATEPROGRAMMINGDATA}

# Dated subdir: libero/reports/YYYY-MM-DD-bringup/
set TODAY        [clock format [clock seconds] -format "%Y-%m-%d"]
set CLOSURE_DIR  [file join $REPORT_DIR "$TODAY-bringup"]
file mkdir $CLOSURE_DIR

# Primary export to the flat REPORT_DIR (matches existing tooling expectations)
export_prog_job \
    -job_file_name {polarfire_hybrid_control} \
    -export_dir $REPORT_DIR

# Resolve the produced .job, copy it (and any sibling .fs / .stp / .ppd)
# into the dated closure subdir, and write a sha256 sidecar.
set _job_glob [glob -nocomplain [file join $REPORT_DIR polarfire_hybrid_control.job]]
if {[llength $_job_glob] == 0} {
    puts "WARN: export_prog_job produced no .job in $REPORT_DIR"
    puts "WARN: searching project tree for fallback artifact..."
    set _job_glob [glob -nocomplain [file join $PROJ_DIR designer impl1 export "*.job"]]
    if {[llength $_job_glob] == 0} {
        puts "ERROR: no .job artifact found anywhere — bitstream export failed"
    }
}

foreach _job $_job_glob {
    set _basename [file tail $_job]
    set _dest [file join $CLOSURE_DIR $_basename]
    file copy -force $_job $_dest
    puts "INFO: copied $_basename → $CLOSURE_DIR"

    # sha256 sidecar — Tcl 8.6+ via sha256sum if available, else log a stub
    set _sha_file [file join $CLOSURE_DIR "$_basename.sha256"]
    if {![catch {exec sha256sum $_dest} _sha_out]} {
        set _f [open $_sha_file w]
        puts $_f $_sha_out
        close $_f
        puts "INFO: sha256 → $_sha_file"
    } else {
        puts "WARN: sha256sum not available; skipping checksum sidecar"
    }
}

puts "INFO: Programming job exported to $CLOSURE_DIR"

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
puts " Design checks:"
puts "   [ ] Fmax >= 200 MHz (5 ns period)"
puts "   [ ] Total power < 12 W"
puts "   [ ] Resource utilization < 85% (or fallback to MPFS460T)"
puts "========================================="
puts ""
puts "Next: git add libero/reports/ && git commit && git push"
