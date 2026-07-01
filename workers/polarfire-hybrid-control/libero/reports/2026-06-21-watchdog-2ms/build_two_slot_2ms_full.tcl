set ROOT   "~/libero_seedsweep/seed7_vbx201_v250_2ms_20260621_160037"
set PRJ    "$ROOT/MPFS_ICICLE_Vectorblox.prjx"
set HDL    "$ROOT/hdl_two_slot"
set EXPORT "$ROOT/export"
set RPT    "$ROOT/two_slot_reports_2ms"
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

proc stage {name} {
    puts "==> run_tool $name [stamp]"
    flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"
        flush stdout
        save_project
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name [stamp]"
    flush stdout
    save_project
}

puts "==> WATCHDOG_2MS_FULL_START [stamp]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
flush stdout

foreach f {pid_csr_block.v pid_csr_axi4_wrap.v vbx_pulse_gen.v watchdog_timer.v} {
    puts "==> import_files $f"
    flush stdout
    if {[catch {import_files -hdl_source "$HDL/$f"} err]} {
        puts "==> import_files WARN ($f): $err"
        flush stdout
    }
}

puts "==> build_design_hierarchy"
flush stdout
build_design_hierarchy
flush stdout

show_states
stage SYNTHESIZE
show_states
stage PLACEROUTE
show_states
stage VERIFYTIMING
show_states

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

stage GENERATEPROGRAMMINGDATA
show_states

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
puts "==> WATCHDOG_2MS_FULL_DONE [stamp]"
flush stdout
exit 0
