#---------------------------------------------------------------------------
# program_two_slot.tcl — FPExpress headless PROGRAM of the clean two-slot bitstream
#
# Programs the demo-watchdog two-slot .job onto the Production MPFS250T via the
# on-board FlashPro6. PROGRAM action only (non-destructive to eMMC/sNVM-INFLASH/
# HSS/U-Boot/Linux). Operator mode. Mirrors libero/scripts/program_kit.tcl.
#
# GUARDRAIL: aborts unless the job path is the two-slot demo job, so a stale
# rollback .job can never be programmed by this script. Rollbacks remain:
#   V250-rebuild  4e3323e8 (export/polarfire_hybrid_control_vbx201_v250.job)
#   seed_7 rung-A d5f3eb4e (.../2026-05-04-bringup/polarfire_hybrid_control.job)
#
# Invocation (bee):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#     SCRIPT:"~/libero_seedsweep/seed7_vbx201_v250/program_two_slot.tcl" \
#     LOGFILE:"~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/program.log"
#---------------------------------------------------------------------------

set EXPORT   "~/libero_seedsweep/seed7_vbx201_v250/export"
set JOB_FILE "$EXPORT/polarfire_hybrid_control_two_slot_demo.job"
set WRAP_DIR "~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/fpx_job_project"

file mkdir $WRAP_DIR

puts "==> two-slot PROGRAM; job = $JOB_FILE"
flush stdout

# Guardrail: the job must exist AND be the two-slot demo job (not a rollback).
if {![file exists $JOB_FILE]} {
    puts "FATAL: job not found: $JOB_FILE"; flush stdout; exit 90
}
if {![string match "*two_slot_demo*" $JOB_FILE]} {
    puts "FATAL: refusing to program non-two-slot job ($JOB_FILE)"; flush stdout; exit 90
}
puts "JOB_PATH_VERIFIED two-slot-demo"
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
    puts "PROGRAM FAILED — preserve forensic state; rollback available (4e3323e8 / d5f3eb4e)."
    flush stdout
    exit 99
}
puts "==> PROGRAM_PASS (two-slot demo)"
flush stdout
exit 0
