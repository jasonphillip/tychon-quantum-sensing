# PolarFire Hybrid Control

Hybrid PID + neural network control system for RT PolarFire SoC. SmartHLS C++ implementation with bounded safety architecture and CoreVectorBlox integration.

## What This Does

- SmartHLS C++ PID controller with bumpless AI-to-PID transfer
- Sector saturation clamps (+/-5%) and slew-rate limiting on AI feedforward
- Hardware watchdog infrastructure with automatic fallback to pure PID; the current demo image is a verified 2 ms fabric watchdog build
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing (SmartTime) and power estimation (SmartPower)

## Architecture

```
+-------------------------------------------------------------+
|                    MPFS250T Fabric                           |
|                                                             |
|  MSS (RISC-V)                                               |
|  +-- FIC0 fabric address space                              |
|  |   +-- 0x60030000 --> CoreVectorBlox V250 control UIO     |
|  |   +-- 0x60040000 --> idfix2 two-slot PID M0/M1 window    |
|  |       +-- M0 0x60040000..0x600407ff gains/start          |
|  |       +-- M1 0x60040800..0x60040fff pid_csr/readback     |
|  |                                                          |
|  +-- FIC2 AXI4 target --> MSS DDR non-cached path           |
|  |                         (V250 model / IO DMA buffers)    |
|                                                             |
|  PID fabric domain --> 125 MHz; V250 core path --> 200 MHz  |
|  PF_INIT_MONITOR_0 --> Reset sequencing                     |
+-------------------------------------------------------------+
```

Current hardware bring-up uses the Linux/Yocto userspace path on the U54 cores:
`generic-uio` exposes the V250 control page, and `/dev/udmabuf-ddr-nc0`
provides non-cached DDR buffers for the V250 data path. The fabric PID remains
the real-time/safety path; Linux is supervisory and used for bring-up/runtime
orchestration.

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
+-- firmware/               RISC-V Linux userspace helpers for V250/PID bring-up and demo control
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
- Linux/Yocto on the U54 cores for the supported CoreVectorBlox Icicle runtime;
  the safety-critical loop lives in fabric, not Linux userspace. (The <150 us
  loop-latency figure is a design budget. RTL-sim bound [TB]: 6 cycles = 48 ns
  start-accept -> actuator-we, constant over 128 iterations on the real
  two-slot RTL — `docs/fabric_latency_sim_2026-07-01.md`. On-kit API-level
  bounds: `docs/latency_measured_2026-06-21.md`. An on-SILICON fabric-internal
  measurement is still open.)

## Current Hardware State

As of 2026-06-21, the dashboard remediation pass is the current status anchor:
`docs/remediation_status_2026-06-21.md` and `docs/remediation_progress_2026-06-21.md`.
The remaining-work execution plan is `docs/everything_else_execution_plan_2026-06-21.md`.
The dashboard LIVE path is idfix2-aware and guarded: enable it only with
`KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`; M0 reads remain blocked; M0 writes are allowlisted to
limits/gains/start; actuator values are read from M1 `R_POST_CLAMP`. A bounded smoke through
`tools/rung_g_replay.py --host icicle --rows 5 --out /tmp/idfix2_smoke --plot` produced nonzero
M1 actuator values and advancing `axi_write_count`. V250 still probes successfully
(`out[0]=-2.9506`, `error_val=0`, `csr_version=0x00010000`).

Evidence captured in this pass:

- `docs/latency_measured_2026-06-21.md` — on-kit V250/PID helper bounds plus host-paced rung-G
  timing. Linux userspace traps `rdcycle`, so pure V250/fabric cycle timing is still pending.
- `libero/reports/2026-06-21-idfix2-resource/` — idfix2 resource bundle; device/package source is
  MPFS250T FCVG484 from the compile report. **Package-label note for all committed reports:**
  Synplify mapper outputs (`*_fpga_mapper*.rpt`, `*.srr`) print Synplify's internal device-DB
  name `mpfs250tfcg1152std`, which maps every MPFS250T package onto one mapper part — it is not
  the board package. The Libero project targets `FCVG484` (`libero/scripts/01_scaffold_proj.tcl`),
  every Libero-proper report says `Package: FCVG484`, and die resources are identical across
  MPFS250T packages, so utilization percentages are unaffected.
