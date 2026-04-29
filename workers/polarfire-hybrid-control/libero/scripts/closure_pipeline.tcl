# closure_pipeline.tcl — gated SYNTHESIZE -> audit -> PLACEROUTE ->
# VERIFYTIMING -> VERIFYPOWER pipeline.
#
# Invokes libero/scripts/audit_synthesis.sh between SYNTHESIZE and
# PLACEROUTE. If the audit gate fails (CL168 prune, missing required
# instance), the pipeline aborts before P&R so we don't burn cycles
# closing on a netlist that doesn't represent the design.
#
# RUN ON BEELINK ONLY:
#   libero "SCRIPT:libero/scripts/closure_pipeline.tcl"
#
# Each stage is wrapped in catch + flush stdout per CLAUDE.md debug rule #8.

set REF_PROJECT_DIR "C:/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox"
set REF_PROJECT     "$REF_PROJECT_DIR/MPFS_ICICLE_Vectorblox.prjx"
set REF_TOP         "MPFS_ICICLE_KIT_BASE_DESIGN"

# Resolve the audit gate path relative to this script's repo location.
# When Libero invokes via SCRIPT:libero/scripts/closure_pipeline.tcl, the
# CWD is the repo root, so a relative path works directly.
set AUDIT_GATE "libero/scripts/audit_synthesis.sh"

puts "==> Opening reference design project"
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

proc run_audit_gate {gate_path} {
    puts "==> AUDIT_GATE $gate_path"
    flush stdout
    if {[catch {exec bash $gate_path} err]} {
        puts "==> AUDIT_GATE_FAILED"
        puts $err
        flush stdout
        save_project
        error "AUDIT_GATE_FAILED — see CL168 / missing-instance output above"
    }
    puts $err
    puts "==> AUDIT_GATE_OK"
    flush stdout
}

# Stage 1: synthesise
run_stage SYNTHESIZE

# Gate: structural audit between SYNTHESIZE and PLACEROUTE
run_audit_gate $AUDIT_GATE

# Stages 2-4: place-and-route then verification
run_stage PLACEROUTE
run_stage VERIFYTIMING
run_stage VERIFYPOWER

save_project
puts "==> CLOSURE_PIPELINE COMPLETE"
puts "    Reports under: $REF_PROJECT_DIR/designer/$REF_TOP/"
flush stdout
