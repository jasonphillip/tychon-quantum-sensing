# PolarFire Hybrid Control

Hybrid PID + neural network control system for RT PolarFire SoC. SmartHLS C++ implementation with bounded safety architecture and CoreVectorBlox integration.

## What This Does

- SmartHLS C++ PID controller with bumpless AI-to-PID transfer
- Sector saturation clamps (+/-5%) and slew-rate limiting on AI feedforward
- Hardware watchdog (200 MHz, 1 ms timeout) with automatic fallback to pure PID
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing (SmartTime) and power estimation (SmartPower)

## Architecture

```
+-------------------------------------------------------------+
|                    MPFS250T Fabric                           |
|                                                             |
|  MSS (RISC-V)                                               |
|  +-- FIC0 (64-bit AXI4) --> CoreVectorBlox V250             |
|  |                          (AI inference DMA)              |
|  |                                                          |
|  +-- FIC1 (64-bit AXI4) --> SmartHLS PID Controller         |
|  |                          (nv_pid_top, AXI target)        |
|  |                                                          |
|  +-- FIC2 (32-bit APB3) --> [Reserved: control regs]        |
|                                                             |
|  PF_CCC_0 --> 200 MHz fabric clock to all fabric IPs        |
|  PF_INIT_MONITOR_0 --> Reset sequencing                     |
+-------------------------------------------------------------+
```

Physical separation of VectorBlox and PID on different FIC ports prevents AXI bus contention between AI inference DMA and real-time PID updates.

## Directory Structure

```
polarfire-hybrid-control/
+-- hls/                    SmartHLS C++ source
|   +-- src/                PID controller, safety clamps, watchdog
|   +-- include/            Fixed-point types, RTA configuration
|   +-- tb/                 Testbenches and stimulus data
+-- libero/                 Libero SoC project
|   +-- scripts/            Tcl automation (scaffold -> synth -> P&R)
|   +-- constraints/        Timing (SDC) and pin (PDC) constraints
|   +-- reports/            Synthesis and timing reports
+-- firmware/               RISC-V bare-metal MSS code (placeholder)
+-- models/                 Compiled .vnnx model artifacts (not committed)
+-- docs/                   Safety architecture documentation
```

## Build

SmartHLS and Libero require an x86 host with Microchip tools installed.

```
make hls-test   # Run SmartHLS C++ software testbench
make clean       # Remove all build artifacts
make help        # Show available targets
```

Libero Tcl scripts must be sourced in order from the Libero Tcl console. If the Libero project does not yet exist on your build machine, re-source all four scripts sequentially to create it from scratch:

```
source libero/scripts/01_scaffold_proj.tcl
source libero/scripts/02_import_ip.tcl
source libero/scripts/03_smartdesign.tcl
source libero/scripts/04_synth_pnr.tcl
```

## Key Constraints

- SmartHLS type: `hls::ap_fixpt<W,I>` (NOT `ap_fixed` -- that's Xilinx)
- VectorBlox SDK **v2.0.3** (NOT v3.0) -- matches CoreVectorBlox IP v2.0.1
- `.vnnx` compiled with `-c V250` flag; not committed to git
- Bare-metal C on RISC-V MSS -- no Linux (jitter violates <150 us guarantee)

## Safety Architecture

The AI feedforward path is bounded by three safety mechanisms:

1. **Sector saturation clamps** -- AI output limited to +/-5% of actuator range (Lure/Circle Criterion)
2. **Slew-rate limiter** -- Per-cycle AI output change bounded to prevent plant resonance excitation
3. **Hardware watchdog** -- 1 ms timeout triggers bumpless transfer from AI+PID to pure PID mode

These mechanisms make the AI feedforward path **sector-bounded by design within the Phase I assumptions** documented in `docs/safety_architecture.md`. They do not constitute a proof that the AI cannot destabilize the loop — that requires discharging the Residual Phase II Proof Obligations table in the same document (plant model identification, ZOH phase margin, transport delay bound, derivative filter SI, ReLU sector verification, workload-driven SmartPower).

## Power Analysis

SmartPower synthesis reports are generated on the Beelink build host and archived on the NAS (`/mnt/nas/projects/polarfire-hybrid-control/reports/`). The numbers below are **default-toggle estimates** (activity-factor heuristic, no VCD): preliminary until workload-driven SmartPower is run with a representative input trace.

| Component | Power (default-toggle estimate) |
|-----------|-------|
| FPGA fabric (PID + VBX + interconnect) | 2,664 mW |
| Total system (MPFS250T + DDR + I/O) | ~5.2 W |
| **SWaP budget** | **12 W** |
| **Margin** | **~57%** (preliminary) |

Static power is derived from SmartPower estimation. The `smartpower_report.rpt` artifact is not committed to this repo — it is regenerated on each synthesis run via `libero/scripts/04_synth_pnr.tcl`. Workload-driven SmartPower is one of the Residual Phase II Proof Obligations in `docs/safety_architecture.md`.
