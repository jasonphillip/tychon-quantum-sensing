# 03_smartdesign.tcl — Wire AXI interconnect in SmartDesign
#
# Architecture:
#
#   ┌─────────────────────────────────────────────────────────┐
#   │                    MPFS250T Fabric                       │
#   │                                                         │
#   │  MSS (RISC-V)                                           │
#   │  ├─ FIC0 (64-bit AXI4) ──→ CoreVectorBlox V250         │
#   │  │                          (AI inference DMA)          │
#   │  │                                                      │
#   │  ├─ FIC1 (64-bit AXI4) ──→ SmartHLS PID Controller     │
#   │  │                          (nv_pid_top, AXI target)    │
#   │  │                                                      │
#   │  └─ FIC2 (32-bit APB3) ──→ [Reserved: control regs]    │
#   │                                                         │
#   │  PF_CCC_0 ──→ 200 MHz fabric clock to all fabric IPs   │
#   │  PF_INIT_MONITOR_0 ──→ Reset sequencing                 │
#   └─────────────────────────────────────────────────────────┘
#
# Physical separation of VectorBlox and PID on different FIC ports
# prevents AXI bus contention between AI inference DMA and real-time
# PID updates. This is critical for the <150 µs PID latency guarantee.
#
# Prerequisites:
#   - 02_import_ip.tcl has been sourced (all IPs imported)
#   - MSS configuration verified (FIC0/FIC1/FIC2 enabled)
#
# Run after 02_import_ip.tcl:
#   cd <repo>/libero/scripts
#   source 03_smartdesign.tcl

# ──────────────────────────────────────────────────────
# Path setup
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set PROJ_DIR    [file join $REPO_ROOT libero work]
set PROJ_FILE   [file join $PROJ_DIR polarfire_hybrid_control.prjx]

# ──────────────────────────────────────────────────────
# Component names — must match what was imported in 02
# ──────────────────────────────────────────────────────
set TOP_SD_NAME      "hybrid_control_top"
set MSS_COMPONENT    "MPFS_ICICLE_MSS"
set MSS_INSTANCE     "MSS_0"
set VBX_COMPONENT    "CoreVectorBlox_0"
set VBX_INSTANCE     "VBX_0"
# VERIFY_AFTER_SHLS_HW: Confirm the SmartHLS component name.
# This is the name from import_component or the module name
# discovered by build_design_hierarchy in script 02.
set PID_COMPONENT    "nv_pid_top"
set PID_INSTANCE     "PID_0"
set CCC_COMPONENT    "PF_CCC_0"
set CCC_INSTANCE     "CCC_0"
set INITMON_COMPONENT "PF_INIT_MONITOR_0"
set INITMON_INSTANCE  "INITMON_0"

# ──────────────────────────────────────────────────────
# Open project
# ──────────────────────────────────────────────────────
puts "INFO: Opening project..."
open_project -file $PROJ_FILE

# ══════════════════════════════════════════════════════
# Section 1: MSS Configuration
# ══════════════════════════════════════════════════════
#
# The PolarFire SoC MSS is configured through the MSS
# Configurator, which generates an XML config and a Tcl
# component. We derive our MSS config from
# the Icicle Kit reference design with these modifications:
#
#   - FIC0: Enabled, 64-bit AXI4, MSS-to-Fabric (for VBX)
#   - FIC1: Enabled, 64-bit AXI4, MSS-to-Fabric (for PID)
#   - FIC2: Enabled, 32-bit APB3 (reserved for control regs)
#   - FIC3: Disabled (not used)
#   - DDR:  Enabled (VBX needs DDR for model + inference data)
#   - MMUART0: Enabled (debug console)
#
# VERIFY_AFTER_SHLS_HW: The MSS configurator should
# be used to generate the initial MSS component. Steps:
#   1. In Libero, open IP Catalog → search "PF_SOC"
#   2. Launch MSS Configurator
#   3. Start from Icicle Kit template
#   4. Verify FIC0/FIC1/FIC2 are enabled with correct widths
#   5. Save → generates MSS component and XML config
#   6. Update MSS_COMPONENT variable above with the generated name
#
# The Tcl below creates the MSS with the Icicle Kit defaults.
# If the MSS Configurator changes parameter names in Libero
# 2025.2, update the create_and_configure_core call.
# ──────────────────────────────────────────────────────

puts "INFO: Configuring MSS..."

# VERIFY_AFTER_SHLS_HW: The MSS VLNV and parameter names may
# differ in Libero 2025.2. Check the MSS Configurator output.
# The parameter set below is representative — the actual MSS
# has ~200 parameters. Only the FIC-relevant ones are shown.
#
# RECOMMENDED: Use the MSS Configurator GUI for the
# initial setup, then export to Tcl. Replace this section with
# the exported Tcl to get all parameters correct.

