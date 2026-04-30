# decision-2-c-pdc-rerun.tcl — Add the XCVR_REF_CLK lock PDC to the active
# Place & Route constraint set on the April 2 Icicle reference project, and
# re-run synth + P&R + timing + power for the decision-2-option-c overlay.
#
# RUN ON BEELINK ONLY. Source from the Libero Tcl console while the
# MPFS_ICICLE_Vectorblox project is the working project.
#
# Prereq: the April 28 decision-2-c-overlay.tcl HLS overlay has already been
# run successfully (synthesis closed at 24.69% 4LUT). This script only adds
# the missing dedicated XCVR_REF_CLK lock and re-drives the P&R pipeline.
#
# IMPORTANT: This script assumes the supplementary PDC has been pre-staged
# into the project's constraint/io/ directory by the calling shell BEFORE
# Libero is invoked. Doing the file copy in Tcl previously caused Libero to
# block on a modal dialog (project-vs-external-path conflict) that never
# resolves in batch mode. The shell-side stage avoids that entirely.

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set IN_PROJ_PDC     "$REF_PROJECT_DIR/constraint/fp/decision-2-option-c.pdc"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

if {![file exists $IN_PROJ_PDC]} {
    error "PDC not pre-staged at $IN_PROJ_PDC — calling shell must copy first"
}

puts "==> Opening reference design project"
open_project -file $REF_PROJECT

# Import the PDC from its in-project location as an fp_pdc (floorplan PDC).
# `set_location -inst_name` constraints live in fp_pdc files, alongside the
# existing constraint/fp/NW_PLL.pdc which holds the CCC PLL placements.
# Importing this as -io_pdc previously caused Libero to crash silently
# during project-load constraint validation.
# Libero 2025.2 auto-organizes fp_pdc files into both Synthesis and
# PlaceRoute constraint sets — no organize_tool_files needed.
puts "==> Importing supplementary FP PDC: $IN_PROJ_PDC"
if {[catch {import_files -fp_pdc [list $IN_PROJ_PDC]} err]} {
    puts "NOTE: import_files returned: $err"
    puts "      Continuing — assuming file is already a project member."
}

build_design_hierarchy
save_project

# Run the pipeline. Each stage is wrapped in its own catch so a failure
# surfaces with a clear marker instead of just stopping the script silently.
foreach stage {SYNTHESIZE PLACEROUTE VERIFYTIMING VERIFYPOWER} {
    puts "==> RUN_TOOL $stage"
    if {[catch {run_tool -name $stage} err]} {
        puts "==> STAGE_FAILED $stage : $err"
        save_project
        error "STAGE_FAILED $stage"
    }
    puts "==> STAGE_OK $stage"
}

save_project
puts "==> PDC RE-RUN COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
puts "    Iteration summary: $REF_PROJECT_DIR/designer/$REF_TOP/${REF_TOP}_iteration_summary.rpt"
