# rebuild_idfix2.tcl — re-synth/P&R/export the two-slot bitstream with BOTH the
# M0 AXI completion fix (reset=~resetn + demux ID-replay, idfix) AND the actuator
# output latch (2026-06-18): pid_subsystem latches nv_pid_top.actuator_out_write_data
# on actuator_out_write_en, feeding the CSR tap so software can read the live PID
# actuator at 0x60040844. Full datapath verified in tests/two_slot_sim/tb_actuator.v
# (actuator = Kp*error, clamp saturates) BEFORE this rebuild.
#
# HDL already overwritten in project hdl/. New export name preserves all rollbacks:
#   two_slot_idfix a... / two_slot_demo a5550f9e / vbx201_v250 4e3323e8.

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
        [list -file "$RPT/two_slot_idfix2_timing.rpt"]} err]} {
    puts "==> timing report WARN: $err"; flush stdout
}

stage GENERATEPROGRAMMINGDATA

puts "==> export_prog_job idfix2"; flush stdout
export_prog_job -job_file_name {polarfire_hybrid_control_two_slot_idfix2} -export_dir $EXPORT
save_project
puts "==> REBUILD_IDFIX2 COMPLETE"; flush stdout
