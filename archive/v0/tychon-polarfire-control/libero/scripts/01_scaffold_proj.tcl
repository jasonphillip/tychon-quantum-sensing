# 01_scaffold_proj.tcl — Initialize Libero SoC project for Tychon PolarFire Control
#
# Target: MPFS250T (PolarFire SoC Icicle Kit) — Silver license
# Fallback: Change DEVICE_DIE to MPFS460T if MPFS250T lacks resources
#           for CoreVectorBlox V250 + PID (also Silver-eligible)
#
# NOTE: Do NOT target RTPF500ZT (RT PolarFire) — requires Gold license (Phase II only)
#
# Run on Beelink from Libero Tcl console:
#   cd <repo>/libero/scripts
#   source 01_scaffold_proj.tcl

# ──────────────────────────────────────────────────────
# Path setup — all paths relative to this script's location
# ──────────────────────────────────────────────────────
set SCRIPT_DIR  [file dirname [info script]]
set REPO_ROOT   [file normalize [file join $SCRIPT_DIR ../..]]
set PROJ_DIR    [file join $REPO_ROOT libero work]
set CONSTR_DIR  [file join $REPO_ROOT libero constraints]

# ──────────────────────────────────────────────────────
# Device selection — change DEVICE_DIE to MPFS460T if
# resource estimation fails after 02_import_ip.tcl
# ──────────────────────────────────────────────────────
set DEVICE_FAMILY  "PolarFireSoC"
set DEVICE_DIE     "MPFS160T"
set DEVICE_PACKAGE "FCSG536"
set DEVICE_SPEED   "STD"
set PROJECT_NAME   "tychon_polarfire_control"

# ──────────────────────────────────────────────────────
# Create project
# ──────────────────────────────────────────────────────
puts "INFO: Creating Libero project: $PROJECT_NAME"
puts "INFO: Device: $DEVICE_DIE / $DEVICE_PACKAGE / $DEVICE_SPEED"

new_project \
    -name $PROJECT_NAME \
    -location $PROJ_DIR \
    -family $DEVICE_FAMILY \
    -die $DEVICE_DIE \
    -package $DEVICE_PACKAGE \
    -speed $DEVICE_SPEED \
    -hdl {VERILOG}

# ──────────────────────────────────────────────────────
# Import constraint files into project
# Libero copies these into the project's constraint/ dir
# ──────────────────────────────────────────────────────
puts "INFO: Importing constraint files..."

import_files -sdc [file join $CONSTR_DIR timing_200mhz.sdc]
import_files -io_pdc [file join $CONSTR_DIR pinout.pdc]

# ──────────────────────────────────────────────────────
# Constraint association
#
# Libero 2025.2 uses the enhanced constraint flow —
# imported SDC and IO_PDC files are auto-associated
# with synthesis, P&R, and timing tools. No manual
# organize_tool_files needed.
# ──────────────────────────────────────────────────────
puts "INFO: Constraints imported (enhanced flow — auto-associated)"

# ──────────────────────────────────────────────────────
# Save and report
# ──────────────────────────────────────────────────────
save_project

puts ""
puts "========================================="
puts " Project scaffold complete"
puts " Location: $PROJ_DIR"
puts " Device:   $DEVICE_DIE ($DEVICE_PACKAGE)"
puts " SDC:      timing_200mhz.sdc (200 MHz)"
puts " PDC:      pinout.pdc"
puts "========================================="
puts ""
puts "Next step: Run 'shls hw' in hls/ to generate PID RTL,"
puts "           then source 02_import_ip.tcl"
