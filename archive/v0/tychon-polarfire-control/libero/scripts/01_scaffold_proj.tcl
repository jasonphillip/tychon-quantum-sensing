# 01_scaffold_proj.tcl — Initialize Libero SoC project
#
# Target: MPFS250T (PolarFire SoC Icicle Kit) — Silver license
# Fallback: MPFS460T if MPFS250T lacks resources for CoreVectorBlox V250 + PID
#
# NOTE: Do NOT target RTPF500ZT (RT PolarFire) — requires Gold license (Phase II only)
#
# Run on Beelink via Libero Tcl console:
#   source 01_scaffold_proj.tcl

# TODO: Populate with Libero project creation commands:
#   new_project -name {tychon_polarfire_control} \
#               -location {C:/Users/.../tychon-polarfire-control/work} \
#               -family {PolarFireSoC} \
#               -die {MPFS250T} \
#               -package {FCSG536} \
#               -speed {STD}
#
# If MPFS250T resource estimation fails after 02_import_ip.tcl,
# change -die to MPFS460T (also Silver-eligible).