create_and_configure_core \
    -core_vlnv {Microchip:PolarFireSoC:PF_SOC_MSS:*} \
    -component_name $MSS_COMPONENT \
    -params { \
        "FIC_0_AMBA_AXI4_SLAVE:Enabled" \
        "FIC_0_AMBA_AXI4_MASTER:Enabled" \
        "FIC_0_AXI4_DATA_WIDTH:64" \
        "FIC_1_AMBA_AXI4_SLAVE:Enabled" \
        "FIC_1_AMBA_AXI4_MASTER:Enabled" \
        "FIC_1_AXI4_DATA_WIDTH:64" \
        "FIC_2_AMBA_APB_MASTER:Enabled" \
        "FIC_3_AMBA_AXI4_SLAVE:Disabled" \
        "FIC_3_AMBA_AXI4_MASTER:Disabled" \
        "DDR_CONTROLLER:Enabled" \
        "MMUART_0:Enabled" \
    }

puts "INFO: MSS configured with FIC0 (AXI4-64), FIC1 (AXI4-64), FIC2 (APB3-32)"

# ══════════════════════════════════════════════════════
# Section 2: Create Top-Level SmartDesign
# ══════════════════════════════════════════════════════

puts "INFO: Creating top-level SmartDesign: $TOP_SD_NAME"

create_smartdesign -sd_name $TOP_SD_NAME

# ──────────────────────────────────────────────────────
# Instantiate all components
# ──────────────────────────────────────────────────────

# MSS
sd_instantiate_component \
    -sd_name $TOP_SD_NAME \
    -component_name $MSS_COMPONENT \
    -instance_name $MSS_INSTANCE

# CoreVectorBlox V250
sd_instantiate_component \
    -sd_name $TOP_SD_NAME \
    -component_name $VBX_COMPONENT \
    -instance_name $VBX_INSTANCE

# SmartHLS PID Controller
sd_instantiate_component \
    -sd_name $TOP_SD_NAME \
    -component_name $PID_COMPONENT \
    -instance_name $PID_INSTANCE

# Clock Conditioning Circuitry
sd_instantiate_component \
    -sd_name $TOP_SD_NAME \
    -component_name $CCC_COMPONENT \
    -instance_name $CCC_INSTANCE

# Init Monitor (reset sequencing)
sd_instantiate_component \
    -sd_name $TOP_SD_NAME \
    -component_name $INITMON_COMPONENT \
    -instance_name $INITMON_INSTANCE

puts "INFO: All components instantiated"

# ══════════════════════════════════════════════════════
# Section 3: Clock and Reset Wiring
# ══════════════════════════════════════════════════════

puts "INFO: Wiring clock and reset network..."

# MSS reference clock → CCC PLL input
# VERIFY_AFTER_SHLS_HW: Confirm MSS reference clock port name.
# On Icicle Kit, the MSS provides a reference clock output to fabric.
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${MSS_INSTANCE}:FIC_0_ACLK" \
        "${CCC_INSTANCE}:OUT0_FABCLK_0" \
    ]

sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${MSS_INSTANCE}:FIC_1_ACLK" \
        "${CCC_INSTANCE}:OUT0_FABCLK_0" \
    ]

# Fabric clock → VectorBlox
# VERIFY_AFTER_SHLS_HW: Confirm CoreVectorBlox clock port name.
# May be "CLK", "ACLK", or "clk" depending on IP version.
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${VBX_INSTANCE}:CLK" \
        "${CCC_INSTANCE}:OUT0_FABCLK_0" \
    ]

# Fabric clock → PID controller
# VERIFY_AFTER_SHLS_HW: Confirm SmartHLS-generated clock port name.
# SmartHLS typically names it "clk" (lowercase).
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${PID_INSTANCE}:clk" \
        "${CCC_INSTANCE}:OUT0_FABCLK_0" \
    ]

# Init Monitor → reset for fabric components
# VERIFY_AFTER_SHLS_HW: Confirm reset port names.
# SmartHLS uses active-high "reset" by default.
# CoreVectorBlox may use active-low "RESETn".
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${PID_INSTANCE}:reset" \
        "${INITMON_INSTANCE}:FABRIC_POR_N" \
    ]

sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${VBX_INSTANCE}:RESETn" \
        "${INITMON_INSTANCE}:FABRIC_POR_N" \
    ]

puts "INFO: Clock and reset wiring complete"

