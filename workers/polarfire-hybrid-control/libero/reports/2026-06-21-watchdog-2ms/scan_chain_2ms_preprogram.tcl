# Read-only FlashPro Express scan before the 2 ms watchdog programming step.
# This loads the newly exported job only to verify chain visibility; it does
# not select or run any programming action.

set JOB_FILE        "~/libero_seedsweep/seed7_vbx201_v250_2ms_20260621_160037/export/polarfire_hybrid_control_two_slot_2ms.job"
set REPORT_DIR      "~/dev/projects/polarfire-hybrid-control/libero/reports/2026-06-21-watchdog-2ms"
set JOB_WRAPPER_DIR "$REPORT_DIR/fpexpress_scan_2ms_preprogram"

file mkdir $REPORT_DIR
file mkdir $JOB_WRAPPER_DIR

puts "==========================================================="
puts "READ-ONLY JTAG chain scan before 2 ms watchdog programming"
puts "Job file        : $JOB_FILE"
puts "Wrapper project : $JOB_WRAPPER_DIR"
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
puts "STEP 1 OK: job project created (programmer auto-detected)"
flush stdout

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

puts "STEP 2 OK: scan_chain_prg completed; no programming action was run"
flush stdout
exit 0
