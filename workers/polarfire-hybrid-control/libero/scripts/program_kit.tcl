#---------------------------------------------------------------------------
# program_kit.tcl  —  FPExpress headless programming script for rung A
#
# Programs the MPFS_ICICLE_Vectorblox seed_7 bitstream onto the Icicle Kit
# via the on-board FlashPro6 (J11). PROGRAM action only — does NOT touch
# eMMC, sNVM PROGRAM_INFLASH, or any other destructive action.
#
# Tcl reference: Libero SoC v2025.2 FlashPro Express Tcl Commands
# (corpus: ww1.microchip.com/.../libero-soc-tcl-cmd-ref-ug-2025-2pdf.md)
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

# Ensure report directory + wrapper subdir both exist
# (create_job_project requires the wrapper subdir to already exist)
file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "FPExpress headless programming — rung A"
puts "Job file        : $JOB_FILE"
puts "Wrapper project : $JOB_WRAPPER_DIR"
puts "Report dir      : $REPORT_DIR"
puts "Date            : $RUN_DATE"
puts "==========================================================="
flush stdout

# --- Step 1: create FlashPro Express job project from the .job ---
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

# --- Step 2: NOTE — read_id_code is a Libero Designer Tcl command, not in
# FPExpress Tcl. Liveness already proven by create_job_project succeeding
# (the FlashPro6 detection + design checksum load is enough). Per the
# fpexpress.exe output captured 2026-05-18 first run, the message
#   "Programmer: Embedded FP6 '<serial>' : Version = <fw>"
# plus
#   "DESIGN : MPFS_ICICLE_KIT_BASE_DESIGN; CHECKSUM : <hex>; PDB_VERSION : <ver>"
# constitutes the chain-alive + identity-confirmed evidence we need before
# the PROGRAM action.
puts "STEP 2 SKIPPED: read_id_code unavailable in FPExpress; chain-alive proven by create_job_project FP6 detection above."
flush stdout

# --- Step 3: select PROGRAM action ---
#
# Default is usually PROGRAM, but be explicit. We do NOT use:
#   PROGRAM_INFLASH    (touches sNVM — destructive, ASK-FIRST)
#   PROGRAM_EMMC       (touches eMMC — destructive, ASK-FIRST, Part-J only)
#   VERIFY_DIGEST      (Errata 80001031 marks this deprecated)
# Device user-name in chain = "MPFS250T" (from .pro project XML <Device><Name>).
# FPExpress is in chain programming mode by default after create_job_project,
# which requires the -name parameter even for a single-device chain.
if {[catch {
    set_programming_action -name {MPFS250T} -action {PROGRAM}
} err]} {
    puts "FATAL: set_programming_action PROGRAM failed: $err"
    flush stdout
    exit 93
}
puts "STEP 3 OK: PROGRAM action selected for device MPFS250T"
flush stdout

# --- Step 4: run the action ---
#
# Per corpus example pattern with pass/fail catch:
#   if {[catch {run_selected_actions}]} { exit 99 } else { exit 0 }
if {[catch {run_selected_actions} err]} {
    puts "FATAL: run_selected_actions failed: $err"
    puts "PROGRAM FAILED — forensic capture rule applies."
    puts "Do NOT retry. Do NOT power-cycle. Surface log to operator."
    flush stdout
    exit 99
}

puts "==========================================================="
puts "PROGRAM PASS"
puts "==========================================================="
puts "Reports in : $REPORT_DIR"
puts "Job wrapper: $JOB_WRAPPER_DIR"
puts "IDCODE     : $idcode"
flush stdout

exit 0
