#---------------------------------------------------------------------------
# program_kit.tcl  —  FPExpress headless programming script for rung A
#
# Programs the MPFS_ICICLE_Vectorblox seed_7 bitstream onto the Production
# MPFS250T Icicle Kit via the on-board FlashPro6 (J11). PROGRAM action only
# — does NOT touch eMMC, sNVM PROGRAM_INFLASH, or any other destructive action.
#
# Production silicon (2026-06-02): the new kit carries Production MPFS250T
# (IDCODE 1F81A1CF, no _ES). The seed_7 .ppd targets Production MPFS250T;
# read-only scan_chain.tcl confirmed Scan-and-Check-Chain PASSED. No device
# rename / developer-mode override (the ES-board workaround) is needed.
# Operator mode (default) + PROGRAM action on MPFS250T.
#
# Tcl reference: Libero SoC v2025.2 FlashPro Express Tcl Commands (corpus,
# DS50003101V §11.6 create_job_project / §11.24 set_programming_action /
# §11.16 run_selected_actions).
#
# Invocation (on bee, MSYS Git Bash; pre-create the LOGFILE dir first):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#       SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/program_kit.tcl" \
#       LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-15-program/program.log"
#---------------------------------------------------------------------------

set REPO_ROOT       "~/dev/projects/polarfire-hybrid-control"
set JOB_FILE        "$REPO_ROOT/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job"
set RUN_DATE        [clock format [clock seconds] -format "%Y-%m-%d"]
set REPORT_DIR      "$REPO_ROOT/libero/reports/$RUN_DATE-program"
set JOB_WRAPPER_DIR "$REPORT_DIR/fpexpress_job_project"

# Pre-create dirs
file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "FPExpress headless programming — rung A (Production MPFS250T)"
puts "Job file        : $JOB_FILE"
puts "Wrapper project : $JOB_WRAPPER_DIR"
puts "Report dir      : $REPORT_DIR"
puts "Date            : $RUN_DATE"
puts "==========================================================="
flush stdout

# --- STEP 1: create job project from .job (operator mode is the default) ---
# create_job_project auto-loads the device list + default action from the .job
# and auto-detects the attached FlashPro6.
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

# --- STEP 2: select the PROGRAM action (non-destructive to eMMC/sNVM) ---
# Try chain form first (-name MPFS250T, evidence-grounded); fall back to the
# single-device form (no -name) if FPExpress is in single mode. NO rename.
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

# --- STEP 3: run the PROGRAM action ---
if {[catch {run_selected_actions} err]} {
    puts "FATAL: run_selected_actions failed: $err"
    puts "PROGRAM FAILED — STOP per rung-A rollback rule."
    puts "Do NOT retry. Do NOT power-cycle. Preserve forensic state."
    puts "Surface full log ($REPORT_DIR) to operator."
    flush stdout
    exit 99
}

puts "==========================================================="
puts "PROGRAM PASS"
puts "==========================================================="
puts "Reports in : $REPORT_DIR"
puts "Job wrapper: $JOB_WRAPPER_DIR"
puts "Device     : MPFS250T (Production, IDCODE 1F81A1CF)"
flush stdout
exit 0
