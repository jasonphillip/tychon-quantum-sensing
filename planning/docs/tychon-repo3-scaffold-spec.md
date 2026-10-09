> Original: claude.ai project document, created 2026-04-01. Edited for publication: names of other people and business details removed.

# Tychon AI — Repo 3 Scaffold Spec: `tychon-polarfire-control`

**Document version:** 1.0  
**Date:** April 1, 2026  
**Author:** Jason Phillip (decisions) + Claude (consolidation & review)  
**Plan:** 90-day build plan  
**Authoritative sources:** Tychon AI Execution Playbook v4 (March 9, 2026), Platform Addendum v4 (March 9, 2026)  
**Consolidated from:** `gemini-dt-repo3-architecture-reviewed.md`, `gemini-dt-smarthls-pid.md`, `gemini-dt-vectorblox-export.md` (Repo 3 portions only)

---

## 1. Purpose and Usage Instructions

This is the **single authoritative input** for scaffolding the `tychon-polarfire-control` repository (Repo 3). Feed this entire document as context when starting Claude Code in Plan Mode.

**What this document covers:**
- File tree and scaffold order
- Dependency verdicts (what to build, exclude, defer)
- Data contracts (upstream from Repos 1 & 2, downstream deliverables)
- Day 1 scaffold vs deferred items
- SmartHLS C++ PID implementation (Claude-reviewed code, ready to adapt)
- Fixed-point type definitions and analysis
- Safety architecture completeness checklist
- VNNX integration points (what Repo 3 consumes from the export pipeline)
- Risk register
- Cross-machine workflow (Spark ↔ Beelink)

**What this document does NOT cover:**
- Repo 1 (tychon-nv-sim) — see `tychon_phase1_repo_architecture_decisions.md`
- Repo 2 (tychon-odmr-ml) — see Section 6 of the repo architecture decisions doc
- Training pipeline or QAT details — see `gemini-dt-training-loop.md` and `gemini-dt-vectorblox-export.md` (Repo 2 portions)
- Final Report narrative — see `gemini-dt-final-report-narrative-reviewed.md`

**Document hierarchy:**
- v4 Playbook → authoritative for requirements and timeline
- v4 Addendum → authoritative for platform specs and safety architecture
- This document → authoritative for Repo 3 scaffold decisions
- `tychon_microchip_toolchain_reference.md` → authoritative for toolchain versions and commands

---

## 2. File Tree

```
tychon-polarfire-control/
├── .gitignore                      # Exclude: /work, /ip_cache, *.vnnx, *.job, synthesis outputs
├── README.md                       # Setup, make targets, cross-machine workflow
├── CLAUDE.md                       # Context doc for Claude Code sessions
├── Makefile                        # Master orchestrator (calls HLS Makefiles & Libero Tcl)
│
├── docs/
│   ├── phase1-context/
│   │   ├── requirements.md         # Deliverable 3 requirements extracted from playbook
│   │   └── safety_architecture.md  # Lur'e/Circle Criterion formal framing from Addendum v4 §3
│   ├── timing_power_plan.md        # Methodology for SmartTime/SmartPower extraction
│   └── cross_machine_workflow.md   # Spark↔Beelink sync protocol
│
├── hls/                            # SmartHLS 2025.2 workspace (C++ → AXI4 RTL)
│   ├── Makefile                    # Targets: sw_run (C++ test), hw (RTL generation)
│   ├── include/
│   │   ├── fp_types.hpp            # hls::ap_fixpt definitions (Q34.30 freq, Q16.16 gains)
│   │   └── rta_config.hpp          # Constants: ±5% clamps, max slew, 200K cycle timeout
│   ├── src/
│   │   ├── nv_pid.hpp              # PID class — adapt from Section 7 of this document
│   │   ├── nv_pid.cpp              # Top-level pipelined PID with AXI interfaces
│   │   ├── safety_clamps.cpp       # Sector saturation + slew-rate limiters
│   │   └── watchdog.cpp            # Hardware counter for VectorBlox AXI timeout
│   └── tb/
│       ├── tb_bumpless.cpp         # Bumpless transfer testbench — adapt from Section 8
│       └── stimulus/               # Drop-in for Repo 1 synthetic ODMR CSVs
│
├── libero/                         # Libero SoC 2025.2 hardware design
│   ├── scripts/
│   │   ├── 01_scaffold_proj.tcl    # Init project targeting MPFS250T (or MPFS460T)
│   │   ├── 02_import_ip.tcl        # Import SmartHLS PID + CoreVectorBlox V250 (v2.0.1)
│   │   ├── 03_smartdesign.tcl      # Wire AXI: MSS FIC0→VectorBlox, FIC1→PID
│   │   └── 04_synth_pnr.tcl       # Synthesis, P&R, extract XML timing/power reports
│   ├── reports/                    # SmartTime/SmartPower XMLs committed from Beelink
│   └── constraints/
│       ├── pinout.pdc              # Physical I/O (board-specific)
│       └── timing_200mhz.sdc      # 200 MHz Fmax clock constraint
│
├── firmware/                       # RISC-V bare-metal MSS orchestrator
│   └── README.md                   # STUB ONLY on Day 1 — defer until SmartDesign memory map exists
│
└── models/                         # Repo 2 compiled network artifacts
    └── README.md                   # Documents .vnnx transfer protocol from shared filesystem
```

