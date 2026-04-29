# rerun_timing_power_only.tcl — re-derive SmartTime + SmartPower analyses from
# the existing run-3 / seed-22 placed-and-routed database. RUN ON BEELINK ONLY.
#
# Does NOT touch SYNTHESIZE or PLACEROUTE. Re-running those would invalidate
# the closed +1.215 ns / 24.71% 4LUT result. VERIFYTIMING and VERIFYPOWER
# operate on the saved layout DB and only emit reports.

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"

puts "==> Opening reference design project"
flush stdout
open_project -file $REF_PROJECT

foreach stage {VERIFYTIMING VERIFYPOWER} {
    puts "==> RUN_TOOL $stage"
    flush stdout
    if {[catch {run_tool -name $stage} err]} {
        puts "==> STAGE_FAILED $stage : $err"
        flush stdout
        save_project
        close_project
        error "STAGE_FAILED $stage"
    }
    puts "==> STAGE_OK $stage"
    flush stdout
}

save_project
close_project
puts "==> TIMING+POWER ANALYSIS RERUN COMPLETE"
flush stdout
