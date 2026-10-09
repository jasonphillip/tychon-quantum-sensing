# Watchdog fallback test plan: PID-only fallback at the actuator

Date: 2026-10-09. Status: plan only. Running it needs the board and Jason. No result exists yet.

## Purpose

The watchdog trip time is measured (`docs/watchdog_trip_measured_2026-07-01.md`: median 2.000 ms over 120 trips). The fallback itself is not yet tested at the actuator. This plan tests three cases:

- (a) The processor-side control process stops while the fabric keeps running.
- (b) Inference completion is suppressed, so the AI deadline passes.
- (c) The timeout signal ends before the next software start.

For each case the plan says what to capture, which numbers decide pass or fail, and how to stay safe.

## How the signals connect (read in the code)

| Signal or register | Where | Notes |
|---|---|---|
| Heartbeat | CoreVectorBlox `output_valid`, through `libero/hdl/vbx_pulse_gen.v` (one pulse per rising edge) | Firmware clears `output_valid` before the next inference. |
| Timeout | `libero/hdl/watchdog_timer.v` lines 41-57 | A fabric-clock counter. It sets `timeout` at 250,000 cycles and holds it until the next heartbeat. It is a level, not a pulse. |
| Timeout into the core | `libero/hdl/pid_subsystem.v` line 159 (`wd_timeout` to `ai_watchdog_timeout`) and line 191 (to the CSR tap) | The same wire goes to both. |
| Timeout register | `0x60040854` | Bit 0 is the live timeout. Bits 31:1 count rising edges (`libero/hdl/pid_csr_block.v` lines 198-201). |
| Core start | `0x60040008` (`acc_start`), write 1 | One write is one controller update (`docs/two_slot_register_map_2026-06-17.md` line 29). |
| Actuator value | `0x60040844` (`post_clamp_out`) | A latch loaded on each actuator write enable (`pid_subsystem.v` line 169). The repository describes no physical actuator pin. "Actuator value" in this plan means this register. |
| Write counter | `0x60040800` (`axi_write_count`) | Advanced by 3 per loop iteration in the recorded soak (`docs/mss_paced_loop_measured_2026-07-02.md`). |
| Inputs | `0x60040810`, `0x60040814` (error), `0x60040818` (`u_ai`) | Written by software before each start. |
| Limits and gains | `0x6004000C` to `0x60040020` | Kp, Ki, Kd, `out_min`, `out_max`, inner clamp. |
| Cooldown and `ai_active` taps | `0x60040858`, `0x6004085C` | Tied off, read 0 (register map lines 53-58). Cooldown state is not directly observable. |

The core reads `ai_watchdog_timeout` only when software starts it. Rising-edge detection compares the wire with its value at the previous start (`hls/src/nv_pid.cpp` lines 40 and 52). Fallback logic is in the same file: bumpless transfer and cooldown at lines 52-56, the cooldown counter at lines 61-67, and `ai_active = !timeout && !in_cooldown` at line 69.

## Constants and the numbers they give

| Constant | Value | Source | Meaning for this test |
|---|---|---|---|
| `WATCHDOG_TIMEOUT_CYCLES` | 250,000 | `hls/include/rta_config.hpp` line 29 | Timeout 2.000 ms at 125 MHz after the last heartbeat. |
| `WATCHDOG_COOLDOWN_CYCLES` | 1000 | `hls/include/rta_config.hpp` line 35 | 1000 controller updates in PID-only mode. See `docs/controller_sample_interval_2026-10.md`: this is a count of updates, not 8 µs. |
| `MAX_SLEW_PER_CYCLE` | 0.001 | `hls/include/rta_config.hpp` line 25 | Largest AI-term change per update. |
| `OUTER_SECTOR_CLAMP_FRACTION` | 0.045 | `hls/include/rta_config.hpp` line 19 | AI term bound: 0.045 × (`out_max` − `out_min`). With limits of ±1, the bound is 0.09. |
| Core latency | 6 cycles, 48 ns | `docs/fabric_latency_sim_2026-07-01.md` (RTL simulation) | From start accept to actuator latch. |
| Soak loop period | median 328 µs, p99 472 µs, max 3.213 ms | `libero/reports/2026-07-02-mss-paced/run_notes.md`, Measurement C | The software start period in the recorded soak. |
| Measured trip time | median 2.000 ms, min 1.978, max 2.032 ms | `docs/watchdog_trip_measured_2026-07-01.md` | Observer jitter 4 to 39 µs per that document. |

