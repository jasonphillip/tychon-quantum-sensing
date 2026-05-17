# 05_smartpower_workload.tcl — Workload-driven SmartPower analysis (Phase II P3-RPO-6)
#
# STATUS (2026-05-17, DLOG-047): INFRASTRUCTURE PREP — not yet runnable.
# Known gaps:
#   1. PROJECT_PATH MISMATCH. The r6_s25 closure that the brief KPP refers to
#      lives in the Microchip reference design at
#         C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/
#      NOT under libero/work/polarfire_hybrid_control/ which this script
#      currently opens. The latter has empty designer/ — no placed netlist.
#      To attach SmartPower to the r6_s25 netlist, change open_project to
#      point at $REF_PROJECT (see closure_pipeline.tcl line 14-15 for the path).
#   2. SmartPower VCD Tcl form is unverified (the catch fallback below exists
#      precisely to discover which command form Libero 2025.2 accepts).
#   3. VCD generation upstream — sim/modelsim_pid_workload.do has been
#      corrected for SmartHLS 2025.2 port names but still has a documented
#      gap around driving Kp_reg/Ki_reg/Kd_reg via hierarchical force or AXI
#      transactions.
#
# Re-runs SmartPower against the existing 2026-04-29-pid-real/r6_s25 P&R
# layout using a representative workload VCD as the activity source, instead
# of Libero's default-toggle activity heuristic. This converts FTR §7.4 KPP
# "Total Power" from PARTIAL to PASS evidence.
#
# Inputs:
#   sim/output/pid_workload.vcd   — produced by sim/modelsim_pid_workload.do
#                                    after `shls hw` + ModelSim simulation
#                                    on the Beelink.
#
# Outputs (all under libero/reports/$REPORT_TAG/):
#   smartpower_workload.rpt          — text power report
#   MPFS_ICICLE_KIT_BASE_DESIGN_power_workload.xml  — XML breakdown
#   smartpower_workload.spw          — Libero SmartPower DB
#
# Does NOT touch:
#   - libero/scripts/04_synth_pnr.tcl (r6_s25 closure remains canonical default-toggle baseline)
#   - libero/reports/2026-04-29-pid-real/* (r6_s25 reports preserved)
#
# Usage from Beelink:
#   ssh bee 'cd ~/dev/projects/polarfire-hybrid-control && libero SCRIPT:libero/scripts/05_smartpower_workload.tcl'

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Date-stamped report tag. Update when re-running for a new closure cycle.
set REPORT_TAG "2026-05-XX-workload-power"

set REPO_ROOT  [pwd]
set PROJECT    "polarfire_hybrid_control"
set REPORT_DIR [file join $REPO_ROOT libero reports $REPORT_TAG]
set WORKLOAD_VCD [file join $REPO_ROOT sim output pid_workload.vcd]

file mkdir $REPORT_DIR

# ---------------------------------------------------------------------------
# Open the existing project. The script assumes the canonical r6_s25
# layout is the latest place-and-route result in the project workspace.
# Re-running 04_synth_pnr.tcl is NOT required — SmartPower runs against the
# already-placed netlist.
# ---------------------------------------------------------------------------
puts "INFO: opening Libero project for workload SmartPower analysis"
open_project -file [file join $REPO_ROOT libero work $PROJECT.prjx]

# ---------------------------------------------------------------------------
# Sanity: workload VCD must exist.
# ---------------------------------------------------------------------------
if {![file exists $WORKLOAD_VCD]} {
    puts "FATAL: workload VCD not found at $WORKLOAD_VCD"
    puts "  Generate it on the Beelink with:"
    puts "    shls hw"
    puts "    vsim -c -do sim/modelsim_pid_workload.do"
    exit 1
}
puts "INFO: workload VCD: $WORKLOAD_VCD"

# ---------------------------------------------------------------------------
# Configure SmartPower to use the workload VCD as the activity source.
#
# NOTE: The exact Tcl command for setting the VCD-based activity source in
# Libero 2025.2 SmartPower is one of:
#   - set_smartpower_options -vcd_file <path>
#   - read_vcd <path>
#   - import_files -smartpower_vcd <path>
# Verify against the Libero 2025.2 SmartPower User Guide / Tcl Command
# Reference at first execution, then pin the working form.
# ---------------------------------------------------------------------------
puts "INFO: registering workload VCD as SmartPower activity source"

# Most likely form per recent Libero releases:
catch {
    set_smartpower_options -vcd_file $WORKLOAD_VCD
} smartpower_set_err
if {$smartpower_set_err ne ""} {
    puts "WARN: set_smartpower_options -vcd_file failed: $smartpower_set_err"
    puts "      trying alternate form..."
    catch { read_vcd $WORKLOAD_VCD } read_vcd_err
    if {$read_vcd_err ne ""} {
        puts "FATAL: both set_smartpower_options and read_vcd failed."
        puts "       Verify exact command name in Libero 2025.2 Tcl reference."
        puts "       Errors: $smartpower_set_err / $read_vcd_err"
        exit 2
    }
}

# ---------------------------------------------------------------------------
# Run SmartPower. The tool ingests the VCD activity and computes
# workload-specific dynamic power, then combines with leakage.
# ---------------------------------------------------------------------------
puts "INFO: running POWERANALYSIS with workload VCD activity"
run_tool -name {POWERANALYSIS}

# ---------------------------------------------------------------------------
# Export reports.
# ---------------------------------------------------------------------------
set power_rpt [file join $REPORT_DIR smartpower_workload.rpt]
set power_xml [file join $REPORT_DIR \
                MPFS_ICICLE_KIT_BASE_DESIGN_power_workload.xml]

puts "INFO: exporting workload SmartPower text report -> $power_rpt"
report \
    -type {power} \
    -format {text} \
    [list -file $power_rpt]

puts "INFO: exporting workload SmartPower XML breakdown -> $power_xml"
report \
    -type {power} \
    -format {xml} \
    [list -file $power_xml]

# ---------------------------------------------------------------------------
# Capture the SmartPower DB so a later session can re-open the analysis
# without re-ingesting the VCD.
# ---------------------------------------------------------------------------
set spw_dst [file join $REPORT_DIR smartpower_workload.spw]
set spw_src [file join $REPO_ROOT libero work $PROJECT.spw]
if {[file exists $spw_src]} {
    file copy -force $spw_src $spw_dst
    puts "INFO: copied SmartPower DB -> $spw_dst"
}

puts ""
puts "DONE: workload-driven SmartPower closure landed in $REPORT_DIR"
puts "  Compare against r6_s25 default-toggle baseline:"
puts "    libero/reports/2026-04-29-pid-real/MPFS_ICICLE_KIT_BASE_DESIGN_power_report.xml"
puts "  Default-toggle baseline: 2,692.88 mW total / 2,247.27 mW dynamic"
puts "  KPP delta: see docs/track2_workload_smartpower.md (TBD on first run)"

close_project -save 0
