# Firmware

Deferred until SmartDesign memory map is locked (~Day 30+).
Do not write main.c or vbx_driver.c yet.

When the SmartDesign is complete and memory-mapped register addresses are known,
this directory will contain:
- `src/main.c` — RISC-V bare-metal MSS orchestrator
- `src/vbx_driver.c` — CoreVectorBlox V250 driver (model load, inference trigger)
- Linker scripts and SoftConsole project files
