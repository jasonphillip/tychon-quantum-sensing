# 01_scaffold_proj.tcl — Initialize Libero SoC project for PolarFire Hybrid Control
#
# Target: MPFS250T (PolarFire SoC Icicle Kit) — Silver license
# Fallback: Change DEVICE_DIE to MPFS460T if MPFS250T lacks resources
#           for CoreVectorBlox V250 + PID (also Silver-eligible)
#
# NOTE: Do NOT target RTPF500ZT (RT PolarFire) — requires Gold license
#
# Run from Libero Tcl console:
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
#
# Package: FCVG484 confirmed from physical Icicle Kit silkscreen
# (MPFS250T-FCVG484E, date code 2241 = ISO week 41 of 2022).
# Corroborated by the pristine Beelink project log
# `MPFS_ICICLE_Vectorblox.log` (2026-04-02), which records the
# same MPFS250T-FCVG484E project info. Supersedes the prior
# FCSG536e working assumption from HW-01.
# ──────────────────────────────────────────────────────
set DEVICE_FAMILY  "PolarFireSoC"
set DEVICE_DIE     "MPFS250T"
set DEVICE_PACKAGE "FCVG484"
set DEVICE_SPEED   "STD"
set PROJECT_NAME   "polarfire_hybrid_control"

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
    -hdl "VERILOG"

# ──────────────────────────────────────────────────────
# Import constraint files into project
# Libero copies these into the project's constraint/ dir
# ──────────────────────────────────────────────────────
puts "INFO: Importing constraint files..."

import_files -sdc [file join $CONSTR_DIR timing_200mhz.sdc]
import_files -pdc [file join $CONSTR_DIR pinout.pdc]

# ──────────────────────────────────────────────────────
# Associate constraints with design flow tools
#
# The SDC timing constraint applies to synthesis, P&R,
# and SmartTime. The PDC pinout constraint applies to
# P&R only. Constraint-to-tool binding ensures each
# tool sees the right constraint set.
# ──────────────────────────────────────────────────────
puts "INFO: Organizing constraints into tool flows..."

organize_tool_files \
    -tool {SYNTHESIZE} \
    -file [file join $PROJ_DIR constraint timing_200mhz.sdc] \
    -module "${PROJECT_NAME}::work" \
    -input_type {constraint}

organize_tool_files \
    -tool {PLACEROUTE} \
    -file [file join $PROJ_DIR constraint timing_200mhz.sdc] \
    -file [file join $PROJ_DIR constraint pinout.pdc] \
    -module "${PROJECT_NAME}::work" \
    -input_type {constraint}

organize_tool_files \
    -tool {VERITIMING} \
    -file [file join $PROJ_DIR constraint timing_200mhz.sdc] \
    -module "${PROJECT_NAME}::work" \
    -input_type {constraint}

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
