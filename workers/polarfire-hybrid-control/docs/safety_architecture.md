# Safety Architecture

## Bounded Hybrid Simplex RTA

The AI feedforward path is treated as a sector-bounded nonlinearity within a Lur'e system framework. Absolute stability is guaranteed via the Circle Criterion, which requires three conditions:

1. **Sector saturation clamps (±5% Phase I bound)** — AI output bounded to a fraction of the actuator range. Implemented in `hls/src/safety_clamps.cpp` with a 4.5% hardware limit to guarantee ±5.0% compliance after worst-case fixed-point rounding. Analytical re-derivation (Phase II) confirms the Circle Criterion holds up to ±50% authority for any positive plant gain, with ±30% proposed as the expanded operational bound for Phase II deployment.

2. **Bounded slew rate** — Per-cycle change in AI feedforward output is clamped (`MAX_SLEW_PER_CYCLE = 0.001`, i.e. 200 V/ms at 200 MHz). Prevents abrupt AI corrections from exciting plant resonances or violating du/dt assumptions in the stability proof.

3. **Asymptotically stable classical PID** — The baseline controller (without AI) must be stable on its own. The AI component adds feedforward corrections but cannot override the PID's stabilizing action.

## Authority Bound Summary

| Phase | Sector Bound | Status |
|-------|-------------|--------|
| Phase I (current) | ±5% (4.5% in hardware) | Implemented, conservative |
| Phase II (proposed) | ±30% operational | Analytically confirmed stable |
| Worst-case floor | ±50% | Circle Criterion limit for any positive plant gain |

The ±5% Phase I bound was chosen conservatively for initial deployment. The Lur'e/Circle Criterion analysis shows k_max floors at ±50% — the nonlinearity sector [0, k_max] admits any gain up to half the actuator range. The ±30% Phase II bound provides margin below this theoretical limit.

## Watchdog and Bumpless Transfer

A hardware watchdog (200 MHz counter, 1 ms timeout) monitors AI inference latency. On timeout:
- The system transfers from AI+PID mode to pure PID mode
- Bumpless transfer absorbs the last AI output into the PID integrator: `I_new = I_old + u_AI_old`
- This prevents voltage discontinuities at the actuator output during mode transitions
- A cooldown period (`WATCHDOG_COOLDOWN_CYCLES = 1000`, 5 µs at 200 MHz) holds the system in PID-only mode after timeout, preventing high-frequency limit-cycling (chattering) between AI+PID and PID-only modes

## Signal Path Assumptions

Phase I assumes a simplified always-valid signal path for `u_AI_in`. The PID reads the VectorBlox output register combinatorially each cycle with no valid/ready handshake. Stale inference results are bounded by the sector clamp and slew limiter but are not distinguished from fresh results. Phase II should implement a valid/ready handshake to gate AI feedforward on actual inference completion.

## Phase II Stability Analysis

The following items extend the Phase I Lur'e/Circle Criterion proof to cover discrete-time and implementation effects:

### (a) ZOH & Digital Transport Delay Characterization

The Phase I proof assumes continuous-time feedback. In practice, the PID operates on a sampled signal (zero-order hold at the DAC output), and the AI inference path introduces a variable transport delay (bounded by the 1 ms watchdog). The ZOH and transport delay must be characterized to confirm that phase margin is preserved at the expanded ±30% authority. Specifically, the Nyquist plot of the loop transfer function including ZOH must remain outside the critical circle defined by the sector bounds.

### (b) Derivative Filter System Identification

The PID derivative term `Kd * (error - prev_error)` is an unfiltered first difference, which amplifies high-frequency noise. For ±30% AI authority, the derivative noise floor interacts with the larger AI corrections. System identification of the derivative filter response (or addition of a proper derivative filter `Kd * s / (1 + s*Td/N)`) is needed to ensure the combined PID+AI system does not excite unmodeled plant dynamics.

### (c) IQC Contingency Framework

If the Circle Criterion proves insufficient under discrete-time effects (ZOH phase loss, transport delay, derivative noise), Integral Quadratic Constraints (IQC) provide a more general multiplier-based stability framework. IQC can handle rate-bounded and slope-restricted nonlinearities jointly, which would allow the sector clamp and slew limiter to be analyzed as a single composite constraint rather than independently. This is a contingency — not required if (a) and (b) confirm adequate margins.

## Residual Phase II Proof Obligations

The following items must be discharged before any "AI cannot destabilize the loop" claim is treated as proved (rather than as a sector-bounded design intent). Each cites the corpus reference that defines the standard.

| Obligation | Standard | Corpus Reference |
|------------|----------|------------------|
| Plant model identification (gain, bandwidth, dominant poles, ZOH at the actuator) | Required input to the Circle Criterion check | Khalil, *Nonlinear Systems 3rd ed.*, Ch. 7 (sector-bounded nonlinearities); `~/.corpus/polarfire-control-corpus/raw/` |
| Quantitative phase margin under ZOH at the operational sample period | Nyquist plot of loop transfer must remain outside the critical circle defined by the +/-5% sector | Same |
| Bounded transport delay characterization (CoreVectorBlox inference latency distribution) | Worst-case delay enters the IQC multiplier or extended Popov criterion | Khalil §7.1 + corpus user-contributed sector-bounded NN feedback notes |
| Derivative filter system identification | Unfiltered first-difference derivative amplifies high-frequency noise; needs measured plant frequency response to size a proper filter | `docs/safety_architecture.md` §(b) |
| ReLU NN sector verification (positivity, positive homogeneity, complementarity) | Strengthened circle criterion for ReLU networks per Richardson et al. 2023 IEEE | Corpus paper at `raw/arxiv/strengthened-circle-popov-relu.md` |
| Workload-driven SmartPower (VCD-based) | Replaces default-toggle SmartPower estimate before final SWaP claim | Corpus: VectorBlox SDK Programmer's Guide power section |

Until these items are discharged, statements about absolute stability should be qualified as "sector-bounded by design within the Phase I assumptions" rather than "proved cannot destabilize."

## Implementation

| Mechanism | File | Function |
|-----------|------|----------|
| Sector clamp | `hls/src/safety_clamps.cpp` | `apply_sector_clamp()` |
| Slew limiter | `hls/src/safety_clamps.cpp` | `apply_slew_limit()` |
| Watchdog | `hls/src/watchdog.cpp` | `watchdog_check()` |
| Watchdog cooldown | `hls/src/nv_pid.cpp` | Cooldown counter in `nv_pid_top()` |
| Bumpless transfer | `hls/src/nv_pid.hpp` | `NVPID::bumpless_transfer()` |
| Config constants | `hls/include/rta_config.hpp` | `SECTOR_CLAMP_FRACTION`, `MAX_SLEW_PER_CYCLE`, `WATCHDOG_TIMEOUT_CYCLES`, `WATCHDOG_COOLDOWN_CYCLES` |
