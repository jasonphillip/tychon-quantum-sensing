# syn_noprune_rerun.tcl — Re-run synth + P&R + verify after appending a
# syn_noprune directive for nv_pid_top to the project-level Synplify user
# Tcl. Forces Synplify to keep the nv_pid_top_0 instance even though all of
# its outputs are presently bound to () in MPFS_ICICLE_KIT_BASE_DESIGN.v
# (Phase II will hook actuator_out_write_* to a real AXI register slave; for
# Phase I credibility we just need the PID core to survive synthesis so the
# placed netlist actually contains the registers and resource counts that
# the writeup cites).
#
# RUN ON BEELINK ONLY. Source from the Libero Tcl console while the
# MPFS_ICICLE_Vectorblox project is the working project, OR launch via:
#   libero SCRIPT:libero/scripts/syn_noprune_rerun.tcl
#
# Prereq: synthesis/MPFS_ICICLE_KIT_BASE_DESIGN_user.tcl on Beelink has been
# edited to append:
#   define_attribute {v:nv_pid_top_top} syn_noprune {1}

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

puts "==> Opening reference design project"
flush stdout
open_project -file $REF_PROJECT
flush stdout

# Run the pipeline. Each stage is wrapped in catch with explicit flush
# stdout before potentially-blocking calls (Libero batch-mode buffering
# rule from CLAUDE.md debug discipline #8).
foreach stage {SYNTHESIZE PLACEROUTE VERIFYTIMING VERIFYPOWER} {
    puts "==> RUN_TOOL $stage"
    flush stdout
    if {[catch {run_tool -name $stage} err]} {
        puts "==> STAGE_FAILED $stage : $err"
        flush stdout
        save_project
        error "STAGE_FAILED $stage"
    }
    puts "==> STAGE_OK $stage"
    flush stdout
}

save_project
puts "==> SYN_NOPRUNE RE-RUN COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
flush stdout
