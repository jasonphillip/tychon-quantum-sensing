# master_synth.tcl — re-run SYNTHESIZE in the "master" clone whose state will
# be propagated to N parallel P&R clones. Argument: a CLONE_DIR string in
# Windows-forward-slash form.
#
# Usage:
#   libero "SCRIPT:C:/path/to/master_synth.tcl"
#
# Edit the CLONE_DIR line below before invoking, or generate the file from
# this template via sed substitution of __MASTER_CLONE_DIR__.
set CLONE_DIR  "__MASTER_CLONE_DIR__"
set REF_PRJ    "$CLONE_DIR/MPFS_ICICLE_Vectorblox.prjx"

puts "==> MASTER_SYNTH_START [clock format [clock seconds]]"
flush stdout

open_project -file $REF_PRJ
flush stdout

if {[catch {run_tool -name {SYNTHESIZE}} err]} {
    puts "==> MASTER_SYNTH_FAILED: $err"
    flush stdout
    save_project
    error "MASTER_SYNTH_FAILED"
}

save_project
close_project
puts "==> MASTER_SYNTH_DONE [clock format [clock seconds]]"
flush stdout
exit 0
