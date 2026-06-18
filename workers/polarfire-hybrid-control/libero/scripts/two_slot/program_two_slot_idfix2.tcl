#---------------------------------------------------------------------------
# program_two_slot_idfix2.tcl — FPExpress headless PROGRAM of the two-slot
# bitstream WITH the M0 AXI fix + the actuator-output latch (2026-06-18).
# Full PID datapath verified in sim (actuator=Kp*error, clamp saturates).
#
# PROGRAM action only (non-destructive to eMMC/sNVM-INFLASH/HSS/U-Boot/Linux/SD).
# Operator mode. Guardrail retargeted to *idfix2*.
#
# Rollbacks remain: idfix 7907a83f / demo a5550f9e / V250 4e3323e8 / seed_7 d5f3eb4e
#
# Invocation (bee):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#     SCRIPT:"~/libero_seedsweep/seed7_vbx201_v250/program_two_slot_idfix2.tcl" \
#     LOGFILE:"~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/program_idfix2.log"
#---------------------------------------------------------------------------

set EXPORT   "~/libero_seedsweep/seed7_vbx201_v250/export"
set JOB_FILE "$EXPORT/polarfire_hybrid_control_two_slot_idfix2.job"
set WRAP_DIR "~/libero_seedsweep/seed7_vbx201_v250/two_slot_reports/fpx_job_idfix2"

file mkdir $WRAP_DIR

puts "==> two-slot IDFIX2 PROGRAM; job = $JOB_FILE"
flush stdout

if {![file exists $JOB_FILE]} {
    puts "FATAL: job not found: $JOB_FILE"; flush stdout; exit 90
}
if {![string match "*two_slot_idfix2*" $JOB_FILE]} {
    puts "FATAL: refusing to program non-idfix2 job ($JOB_FILE)"; flush stdout; exit 90
}
puts "JOB_PATH_VERIFIED two-slot-idfix2"
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
    puts "PROGRAM FAILED — preserve forensic state; rollback available (idfix/demo/V250/seed_7)."
    flush stdout
    exit 99
}
puts "==> PROGRAM_PASS (two-slot idfix2)"
flush stdout
exit 0
