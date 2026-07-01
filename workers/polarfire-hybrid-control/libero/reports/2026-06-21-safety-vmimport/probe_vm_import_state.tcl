set ROOT "~/libero_seedsweep/seed7_vbx201_v250_safety_vmimport_20260621_1128"
set PRJ "$ROOT/MPFS_ICICLE_Vectorblox.prjx"
set VM "$ROOT/synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm"
puts "==> VM_IMPORT_PROBE_START [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
puts "==> open_project $PRJ"
flush stdout
open_project -file $PRJ
proc show_states {label} {
    puts "==> STATES $label"
    foreach t {SYNTHESIZE PLACEROUTE VERIFYTIMING GENERATEPROGRAMMINGDATA EXPORTPROGRAMMINGJOB} {
        if {[catch {get_tool_state -name $t} s]} {
            puts "==> state $t WARN $s"
        } else {
            puts "==> state $t = $s"
        }
    }
    flush stdout
}
show_states before
puts "==> import_files -verilog_netlist $VM"
flush stdout
if {[catch {import_files -verilog_netlist $VM} err]} {
    puts "==> IMPORT_VM_FAILED : $err"
} else {
    puts "==> IMPORT_VM_OK"
}
flush stdout
puts "==> organize_tool_files PLACEROUTE source $VM"
flush stdout
if {[catch {organize_tool_files -tool {PLACEROUTE} -file $VM -module {MPFS_ICICLE_KIT_BASE_DESIGN::work} -input_type {source}} err]} {
    puts "==> ORGANIZE_PLACEROUTE_FAILED : $err"
} else {
    puts "==> ORGANIZE_PLACEROUTE_OK"
}
flush stdout
puts "==> organize_tool_files VERIFYTIMING source $VM"
flush stdout
if {[catch {organize_tool_files -tool {VERIFYTIMING} -file $VM -module {MPFS_ICICLE_KIT_BASE_DESIGN::work} -input_type {source}} err]} {
    puts "==> ORGANIZE_VERIFYTIMING_FAILED : $err"
} else {
    puts "==> ORGANIZE_VERIFYTIMING_OK"
}
flush stdout
puts "==> build_design_hierarchy"
flush stdout
if {[catch {build_design_hierarchy} err]} {
    puts "==> BUILD_HIERARCHY_FAILED : $err"
} else {
    puts "==> BUILD_HIERARCHY_OK"
}
flush stdout
show_states after
save_project
close_project
puts "==> VM_IMPORT_PROBE_DONE [clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}]"
flush stdout
exit 0
