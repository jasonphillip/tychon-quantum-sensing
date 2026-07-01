# 05_smartpower_workload_inner.tcl
#
# SmartPower-context Tcl script invoked by 05_smartpower_workload.tcl via
# `update_and_run_tool -name {POWERANALYSIS} -script <this-file>`. This file
# runs INSIDE SmartPower's Tcl namespace where smartpower_* commands are
# available.
#
# Reference: Libero SoC v2025.2 SmartPower Tcl Commands User Guide,
# §9.16 smartpower_import_vcd, §9.x smartpower_report_power.

if {[info exists ::env(SMARTPOWER_REPO_ROOT)] && $::env(SMARTPOWER_REPO_ROOT) ne ""} {
    set REPO_ROOT $::env(SMARTPOWER_REPO_ROOT)
} else {
    set REPO_ROOT "~/dev/projects/polarfire-hybrid-control"
}
if {[info exists ::env(SMARTPOWER_WORKLOAD_VCD)] && $::env(SMARTPOWER_WORKLOAD_VCD) ne ""} {
    set WORKLOAD_VCD $::env(SMARTPOWER_WORKLOAD_VCD)
} else {
    set WORKLOAD_VCD "$REPO_ROOT/sim/output/pid_workload.vcd"
}
if {[info exists ::env(SMARTPOWER_VCD_TOP_LEVEL_NAME)] && $::env(SMARTPOWER_VCD_TOP_LEVEL_NAME) ne ""} {
    set VCD_TOP_LEVEL_NAME $::env(SMARTPOWER_VCD_TOP_LEVEL_NAME)
} else {
    set VCD_TOP_LEVEL_NAME "nv_pid_top_top"
}

# SmartPower's restricted Tcl namespace may not expose ::tcl::clock::format.
# The outer Libero script passes a dated report tag through the environment;
# keep a fixed fallback for direct SmartPower-context debugging.
if {[info exists ::env(SMARTPOWER_REPORT_TAG)] && $::env(SMARTPOWER_REPORT_TAG) ne ""} {
    set REPORT_DIR_TAG $::env(SMARTPOWER_REPORT_TAG)
} else {
    set REPORT_DIR_TAG "2026-06-21-workload-power"
}
set REPORT_DIR "$REPO_ROOT/libero/reports/$REPORT_DIR_TAG"

file mkdir $REPORT_DIR

puts "INFO (sp inner): importing workload VCD = $WORKLOAD_VCD"
flush stdout

if {[catch {
    smartpower_import_vcd \
        -file $WORKLOAD_VCD \
        -opmode {Active} \
        -auto_detect_top_level_name {FALSE} \
        -top_level_name $VCD_TOP_LEVEL_NAME \
        -glitch_filtering {auto}
} err]} {
    puts "FATAL (sp inner): smartpower_import_vcd failed: $err"
    exit 11
}
puts "INFO (sp inner): VCD imported"
flush stdout

# Emit an activity map directly from the same VCD/top selection. This gives a
# durable diagnostic for whether SmartPower saw real toggling even if the final
# power number remains default-equivalent.
set activity_file "$REPORT_DIR/smartpower_activity_map.csv"
puts "INFO (sp inner): writing activity map -> $activity_file"
if {[catch {
    smartpower_report_power_activity_map \
        -vcd_file $WORKLOAD_VCD \
        -style {CSV} \
        -auto_detect_top_level_name {FALSE} \
        -top_level_name $VCD_TOP_LEVEL_NAME \
        -glitch_filtering {auto} \
        -opmode {Active} \
        -report_query {Report by Net - summary} \
        -report_type {activity and power} \
        -sortby {functional transitions} \
        -sortorder {descending} \
        -max_net {500} \
        -clock_period {5000.0} \
        -clock_offset {0.0} \
        -file $activity_file
} err]} {
    puts "WARN (sp inner): smartpower_report_power_activity_map failed: $err"
} else {
    puts "INFO (sp inner): activity map written"
}
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