---

## 3. Dependency Verdicts

| Dependency | Version | Verdict | Rationale |
|-----------|---------|---------|-----------|
| Libero SoC | 2025.2 (Silver) | **BUILD** | Silver supports MPFS250T/MPFS460T. Gold required for RT PolarFire — out of scope for this plan. |
| SmartHLS | 2025.2 | **BUILD** | C++ → AXI4 RTL. Essential for PID iteration. Bundled with Libero. |
| CoreVectorBlox IP | v2.0.1 | **BUILD** | Latest in MegaVault. V250 preset for power budget. |
| VectorBlox SDK | **v2.0.3** | **BUILD** | Must match IP core major version (v2.0.x). Pin across Repos 2 and 3. |
| VectorBlox SDK | v3.0 | **EXCLUDE** | Major version mismatch with v2.0.1 IP. Risk of silent AXI faults due to potential V-ISA/header changes. Re-evaluate when Microchip releases matching v3.x IP in MegaVault. |
| Target: RTPF500ZT | — | **EXCLUDE** | Requires Gold license. Out of scope for this plan. |
| Target: MPFS250T | — | **BUILD** | This plan eval target. Verify resource headroom for CoreVectorBlox V250 after `02_import_ip.tcl`. |
| Target: MPFS460T | — | **FALLBACK** | If MPFS250T lacks resources for VectorBlox V250. Still Silver-eligible. |
| MSS RTOS | Bare-metal C | **BUILD** | Linux jitter violates <150 µs guarantee. |
| SoftConsole | — | **DEFER** | Only needed when `firmware/main.c` is active (~Day 30+). |

**CRITICAL: SDK version propagates to Repo 2.** The `vnnx_compile` tool in Repo 2's export pipeline must use SDK v2.0.3, not v3.0. The `.vnnx` must be compiled with `-s V250` flag to match the CoreVectorBlox V250 preset. Document this in both repos' CLAUDE.md files.

**OPEN QUESTION: MPFS250T resource sufficiency.** V250 is the smallest core, MPFS250T is the smallest SoC. Run resource estimation after `02_import_ip.tcl` before committing. Have MPFS460T as fallback.

---

## 4. Data Contracts

### Upstream (what this repo consumes)

| Source | Artifact | Format | Location in Repo 3 | Transfer Mechanism |
|--------|----------|--------|-------------------|-------------------|
| Repo 1 | Synthetic ODMR spectra | CSV | `hls/tb/stimulus/` | Copied from `~/projects/tychon-shared-data/` |
| Repo 2 | INT8 quantized model | `.vnnx` binary | `models/` | Copied from `~/projects/tychon-shared-data/models/` |

