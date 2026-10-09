# Controller update period: what the count-based constants mean in seconds

Date: 2026-10-09. Status: memo with a design option. The decision belongs to Jason.

## Summary

The controller core `nv_pid_top` has no clock input in its C++ source. Each call is one update. Every count-based constant therefore counts updates, not fabric clock cycles.

The comment on `WATCHDOG_COOLDOWN_CYCLES` says "1000 cycles at 125 MHz = 8.0 µs". That holds only if the core runs an update on every fabric clock cycle. No build in this repository does that.

In the 8-hour soak, software on the SoC processor started the core about 3.3 kHz. There, 1000 updates last about 0.30 s, not 8 µs. The same factor applies to the derivative filter and the slew limit.

## Facts checked in the code

All line numbers below were read in this worktree on 2026-10-09.

| Item | Where | What it says |
|---|---|---|
| Cooldown increment | `hls/src/nv_pid.cpp` line 63 | `cooldown_counter++` runs once per call, inside `if (in_cooldown)`. |
| Cooldown start | `hls/src/nv_pid.cpp` lines 52-56 | A rising edge of `ai_watchdog_timeout` seen at a call sets `in_cooldown` and zeroes the counter. |
| Cooldown end | `hls/src/nv_pid.cpp` lines 61-67 | The counter counts up to the limit. The next call clears `in_cooldown`. |
| Cooldown constant | `hls/include/rta_config.hpp` lines 34-35 | `WATCHDOG_COOLDOWN_CYCLES = 1000`, comment "1000 cycles at 125 MHz = 8.0 µs". |
| Slew constant | `hls/include/rta_config.hpp` line 25 | `MAX_SLEW_PER_CYCLE = 0.001`, applied once per call (`hls/src/safety_clamps.cpp` lines 126-136). |
| Derivative filter | `hls/include/rta_config.hpp` lines 73-75, `hls/src/nv_pid.hpp` lines 52-60 | `a = 0.999000999`, `beta = 0.000999001`, applied once per call. No `dt` appears. |
| Integrator | `hls/src/nv_pid.hpp` line 41 | `integral = integral + Ki * error` once per call. No `dt` appears. |
| Fabric clock constant | `hls/include/rta_config.hpp` lines 37-42 | `CLOCK_FREQ_HZ` is documentation only. The file says no source derives counts from it. |

Cooldown length in calls, counted from the code: the call that sees the rising edge is call 1. The controller stays PID-only for calls 1 to 1000. Call 1001 clears `in_cooldown`. AI re-entry then depends only on the timeout wire being low.

The watchdog timeout itself is different. It counts fabric clock cycles in hardware (`libero/hdl/watchdog_timer.v`, parameter `WATCHDOG_TIMEOUT_CYCLES`, 250,000 cycles, lines 24-26 and 41-57). It is a true time: 2.000 ms at 125 MHz. The measured median was 2.000 ms (`docs/watchdog_trip_measured_2026-07-01.md`). The timeout does not depend on how often software starts the core. The cooldown does.

## Semantics per build

### Build 1: software testbench

- Build: `make hls-test-local` (`Makefile` lines 29-36), `g++ -std=c++17` with the checked-in `ap_fixpt` shim.
- One invocation: one C++ call of `nv_pid_top`.
- Invocation rate: none. The testbench has no time base.
- Cooldown: 1000 calls. Time has no meaning here.
- Test evidence: `flush_state` runs 1200 calls to drain the cooldown (`hls/tb/tb_bumpless.cpp` lines 26-39). The chatter test comment converts its toggle period to time with the 125 MHz clock (lines 212-218). That conversion is correct only for a core that runs every cycle.

### Build 2: synthesised core started by the processor

