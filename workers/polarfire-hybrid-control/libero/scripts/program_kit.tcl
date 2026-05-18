#---------------------------------------------------------------------------
# program_kit.tcl  —  FPExpress headless programming script for rung A
#
# Programs the MPFS_ICICLE_Vectorblox seed_7 bitstream onto the Icicle Kit
# via the on-board FlashPro6 (J11). PROGRAM action only — does NOT touch
# eMMC, sNVM PROGRAM_INFLASH, or any other destructive action.
#
# Silicon-identity correction 2026-05-18: kit silicon is MPFS250T_ES (engineering
# sample) populated on a Production-SKU Icicle Kit board. The April-2 Beelink
# session log + today's FPExpress class-level match (Found: MPFS250(T_ES|TS_ES))
# are the corroborating evidence. The .ppd targets MPFS250T Production; the
# bitstream is electrically compatible (same fabric die) but FPExpress's
# chain check rejects the silicon-class mismatch. Override path: switch to
# developer_mode + rename device to MPFS250T_ES.
#
# Tcl reference: Libero SoC v2025.2 FlashPro Express Tcl Commands (corpus).
#
# Invocation (on bee, MSYS Git Bash):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#       SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/program_kit.tcl" \
#       LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/<YYYY-MM-DD>-program/program.log"
#---------------------------------------------------------------------------

# Absolute paths (Windows-style, FPExpress is a native Windows tool)
set REPO_ROOT       "~/dev/projects/polarfire-hybrid-control"
set JOB_FILE        "$REPO_ROOT/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job"
set RUN_DATE        [clock format [clock seconds] -format "%Y-%m-%d"]
set REPORT_DIR      "$REPO_ROOT/libero/reports/$RUN_DATE-program"
set JOB_WRAPPER_DIR "$REPORT_DIR/fpexpress_job_project"

# Pre-create dirs
file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "FPExpress headless programming — rung A (ES-override attempt)"
puts "Job file        : $JOB_FILE"
puts "Wrapper project : $JOB_WRAPPER_DIR"
puts "Report dir      : $REPORT_DIR"
puts "Date            : $RUN_DATE"
puts "==========================================================="
flush stdout

# --- STEP 0: switch to FPExpress Developer mode BEFORE create_job_project ---
# Operator mode is default; Developer mode "allows to update jobs before
# running programming" — required for set_device_name to take effect.
# Corpus: libero-soc-tcl-cmd-ref-ug-2025-2pd.md §11.x set_fpexpress_mode.
if {[catch {set_fpexpress_mode -mode {developer}} err]} {
    puts "WARNING: set_fpexpress_mode developer failed (continuing): $err"
    flush stdout
} else {
    puts "STEP 0 OK: switched to FPExpress developer mode"
    flush stdout
}

# --- STEP 1: create job project from .job ---
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
puts "STEP 1 OK: job project created"
flush stdout

# --- STEP 2: try to rename the chain device to MPFS250T_ES (ES silicon) ---
# If set_device_name accepts this, the subsequent chain check should accept
# the ES silicon-class IDCODE match.
if {[catch {set_device_name -name {MPFS250T} -new_name {MPFS250T_ES}} err_rename]} {
    puts "WARNING: set_device_name MPFS250T->MPFS250T_ES failed: $err_rename"
    puts "  (will try set_programming_action with both ES and Production names)"
    set RENAMED 0
    flush stdout
} else {
    puts "STEP 2 OK: chain device renamed MPFS250T -> MPFS250T_ES"
    set RENAMED 1
    flush stdout
}

# --- STEP 3: select PROGRAM action (try ES name first, fall back) ---
set ACTION_NAME ""
if {$RENAMED == 1} {
    if {[catch {set_programming_action -name {MPFS250T_ES} -action {PROGRAM}} err]} {
        puts "WARNING: set_programming_action MPFS250T_ES failed: $err"
        flush stdout
    } else {
        set ACTION_NAME "MPFS250T_ES"
    }
}
if {$ACTION_NAME eq ""} {
    if {[catch {set_programming_action -name {MPFS250T} -action {PROGRAM}} err]} {
        puts "FATAL: set_programming_action MPFS250T failed: $err"
        flush stdout
        exit 93
    }
    set ACTION_NAME "MPFS250T"
}
puts "STEP 3 OK: PROGRAM action selected for device $ACTION_NAME"
flush stdout

# --- STEP 4: run the action ---
if {[catch {run_selected_actions} err]} {
    puts "FATAL: run_selected_actions failed: $err"
    puts "PROGRAM FAILED after ES-override attempt — STOP per rollback rule."
    puts "Do NOT retry. Do NOT power-cycle. Surface log to operator."
    flush stdout
    exit 99
}

puts "==========================================================="
puts "PROGRAM PASS"
puts "==========================================================="
puts "Reports in : $REPORT_DIR"
puts "Job wrapper: $JOB_WRAPPER_DIR"
puts "Device     : $ACTION_NAME"
flush stdout
exit 0
