set ROOT   "~/libero_seedsweep/seed7_vbx201_v250_safety_export_unverified_20260621_1120"
set PRJ    "$ROOT/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "$ROOT/export_unverified_do_not_program"
set JOB    "polarfire_hybrid_control_two_slot_safety_UNVERIFIED_DO_NOT_PROGRAM"
file mkdir $EXPORT
puts "==> EXPORT_UNVERIFIED_START [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
foreach t {SYNTHESIZE PLACEROUTE VERIFYTIMING GENERATEPROGRAMMINGDATA EXPORTPROGRAMMINGJOB} {
    if {[catch {get_tool_state -name $t} s]} {
        puts "==> state $t WARN $s"
    } else {
        puts "==> state $t = $s"
    }
    flush stdout
}
puts "==> SKIP VERIFYTIMING intentionally; prior safety-direct VERIFYTIMING failed with not ROUTED_CONNECT"
puts "==> run_tool GENERATEPROGRAMMINGDATA"
flush stdout
set gen_ok 0
if {[catch {run_tool -name {GENERATEPROGRAMMINGDATA}} err]} {
    puts "==> GENERATEPROGRAMMINGDATA_FAILED : $err"
} else {
    set gen_ok 1
    puts "==> GENERATEPROGRAMMINGDATA_OK"
    save_project
}
flush stdout
puts "==> export_prog_job $JOB"
flush stdout
set exp_ok 0
if {[catch {export_prog_job -job_file_name $JOB -export_dir $EXPORT} err]} {
    puts "==> EXPORT_PROG_JOB_FAILED : $err"
} else {
    set exp_ok 1
    puts "==> EXPORT_PROG_JOB_OK"
    save_project
}
flush stdout
foreach f [glob -nocomplain "$EXPORT/*"] {
    puts "==> EXPORT_FILE [file tail $f] size=[file size $f] mtime=[clock format [file mtime $f] -format {%Y-%m-%dT%H:%M:%S%z}]"
}
close_project
puts "==> EXPORT_UNVERIFIED_DONE gen_ok=$gen_ok exp_ok=$exp_ok [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
flush stdout
if {$exp_ok == 1} { exit 0 } else { exit 1 }