- One invocation: one write of `1` to `acc_start` at `0x60040008` (`docs/two_slot_register_map_2026-06-17.md` line 29, "write 1 = start"). The processor driver `firmware/linux/v250_pid_loop.c` writes `error`, `u_ai`, then `acc_start` once per loop iteration (lines 676-679).
- Core latency: 6 fabric cycles, 48 ns, from start accept to actuator write enable (RTL simulation, `docs/fabric_latency_sim_2026-07-01.md`). The core is idle between starts.
- Gains in the soak: the driver writes Kp = 0.8, Ki = 0, Kd = 0 (`v250_pid_loop.c` lines 597-602). The integrator and the derivative filter did not act in the soak. The cooldown and the slew limit could act.

Recorded invocation rates and the time that 1000 updates take at each:

| Driver and condition | Rate | Source | 1000 updates |
|---|---|---|---|
| `v250_pid_loop` daemon, state file on tmpfs (8-hour soak) | 3318.9 Hz overall; 3295.9 to 3338.1 Hz per sample | `docs/mss_paced_loop_measured_2026-07-02.md` | 0.301 s |
| Same loop, 60 s burst | 2969.7 Hz; median period 328 µs, p99 472 µs, max 3.213 ms | `libero/reports/2026-07-02-mss-paced/run_notes.md`, Measurement C | 0.337 s at the 2969.7 Hz mean |
| Same loop, no state file | about 9.07 kHz ceiling, median period 107 µs | same file, Measurement A | 0.110 s |
| Same loop, state file on flash storage | about 536 Hz | same file, Measurement B | 1.87 s |
| Host-driven replay `tools/rung_g_replay.py` | two starts per sample (lines 212 and 228); inter-sample median 10.122 ms, so about 198 starts/s (my arithmetic) | `docs/remediation_progress_2026-06-21.md` line 122 | about 5.06 s |
| Manual tools `pid_ctl`, `pid_poke`, `pid_latency` | not recorded as a loop rate | I read the three source files | not applicable |

The jitter matters. In the soak, the period had a tail up to 3.2 ms. A cooldown counted in updates therefore varies in seconds with the scheduler.

### Build 3: core that free-runs

- Found: none. I searched `hls/`, `firmware/`, `libero/hdl/` and `tools/` for a start signal tied high, a free-run mode or a streaming driver. The only start path I found is the `acc_start` register. The top function has `#pragma HLS interface control type(axi_target)` (`hls/src/nv_pid.cpp` line 25).
- If a future build starts the core every fabric cycle, the original comments become true: cooldown 8.0 µs, filter time constant 8 µs, slew 125 V/ms. That build would need its own check, because a 1000-cycle cooldown would then be shorter than the 2 ms watchdog timeout by a factor of 250.

## What the other count-based constants mean in seconds

Let Ts be the time between updates. Results for the soak (Ts = 301.3 µs, from 3318.9 Hz):

| Constant | Per update | Meaning in seconds at Ts | Soak value |
|---|---|---|---|
| `WATCHDOG_COOLDOWN_CYCLES` | 1000 updates | 1000 × Ts | 0.301 s |
| Derivative filter time constant | `a / (1 - a)` = 1000 updates with the literals | 1000 × Ts (the rta_config comment lines 55-66 gives 8.0 µs for Ts = 8 ns) | 0.301 s; corner 1/(2π·0.301 s) = 0.53 Hz |
| Derivative gain | `Kd * (e[k] - e[k-1])`, no division by Ts | continuous gain = Kd / Ts | not exercised, Kd = 0 |
| Integral gain | `Ki * e[k]`, no multiplication by Ts | continuous gain = Ki / Ts | not exercised, Ki = 0 |
| `MAX_SLEW_PER_CYCLE` | 0.001 per update | 0.001 / Ts per second | 3.32 per second, against 125,000 per second (125 V/ms) in the comment |

Two notes on the filter. First, with the Q16.16 values quoted in `docs/derivative_filter_design.md` (lines 99-101), `a / (1 - a)` is about 1007 rather than 1000. Second, the design target was Tf = 5 µs. At Ts = 301 µs, Tf is far below the update period. A filter with Tf much smaller than Ts passes the signal nearly unchanged. The design target is only reachable at an update period near 5 µs or less.

