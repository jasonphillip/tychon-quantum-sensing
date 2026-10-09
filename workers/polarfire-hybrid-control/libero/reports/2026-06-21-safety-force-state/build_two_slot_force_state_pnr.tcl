set PRJ    "~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055/export"
set RPT    "~/libero_seedsweep/seed7_vbx201_v250_safety_cleanhandoff_20260621_1055/two_slot_reports_force_state"
file mkdir $RPT
file mkdir $EXPORT
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
flush stdout
foreach t {SYNTHESIZE PLACEROUTE VERIFYTIMING GENERATEPROGRAMMINGDATA} {
    if {[catch {get_tool_state -name $t} s]} {
        puts "==> get_tool_state $t WARN: $s"
    } else {
        puts "==> get_tool_state $t = $s"
    }
    flush stdout
}
puts "==> set_tool_state SYNTHESIZE StateSuccess"
flush stdout
set_tool_state -name {SYNTHESIZE} -state {StateSuccess}
save_project
proc stage {name} {
    puts "==> run_tool $name"
    flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"
        flush stdout
        save_project
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name"
    flush stdout
    save_project
}
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
close_project
puts "==> FORCE_STATE_PNR SCRIPT COMPLETE"
flush stdout
exit 0