- `libero/reports/2026-06-21-scan/` — read-only FlashPro scan-chain evidence; no programming action.
- `libero/reports/2026-06-21-latency/` — raw on-kit `vnnx_latency` and `pid_latency` logs.
- `libero/reports/2026-06-21-safety-build/` — cloned 1 ms watchdog safety-build attempt. The clone
  was patched to `WATCHDOG_TIMEOUT_CYCLES=125000`, but Libero/Synplify hung before exporting a `.job`;
  no programming action. Forward-looking demo acceptance has been relaxed to a verified 2 ms
  watchdog target (`WATCHDOG_TIMEOUT_CYCLES=250000` at 125 MHz); see
  `docs/credible_demo_finish_criteria_2026-06-21.md`.
- `libero/reports/2026-06-21-watchdog-2ms/` — exported and programmed
  `WATCHDOG_TIMEOUT_CYCLES=250000` two-slot image. Timing met, FlashPro scan passed, PROGRAM passed,
  rollback command/hash recorded, V250 probe passed, dashboard guarded stream passed, and the kit-side
  V250 loop clears the watchdog until stopped.
- `libero/reports/2026-06-21-workload-power-topname/` — SmartPower explicit-VCD-top rerun attempt.
  The run produced a default-equivalent report with no annotation evidence; no workload-annotated
  SmartPower report was produced.
- `docs/nn_sector_certificate_plan_2026-06-21.md` and
  `docs/real_nv_dataset_hunt_2026-06-21.md` — research-track status, both partial.

Persistent programming was performed only for the dated 2 ms watchdog image after rollback hashes,
the exact rollback command, and FlashPro scan visibility were recorded. Post-program checks confirmed
CSR access, V250 inference, guarded actuator telemetry, and watchdog clear/trip behavior. A physical
cold power-cycle remains a recommended operator check, but was not needed for the captured V250
post-program probe.

Current measured bounds from 2026-06-21: V250 `vbx_cnn_model_start`+poll via `vnnx_latency` has
median `32 us` and p99 `33 us` for the already-loaded model path; idfix2 M0 start pulse plus M1
`post_clamp_out` read via `pid_latency` has median `4 us` and p99 `4 us`; the host-paced
`tools/rung_g_replay.py --rows 120` loop has median inter-sample period `10122 us`.

As of 2026-06-16, the CoreVectorBlox **2.0.1/V250** rebuild bitstream is programmed and
**V250 inference runs to completion on Production MPFS250T silicon** (`vbx_probe` →
INFERENCE COMPLETED, `vnnx_smoke` → `out[0]=-2.9506`; VERSION `0x60030028`=`0x20000000`).
See `docs/rung_f_v250_on_silicon_results_2026-06-16.md`, `docs/track0_bringup_runbook.md`,
and `docs/fpga_reproducibility_inventory_2026-06-16.md`.

**As of 2026-06-18 the clean two-slot bitstream `idfix2` is programmed and FULLY FUNCTIONAL on
Production MPFS250T silicon** (job `39c8bcf2…`, timing met +0.789 ns). All three rungs work:
- **V250 inference** — `vbx_probe` INFERENCE COMPLETED, `vnnx_smoke` `out[0]=-2.9506` (a cold
  power-cycle is required after any fabric program for V250 init).
- **Clean M0/M1 CSR plane** — gains slave (M0 `0x60040000`) and `pid_csr` (M1 `0x60040800`) both
  read/write bit-exact, no wedge.
- **LIVE PID actuator** — set gains via M0, inject error via M1 (`0x810/0x814`), pulse start
  (`0x60040008`), read the latched actuator (`0x60040844`): it tracks `error` at Kp and the sector
  clamp saturates (err 2.0 → +1.0). `tools/rung_g_replay.py --host icicle` streams the ODMR trace
  through it; `tools/rung_g_animate.py` renders the moving dashboard.

