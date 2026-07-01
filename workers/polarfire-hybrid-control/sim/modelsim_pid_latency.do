# sim/modelsim_pid_latency.do — fabric-internal PID latency cycle count on
# the real two-slot RTL (tb_pid_latency: M0 start-pulse -> actuator-we).
# No VCD needed; the deliverable is the transcript's cycle-count summary.
#
# Usage (Beelink Git Bash, repo root ~/dev/projects/polarfire-hybrid-control):
#   vsim -c -do sim/modelsim_pid_latency.do
#
# Precondition: hls/hls_output/rtl/*.v present at the netlist vintage
# (same rule as the workload .do — do not casually re-run `shls hw`).

set RTL_DIR  "hls/hls_output/rtl"
set HDL_DIR  "libero/hdl"

if {![file exists "$RTL_DIR/nv_pid_top_nv_pid_top.v"]} {
    puts "FATAL: $RTL_DIR/nv_pid_top_nv_pid_top.v missing — sim RTL not present"
    exit 1
}
vlog -sv "$RTL_DIR/nv_pid_top_nv_pid_top.v"
foreach v [glob -nocomplain "$RTL_DIR/*.v"] {
    if {[file tail $v] ne "nv_pid_top_nv_pid_top.v"} { vlog -sv $v }
}

vlog "$HDL_DIR/axi4_demux2.v"
vlog "$HDL_DIR/pid_csr_block.v"
vlog "$HDL_DIR/pid_csr_axi4_wrap.v"
vlog "$HDL_DIR/vbx_pulse_gen.v"
vlog "$HDL_DIR/watchdog_timer.v"
vlog "$HDL_DIR/pid_subsystem.v"

vlog -sv tests/two_slot_sim/tb_pid_latency.v

vsim -t ps -voptargs=+acc work.tb_pid_latency
run -all
quit -f
