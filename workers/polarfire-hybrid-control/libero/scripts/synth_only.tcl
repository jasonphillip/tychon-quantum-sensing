# synth_only.tcl — open project, rebuild hierarchy, run SYNTHESIZE, exit.
#
# Audit gate is run separately from a regular shell after this script
# completes (Libero's `exec bash` from Tcl was observed to hang on the
# Beelink Git Bash environment). Just synthesise and exit cleanly here.
#
# Usage:
#   libero "SCRIPT:libero/scripts/synth_only.tcl"

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"

puts "==> opening project"
flush stdout
open_project -file $REF_PROJECT
flush stdout

puts "==> rebuilding design hierarchy"
flush stdout
build_design_hierarchy
flush stdout

save_project

puts "==> RUN_TOOL SYNTHESIZE"
flush stdout
if {[catch {run_tool -name SYNTHESIZE} err]} {
    puts "==> SYNTHESIZE FAILED: $err"
    flush stdout
    save_project
    error "SYNTHESIZE_FAILED"
}
puts "==> SYNTHESIZE OK"
flush stdout

save_project
puts "==> SYNTH_ONLY COMPLETE"
flush stdout