Two latent RTL bugs were fixed to get here (verified in ModelSim *and* on silicon): the M0
`nv_pid_top.reset` tie-off + demux 9→1-bit ID truncation (bus wedge), and the un-latched 1-cycle
actuator output. Engineering log: `docs/two_slot_handoff_2026-06-17.md` (2026-06-18 sections) +
`docs/two_slot_demo_scope_2026-06-18.md`. Rollbacks: idfix `7907a83f`, demo `a5550f9e`, V250 `4e3323e8`.

Known open hardware blockers:

- **Fabric PCIe @ `0x3000000000` is broken in the 2.0.1/V250 rebuild** — the Linux
  `microchip-pcie` probe hangs on it (the V250/FIC path is fine). This *was* a boot-loop; it is now
  **persistently worked around** — the PCIe device-tree node is disabled at boot via a reversible
  U-Boot env `fdt set`, so a normal reboot recovers autonomously to an inference-ready kit (see
  `docs/rung_f_v250_on_silicon_results_2026-06-16.md` §6 and `/root/PCIE-DISABLED-README.md` on the kit).
  The only remaining work is the *optional* long-term fix (re-synth with the fabric PCIe intact) **if
  PCIe is ever needed**. The trusted rung-A seed_7 (1.1.12/V500) `.job` remains the bitstream rollback.
- **`0x60001000` is the DMA controller, not the PID — never poke it.** On the two-slot bitstream
  the PID lives on SLAVE3 `0x60040000`: the **M1 `pid_csr` (`0x60040800`) is clean and validated**,
  the **M0 AXI-completion defect that wedged a U54 was FIXED 2026-06-18 (`idfix2`)** — M0 now
  reads/writes cleanly and the live PID actuator works. (Historical: on the older `idfix`/demo/
  seed_7 bitstreams an M0 read wedged the kit — never run M0 accesses against those.)
  See `docs/two_slot_demo_scope_2026-06-18.md`.

## Safety Architecture

The AI feedforward path is bounded by three safety mechanisms:

1. **Sector saturation clamps** -- AI output limited to +/-5% of actuator range (Lure/Circle Criterion)
2. **Slew-rate limiter** -- Per-cycle AI output change bounded to prevent plant resonance excitation
3. **Hardware watchdog** -- timeout triggers bumpless transfer from AI+PID to pure PID mode; the
   current programmed image uses the verified `250000`-cycle / 2 ms fabric watchdog.

These mechanisms make the AI feedforward path **sector-bounded by design within the Phase I assumptions** documented in `docs/safety_architecture.md`. They do not constitute a proof that the AI cannot destabilize the loop — that requires discharging the Residual Proof Obligations table (closable under follow-on path) in the same document (plant model identification, ZOH phase margin, transport delay bound, derivative filter SI, ReLU sector verification, workload-driven SmartPower).

## Power Analysis

SmartPower synthesis reports are generated on the Beelink build host and archived on the NAS (`/mnt/nas/projects/polarfire-hybrid-control/reports/`). The numbers below are **default-toggle estimates** (activity-factor heuristic, no VCD): preliminary until workload-driven SmartPower is run with a representative input trace.

| Component | Power (vectorless SmartPower) |
|-----------|-------|
| FPGA fabric (PID + VBX + interconnect) | 2,622.9 mW (2026-06-21 run: Total 2622.855 / Static 445.612 / Dynamic 2177.243) |
| Total system (MPFS250T + DDR + I/O) | ~5.2 W (fabric + MSS estimate) |
| **SWaP budget** | **12 W** |
| **Margin** | **~57%** (preliminary — vectorless; workload-driven SmartPower (RPO-6) still open) |

Static power is derived from SmartPower estimation. The `smartpower_report.rpt` artifact is not committed to this repo — it is regenerated on each synthesis run via `libero/scripts/04_synth_pnr.tcl`. Workload-driven SmartPower is one of the Residual Proof Obligations (closable under follow-on path) in `docs/safety_architecture.md`.

2026-06-21 update: the SmartPower workload flow was patched to import the VCD with explicit top
`nv_pid_top_top`; the rerun produced Total `2622.855 mW`, Static `445.612 mW`, Dynamic
`2177.243 mW`, matching the previous default/vectorless result. No annotation log/result was
produced, so the report is still vectorless/default activity rather than workload-driven.
