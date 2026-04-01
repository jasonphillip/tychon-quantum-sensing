# 03_smartdesign.tcl — Wire AXI interconnect in SmartDesign
#
# Architecture (from Playbook v4, Deliverable 3):
#   MSS FIC0 (64-bit AXI4) → CoreVectorBlox V250 (AI inference DMA)
#   MSS FIC1 (64-bit AXI4) → SmartHLS PID controller (separate FIC to avoid bus contention)
#   MSS FIC2 (32-bit APB3) → Control registers (config, status, watchdog)
#
# Physical separation of VectorBlox and PID on different FIC ports prevents
# AXI bus contention between AI inference DMA and real-time PID updates.
#
# Run on Beelink after 02_import_ip.tcl:
#   source 03_smartdesign.tcl

# TODO: Populate with SmartDesign wiring commands after IP import is verified
