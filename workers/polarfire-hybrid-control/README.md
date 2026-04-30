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

1. **Sector saturation clamps** -- AI output limited to +/-5% of actuator range (sector-bounded Lur'e nonlinearity per Khalil 2002)
2. **Slew-rate limiter** -- Per-cycle AI output change bounded to prevent plant resonance excitation
3. **Hardware watchdog** -- 1 ms timeout triggers bumpless transfer from AI+PID to pure PID mode

Within the documented Phase I assumptions (sector bound +/-5%, slew limit, asymptotically stable classical PID, plant model and ZOH characterization deferred to Phase II), these mechanisms confine the AI component to a sector-bounded perturbation of the classical PID loop. **A full absolute-stability proof under discrete-time effects (ZOH phase loss, bounded transport delay, derivative noise) is a residual Phase II obligation** -- see the "Phase II Stability Analysis" section of `docs/safety_architecture.md` for the open items (ZOH characterization, derivative filter system identification, IQC contingency framework).

## Phase I vs Phase II Wiring

The current build defeats Synplify constant-folding of the PID datapath via the `patch_smartdesign_pid_axi.py` rewires (FIC_0 master taps to nv_pid_top's axi4target slave) plus the `pid_io_block` companion slave at FIC_0_PERIPHERALS. Both slaves eavesdrop on the same FIC_0 traffic in Phase I; deterministic two-slot AXI interconnect routing is a Phase II SmartDesign canvas change documented in `libero/scripts/patch_smartdesign_pid_axi.py`. The CoreVectorBlox `output_valid` watchdog source is opt-in via `--vbx-output-valid` and requires the canvas to expose `Vectorblox_ss_output_valid` to top level.

## Power Analysis

SmartPower synthesis reports are generated on the Beelink build host and archived on the NAS (`/mnt/nas/projects/polarfire-hybrid-control/reports/`). Key numbers from the most recent analysis:

| Component | Power (default-toggle estimate) |
|-----------|---------------------------------|
| FPGA fabric (PID + VBX + interconnect) | 2,664 mW |
| Total system (MPFS250T + DDR + I/O) | ~5.2 W |
| **SWaP budget** | **12 W** |
| **Margin** | **~57%** |

**Power numbers are SmartPower default-toggle estimates, not workload-driven measurements.** Static power is derived from activity-factor defaults; no VCD has been captured against representative ODMR closed-loop traffic. Treat these as preliminary until a workload-driven SmartPower run replaces them. The `smartpower_report.rpt` artifact is not committed to this repo — it is regenerated on each synthesis run via `libero/scripts/04_synth_pnr.tcl`.
