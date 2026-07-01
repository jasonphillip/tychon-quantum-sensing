# FlashPro Express rollback PROGRAM action for the known-good idfix2 image.
# Use only if the 2 ms watchdog image needs to be reverted.

set JOB_FILE        "~/libero_seedsweep/seed7_vbx201_v250_2ms_20260621_160037/export/polarfire_hybrid_control_two_slot_idfix2.job"
set REPORT_DIR      "~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms"
set JOB_WRAPPER_DIR "$REPORT_DIR/fpexpress_program_idfix2_rollback"

file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "FPExpress programming - rollback to idfix2"
puts "Job file        : $JOB_FILE"
puts "Wrapper project : $JOB_WRAPPER_DIR"
puts "Action          : PROGRAM"
puts "==========================================================="
flush stdout

if {[catch {
    create_job_project \
        -job_project_location $JOB_WRAPPER_DIR \
        -job_file $JOB_FILE \
        -overwrite 1
} err]} {
    puts "FATAL: create_job_project failed: $err"
    flush stdout
    exit 91
}
puts "STEP 1 OK: job project created (FlashPro6 auto-detected, operator mode)"
flush stdout

if {[catch {set_programming_action -name {MPFS250T} -action {PROGRAM}} err_chain]} {
    puts "NOTE: set_programming_action -name {MPFS250T} failed ($err_chain)"
    puts "  retrying without -name (single-device mode)"
    flush stdout
    if {[catch {set_programming_action -action {PROGRAM}} err_single]} {
        puts "FATAL: set_programming_action PROGRAM failed: $err_single"
        flush stdout
        exit 93
    }
    puts "STEP 2 OK: PROGRAM action selected (single-device mode)"
} else {
    puts "STEP 2 OK: PROGRAM action selected (chain mode, device MPFS250T)"
}
flush stdout

if {[catch {run_selected_actions} err]} {
    puts "FATAL: run_selected_actions failed: $err"
    puts "ROLLBACK PROGRAM FAILED - preserve forensic state."
    flush stdout
    exit 99
}

puts "==========================================================="
puts "PROGRAM PASS - rollback idfix2"
puts "==========================================================="
flush stdout
exit 0
