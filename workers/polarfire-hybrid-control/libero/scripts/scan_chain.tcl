#---------------------------------------------------------------------------
# scan_chain.tcl  —  READ-ONLY FPExpress JTAG chain scan
#
# Confirms which silicon is on the JTAG chain WITHOUT programming anything.
# Used 2026-06-02 to verify the newly-installed kit carries Production
# MPFS250T silicon (vs the Engineering-Sample MPFS250T_ES that blocked
# rung A on 2026-05-18).
#
# scan_chain_prg is read-only: it scans + analyzes the JTAG chain and
# reports devices found (Device N: <IDCODE> Mfr: <mfr> Part: <part>).
# NO set_programming_action {PROGRAM} / run_selected_actions here — nothing
# is written to the device.
#
# Invocation (on bee, MSYS Git Bash):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/fpexpress.exe \
#       SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/scan_chain.tcl" \
#       LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-02-scan/scan.log"
#---------------------------------------------------------------------------

set REPO_ROOT       "~/dev/projects/polarfire-hybrid-control"
set JOB_FILE        "$REPO_ROOT/libero/reports/2026-05-04-bringup/polarfire_hybrid_control.job"
set REPORT_DIR      "$REPO_ROOT/libero/reports/2026-06-02-scan"
set JOB_WRAPPER_DIR "$REPORT_DIR/fpexpress_job_project"

file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "READ-ONLY JTAG chain scan — new kit silicon-identity check"
puts "==========================================================="
flush stdout

# Create the job project (loads .ppd, auto-detects the FlashPro6).
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
puts "STEP 1 OK: job project created (programmer auto-detected)"
flush stdout

# Read-only scan. Try the new programmer serial first; fall back to no-name
# (single-programmer mode scans the only attached programmer).
set PRG_NAME "F31E000A"
if {[catch {scan_chain_prg -name $PRG_NAME} err]} {
    puts "WARN: scan_chain_prg -name $PRG_NAME failed: $err"
    puts "  retrying without -name (single-programmer mode)"
    flush stdout
    if {[catch {scan_chain_prg} err2]} {
        puts "FATAL: scan_chain_prg failed: $err2"
        flush stdout
        exit 92
    }
}
puts "STEP 2 OK: scan_chain_prg completed — see chain dump above"
flush stdout
exit 0