**Transfer rules:**
- Use the shared filesystem (`~/projects/tychon-shared-data/`) as the transfer mechanism
- Do NOT put .vnnx binaries in git (they're large binaries)
- Do NOT use git submodules (unnecessary complexity for solo founder)
- Simple `cp` or symlink
- The `.vnnx` must be compiled with `-s V250` flag in Repo 2's `vnnx_compile` step

### Downstream (what this repo produces)

| Artifact | Format | Purpose |
|----------|--------|---------|
| SmartTime reports | XML | Proves <150 µs PID, <1 ms AI inference |
| SmartPower reports | XML | Proves <12 W total |
| Resource utilization | Text/XML | LUTs, LSRAM, Math Blocks, DSPs |
| Hardware bitstream | .job | Board programming (this plan eval only) |
| Testbench pass/fail logs | Text | Bumpless transfer and safety clamp verification |

---

## 5. Day 1 Scaffold vs Deferred

### Build on Day 1

| Item | Notes |
|------|-------|
| File tree with stubs | All directories, READMEs, .gitignore |
| `fp_types.hpp` | Fixed-point type definitions (see Section 6) |
| `rta_config.hpp` | Safety constants: ±5% clamp, max slew, 200K cycle timeout |
| `nv_pid.hpp` / `nv_pid.cpp` | Adapt from Section 7 of this document (Claude-reviewed code) |
| `safety_clamps.cpp` | Sector saturation + slew-rate limiter shells |
| `watchdog.cpp` | Free-running counter shell |
| `tb_bumpless.cpp` | Bumpless transfer testbench (adapt from Section 8) |
| `01_scaffold_proj.tcl` | Empty Libero MPFS250T project initialization |
| `Makefile` (top-level + hls/) | Build orchestration |
| Run `shls sw_run` | Verify C++ testbench passes before any hardware synthesis |

### Defer

| Item | When | Prerequisite |
|------|------|-------------|
| `shls hw` (RTL generation) | Day 15+ | C++ testbench passes |
| SmartDesign assembly (`03_smartdesign.tcl`) | Day 20+ | SmartHLS IP generated, CoreVectorBlox V250 instantiated |
| Libero synthesis + P&R (`04_synth_pnr.tcl`) | Day 30+ | SmartDesign complete |
| SmartTime / SmartPower extraction | Day 30+ | P&R complete |
| `firmware/src/main.c` | Day 30+ | SmartDesign memory map locked |
| `firmware/src/vbx_driver.c` | Day 30+ | CoreVectorBlox instantiated |

---

## 6. Fixed-Point Type Definitions

**CRITICAL: Use SmartHLS syntax, NOT Xilinx/Vivado syntax.**

```cpp
#include <hls/ap_fixpt.hpp>

// DO NOT use ap_fixed<W,I> — that is Xilinx Vivado/Vitis HLS
// SmartHLS uses hls::ap_fixpt<W,I> where W = total bits, I = integer bits

typedef hls::ap_fixpt<64, 34> freq_t; // Q34.30: 34 integer bits, 30 fractional
typedef hls::ap_fixpt<32, 16> gain_t; // Q16.16: 16 integer bits, 16 fractional
typedef hls::ap_fixpt<32, 16> out_t;  // Q16.16: matches gain_t for DAC interface
```

**Design rationale:**

| Type | Format | Range | Precision | Use | Hardware Cost |
|------|--------|-------|-----------|-----|--------------|
| `freq_t` | Q34.30 | ±8.58 GHz | ~0.93 mHz | Hz detuning error | 64-bit: requires DSP splitting (multiple 18×18 Math blocks) |
| `gain_t` | Q16.16 | ±32,767 | ~15 µ | Kp, Ki, Kd | 32-bit: maps well to PolarFire 18×18 Math blocks (4 partial products) |
| `out_t` | Q16.16 | ±32,767 | ~15 µ | Actuator voltage, clamp values | Same as gain_t; ideal for 16-bit DAC interfaces |

**Why Q34.30 for frequency error:** The integral state accumulates small ~kHz errors multiplied by tiny Ki gains. Insufficient fractional precision causes truncation-to-zero and limit cycling. The 30 fractional bits provide ~0.93 mHz resolution. The 34 integer bits are defensive — prevents overflow if host software accidentally sends absolute frequency (~2.87 GHz) rather than detuning error.

**Interface contract:** Only pass detuning error (not absolute frequency) to the PID. The Q34.30 format is defensive engineering, not a recommendation to pass raw GHz values.

---

## 7. SmartHLS C++ PID Implementation (Claude-Reviewed)

This code has been reviewed against the Addendum Section 3.1-3.2 safety architecture spec. It is the starting point for `nv_pid.hpp` and `nv_pid.cpp` in the scaffold.

**Status:** Architecturally correct. Two safety components (sector saturation clamps, slew-rate limiter) are documented as missing and must be implemented in `safety_clamps.cpp`. Pragma syntax needs verification against SmartHLS 2025.2 installed docs on Beelink.

### nv_pid.hpp

```cpp
#ifndef NV_PID_HPP
#define NV_PID_HPP

#include <hls/ap_fixpt.hpp>

// Fixed-point type definitions (see Section 6 for rationale)
typedef hls::ap_fixpt<64, 34> freq_t; // Q34.30 (Hz Detuning Error)
typedef hls::ap_fixpt<32, 16> gain_t; // Q16.16 (Controller Gains)
typedef hls::ap_fixpt<32, 16> out_t;  // Q16.16 (Actuator Voltage)

class NVPID {
private:
    out_t integral;
    freq_t prev_error;
    out_t out_min;
    out_t out_max;

public:
    NVPID() : integral(0), prev_error(0), out_min(0), out_max(0) {}

    void set_limits(out_t min_val, out_t max_val) {
        out_min = min_val;
        out_max = max_val;
    }

    // Bumpless Transfer from AI feedforward to PID
    // Algorithm: I_new = I_old + u_AI_old (Addendum Section 3.2)
    void bumpless_transfer(out_t u_AI_old) {
        integral = integral + u_AI_old;
        if (integral > out_max) integral = out_max;
        if (integral < out_min) integral = out_min;
    }

    out_t compute(freq_t error, gain_t Kp, gain_t Ki, gain_t Kd) {
        #pragma HLS function inline

        out_t p_term = (out_t)(Kp * error);
        integral = integral + (out_t)(Ki * error);
        if (integral > out_max) integral = out_max;
        if (integral < out_min) integral = out_min;

        out_t d_term = (out_t)(Kd * (error - prev_error));
        prev_error = error;

        out_t output = p_term + integral + d_term;
        if (output > out_max) output = out_max;
        if (output < out_min) output = out_min;

        return output;
    }
};

#endif // NV_PID_HPP
```

### nv_pid.cpp

**NOTE:** This code is missing sector saturation clamps and slew-rate limiting on `u_AI_in`. Those must be implemented in `safety_clamps.cpp` and called before the summation line. See Section 9 (Safety Completeness) for the full checklist.

```cpp
#include "nv_pid.hpp"

void nv_pid_top(
    freq_t error,
    out_t u_AI_in,
    bool ai_watchdog_timeout,
    gain_t Kp, gain_t Ki, gain_t Kd,
    out_t out_min, out_t out_max,
    out_t &actuator_out
) {
    #pragma HLS function top
    #pragma HLS function pipeline II(1)

    // AXI4 Target for CPU/VectorBlox configuration
    #pragma HLS interface control type(axi_target)
    #pragma HLS interface argument(Kp) type(axi_target)
    #pragma HLS interface argument(Ki) type(axi_target)
    #pragma HLS interface argument(Kd) type(axi_target)
    #pragma HLS interface argument(out_min) type(axi_target)
    #pragma HLS interface argument(out_max) type(axi_target)

    // Bare wires for real-time nanosecond datapath
    #pragma HLS interface argument(error) type(simple)
    #pragma HLS interface argument(u_AI_in) type(simple)
    #pragma HLS interface argument(ai_watchdog_timeout) type(simple)
    #pragma HLS interface argument(actuator_out) type(simple)

    static NVPID pid;
    static bool prev_watchdog = false;
    static out_t u_AI_latch = 0;

    pid.set_limits(out_min, out_max);

    // Watchdog rising edge detection for bumpless handoff
    if (ai_watchdog_timeout && !prev_watchdog) {
        pid.bumpless_transfer(u_AI_latch);
    }

    out_t u_pid = pid.compute(error, Kp, Ki, Kd);

    out_t total_out;
    if (ai_watchdog_timeout) {
        total_out = u_pid;
    } else {
        // TODO: Insert safety_clamps (sector saturation + slew-rate) on u_AI_in HERE
        // u_AI_clamped = apply_sector_clamp(u_AI_in);  // ±5% of (out_max - out_min)
        // u_AI_safe = apply_slew_limit(u_AI_clamped, u_AI_latch);  // du/dt bounded
        // total_out = u_AI_safe + u_pid;
        total_out = u_AI_in + u_pid;  // TEMPORARY: replace with clamped version
        u_AI_latch = u_AI_in;
    }

    if (total_out > out_max) total_out = out_max;
    if (total_out < out_min) total_out = out_min;

    actuator_out = total_out;
    prev_watchdog = ai_watchdog_timeout;
}
```

### SmartHLS Pragma Notes (verify against 2025.2 docs)

| Pragma | Purpose | Verification Status |
|--------|---------|-------------------|
| `#pragma HLS function pipeline II(1)` | One output per clock cycle | Syntax consistent with 2022-2023 docs; verify 2025.2 |
| `#pragma HLS interface argument(...) type(axi_target)` | AXI4 slave for config registers | Same |
| `#pragma HLS interface argument(...) type(simple)` | Bare wires for real-time datapath | Same |
| `#pragma HLS function inline` | Inline PID math into top-level pipeline | Correct pattern |

**Known concern:** The `set_limits()` call every cycle inside a pipelined function may create a cross-iteration dependency if SmartHLS doesn't recognize the pattern. Consider moving limit configuration to initialization or making limits function arguments with `stable` pragma.

---

## 8. Verification Testbench (Claude-Reviewed)

Verifies the key property: **zero actuator voltage discontinuity at the AI→PID handoff.** The only expected delta is the natural Ki×error accumulation from the PID's own integral step.

This is a software testbench for `shls sw_run`. Cycle-accurate co-simulation (`shls cosim`) is a later step.

```cpp
#include <iostream>
#include <cmath>
#include "nv_pid.hpp"

void nv_pid_top(freq_t, out_t, bool, gain_t, gain_t, gain_t, out_t, out_t, out_t&);

int main() {
    freq_t error = 5000.0;    // 5 kHz frequency error
    out_t u_AI = 2.5;          // AI outputting 2.5V feedforward
    bool watchdog = false;

    gain_t Kp = 0.0001, Ki = 0.00002, Kd = 0.00001;
    out_t out_min = 0.0, out_max = 5.0;
    out_t actuator_out;

    std::cout << "--- SmartHLS NV-Magnetometer Bumpless Transfer Testbench ---\n\n";

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    std::cout << "Cycle 1 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    out_t pre_fail_out = actuator_out;
    std::cout << "Cycle 2 [AI Active]        Actuator Output: "
              << actuator_out.to_double() << " V\n";

    // Simulate >1ms AI inference lag
    watchdog = true;
    u_AI = 0.0;
    nv_pid_top(error, u_AI, watchdog, Kp, Ki, Kd, out_min, out_max, actuator_out);
    out_t post_fail_out = actuator_out;

    std::cout << "Cycle 3 [Watchdog Trip]    Actuator Output: "
              << actuator_out.to_double() << " V\n";

    double delta = post_fail_out.to_double() - pre_fail_out.to_double();
    double expected_natural_step = (Ki * error).to_double();
    std::cout << "\nDelta at transition:   " << delta << " V\n";
    std::cout << "Expected natural step: " << expected_natural_step << " V\n";

    if (std::abs(delta - expected_natural_step) < 1e-5) {
        std::cout << "\nPASS: Bumpless transfer successful.\n";
    } else {
        std::cout << "\nFAIL: Voltage jump detected.\n";
    }

    return 0;
}
```

---

## 9. Safety Architecture Completeness Checklist

| Safety Component | Addendum Section | In PID Code (Section 7)? | Action |
|-----------------|-----------------|--------------------------|--------|
| Sector Saturation Clamps (±5% AI authority) | 3.1 | ✗ Missing | Implement in `safety_clamps.cpp`. Clamp formula: `u_AI_clamped = clamp(u_AI_in, -0.05 * (out_max - out_min), +0.05 * (out_max - out_min))` |
| Slew-Rate Limiting (du_AI/dt clamped) | 3.1 | ✗ Missing | Implement in `safety_clamps.cpp`. Register previous AI value; clamp delta per cycle. |
| Execution Watchdog (1 ms timeout) | 3.1 | ✓ Present | Rising-edge detection correct. Implement counter in `watchdog.cpp` (200K cycles at 200 MHz = 1 ms). |
| Bumpless Transfer (I_new = I_old + u_AI_old) | 3.2 | ✓ Present | Algorithm correct. Anti-windup clamping after transfer is correct. |
| Anti-windup clamping | Standard PID | ✓ Present | On integral and output. |
| AXI4 target for config registers | Deliverable 3 | ✓ Present | Pragma syntax needs 2025.2 verification. |
| Simple wires for real-time datapath | Deliverable 3 | ✓ Present | Correct for nanosecond-latency signals. |
| II=1 pipelining | Deliverable 3 | ✓ Present | Deterministic latency guarantee. |

**Implementation note on sector clamps:** Clamp at ±4.5% in hardware to guarantee ±5.0% compliance with worst-case fixed-point rounding. Verify via bit-true C++ sim.

---

## 10. SmartHLS Module Decomposition

| File | Responsibility | Safety Role |
|------|---------------|-------------|
| `nv_pid.hpp` / `nv_pid.cpp` | Classical PID with anti-windup, bumpless transfer | The asymptotically stable core — must function independently |
| `safety_clamps.cpp` | Sector saturation (±5%) + slew-rate limiter | The nonlinear bounds φ(y,t) for Lur'e absolute stability |
| `watchdog.cpp` | 200 MHz free-running counter, 1.0 ms timeout | Triggers AI isolation on timeout |
| `top_controller.cpp` | AXI4 wrapper, module integration | Bumpless transfer orchestration |

### Integration Logic (top_controller.cpp)

```cpp
// Pseudocode — actual implementation uses SmartHLS pragmas
if (ai_timeout) {
    pid_core.bumpless_transfer(u_ai_prev);  // I_new = I_old + u_AI_old
    u_ai_safe = 0;
} else {
    u_ai_safe = apply_sector_clamp(u_ai_raw);  // ±5% of MAX_RANGE
    u_ai_safe = apply_slew_limit(u_ai_safe, u_ai_prev);  // du/dt bounded
    u_ai_prev = u_ai_safe;
}
u_actuator = pid_core.compute(error) + u_ai_safe;
```

---

## 11. VNNX Integration Points (Repo 3's Interface to the Export Pipeline)

Repo 3 does not run the export pipeline — that's Repo 2's job. Repo 3 consumes the output.

| What Repo 3 Needs | Format | Source | Constraint |
|-------------------|--------|--------|-----------|
| Compiled model binary | `.vnnx` | Repo 2's `vnnx_compile` output | Must be compiled with `-s V250` flag and SDK v2.0.3 |
| Bit-accuracy verification results | Text/logs | Repo 2's verification script | TFLite vs VNNX simulator max abs error ≤1 bit |

**Steps 3-4 of the export pipeline (TFLite → VNNX, verification) run on the Beelink** because they require VectorBlox SDK. Steps 1-2 (QAT, ONNX→TFLite) run on DGX Spark. Transfer TFLite files via shared filesystem.

**VectorBlox SDK v2.0.3 compile command:**
```bash
vnnx_compile -s V250 -t <model>_integer_quant.tflite -o <model>.vnnx
```
Note: `-s V250` (not `-c V250`) — verify exact flag syntax against `vnnx_compile --help` after installing SDK.

---

## 12. Deterministic Latency Analysis

**PID:** With `II(1)` at 200 MHz (5 ns period), the 64-bit and 32-bit math creates a pipeline of roughly 10-15 stages → 50-75 ns deterministic latency per PID update. This is well within the 150 µs budget (2000× margin).

**64-bit multiplication cost:** Q34.30 × Q16.16 requires 64-bit × 32-bit multiply. PolarFire has 18×18 Math blocks, so this splits into multiple DSP operations. SmartHLS handles the splitting automatically. Check the SmartHLS resource report after compilation for actual DSP usage.

**AI inference:** VectorBlox V250 target is <1 ms for the INT8 CNN. This runs asynchronously — CNN provides periodic bias correction, PID runs every cycle.

**These are estimates.** Actual numbers come from SmartTime after synthesis on the Beelink. Do not report these as measured values in the Final Technical Report.

---

## 13. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Q34.30 timing closure failure at 200 MHz | High | Medium | `#pragma HLS pipeline II=1`. Fallback: drop to 100 MHz (still 15,000 cycles within 150 µs budget — massive headroom). |
| AXI bus contention (VectorBlox vs PID) | Critical | Low | Physical separation: VectorBlox on FIC0, PID on FIC1. ODMR data bypasses DDR. |
| Power budget >12 W | High | Medium | V250 preset. Duty-cycle AI inference (10-100 Hz) with VectorBlox sleep mode between inferences. |
| Fixed-point truncation breaks stability proof | High | Low | Clamp at ±4.5% in hardware to guarantee ±5.0% compliance. Verify via bit-true C++ sim. |
| MPFS250T too small for CoreVectorBlox V250 | Medium | Medium | Run resource estimation early after `02_import_ip.tcl`. Fallback to MPFS460T (still Silver-eligible). |
| SDK v2.0.x missing operators needed by Repo 2 models | High | Low | Run `vnnx_compile` with v2.0.3 on the MLP architecture early. If ops are missing, simplify model. |
| SmartHLS pragma syntax differs in 2025.2 | Medium | Medium | Verify all pragmas against installed 2025.2 docs on Beelink before committing. |
| Cross-machine sync errors (Spark↔Beelink) | Medium | Medium | Use git as sync mechanism. Document workflow. Never edit on both machines without syncing. |

---

## 14. Cross-Machine Workflow

Repo 3 source lives on DGX Spark (where Claude Code CLI operates). Synthesis runs on Beelink (where Libero/SmartHLS are installed).

```
DGX Spark (source of truth):
  ~/projects/tychon-polarfire-control/
  - Edit C++ source, write testbenches, commit, push to GitHub
  - Run ops_guard checks on model architectures

    ↓ git push / git pull ↓

Beelink (synthesis machine):
  C:\Users\...\tychon-polarfire-control\
  - git pull from GitHub
  - shls sw_run (C++ testbench — verifies on x86)
  - shls hw (RTL generation)
  - Run Libero Tcl scripts for synthesis, P&R
  - Extract SmartTime / SmartPower reports
  - Push reports back to GitHub

    ↓ git push / git pull ↓

DGX Spark:
  - git pull to get synthesis reports
  - Analyze, document, iterate
```

**Rules:**
- Never edit source on Beelink — it's a build machine only
- Synthesis outputs (.job, reports) committed to `libero/reports/` and pushed
- `.gitignore` excludes Libero work directories, IP caches, intermediate synthesis files
- All Libero operations are Tcl-scripted — no GUI state to lose

---

## 15. CLAUDE.md Template for Repo 3

When scaffolding, create a `CLAUDE.md` at the repo root with this content (adjust as needed):

```markdown
# Tychon PolarFire Control — Claude Code Context

## Project
Tychon AI 90-day plan: FPGA implementation of hybrid PID+AI control loop on RT PolarFire SoC.
Solo founder, 90-day sprint. This is Repo 3 of a three-repo architecture.

## Authoritative Documents
- `docs/phase1-context/requirements.md` — Deliverable 3 requirements extracted from playbook
- `docs/phase1-context/safety_architecture.md` — Lur'e/Circle Criterion formal framing

## What This Repo Does
- SmartHLS C++ PID controller with bumpless AI→PID transfer
- Sector saturation clamps (±5%) and slew-rate limiting on AI output
- Hardware watchdog (200 MHz counter, 1 ms timeout)
- Libero SoC project targeting MPFS250T with CoreVectorBlox V250
- Static timing analysis (SmartTime) and power estimation (SmartPower)

## What This Repo Does NOT Do
- No ML training (that's Repo 2: tychon-odmr-ml)
- No physics simulation (that's Repo 1: tychon-nv-sim)
- No SDK v3.0 — pinned to v2.0.x (see dependency verdicts)
- No Linux on MSS — bare-metal C only

## Critical Constraints
- VectorBlox SDK v2.0.3 (NOT v3.0) — matches CoreVectorBlox IP v2.0.1
- .vnnx files compiled with `-s V250` flag
- SmartHLS type: hls::ap_fixpt (NOT ap_fixed — that's Xilinx)
- Silver license targets MPFS250T (fallback MPFS460T), NOT RT PolarFire (Gold, out of scope)

## Cross-Machine Workflow
- Source edited on DGX Spark, pushed to GitHub
- Beelink pulls, runs SmartHLS and Libero synthesis, pushes reports
- Never edit source on Beelink

## Do NOT
- Add CI workflows unless explicitly asked
- Use VectorBlox SDK v3.0
- Target RT PolarFire (RTPF500ZT) — out of scope for this plan
- Put .vnnx binaries in git
- Write firmware/main.c until SmartDesign memory map is locked
```

---

*End of document. This is the single authoritative input for scaffolding `tychon-polarfire-control`. Feed to Claude Code in Plan Mode.*

