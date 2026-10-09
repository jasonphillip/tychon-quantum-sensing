set PROJ_FILE "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/MPFS_ICICLE_Vectorblox.prjx"

open_project -file $PROJ_FILE

# Try common SmartPower tool names
foreach tool_name {SMARTPOWER POWERANALYSIS POWER GENERATEPOWER VERIFPOWER VERIFYPOWER ESTIMATEPOWER ANALYZE_POWER SmartPower} {
    puts "Trying: $tool_name"
    if {[catch {run_tool -name $tool_name} err]} {
        puts "  -> $err"
    } else {
        puts "  -> SUCCESS"
    }
}

close_project
