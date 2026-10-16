# Safety Architecture

## Bounded AI Authority Plus Watchdog Detection

The safety design has two mechanisms.

1. **Bounded AI authority.** The AI path can move the actuator only within a clamped amplitude and a slew budget. The clamp and the slew limiter sit between the AI output and the sum with the PID output.
2. **Watchdog detection.** A watchdog detects a missed AI inference deadline. A controller update while the timeout is asserted can hand control to the classical PID. The recorded software-paced build requires the processor to start that update.

This document does not claim that the architecture guarantees stability or safety without conditions. The stability results below hold only under the assumptions listed beside each one. The open items are in *Residual Proof Obligations*.

**Board-test correction (2026-10-16).** The [October 9 trip-start fix and retest](watchdog_fallback_test_plan.md#fix-1a-trip-start-software-retested-2026-10-09-18451900-utc) covered a one-second pause of the control process. All ten cases were PID-only after execution resumed: nine through a forced start after resume, and one already PID-only before the pause. This tests recovery after a process pause, not autonomous recovery during a processor freeze. A processor that stays frozen cannot start a new PID-only output. Recovery discontinuities also remain; see [Residual Proof Obligations](#residual-proof-obligations).

## Bounded Hybrid Simplex RTA

The analysis treats the AI feedforward path as a sector-bounded nonlinearity in a Lur'e system. The Circle Criterion then gives a sufficient condition for absolute stability. The condition requires three items:

1. **Sector saturation clamp (±5% analysis bound).** The clamp limits the AI output to a fraction of the actuator range. It is implemented in `hls/src/safety_clamps.cpp` (`apply_sector_clamp_gated()`). The hardware limit is 4.5% (`OUTER_SECTOR_CLAMP_FRACTION = 0.045` in `hls/include/rta_config.hpp`). The 4.5% value leaves room for ±5.0% after worst-case fixed-point rounding. The 4.5% limit is a compile-time constant, and the AXI-writable inner limit can only tighten it.

2. **Bounded slew rate.** The change in the AI feedforward output per controller invocation is clamped (`MAX_SLEW_PER_CYCLE = 0.001`). At the 125 MHz PID fabric clock, with one invocation per clock, this equals 125 V/ms. The V/ms figure holds only if the controller runs once per fabric clock cycle. At a slower update rate, the per-invocation bound stays 0.001 and the bound per unit time changes in proportion to the update period. The slew limit is meant to keep abrupt AI corrections from exciting plant resonances or violating the du/dt assumption in the stability analysis.

3. **Asymptotically stable classical PID.** The baseline controller, without AI, must be stable on its own. The AI component adds a feedforward correction. The AI term is bounded by the clamp, and the final sum is saturated to the actuator limits.

### Conditional result: absolute stability at ±5% authority

The Circle Criterion argument holds only if all of these assumptions hold:

- The plant model used in the analysis is valid, and the plant gain stays in the range the analysis assumes. Plant model identification is an open obligation (see below).
- The classical PID is asymptotically stable on that plant for the configured Kp, Ki and Kd.
- The AI contribution at the actuator is bounded by the clamp. The code re-applies the clamp after slew limiting (C++ testbench verified; synthesis check open, see below).
- The update period is fixed and known, and the analysis uses the same period. The analysis so far is continuous-time. Sampled-data effects are open (see below).
- The slew limiter and the final actuator saturation are active as modelled.
- The AI block behaves as a sector-bounded nonlinearity. For a neural network this needs separate verification of the trained weights (see below).

If any assumption fails, the result does not apply.

## Authority Bound Summary

| Level | Sector Bound | Status |
|-------|-------------|--------|
| Current implementation | ±5% (4.5% in hardware) | Implemented. Stability result is conditional (see above). |
| Expanded authority (proposed) | ±30% operational | Analytical result only, under the conditions below. Not implemented. |
| Analytical limit | ±50% | Circle Criterion limit in the analysis, for any positive plant gain, under the conditions below. Not implemented. |

The ±5% bound was chosen conservatively for initial deployment. The Lur'e/Circle Criterion analysis reports that k_max floors at ±50%: the nonlinearity sector [0, k_max] admits any gain up to half the actuator range.

### Conditional result: expanded authority up to ±30%

The ±30% bound is proposed as an operating point below the ±50% analytical limit. It is a result of analysis, not of test. It holds only under these assumptions:

- All assumptions of the ±5% result above hold.
- The plant gain is positive, as the ±50% derivation assumes. A positive-gain plant model is not yet identified from data.
- The sampled-data and transport-delay effects in items (a) and (b) below have been shown to leave enough phase margin at this authority. They have not been shown yet.
- The hardware clamp is changed to match the new bound. The current hardware clamp is 4.5%.

## Watchdog and Bumpless Transfer

A hardware watchdog (`hls/src/watchdog.cpp`, `watchdog_check()`) monitors AI inference latency through a heartbeat input. The near-term hardware target is 250,000 cycles at the 125 MHz fabric clock, or 2 ms (`WATCHDOG_TIMEOUT_CYCLES`). The watchdog output stays set until the next heartbeat. On timeout:
- On a controller update that observes the timeout, the system transfers from AI+PID mode to pure PID mode.
- Bumpless transfer absorbs the last AI output into the PID integrator: `I_new = I_old + u_AI_old`.
- This reduces voltage discontinuities at the actuator output during mode transitions.
- A cooldown period holds the system in PID-only mode after timeout. It reduces high-frequency switching (chattering) between AI+PID and PID-only modes.

### Conditional result: handover to the PID on a missed deadline

The watchdog detects a missed deadline, and control returns to the classical PID, only if:

- The watchdog logic keeps running, and the heartbeat input reflects real inference completion.
- The watchdog fires within its configured deadline, and the timeout signal reaches `nv_pid_top()`.
- The PID path that takes over runs on logic that does not depend on the stalled processor. In the current software-paced build this condition does not hold: the core computes only when the processor starts it (`firmware/linux/v250_pid_loop.c` runs the inference, then writes `R_ACC_START`), so a stalled processor stops PID updates too. Confirmed on the board 2026-10-09 (test plan scenario (a), 10/10): during a 1 s stop of the control process the actuator register held its last value and no PID-only update occurred.
- The fallback at the actuator takes effect only if a software start happens while the timeout is still asserted. Before the October 9 correction, a 0.54 ms timeout pulse could end before the next start; scenario c1 fell back 0/20 times. The trip-start correction forces a controller update before inference can clear an observed timeout; the same scenario then fell back 20/20 times. This still requires processor execution ([before/after report](watchdog_fallback_test_plan.md#fix-1a-trip-start-software-retested-2026-10-09-18451900-utc)).

The cooldown length depends on the controller update period, as described in the open obligations.

## Signal Path Assumptions

The current design assumes a simplified always-valid signal path for `u_AI_in`. The PID reads the VectorBlox output register combinatorially each cycle with no valid/ready handshake. Stale inference results are bounded by the sector clamp and slew limiter but are not distinguished from fresh results. A later deployment should add a valid/ready handshake to gate the AI feedforward on actual inference completion.

## Stability Analysis (Expanded-Authority Extension)

The following items extend the continuous-time Lur'e/Circle Criterion analysis to discrete-time and implementation effects. None of them is complete. The results in the sections above stay conditional until these items are done.

### (a) ZOH & Digital Transport Delay Characterization

The analysis above assumes continuous-time feedback. In practice, the PID operates on a sampled signal (zero-order hold at the DAC output), and the AI inference path adds a variable transport delay. The near-term bound on that delay is the 2 ms watchdog target, once built and verified. The ZOH and transport delay must be characterized to confirm that phase margin is preserved at the expanded ±30% authority. Specifically, the Nyquist plot of the loop transfer function including ZOH must remain outside the critical circle defined by the sector bounds. This check assumes a fixed, known update period.

### (b) Derivative Filter System Identification

The PID derivative term `Kd * (error - prev_error)` is described here as an unfiltered first difference, which amplifies high-frequency noise. For ±30% AI authority, the derivative noise floor interacts with the larger AI corrections. System identification of the derivative filter response (or addition of a proper derivative filter `Kd * s / (1 + s*Td/N)`) is needed to ensure the combined PID+AI system does not excite unmodeled plant dynamics.

### (c) IQC Contingency Framework

If the Circle Criterion proves insufficient under discrete-time effects (ZOH phase loss, transport delay, derivative noise), Integral Quadratic Constraints (IQC) provide a more general multiplier-based stability framework. IQC can handle rate-bounded and slope-restricted nonlinearities jointly. The sector clamp and slew limiter could then be analyzed as a single composite constraint rather than independently. This is a contingency, not required if (a) and (b) confirm adequate margins.

## Residual Proof Obligations

The results above hold *within the assumptions listed beside each one*. The following items are **not** proven yet. They must be discharged before any claim that the AI path "cannot destabilize" the loop is admissible.

| Obligation | Why required | Reference |
|---|---|---|
| Plant model identification | Circle Criterion needs a sector-bounded plant; the analysis assumes "any positive gain" | Khalil 3rd ed. §7 (Lur'e / Circle Criterion) |
| Quantitative phase margin under ZOH | Sampled-data closure changes Nyquist contour | Khalil §11 (digital control); Astrom-Hagglund Ch.6 |
| Bounded transport delay verification | The 2 ms watchdog target is the near-term worst case; nominal delay bound must be measured | Closed-loop FPGA-PID literature |
| Derivative filter SI | Unfiltered first-difference amplifies HF noise at expanded authority | Astrom-Hagglund Ch.4 |
| ReLU sector verification (NN-in-loop) | The AI block is a sector-bounded nonlinearity only if the trained weights satisfy a sector bound | Recent arXiv work on sector-bounded NN feedback |
| Workload-driven SmartPower | Default-toggle estimate is an upper bound, not an operational measurement | Microchip SmartPower UG 2025.2 |
| Cooldown counter units (verified in code 2026-10-09) | The cooldown counter in `hls/src/nv_pid.cpp` (line 63, `cooldown_counter++` inside `if (in_cooldown)`) increments once per controller invocation. `hls/include/rta_config.hpp` (lines 34-35) describes `WATCHDOG_COOLDOWN_CYCLES = 1000` as "1000 cycles at 125 MHz = 8.0 µs". At the measured software-paced cadence of about 3.3 kHz, 1000 invocations take about 0.3 s. Every time-based statement about the cooldown depends on the update period. The memo [`docs/controller_sample_interval_2026-10.md`](controller_sample_interval_2026-10.md) gives the per-build semantics and a proposed explicit update period; the design change is open. | Code inspection; measured update cadence |
| Clamp bound after slew limiting (verified in code 2026-10-09) | Until 2026-10-09, `hls/src/nv_pid.cpp` applied the AI amplitude clamp before the slew limiter only, so a lowered bound was not re-enforced after the slew step. The clamp now runs again after slew, and `hls/tb/tb_bumpless.cpp` checks that a zero inner bound gives zero AI contribution on the next update (C++ testbench). The SmartHLS synthesis check of this change is still open. | Code inspection |
| Watchdog fallback on the board (tested 2026-10-09) | Tested per [`docs/watchdog_fallback_test_plan.md`](watchdog_fallback_test_plan.md), Results section. Hand-over works when a start sees the timeout: one update latency, bumpless, 1000-update cooldown (b1, b2, c0: 60/60). Without a fix it does **not** happen when the timeout clears before the next start (c1: 0/20). **Fixed in software the same day** (`firmware/linux/wd_trip_start.h`, on by default in `v250_pid_loop`): c1 now falls back 20/20 and a 1 s pause ends PID-only 10/10. A processor that stays frozen still yields no fallback value until it resumes. Recovery adds the AI term back in a step of about 0.01 (B7). Open: software-started controller has no PID-only output during a processor stall; absorbed AI values accumulate in the integrator and clip at the output limit (core change). | Board runs 2026-10-09, `libero/reports/2026-10-09-watchdog-fallback/` and `libero/reports/2026-10-09-trip-start-fix/` |

Until these items are discharged, all stability and power statements in this file and the README are qualified as "sector-bounded by design, within the listed assumptions". They are not statements that the loop is proven unable to destabilize.

## Implementation

| Mechanism | File | Function |
|-----------|------|----------|
| Sector clamp | `hls/src/safety_clamps.cpp` | `apply_sector_clamp_gated()` |
| Slew limiter | `hls/src/safety_clamps.cpp` | `apply_slew_limit()` |
| Watchdog | `hls/src/watchdog.cpp` | `watchdog_check()` |
| Watchdog cooldown | `hls/src/nv_pid.cpp` | Cooldown counter in `nv_pid_top()` |
| Bumpless transfer | `hls/src/nv_pid.hpp` | `NVPID::bumpless_transfer()` |
| Config constants | `hls/include/rta_config.hpp` | `OUTER_SECTOR_CLAMP_FRACTION`, `MAX_SLEW_PER_CYCLE`, `WATCHDOG_TIMEOUT_CYCLES`, `WATCHDOG_COOLDOWN_CYCLES` |
