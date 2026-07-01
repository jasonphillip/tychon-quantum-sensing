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
    # Default = the subsystem-level netlist-mirroring VCD (tb_power_wrap.v via
    # sim/modelsim_pid_workload_subsystem.do). The old standalone
    # pid_workload.vcd annotates 0.00% (scope mismatch) — do not use it.
    set WORKLOAD_VCD "$REPO_ROOT/sim/output/pid_workload_subsystem.vcd"
}
if {[info exists ::env(SMARTPOWER_VCD_TOP_LEVEL_NAME)] && $::env(SMARTPOWER_VCD_TOP_LEVEL_NAME) ne ""} {
    set VCD_TOP_LEVEL_NAME $::env(SMARTPOWER_VCD_TOP_LEVEL_NAME)
} else {
    set VCD_TOP_LEVEL_NAME "tb_power"
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

# Make sure Active mode is the analysis mode (the imported VCD lives there)
if {[catch {smartpower_set_mode_for_analysis -mode {Active}} err]} {
    puts "WARN (sp inner): smartpower_set_mode_for_analysis failed (continuing): $err"
}

# Emit the ESSENTIAL artifact FIRST: the text power report. (Ordering matters:
# the 2026-07-01 run showed smartpower_report_power_activity_map can take down
# the whole SmartPower session — it re-imports the VCD — so it must never run
# before the power report is safely on disk.)
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

# OPTIONAL activity map (secondary diagnostic; opt-in via env because it
# performs a second full VCD import and crashed the 2026-07-01 session).
if {[info exists ::env(SMARTPOWER_ACTIVITY_MAP)] && $::env(SMARTPOWER_ACTIVITY_MAP) eq "1"} {
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
            -clock_period {8000.0} \
            -clock_offset {0.0} \
            -file $activity_file
    } err]} {
        puts "WARN (sp inner): smartpower_report_power_activity_map failed: $err"
    } else {
        puts "INFO (sp inner): activity map written"
    }
    flush stdout
} else {
    puts "INFO (sp inner): activity map skipped (set SMARTPOWER_ACTIVITY_MAP=1 to enable)"
}
exit 0
