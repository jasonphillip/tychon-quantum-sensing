set ROOT   "~/libero_seedsweep/seed7_vbx201_v250_safety_runsynth_20260621_1118"
set PRJ    "$ROOT/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "$ROOT/export"
set RPT    "$ROOT/two_slot_reports_runsynth"
set TARGET "$ROOT/synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm"
file mkdir $RPT
file mkdir $EXPORT
puts "==> RUNSYNTH_PNR_START [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
proc show_states {} {
    foreach t {SYNTHESIZE PLACEROUTE VERIFYTIMING GENERATEPROGRAMMINGDATA EXPORTPROGRAMMINGJOB} {
        if {[catch {get_tool_state -name $t} s]} {
            puts "==> state $t WARN $s"
        } else {
            puts "==> state $t = $s"
        }
        flush stdout
    }
}
proc stage {name} {
    puts "==> run_tool $name [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
    flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"
        flush stdout
        save_project
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
    flush stdout
    save_project
}
show_states
puts "==> run_synthesis target=$TARGET"
flush stdout
if {[catch {run_synthesis -logfile "$RPT/run_synthesis.log" -target $TARGET} err]} {
    puts "==> RUN_SYNTHESIS_FAILED : $err"
    flush stdout
    save_project
    error "RUN_SYNTHESIS_FAILED"
}
puts "==> RUN_SYNTHESIS_OK [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
flush stdout
save_project
show_states
if {[file exists $TARGET]} {
    puts "==> TARGET_VM_EXISTS size=[file size $TARGET] mtime=[clock format [file mtime $TARGET] -format {%Y-%m-%dT%H:%M:%S%z}]"
} else {
    puts "==> TARGET_VM_MISSING"
}
flush stdout
stage PLACEROUTE
stage VERIFYTIMING
if {[catch {report -type {timing} -format {text} -max_paths {20} [list -file "$RPT/two_slot_timing.rpt"]} err]} {
    puts "==> timing report WARN: $err"
    flush stdout
}
if {[catch {report -type {status} -format {text} [list -file "$RPT/two_slot_resources.rpt"]} err]} {
    puts "==> status report WARN: $err"
    flush stdout
}
stage GENERATEPROGRAMMINGDATA
puts "==> export_prog_job polarfire_hybrid_control_two_slot_safety"
flush stdout
export_prog_job -job_file_name {polarfire_hybrid_control_two_slot_safety} -export_dir $EXPORT
flush stdout
save_project
show_states
close_project
puts "==> RUNSYNTH_PNR_DONE [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
flush stdout
exit 0
