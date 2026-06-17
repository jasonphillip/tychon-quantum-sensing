# build_two_slot_synth.tcl — import the two-slot leaf HDL and synthesize.
#
# Runs IN-PLACE in the working V250 project (seed7_vbx201_v250) after the
# generated netlist has been patched by patch_two_slot.py. Rollback is the
# externally-archived V250 .job (sha256 4e3323e8) plus the patcher's
# .pre_two_slot.bak netlist backups.
#
# Run on Beelink:  libero "SCRIPT:~/.../build_two_slot_synth.tcl"
# (Tcl needs Windows-style paths; see libero/scripts/parallel/README.md.)
#
# Each stage flushes stdout (CLAUDE.md debug rule #8) and is catch-wrapped.

set PRJ "~/libero_seedsweep/seed7_vbx201_v250/MPFS_ICICLE_Vectorblox.prjx"
set HDL "~/libero_seedsweep/seed7_vbx201_v250/hdl_two_slot"

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

puts "==> run_tool SYNTHESIZE"
flush stdout
if {[catch {run_tool -name {SYNTHESIZE}} err]} {
    puts "==> SYNTHESIZE FAILED: $err"
    flush stdout
    save_project
    error "SYNTHESIZE failed"
}
puts "==> SYNTHESIZE OK"
flush stdout
save_project
puts "==> SYNTH SCRIPT COMPLETE"
flush stdout
