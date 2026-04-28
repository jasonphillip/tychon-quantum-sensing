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

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set REPO_DIR        "~/dev/projects/polarfire-hybrid-control"
set NEW_PDC         "$REPO_DIR/libero/constraints/decision-2-option-c.pdc"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

puts "==> Opening reference design project"
open_project -file $REF_PROJECT

# Import the new PDC as an I/O PDC. If it was imported by a prior run,
# Libero will return an "already exists" warning we tolerate.
puts "==> Importing supplementary I/O PDC: $NEW_PDC"
if {[catch {import_files -io_pdc [list $NEW_PDC]} err]} {
    puts "NOTE: import_files returned: $err"
    puts "      Assuming PDC is already a project member; continuing."
}

# Organize the new PDC for the Place & Route tool against the top-level
# module. Without this step Libero will keep the file as project-only and
# not feed it to placer.
puts "==> Organizing PDC for PLACEROUTE on $REF_TOP"
set PROJ_PDC_PATH "<project>/constraint/io/decision-2-option-c.pdc"
# Copy the file into the project's constraint/io area so Libero treats it
# alongside the other ICICLE_*.pdc members.
set DEST_PDC "$REF_PROJECT_DIR/constraint/io/decision-2-option-c.pdc"
if {[file exists $DEST_PDC]} {
    file delete -force $DEST_PDC
}
file copy -force $NEW_PDC $DEST_PDC
puts "    Copied to: $DEST_PDC"

# Re-import from the in-project location so Libero picks up the canonical
# project-relative path.
if {[catch {import_files -io_pdc [list $DEST_PDC]} err]} {
    puts "NOTE: re-import returned: $err"
}

# Organize for synthesis (informational only, dedicated XCVR placement is
# P&R-only) and place-and-route.
if {[catch {organize_tool_files -tool {PLACEROUTE} \
        -file $DEST_PDC \
        -input_type {constraint} \
        -module "${REF_TOP}::work"} err]} {
    puts "NOTE: organize_tool_files returned: $err"
}

build_design_hierarchy
save_project

puts "==> SYNTHESIZE (will re-run because constraint set changed)"
run_tool -name {SYNTHESIZE}

puts "==> PLACEROUTE (multi-seed; the April 28 -starting_seed_index 2 was used,"
puts "    Libero defaults will pick a fresh seed sequence)"
run_tool -name {PLACEROUTE}

puts "==> VERITIMING (post-P&R STA)"
run_tool -name {VERITIMING}

puts "==> POWERANALYSIS (SmartPower post-P&R)"
run_tool -name {POWERANALYSIS}

save_project

puts "==> PDC RE-RUN COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
puts "    Iteration summary: $REF_PROJECT_DIR/designer/$REF_TOP/${REF_TOP}_iteration_summary.rpt"
