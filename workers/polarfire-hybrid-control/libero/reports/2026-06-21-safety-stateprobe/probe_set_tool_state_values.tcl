set PRJ "~/libero_seedsweep/seed7_vbx201_v250_safety_stateprobe_20260621_1117/MPFS_ICICLE_Vectorblox.prjx"
puts "==> STATE_VALUE_PROBE_START [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
foreach t {SYNTHESIZE PLACEROUTE VERIFYTIMING GENERATEPROGRAMMINGDATA EXPORTPROGRAMMINGJOB} {
    if {[catch {get_tool_state -name $t} s]} {
        puts "==> INITIAL $t WARN $s"
    } else {
        puts "==> INITIAL $t = $s"
    }
    flush stdout
}
set candidates [list 1 0 2 3 4 5 6 Success Passed StateSuccess StateFailure StateNoResult "Tool passed" "Tool succeeded" "Tool inputs are up to date" "Tool completed successfully" "Tool inputs are out of date"]
foreach st $candidates {
    puts "==> TRY SYNTHESIZE state=<$st>"
    flush stdout
    if {[catch {set_tool_state -name {SYNTHESIZE} -state $st} err]} {
        puts "==> REJECT SYNTHESIZE state=<$st> err=<$err>"
    } else {
        puts "==> ACCEPT SYNTHESIZE state=<$st>"
        if {[catch {get_tool_state -name {SYNTHESIZE}} s2]} {
            puts "==> AFTER SYNTHESIZE WARN $s2"
        } else {
            puts "==> AFTER SYNTHESIZE = $s2"
        }
        save_project
    }
    flush stdout
}
close_project
puts "==> STATE_VALUE_PROBE_DONE [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
flush stdout
exit 0
