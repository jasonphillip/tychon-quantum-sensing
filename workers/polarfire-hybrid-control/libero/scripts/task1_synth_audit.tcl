# task1_synth_audit.tcl — Phase I integration of pid_io_block.
#
# Steps (assumes the .v patch has already been applied by
# libero/scripts/patch_smartdesign_top.py):
#   1. Open the live Microchip reference-design project on Beelink.
#   2. Import libero/hdl/pid_io_block.v as a Verilog source (idempotent).
#   3. Rebuild the design hierarchy so Synplify picks up the new module.
#   4. Run SYNTHESIZE.
#   5. Invoke the audit gate (libero/scripts/audit_synthesis.sh) — fail
#      pipeline on CL168 / missing-instance.
#
# RUN ON BEELINK ONLY:
#   libero "SCRIPT:libero/scripts/task1_synth_audit.tcl"

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"

# Repo-relative path to the slave HDL — the SCRIPT: invocation runs from
# the repo root, so this resolves correctly.
set PID_IO_BLOCK_HDL "[file normalize libero/hdl/pid_io_block.v]"
set AUDIT_GATE       "libero/scripts/audit_synthesis.sh"

puts "==> opening project"
flush stdout
open_project -file $REF_PROJECT
flush stdout

puts "==> importing pid_io_block.v"
flush stdout
if {[catch {import_files -hdl_source $PID_IO_BLOCK_HDL} err]} {
    # Likely already imported; not fatal. Surface the message and continue.
    puts "    NOTE: import returned: $err"
}
flush stdout

puts "==> rebuilding design hierarchy"
flush stdout
build_design_hierarchy
flush stdout

save_project

puts "==> RUN_TOOL SYNTHESIZE"
flush stdout
if {[catch {run_tool -name SYNTHESIZE} err]} {
    puts "==> SYNTHESIZE FAILED: $err"
    flush stdout
    save_project
    error "SYNTHESIZE_FAILED"
}
puts "==> SYNTHESIZE OK"
flush stdout

puts "==> AUDIT_GATE $AUDIT_GATE"
flush stdout
if {[catch {exec bash $AUDIT_GATE} err]} {
    puts "==> AUDIT_GATE FAILED"
    puts $err
    flush stdout
    save_project
    error "AUDIT_GATE_FAILED"
}
puts $err
puts "==> AUDIT_GATE OK"
flush stdout

save_project
puts "==> TASK1_SYNTH_AUDIT COMPLETE"
flush stdout