## Design option (decision: Jason)

This is a suggested design. I changed no code. Jason decides whether to adopt any part of it.

1. **One explicit period constant.** Add `CONTROL_PERIOD_S` to `rta_config.hpp`, with the build it describes. Add the matching count in fabric cycles, for example `CONTROL_PERIOD_CYCLES`.
2. **State requirements in seconds, convert once.** Write the cooldown as `WATCHDOG_COOLDOWN_S`. Derive the update count with one expression from `CONTROL_PERIOD_S`. The required cooldown in seconds is not recorded in the repository, and the rationale for the value 1000 is not located. Jason sets the number.
3. **Rename counts to say what they count.** `WATCHDOG_COOLDOWN_CYCLES` becomes `WATCHDOG_COOLDOWN_UPDATES`. `MAX_SLEW_PER_CYCLE` becomes `MAX_SLEW_PER_UPDATE`. Keep `WATCHDOG_TIMEOUT_CYCLES` as is, because it does count fabric cycles.
4. **Use `dt` where a constant assumes it.** Compute `a` and `beta` from `Tf` and `CONTROL_PERIOD_S`. Scale `Ki` by Ts and `Kd` by 1/Ts, or document the gains as per-update gains with their continuous equivalents.
5. **Two options for the cooldown, one choice needed.**
   - Option A: count time in the core. A free-running 125 MHz tick counter, started at the timeout edge, measures the cooldown in fabric cycles. The result does not move with software jitter. Cost: one counter and one compare in the core, and a new synthesis run.
   - Option B: keep counting updates, but derive the count from `CONTROL_PERIOD_S`. No hardware change. The cooldown then moves with the scheduler jitter listed above.
   I lean toward Option A for the cooldown, because the soak shows a 7-fold spread between the median and the worst period. That is a recommendation, not a decision.

Changing `a` and `beta` changes the synthesised netlist. `rta_config.hpp` lines 55-66 already records this. Any change to the filter literals needs a new synthesis, timing check and board run.

## Check to run after any change

Run this in the software testbench. It needs no board.

1. Add a testbench-only assumed period `TB_PERIOD_S`. Run the same scenario at 330 Hz, 3.3 kHz and, as a reference, 125 MHz. The scenario gives a rising edge on `ai_watchdog_timeout`, then holds the timeout low.
2. Measure the cooldown in seconds: the number of updates in PID-only mode multiplied by `TB_PERIOD_S`.
3. Measure the filter step response: apply a step to the error with Kp = Ki = 0, find the number of updates to reach 63 % of the final derivative output, and multiply by `TB_PERIOD_S`.
4. Measure the slew time: the time for the AI term to ramp over its full clamp range.

Expected results:

| Quantity | Today's code (predicted from the code, not yet run) | After the change |
|---|---|---|
| Cooldown in updates | 1000 at every rate | scales: 100 at 330 Hz, 1000 at 3.3 kHz, for a 0.30 s cooldown |
| Cooldown in seconds | 3.03 s at 330 Hz; 0.303 s at 3.3 kHz | the same at every rate, within one update period |
| Filter time constant in seconds | 1000 × Ts, so it changes 10-fold | equal to the requested Tf, to within the limit that Tf must exceed Ts |
| Slew time in seconds | changes 10-fold | equal at every rate |

Pass criterion: for every time-based quantity, the two cadences differ by no more than one update period of the slower cadence. For the count-based quantities, the counts differ by the cadence ratio. A run in which the seconds change by the cadence ratio fails.

Run this check also on the board once, with the soak driver at its recorded rate. Measure the cooldown there by counting PID-only updates between the timeout rising edge and the first AI-path output. The cooldown state is not readable from the CSR page today: the cooldown tap at `0x60040858` is tied off and reads 0 (`docs/two_slot_register_map_2026-06-17.md` lines 53-58).
