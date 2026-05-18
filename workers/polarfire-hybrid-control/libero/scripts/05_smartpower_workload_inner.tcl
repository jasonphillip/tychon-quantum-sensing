# 05_smartpower_workload_inner.tcl
#
# SmartPower-context Tcl script invoked by 05_smartpower_workload.tcl via
# `update_and_run_tool -name {POWERANALYSIS} -script <this-file>`. This file
# runs INSIDE SmartPower's Tcl namespace where smartpower_* commands are
# available.
#
# Reference: Libero SoC v2025.2 SmartPower Tcl Commands User Guide,
# §9.16 smartpower_import_vcd, §9.x smartpower_report_power.

set REPO_ROOT "~/dev/projects/polarfire-hybrid-control"
set WORKLOAD_VCD "$REPO_ROOT/sim/output/pid_workload.vcd"
# Note: SmartPower's restricted Tcl namespace doesn't expose ::tcl::clock::format,
# so REPORT_DIR_TAG is hardcoded here. Update the date constant manually for
# multi-day re-runs.
set REPORT_DIR_TAG "2026-05-18-workload-power"
set REPORT_DIR "$REPO_ROOT/libero/reports/$REPORT_DIR_TAG"

file mkdir $REPORT_DIR

puts "INFO (sp inner): importing workload VCD = $WORKLOAD_VCD"
flush stdout

if {[catch {
    smartpower_import_vcd -file $WORKLOAD_VCD -opmode {Active}
} err]} {
    puts "FATAL (sp inner): smartpower_import_vcd failed: $err"
    exit 11
}
puts "INFO (sp inner): VCD imported"
flush stdout

# Make sure Active mode is the analysis mode (the imported VCD lives there)
if {[catch {smartpower_set_mode_for_analysis -mode {Active}} err]} {
    puts "WARN (sp inner): smartpower_set_mode_for_analysis failed (continuing): $err"
}

# Emit text-format power report
set rpt_file "$REPORT_DIR/smartpower_workload.rpt"
puts "INFO (sp inner): writing text power report -> $rpt_file"
if {[catch {
    smartpower_report_power \
        -frequnit {MHz} \
        -opcond {Typical} \
        -opmode {Active} \
        -file $rpt_file
} err]} {
    puts "FATAL (sp inner): smartpower_report_power failed: $err"
    exit 12
}
puts "INFO (sp inner): power report written"
flush stdout
exit 0
