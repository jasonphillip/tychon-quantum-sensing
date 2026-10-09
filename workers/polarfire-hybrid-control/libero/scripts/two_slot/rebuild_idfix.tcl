# rebuild_idfix.tcl — re-synth/P&R/export the two-slot bitstream with the M0 AXI
# completion fix (2026-06-18): nv_pid_top.reset = ~resetn (was 1'b0) +
# axi4_demux2 latches/replays the master AW/AR ID on B/R. Both verified in a
# ModelSim AXI testbench (tests/two_slot_sim/tb_m0.v) BEFORE this rebuild.
#
# HDL already overwritten in project hdl/ (pid_subsystem.v, axi4_demux2.v).
# Exports a NEW job name so the prior rollbacks stay intact:
#   polarfire_hybrid_control_two_slot_demo.job  (a5550f9e, current on-silicon)
#   polarfire_hybrid_control_vbx201_v250.job    (4e3323e8, V250 rollback)
#
# Run on Beelink:  libero "SCRIPT:~/rebuild_idfix.tcl"

set PRJ    "~/libero_seedsweep/seed7_vbx201_v250/MPFS_ICICLE_Vectorblox.prjx"
set EXPORT "~/libero_seedsweep/seed7_vbx201_v250/export"
set RPT    "~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports"
file mkdir $RPT
file mkdir $EXPORT

puts "==> open_project"; flush stdout
open_project -file $PRJ
puts "==> build_design_hierarchy"; flush stdout
build_design_hierarchy

proc stage {name} {
    puts "==> run_tool $name"; flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"; flush stdout
        save_project
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name"; flush stdout
}

stage SYNTHESIZE
stage PLACEROUTE
stage VERIFYTIMING

if {[catch {report -type {timing} -format {text} -max_paths {20} \
        [list -file "$RPT/two_slot_idfix_timing.rpt"]} err]} {
    puts "==> timing report WARN: $err"; flush stdout
}
if {[catch {report -type {status} -format {text} \
        [list -file "$RPT/two_slot_idfix_status.rpt"]} err]} {
    puts "==> status report WARN: $err"; flush stdout
}

stage GENERATEPROGRAMMINGDATA

puts "==> export_prog_job idfix"; flush stdout
export_prog_job -job_file_name {polarfire_hybrid_control_two_slot_idfix} -export_dir $EXPORT
save_project
puts "==> REBUILD_IDFIX COMPLETE"; flush stdout
