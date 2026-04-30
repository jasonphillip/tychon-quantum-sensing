# decision-2-c-pdc-smoke.tcl — Smoke test: open the project, import the PDC
# as fp_pdc, save and close. Verifies the import path before committing to
# a 15-25 minute synth + P&R run.

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set IN_PROJ_PDC     "$REF_PROJECT_DIR/constraint/fp/decision-2-option-c.pdc"

if {![file exists $IN_PROJ_PDC]} {
    error "PDC not pre-staged at $IN_PROJ_PDC"
}

puts "==> SMOKE: opening project"
open_project -file $REF_PROJECT
puts "==> SMOKE: project opened"

puts "==> SMOKE: importing fp_pdc"
if {[catch {import_files -fp_pdc [list $IN_PROJ_PDC]} err]} {
    puts "==> SMOKE: import returned: $err"
} else {
    puts "==> SMOKE: import_files OK"
}

puts "==> SMOKE: build_design_hierarchy"
build_design_hierarchy

puts "==> SMOKE: save_project"
save_project

puts "==> SMOKE: close_project"
close_project

puts "==> SMOKE COMPLETE"
