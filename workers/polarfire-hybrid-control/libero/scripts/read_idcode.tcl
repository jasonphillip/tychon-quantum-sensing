#---------------------------------------------------------------------------
# read_idcode.tcl  —  SmartDebug headless raw IDCODE capture for rung A
# forensic evidence (silicon-identity resolution 2026-05-18).
#
# FPExpress's read_id_code Tcl command does NOT exist in the 2025.2 FPExpress
# Tcl set, but it DOES exist in SmartDebug's Tcl. This script uses sdbg.exe
# to obtain the raw 32-bit hex IDCODE from the device on the JTAG chain.
#
# Invocation (on bee, MSYS Git Bash):
#   /c/Microchip/Libero_SoC_2025.2/Libero_SoC/Designer/bin/sdbg.exe \
#       SCRIPT:"~/dev/projects/polarfire-hybrid-control/libero/scripts/read_idcode.tcl" \
#       LOGFILE:"~/dev/projects/polarfire-hybrid-control/libero/reports/2026-05-18-program-failure/sdbg_idcode.log"
#---------------------------------------------------------------------------

puts "================================================================"
puts "SmartDebug headless IDCODE read — rung A forensic capture"
puts "================================================================"
flush stdout

# --- Step 1: identify the connected FlashPro6 programmer ---
# Programmer ID from prior FPExpress run: '065D9ACD' (Embedded FP6).
set PROGRAMMER_NAME "065D9ACD"

# --- Step 2: bind SmartDebug to the programmer ---
if {[catch {
    set_debug_programmer -name $PROGRAMMER_NAME
} err]} {
    puts "FATAL: set_debug_programmer failed: $err"
    flush stdout
    exit 81
}
puts "STEP 2 OK: bound to programmer $PROGRAMMER_NAME"
flush stdout

# --- Step 3: try a few candidate device names (chain says ES variant) ---
#   The April 2 Beelink session log identified the silicon as MPFS250T_ES.
#   FPExpress's pattern match said MPFS250(T_ES|TS_ES). Try both.
set CANDIDATES [list "MPFS250T_ES" "MPFS250TS_ES" "MPFS250T"]

foreach CAND $CANDIDATES {
    puts "----------------------------------------------------------------"
    puts "Trying device name: $CAND"
    flush stdout

    if {[catch {
        set_debug_device -name $CAND
    } err1]} {
        puts "  set_debug_device failed: $err1"
        flush stdout
        continue
    }
    puts "  set_debug_device $CAND OK"

    if {[catch {
        set idcode [read_id_code]
        puts "  read_id_code returned: $idcode"
        flush stdout
        puts "================================================================"
        puts "RAW IDCODE = $idcode  (device candidate: $CAND)"
        puts "================================================================"
        flush stdout
        exit 0
    } err2]} {
        puts "  read_id_code failed: $err2"
        flush stdout
        continue
    }
}

puts "FATAL: no device candidate succeeded"
flush stdout
exit 80