## What the code predicts (reading only, not tested)

These predictions need the board to confirm. Each one shapes a scenario.

1. **A stopped control process produces no fallback value.** The core computes only when software starts it. If the process stops, no new actuator value is computed. The register holds its last value. The timeout bit rises, but nothing consumes it. Scenario (a) therefore tests how the system holds, not a switch to PID-only.
2. **A short timeout is invisible to the core.** In `v250_pid_loop.c` each iteration runs inference first, then writes `acc_start` (lines 663 to 679). The inference completion clears the timeout before the start. A stall longer than 2 ms that ends before the next inference completes therefore usually leaves `timeout = 0` at the next start. The core never sees the rising edge. Scenario (c) tests this directly. If it holds, the "5 trips, all recovered" soak figure counts the CSR trip counter only. It does not show the controller falling back.
3. **Bumpless transfer hides the switch in the actuator value.** At the rising edge the core adds the last AI output to the integrator (`hls/src/nv_pid.hpp` lines 30-34). The output stays continuous. The fallback therefore shows in the actuator value only as "the AI term stops following `u_ai`". The test inputs below are built for that.
4. **Recovery may step.** The absorbed AI value stays in the integrator (with Ki = 0 nothing unwinds it). When the AI path re-enters, it adds the AI term again (`hls/src/nv_pid.cpp` lines 91-93). The prediction is a step of about `u_AI` at recovery, larger than the slew limit. Repeated fallbacks may absorb the stale value again. The test records this either way.

## Test tools

Existing tools in `firmware/linux/`:

- `watchdog_trip.c`: polls `0x60040854`, timestamps both edges of bit 0, writes nothing.
- `v250_pid_loop.c`: runs inference, writes `u_ai`, starts the core, reads the actuator and the timeout register. It sets Kp = 0.8, Ki = 0, Kd = 0, limits ±1.0 and inner clamp 0.045 (lines 597-602). It handles SIGINT and SIGTERM (lines 577-578).
- `pid_latency.c`: starts the core with no inference. It writes `u_ai = 0` only and does not set the inner clamp, so it is not enough for this plan.

Two tools do not exist yet and must be written first (read-only to the same pages, same address checks as the tools above, never touching `0x60001000`):

- **`wd_fallback_test`**, derived from `v250_pid_loop.c`. It keeps the same register setup. It adds a fixed error (0.20) and a `u_ai` that follows a slow triangle between −0.08 and +0.08 at 0.0005 per update. The slope is under the 0.001 slew limit, so in AI mode the actuator tracks it. In PID-only mode the actuator is flat. The tool logs one row per update: index, `rdtime` ticks, error and `u_ai` written, `post_clamp_out`, watchdog register. It takes a mode:
  - `normal`: inference then start, every period P (P near 300 µs to match the soak).
  - `skip-inference-after N`: after N updates, keep starting the core but run no inference (scenario b).
  - `resume-after M`: run inference again M updates after the timeout edge (scenario b2).
  - `gap-then-inference D`: stop starting the core for D, run one inference, resume (scenario c).
- **`wd_observer`**, derived from `watchdog_trip.c`. It polls `0x60040854`, `0x60040800` and `0x60040844` as fast as it can and logs one row per change with `rdtime` ticks and `poll_gap_max_ns`. Pin it to a different core than the control tool (`taskset`), as `docs/watchdog_trip_runbook_2026-07-01.md` suggests.

Capture methods available in the repository: register polling (above) and the tool's own log. A logic analyzer or on-chip probe: no pin map, probe configuration or debug core was found in the files I searched (`README.md`, `docs/`, `firmware/README.md`, `firmware/linux/README.md`). If Jason wants a hardware cross-check, he must name the pins. The observer resolution is a few microseconds (a pulse-plus-read measured 4 µs median, `docs/fabric_latency_sim_2026-07-01.md`). Pass bands below allow for it.

## Preconditions

