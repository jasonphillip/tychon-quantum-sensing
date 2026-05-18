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

# Date-stamped report tag.
set REPORT_TAG [clock format [clock seconds] -format "%Y-%m-%d-workload-power"]

set REPO_ROOT  [pwd]
set PROJECT    "polarfire_hybrid_control"
set REPORT_DIR [file join $REPO_ROOT libero reports $REPORT_TAG]
set WORKLOAD_VCD [file join $REPO_ROOT sim output pid_workload.vcd]

# Gap 2 closure (2026-05-18): point at the Microchip reference design where
# the canonical r6_s25 placed netlist actually lives. The local
# libero/work/polarfire_hybrid_control.prjx has an empty designer/ — no
# placed netlist exists there. See closure_pipeline.tcl line 14-15 for the
# canonical path.
set REF_PRJX "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/MPFS_ICICLE_Vectorblox.prjx"

file mkdir $REPORT_DIR

# ---------------------------------------------------------------------------
# Open the existing project. The script attaches SmartPower to the r6_s25
# closed P&R'd netlist inside the Microchip reference design tree.
# Re-running synth/P&R is NOT required — SmartPower runs against the
# already-placed netlist.
# ---------------------------------------------------------------------------
puts "INFO: opening Libero reference-design project: $REF_PRJX"
open_project -file $REF_PRJX

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
# Gap 3 closure (2026-05-18): smartpower_* commands live in SmartPower's
# Tcl namespace, NOT in Libero Designer's top-level batch namespace. Run
# them via `update_and_run_tool -name {POWERANALYSIS} -script <inner.tcl>`
# which invokes SmartPower with its tool-specific Tcl context.
#
# Inner script handles: smartpower_import_vcd + smartpower_report_power.
# ---------------------------------------------------------------------------
set INNER_SCRIPT "$REPO_ROOT/libero/scripts/05_smartpower_workload_inner.tcl"
puts "INFO: invoking VERIFYPOWER with SmartPower inner script: $INNER_SCRIPT"
if {[catch {
    run_tool -name {VERIFYPOWER} -script $INNER_SCRIPT
} err]} {
    puts "FATAL: VERIFYPOWER via run_tool failed: $err"
    exit 2
}
puts "INFO: VERIFYPOWER completed"

# Report generation is handled by the inner SmartPower-context script
# (smartpower_report_power -file <rpt>). The default report-dir tag is
# computed identically in both files (clock format YYYY-MM-DD-workload-power).

puts ""
puts "DONE: workload-driven SmartPower closure landed in $REPORT_DIR"
puts "  Compare against r6_s25 default-toggle baseline:"
puts "    libero/reports/2026-04-29-pid-real/MPFS_ICICLE_KIT_BASE_DESIGN_power_report.xml"
puts "  Default-toggle baseline: 2,692.88 mW total / 2,247.27 mW dynamic"

close_project -save 0
