# 05_add_pid_to_design.tcl — Add PID for synthesis resource estimation
#
# Strategy: Remove the AXI4 bus interface from the HDL+ core so individual
# pins are exposed, then tie inputs to GND and mark outputs unused.
# syn_preserve keeps all logic for accurate resource counts.
#
# Run from Libero: Ctrl+U -> select this file, no arguments

puts "INFO: Adding PID controller at top level..."

# ──────────────────────────────────────────────────────
# Step 0: Clean up previous attempts
# ──────────────────────────────────────────────────────

puts "INFO: Cleaning up..."
catch { sd_delete_instances -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -instance_names {nv_pid_top_0} }

# Remove leftover top-level ports from previous I/O attempt
foreach portname {
    PID_RESET PID_error PID_u_AI_in PID_ai_watchdog_timeout
    PID_actuator_out_write_en PID_actuator_out_write_data
} {
    catch { sd_delete_ports -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -port_names $portname }
}

# ──────────────────────────────────────────────────────
# Step 1: Remove bus interface from HDL+ core
# This exposes AXI signals as individual pins
# ──────────────────────────────────────────────────────

puts "INFO: Removing AXI4 bus interface from HDL+ core..."
catch { hdl_core_remove_bif -hdl_core_name {nv_pid_top_top} -bif_name {axi4target} }

# ──────────────────────────────────────────────────────
# Step 2: Instantiate PID in top-level SmartDesign
# ──────────────────────────────────────────────────────

puts "INFO: Instantiating nv_pid_top_top..."
open_smartdesign -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN}
sd_instantiate_hdl_core -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -hdl_core_name {nv_pid_top_top} -instance_name {nv_pid_top_0}

# ──────────────────────────────────────────────────────
# Step 3: Connect clock
# ──────────────────────────────────────────────────────

puts "INFO: Connecting clock..."
sd_connect_pins -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {"nv_pid_top_0:clk" "CLOCKS_AND_RESETS:FIC_0_CLK"}

# ──────────────────────────────────────────────────────
# Step 4: Tie all inputs to GND
# ──────────────────────────────────────────────────────

puts "INFO: Tying inputs to constants..."

# Reset and direct inputs
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:reset} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:error} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:u_AI_in} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:ai_watchdog_timeout} -value {GND}

# AXI4 target inputs (now individual pins, no bus interface)
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awaddr} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awvalid} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awid} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awlen} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awsize} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awburst} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awlock} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awcache} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awprot} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awqos} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awregion} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awuser} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wdata} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wstrb} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wlast} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wvalid} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wuser} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_bready} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_araddr} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arvalid} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arid} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arlen} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arsize} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arburst} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arlock} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arcache} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arprot} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arqos} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arregion} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_aruser} -value {GND}
sd_connect_pins_to_constant -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rready} -value {GND}

# ──────────────────────────────────────────────────────
# Step 5: Mark all outputs as unused
# ──────────────────────────────────────────────────────

puts "INFO: Marking outputs unused..."

sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_awready}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_wready}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_bid}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_bresp}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_bvalid}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_buser}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_arready}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rid}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rdata}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rresp}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rlast}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_rvalid}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:axi4target_ruser}

# Direct outputs
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:actuator_out_write_en}
sd_mark_pins_unused -sd_name {MPFS_ICICLE_KIT_BASE_DESIGN} -pin_names {nv_pid_top_0:actuator_out_write_data}

# ──────────────────────────────────────────────────────
# Step 6: Add syn_preserve to prevent optimization
# ──────────────────────────────────────────────────────

puts "INFO: Adding synthesis preserve attribute..."
catch {
    configure_tool -name {SYNTHESIZE} \
        -params {SYNPLIFY_OPTIONS:define_attribute {v:MPFS_ICICLE_KIT_BASE_DESIGN.nv_pid_top_0} syn_preserve {1}}
}

# ──────────────────────────────────────────────────────
# Step 7: Generate, build, save
# ──────────────────────────────────────────────────────

puts "INFO: Final build..."
generate_component -component_name {MPFS_ICICLE_KIT_BASE_DESIGN} -recursive 0
build_design_hierarchy
derive_constraints_sdc
save_project

puts ""
puts "========================================="
puts " PID controller added (no I/O pins used)"
puts " Bus interface removed for pin access"
puts " syn_preserve: ON"
puts "========================================="
puts ""
puts "Next: Run Synthesis from Design Flow tab"
