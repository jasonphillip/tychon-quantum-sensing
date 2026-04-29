# pnr_verify_only.tcl — run PLACEROUTE -> VERIFYTIMING -> VERIFYPOWER
# after a successful synth + audit gate. No `exec bash` (that hung from
# Tcl on the Beelink Git Bash environment); the audit gate must already
# have been run manually.
#
# Usage:
#   libero "SCRIPT:libero/scripts/pnr_verify_only.tcl"

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

puts "==> opening project"
flush stdout
open_project -file $REF_PROJECT
flush stdout

proc run_stage {name} {
    puts "==> RUN_TOOL $name"
    flush stdout
    if {[catch {run_tool -name $name} err]} {
        puts "==> STAGE_FAILED $name : $err"
        flush stdout
        save_project
        error "STAGE_FAILED $name"
    }
    puts "==> STAGE_OK $name"
    flush stdout
}

run_stage PLACEROUTE
run_stage VERIFYTIMING
run_stage VERIFYPOWER

save_project
puts "==> PNR_VERIFY_ONLY COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
flush stdout
close_project
exit 0
