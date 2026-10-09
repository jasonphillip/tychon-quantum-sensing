#---------------------------------------------------------------------------
# program_two_slot_idfix.tcl — FPExpress headless PROGRAM of the two-slot
# bitstream WITH the M0 AXI completion fix (reset=~resetn + demux ID-replay,
# verified in ModelSim tb_m0.v, rebuilt 2026-06-18, timing met +0.825 ns).
#
# PROGRAM action only (non-destructive to eMMC/sNVM-INFLASH/HSS/U-Boot/Linux/SD).
# Operator mode. Mirrors program_two_slot.tcl; guardrail retargeted to *idfix*.
#
# Job sha256 7907a83f9fc6e99ca25ebc3c389c802d6d07e42b71403767ee644103783dff6e
# Rollbacks remain (program via program_two_slot.tcl / program_kit.tcl):
#   two-slot demo  a5550f9e (export/polarfire_hybrid_control_two_slot_demo.job)
#   V250-rebuild   4e3323e8 (export/polarfire_hybrid_control_vbx201_v250.job)
#   seed_7 rung-A  d5f3eb4e (.../2026-05-04-bringup/polarfire_hybrid_control.job)
#
# Invocation (bee):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#     SCRIPT:"~/libero_seedsweep/seed7_vbx201_v250/program_two_slot_idfix.tcl" \
#     LOGFILE:"~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/program_idfix.log"
#---------------------------------------------------------------------------

set EXPORT   "~/libero_seedsweep/seed7_vbx201_v250/export"
set JOB_FILE "$EXPORT/polarfire_hybrid_control_two_slot_idfix.job"
set WRAP_DIR "~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/fpx_job_idfix"

file mkdir $WRAP_DIR

puts "==> two-slot IDFIX PROGRAM; job = $JOB_FILE"
flush stdout

if {![file exists $JOB_FILE]} {
    puts "FATAL: job not found: $JOB_FILE"; flush stdout; exit 90
}
if {![string match "*two_slot_idfix*" $JOB_FILE]} {
    puts "FATAL: refusing to program non-idfix job ($JOB_FILE)"; flush stdout; exit 90
}
puts "JOB_PATH_VERIFIED two-slot-idfix"
flush stdout

if {[catch {create_job_project -job_project_location $WRAP_DIR -job_file $JOB_FILE -overwrite 1} err]} {
    puts "FATAL: create_job_project failed: $err"; flush stdout; exit 91
}
puts "STEP1_OK job project created (FlashPro6 auto-detect, operator mode)"
flush stdout

if {[catch {set_programming_action -name {MPFS250T} -action {PROGRAM}} e1]} {
    puts "NOTE chain-form failed ($e1); retry single-device"; flush stdout
    if {[catch {set_programming_action -action {PROGRAM}} e2]} {
        puts "FATAL: set_programming_action PROGRAM failed: $e2"; flush stdout; exit 93
    }
    puts "STEP2_OK PROGRAM action (single-device mode)"
} else {
    puts "STEP2_OK PROGRAM action (chain mode, MPFS250T)"
}
flush stdout

if {[catch {run_selected_actions} err]} {
    puts "FATAL: run_selected_actions failed: $err"
    puts "PROGRAM FAILED — preserve forensic state; rollback available (a5550f9e / 4e3323e8 / d5f3eb4e)."
    flush stdout
    exit 99
}
puts "==> PROGRAM_PASS (two-slot idfix)"
flush stdout
exit 0