# ══════════════════════════════════════════════════════
# Section 4: FIC0 → CoreVectorBlox (AI Inference)
# ══════════════════════════════════════════════════════
#
# FIC0 carries two AXI channels:
#   - MSS AXI Master → VBX AXI Slave (MSS configures VBX, loads VNNX)
#   - VBX AXI Master → MSS AXI Slave (VBX DMA reads/writes DDR data)
#
# VERIFY_AFTER_SHLS_HW: CoreVectorBlox port names depend on the
# IP version. Check the configured CoreVectorBlox_0 component
# in SmartDesign for exact AXI port names. Common patterns:
#   Slave:  AXI4_S, S_AXI, AXI_TARGET
#   Master: AXI4_M, M_AXI, AXI_INITIATOR
# ──────────────────────────────────────────────────────

puts "INFO: Wiring FIC0 → CoreVectorBlox..."

# MSS FIC0 Master → VBX Slave (configuration + VNNX model loading)
# VERIFY_AFTER_SHLS_HW: Confirm pin names from MSS and VBX components
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${MSS_INSTANCE}:FIC_0_AXI4_MASTER" \
        "${VBX_INSTANCE}:AXI4_S" \
    ]

# VBX Master → MSS FIC0 Slave (DMA: VBX reads inference data from DDR)
# VERIFY_AFTER_SHLS_HW: Confirm VBX has a master port for DMA.
# If VBX only has a slave interface, remove this connection and
# the MSS firmware will push data to VBX instead of VBX pulling.
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${VBX_INSTANCE}:AXI4_M" \
        "${MSS_INSTANCE}:FIC_0_AXI4_SLAVE" \
    ]

puts "INFO: FIC0 ↔ VectorBlox wired (bidirectional AXI4)"

# ══════════════════════════════════════════════════════
# Section 5: FIC1 → SmartHLS PID Controller
# ══════════════════════════════════════════════════════
#
# FIC1 carries one AXI channel:
#   - MSS AXI Master → PID AXI Target (MSS writes gains, reads status)
#
# The PID controller uses AXI Target for configuration registers
# (Kp, Ki, Kd, out_min, out_max) and simple wires for the real-time
# datapath (error, u_AI_in, actuator_out). The simple wire ports
# are NOT connected through the AXI bus — they connect directly
# to fabric I/O or other IP blocks.
#
# VERIFY_AFTER_SHLS_HW: SmartHLS generates the AXI target interface
# based on #pragma HLS interface pragmas in nv_pid.cpp. The port
# name is typically the function argument name prefixed with the
# interface type. Confirm by examining the generated Verilog.
# ──────────────────────────────────────────────────────

puts "INFO: Wiring FIC1 → PID controller..."

# MSS FIC1 Master → PID AXI Target (register configuration)
# VERIFY_AFTER_SHLS_HW: Confirm the SmartHLS-generated AXI target
# port name. Common patterns:
#   - "axi_target_0" (SmartHLS auto-generated)
#   - "s_axi"
#   - Module-specific name from pragma
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list \
        "${MSS_INSTANCE}:FIC_1_AXI4_MASTER" \
        "${PID_INSTANCE}:axi_target_0" \
    ]

puts "INFO: FIC1 → PID wired (AXI4 target for gain configuration)"

# ══════════════════════════════════════════════════════
# Section 6: PID Real-Time Datapath (Simple Wires)
# ══════════════════════════════════════════════════════
#
# The PID controller's real-time ports use #pragma HLS interface
# type(simple), meaning they are bare wires with no protocol
# overhead. These connect to:
#   - error: frequency detuning from ODMR sensor (Q34.30)
#   - u_AI_in: AI feedforward from VectorBlox output register
#   - ai_watchdog_timeout: watchdog status flag
#   - actuator_out: DAC control voltage (Q16.16)
#
# For Libero synthesis, these can be promoted to
# top-level SmartDesign ports for timing analysis. Actual
# board-level wiring depends on the Icicle Kit I/O assignment.
# ──────────────────────────────────────────────────────

puts "INFO: Promoting PID datapath ports to top level..."

# VERIFY_AFTER_SHLS_HW: Confirm the exact port names and widths
# from the SmartHLS-generated Verilog. The names below are based
# on the C++ function signature in nv_pid.cpp:
#
#   void nv_pid_top(
#       freq_t error,           // 64-bit input  (Q34.30)
#       out_t u_AI_in,          // 32-bit input  (Q16.16)
#       bool ai_watchdog_timeout, // 1-bit input
#       gain_t Kp, Ki, Kd,     // 32-bit AXI target (not wired here)
#       out_t out_min, out_max, // 32-bit AXI target (not wired here)
#       out_t &actuator_out     // 32-bit output (Q16.16)
#   )

