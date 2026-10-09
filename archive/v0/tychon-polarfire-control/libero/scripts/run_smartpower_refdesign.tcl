# run_smartpower_refdesign.tcl — Run SmartPower on the Icicle+VBX reference design
#
# Opens the completed P&R project and runs power analysis with default toggle rates.

set PROJ_FILE "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/MPFS_ICICLE_Vectorblox.prjx"
set REPORT_DIR "~/dev/projects/tychon-polarfire-control/libero/reports"

file mkdir $REPORT_DIR

puts "INFO: Opening project $PROJ_FILE"
open_project -file $PROJ_FILE

# Create the SmartPower report script (passed via -script flag)
set sp_script [file join $REPORT_DIR _sp_report.tcl]
set fd [open $sp_script w]
puts $fd "smartpower_report_power -style Text -clock_breakdown TRUE -rail_breakdown TRUE -type_breakdown TRUE {[file join $REPORT_DIR smartpower_refdesign.rpt]}"
close $fd

puts "INFO: Running SmartPower (VERIFYPOWER) with default toggle rates..."
run_tool -name {VERIFYPOWER} -script $sp_script

puts "INFO: SmartPower complete."

save_project
close_project

puts "INFO: Report written to $REPORT_DIR/smartpower_refdesign.rpt"