1. Board powered; the 2 ms watchdog image resident. Check `csr_version` at `0x60040804` reads `0x00010000`.
2. Read `0x60040854` once. Expect `timeout = 1` if no inference has run since boot (runbook sanity check).
3. Both new tools built, their SHA-256 recorded, and a dry run with `normal` mode showing zero timeouts over 60 s (the soak had 0 trips in a 12 s probe at this rate).
4. Limits: set `out_min` and `out_max` (`0x60040018`, `0x6004001C`). The tools default to ±1.0. If any load is attached to the output, Jason sets narrower limits first, for example ±0.5. The expected values in this plan reach about 0.4 at most (PID 0.16, integrator up to 0.08, AI up to 0.08, with Kp = 0.8 and error 0.20).
5. Inner clamp `0x60040020` set to 0.045 by the tool. The AI term stays within 0.09.
6. No other process touches `0x60040000`. Stop the soak daemon and any dashboard backend.

## Safety and abort

- Abort at any time with SIGTERM or SIGINT to the control tool. Registers keep their last values after the process exits.
- Then run the zeroing sequence: write `out_min = 0` and `out_max = 0`, then one write of 1 to `acc_start`. By code reading, this clamps the integrator and the output to 0 (`hls/src/nv_pid.hpp` lines 41-42 and 63-64). Confirm on the first dry run by reading `0x60040844`.
- A stopped process (scenario a): send SIGCONT before SIGTERM, or send SIGKILL, then run the zeroing sequence.
- If the board hangs or the readback is not 0 after the zeroing sequence, power-cycle the board.
- Do not write registers during an observer run except through the control tool.

## Scenario (a): stop the control process, fabric keeps running

Steps:

1. Start `wd_observer`. Start `wd_fallback_test normal` and let it run 5 s.
2. Send SIGSTOP to the control process. Wait 1 s. Send SIGCONT.
3. Run 10 repetitions, 5 s apart.

Capture: timeout bit and trip count, `axi_write_count`, `post_clamp_out`, the control tool's last row before SIGSTOP and first row after SIGCONT.

Expected (prediction 1, 2): bit 0 rises 2.0 ms after the last inference completion; trip count rises by 1; `axi_write_count` and `post_clamp_out` stay frozen during the pause. After SIGCONT the tool's first inference clears the timeout before the first start, so the core likely sees no edge and no cooldown runs.

Pass criteria:

- A1: bit 0 rises 2.000 ms ± 0.050 ms after the last heartbeat clear (1.95 to 2.05 ms; measured range 1.978 to 2.032 ms). Observer rows with `poll_gap_max_ns` above 50 µs are excluded and counted.
- A2: trip count rises by exactly 1 per pause.
- A3: during the pause `axi_write_count` does not change. If it changes, something else starts the core. Stop and investigate.
- A4 (requirement check, no numeric limit recorded): the actuator register holds its last value for the whole pause. The repository records no maximum allowed hold time. Jason sets one. Until then A4 is an observation, and the plan reports the longest hold seen.

Fallback latency for (a): not defined in the current design, because nothing computes a PID-only value without a software start. Report it as "no fallback value until restart".

## Scenario (b): suppress inference completion

Steps:

1. Start `wd_observer`. Start `wd_fallback_test` in `normal` mode for 1 s, so the AI term has ramped and tracks the triangle.
2. **b1**: switch to `skip-inference-after`, keeping starts every P. Run for 2000 updates (about 0.6 s at the soak period). Then stop.
3. **b2**: repeat, but use `resume-after 200`: run inference again 200 updates after the timeout edge is seen by the core, while the cooldown is still running.
4. Run 20 repetitions of each, 2 s apart. In 3 of the b2 repetitions, repeat the trip three times in a row without a long pause (checks prediction 4).

Capture: observer rows for bit 0, trip count, `axi_write_count`, `post_clamp_out`; tool rows per update; the update index of the first start that the core sees with bit 0 high.

Detection of the fallback in the data: the fallback update is the first update after the timeout edge where the actuator delta is 0 (within 2^-16) while the logged `u_ai` still moves by 0.0005. Recovery is the first later update where the actuator delta is not 0.

Pass criteria:

- B1: timeout assertion as A1.
- B2 (fallback latency, deadline miss to first PID-only value): at most 0.5 ms, equal to one soak p99 period (472 µs) plus the 48 ns core latency. Measure from the observer's bit-0 rising time to the tool timestamp of the first flat actuator row. Report the 2.0 ms trip time as well, so the end-to-end figure (last heartbeat to first PID-only value) is at most 2.5 ms.
- B3: at the fallback update, the actuator step is at most 1e-3 (the tolerance in the existing bumpless test, `hls/tb/tb_bumpless.cpp` lines 280-283).
- B4 (sustained suppression, b1): from the fallback update to the end, the actuator stays flat. No update shows the AI term moving. This is the no-chatter check.
- B5 (cooldown, b2): the number of flat updates from the first PID-only update to recovery is 1000, and the AI term returns on update 1001. Cross-check with `axi_write_count` ÷ 3. If the timeout bit is still high at update 1001, the core stays PID-only and the criterion does not apply.
- B6 (recovery time): at the loop period P, recovery takes about 1000 × P (0.30 s at the soak rate). Report the measured seconds next to the count.
- B7 (recovery step): the actuator change at the recovery update is at most `MAX_SLEW_PER_CYCLE` = 0.001. Prediction 4 says this may fail. Report the measured step either way.
- B8 (bounds): the AI term never exceeds 0.09 in magnitude and the actuator stays within `out_min` and `out_max` in every row.

## Scenario (c): timeout ends before the next software start

Steps:

1. Start `wd_observer`. Start `wd_fallback_test normal` for 1 s.
2. **c1**: run `gap-then-inference` with D = 2.5 ms. The tool stops starting the core after an inference completion at time T. The timeout rises at T + 2.0 ms. At T + 2.5 ms the tool runs one inference, whose completion clears the timeout about 32 µs later (V250 inference time, `docs/mss_paced_loop_measured_2026-07-02.md`). The tool then resumes starts. The timeout is high for about 0.5 ms and low again before the next start.
3. **c0 (control)**: the same, but the tool writes one start at T + 2.2 ms, while bit 0 is high. This case is known to show the rising edge to the core.
4. Run 20 repetitions of each, 2 s apart. Log busy-wait overruns: discard a repetition in which the observer shows a different high time than D − 2.0 ms ± 0.1 ms.

Capture: the same rows as (b). The observer must show the high interval of bit 0 and the trip count.

Expected (prediction 2): in c1 the trip count rises by 1, the core sees no rising edge, and the actuator keeps tracking the AI term. In c0 the core falls back and the cooldown runs.

Pass criteria:

- C1: the high time of bit 0 is D − 2.0 ms ± 0.1 ms, i.e. 0.5 ms ± 0.1 ms. Otherwise the repetition is invalid.
- C2: trip count rises by exactly 1 in each valid repetition.
- C3 (the requirement under test): after a trip, the controller completes 1000 PID-only updates even though the timeout was low at every start (c1). The prediction is that c1 fails C3. A failure is the finding, not a test error. The fix direction is Jason's decision. One option is a sticky hardware bit set by the timeout edge and cleared only when the core consumes it.
- C4: in c0, criteria B2 to B5 hold, with latency measured from the first start that sees bit 0 high.

## Data to save

For every run, in one directory named for the date and scenario:

1. Raw observer log (all rows) and the control tool log (all rows).
2. The exact command lines, including `taskset` masks and `P`, `D`, `N`, `M`.
3. The SHA-256 of both tool binaries and the repository commit they were built from.
4. `csr_version`, the watchdog register at start, the kernel version, and the identifier of the programmed image.
5. The values of `WATCHDOG_TIMEOUT_CYCLES`, `WATCHDOG_COOLDOWN_CYCLES` and `MAX_SLEW_PER_CYCLE` from `rta_config.hpp` at the build commit.
6. Event table: for each repetition, bit-0 rise time, first core-visible edge update index, fallback latency, number of PID-only updates, recovery update index and step, and a pass or fail per criterion.
7. The count of rejected repetitions and the reason for each.
8. Room temperature and the load connected to the output, if any.

## Decisions for Jason

- Maximum allowed hold time for a stopped control process (criterion A4).
- Output limits for any attached load.
- Whether to add a logic analyzer cross-check, and which pins.
- Whether a failed C3 should lead to a hardware change (sticky trip bit) or a software rule.
