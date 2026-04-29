# decision-2-c-load-only.tcl — Minimum-viable load test for Phase A1 diagnosis.
#
# Opens the reference project and immediately closes/exits. No imports, no
# saves, no design-hierarchy build. Used to isolate whether the deterministic
# project-load crash on Beelink is triggered by open_project alone (vs by
# downstream operations like fp_pdc import or design-hierarchy rebuild).
#
# RUN ON BEELINK ONLY. Source via `libero "SCRIPT:.../decision-2-c-load-only.tcl"`.

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"

puts "==> LOAD_ONLY: opening project at $REF_PROJECT"
if {[catch {open_project -file $REF_PROJECT} err]} {
    puts "==> LOAD_ONLY: open_project FAILED: $err"
    exit 1
}
puts "==> LOAD_ONLY: project opened cleanly"

if {[catch {close_project} err]} {
    puts "==> LOAD_ONLY: close_project warned: $err"
}
puts "==> LOAD_ONLY COMPLETE"
exit 0
