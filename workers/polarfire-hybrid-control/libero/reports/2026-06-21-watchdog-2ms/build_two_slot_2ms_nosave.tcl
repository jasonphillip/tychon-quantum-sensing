set ROOT   "~/libero_seedsweep/seed7_vbx201_v250_2ms_20260621_160037"
set PRJ    "$ROOT/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "$ROOT/export"
set RPT    "$ROOT/two_slot_reports_2ms_nosave"
set JOB    "polarfire_hybrid_control_two_slot_2ms"

file mkdir $RPT
file mkdir $EXPORT

proc stamp {} {
    return [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]
}

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

proc run_stage_no_save {name} {
    puts "==> run_tool $name [stamp]"
    flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"
        flush stdout
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name [stamp]"
    flush stdout
}

proc run_stage_save {name} {
    run_stage_no_save $name
    save_project
}

puts "==> WATCHDOG_2MS_NOSAVE_START [stamp]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
flush stdout

show_states

# Do not import, build hierarchy, save, or query tool state between SYNTHESIZE
# and PLACEROUTE. Prior attempts saw SYNTHESIZE return OK but the saved Libero
# state immediately become "Tool inputs are out of date."
run_stage_no_save SYNTHESIZE
run_stage_no_save PLACEROUTE
save_project
show_states

run_stage_save VERIFYTIMING

if {[catch {report -type {timing} -format {text} -max_paths {20} \
        [list -file "$RPT/two_slot_2ms_timing.rpt"]} err]} {
    puts "==> timing report WARN: $err"
    flush stdout
}
if {[catch {report -type {status} -format {text} \
        [list -file "$RPT/two_slot_2ms_resources.rpt"]} err]} {
    puts "==> status report WARN: $err"
    flush stdout
}

run_stage_save GENERATEPROGRAMMINGDATA

puts "==> export_prog_job $JOB"
flush stdout
if {[catch {export_prog_job -job_file_name $JOB -export_dir $EXPORT} err]} {
    puts "==> EXPORT_FAILED $JOB : $err"
    flush stdout
    save_project
    error "EXPORT_FAILED $JOB"
}
puts "==> EXPORT_OK $JOB"
flush stdout

save_project
show_states
close_project
puts "==> WATCHDOG_2MS_NOSAVE_DONE [stamp]"
flush stdout
exit 0
