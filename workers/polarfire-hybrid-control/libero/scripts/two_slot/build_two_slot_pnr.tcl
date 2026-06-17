# build_two_slot_pnr.tcl — place-and-route, timing, and programming-job export
# for the two-slot integration. Run AFTER build_two_slot_synth.tcl + the
# synthesis audit gate has passed.
#
# Run on Beelink:  libero "SCRIPT:~/.../build_two_slot_pnr.tcl"

set PRJ    "~/libero_seedsweep/seed7_vbx201_v250/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "~/libero_seedsweep/seed7_vbx201_v250/export"
set RPT    "~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports"

file mkdir $RPT
file mkdir $EXPORT

puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
flush stdout

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
}

stage PLACEROUTE
stage VERIFYTIMING

# Timing report (text) for slack extraction.
if {[catch {report -type {timing} -format {text} -max_paths {20} \
        [list -file "$RPT/two_slot_timing.rpt"]} err]} {
    puts "==> timing report WARN: $err"
    flush stdout
}
# Resource utilization.
if {[catch {report -type {status} -format {text} \
        [list -file "$RPT/two_slot_resources.rpt"]} err]} {
    puts "==> status report WARN: $err"
    flush stdout
}

stage GENERATEPROGRAMMINGDATA

puts "==> export_prog_job polarfire_hybrid_control_two_slot"
flush stdout
export_prog_job -job_file_name {polarfire_hybrid_control_two_slot} -export_dir $EXPORT
flush stdout

save_project
puts "==> PNR SCRIPT COMPLETE"
flush stdout