# Create top-level ports for real-time datapath signals
sd_create_bus_port -sd_name $TOP_SD_NAME \
    -port_name {error_in} \
    -port_direction {IN} \
    -port_range {[63:0]}

sd_create_bus_port -sd_name $TOP_SD_NAME \
    -port_name {u_AI_in} \
    -port_direction {IN} \
    -port_range {[31:0]}

sd_create_scalar_port -sd_name $TOP_SD_NAME \
    -port_name {ai_watchdog_timeout} \
    -port_direction {IN}

sd_create_bus_port -sd_name $TOP_SD_NAME \
    -port_name {actuator_out} \
    -port_direction {OUT} \
    -port_range {[31:0]}

# Connect top-level ports to PID instance
# VERIFY_AFTER_SHLS_HW: SmartHLS may mangle port names (e.g.,
# adding suffixes like _V for std_logic_vector). Check the
# generated Verilog port list.
sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list "error_in" "${PID_INSTANCE}:error"]

sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list "u_AI_in" "${PID_INSTANCE}:u_AI_in"]

sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list "ai_watchdog_timeout" "${PID_INSTANCE}:ai_watchdog_timeout"]

sd_connect_pins -sd_name $TOP_SD_NAME \
    -pin_names [list "actuator_out" "${PID_INSTANCE}:actuator_out"]

puts "INFO: PID datapath ports promoted to top level"

# ══════════════════════════════════════════════════════
# Section 7: Mark Unused Pins
# ══════════════════════════════════════════════════════
#
# VERIFY_AFTER_SHLS_HW: After all connections are made, some
# MSS and IP pins will remain unconnected. Mark them unused
# to prevent Libero warnings. The list below is a starting
# point — add pins as needed based on actual component ports.
# ──────────────────────────────────────────────────────

puts "INFO: Marking unused pins..."

# FIC2 APB — reserved, no fabric peripheral yet
sd_mark_pins_unused -sd_name $TOP_SD_NAME \
    -pin_names [list "${MSS_INSTANCE}:FIC_2_APB_MASTER"]

# FIC3 — disabled, but may still expose ports
# sd_mark_pins_unused -sd_name $TOP_SD_NAME \
#     -pin_names [list "${MSS_INSTANCE}:FIC_3_AXI4_MASTER"]

# VERIFY_AFTER_SHLS_HW: Run generate_component and check for
# unconnected pin warnings. Add sd_mark_pins_unused calls for
# each warning until the design generates cleanly.

# ══════════════════════════════════════════════════════
# Section 8: Generate Design
# ══════════════════════════════════════════════════════

puts "INFO: Generating SmartDesign..."

generate_component -component_name $TOP_SD_NAME

# Set as root of the design hierarchy
set_root -module "${TOP_SD_NAME}::work"

build_design_hierarchy

save_project

puts ""
puts "========================================="
puts " SmartDesign assembly complete"
puts ""
puts " Top-level: $TOP_SD_NAME"
puts " Components:"
puts "   $MSS_INSTANCE  — RISC-V MSS (FIC0/FIC1/FIC2)"
puts "   $VBX_INSTANCE  — CoreVectorBlox V250 on FIC0"
puts "   $PID_INSTANCE  — SmartHLS PID on FIC1"
puts "   $CCC_INSTANCE  — 200 MHz fabric clock"
puts "   $INITMON_INSTANCE — Reset sequencing"
puts ""
puts " FIC Mapping:"
puts "   FIC0 (AXI4-64) ↔ VectorBlox (bidirectional)"
puts "   FIC1 (AXI4-64) → PID AXI target (config regs)"
puts "   FIC2 (APB3-32)   [reserved]"
puts ""
puts " VERIFY_AFTER_SHLS_HW checklist:"
puts "   [ ] SmartHLS component name matches PID_COMPONENT"
puts "   [ ] SmartHLS AXI target port name (axi_target_0?)"
puts "   [ ] SmartHLS simple wire port names (error, u_AI_in, etc.)"
puts "   [ ] SmartHLS port widths (may have _V suffix)"
puts "   [ ] CoreVectorBlox AXI port names (AXI4_S, AXI4_M?)"
puts "   [ ] CoreVectorBlox clock/reset port names"
puts "   [ ] MSS FIC port names match Libero 2025.2"
puts "   [ ] MSS configuration complete (use GUI first pass)"
puts "   [ ] All unused pins marked (check generate warnings)"
puts "========================================="
puts ""
puts "Next step: source 04_synth_pnr.tcl"
