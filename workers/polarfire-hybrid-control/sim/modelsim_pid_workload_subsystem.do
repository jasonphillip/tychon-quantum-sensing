# sim/modelsim_pid_workload_subsystem.do — workload VCD generation at the
# pid_subsystem level with a NETLIST-MIRRORING scope hierarchy.
#
# Replaces the standalone-nv_pid_top_top flow in modelsim_pid_workload.do,
# whose VCD scope could not match the placed netlist path
# (MPFS_ICICLE_KIT_BASE_DESIGN/FIC_0_PERIPHERALS_1/u_pid_subsystem/...) and
# annotated 0.00% of pins. tb_power (tests/two_slot_sim/tb_power_wrap.v)
# instantiates shims named MPFS_ICICLE_KIT_BASE_DESIGN / FIC_0_PERIPHERALS_1
# so the VCD path lines up 1:1 with the netlist below the testbench root.
#
# Stimulus: real AXI transactions (gains via M0, the 1000-row chirped ODMR
# trace via M1 + M0 start pulses) at the 125 MHz PID fabric clock. See the
# TB header for details.
#
# Usage (Beelink Git Bash, repo root ~/dev/projects/polarfire-hybrid-control):
#   vsim -c -do sim/modelsim_pid_workload_subsystem.do
#
# Preconditions:
#   - hls/hls_output/rtl/*.v present and AT THE NETLIST VINTAGE (do NOT re-run
#     `shls hw` casually: rta_config.hpp changed after the r12_s31 build; the
#     sim RTL must match what was synthesized).
#   - sim/stimulus/odmr_representative_trace.hex committed (trace_to_hex.py).

set RTL_DIR  "hls/hls_output/rtl"
set HDL_DIR  "libero/hdl"
set TB       "tests/two_slot_sim/tb_power_wrap.v"
set VCD_OUT  "sim/output/pid_workload_subsystem.vcd"

file mkdir sim/output

# --- compile SmartHLS RTL (SystemVerilog constructs -> -sv) ---
if {![file exists "$RTL_DIR/nv_pid_top_nv_pid_top.v"]} {
    puts "FATAL: $RTL_DIR/nv_pid_top_nv_pid_top.v missing — sim RTL not present (see preconditions)"
    exit 1
}
vlog -sv "$RTL_DIR/nv_pid_top_nv_pid_top.v"
foreach v [glob -nocomplain "$RTL_DIR/*.v"] {
    if {[file tail $v] ne "nv_pid_top_nv_pid_top.v"} { vlog -sv $v }
}

# --- compile the two-slot HDL (explicit list; pid_io_block.v is the old
#     seed_7 block, not part of pid_subsystem — deliberately excluded) ---
vlog "$HDL_DIR/axi4_demux2.v"
vlog "$HDL_DIR/pid_csr_block.v"
vlog "$HDL_DIR/pid_csr_axi4_wrap.v"
vlog "$HDL_DIR/vbx_pulse_gen.v"
vlog "$HDL_DIR/watchdog_timer.v"
vlog "$HDL_DIR/pid_subsystem.v"

# --- testbench ---
vlog -sv $TB

# --- elaborate + VCD (scope rooted at the netlist-named shim) ---
vsim -t ps -voptargs=+acc work.tb_power
vcd file $VCD_OUT
vcd add -r /tb_power/MPFS_ICICLE_KIT_BASE_DESIGN/*

run -all
vcd flush
puts "INFO: VCD written to $VCD_OUT"
quit -f
