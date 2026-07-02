# MSS-paced closed loop — sustained rate + laptop-disconnected, measured on silicon, 2026-07-02

**Result: the on-kit `v250_pid_loop` daemon runs the V250→PID closed loop entirely on the
Icicle Kit's RISC-V Linux (MSS), sustaining ~3.3 kHz standalone. It was proven to keep
running with the host laptop disconnected (≥10 min, host issued no commands), with continuity
established from two independent monotonic counters and a persistent on-kit heartbeat log.
The same daemon configuration was then left running as the item-3 daytime soak.
Tag: [HW] (kit-resident MSS-paced loop; still not a fabric-resident loop, and the input is a
replayed vector, not a live sensor).**

Raw evidence: `libero/reports/2026-07-02-mss-paced/` (verbatim tool logs + run notes with
exact commands). Tools: `firmware/linux/v250_pid_loop.c` (daemon), `mss_paced_heartbeat.sh`
(persistent soak monitor), `mss_paced_soak_summary.sh` (harvest summarizer).

## What "MSS-paced" means here (and what it is not)

- **Is:** the kit's RISC-V Linux daemon drives every loop step on-kit — read a spectrum/anchor
  row (replayed CSV, stand-in for the sensor), run V250 inference, dequantize, write `u_ai`,
  pulse the SmartHLS PID `acc_start`, read the latched M1 actuator + watchdog — with **no host
  in the loop.** Proven by running with the laptop disconnected.
- **Is not:** a *fabric-resident* closed loop (the loop logic is MSS software, not fabric
  hardware — that is the first TRL-4 milestone), and it is **not** sensor-in-the-loop (the
  error/spectrum input is a replayed vector `odmr_v250_rows.csv`, not a live NV sensor).

This is a genuine step past the earlier *host-paced* demo (where the SSH host/dashboard drove
each step over the link): the host is now out of the loop, but the two standing boundaries
(fabric-resident, real-sensor) are unchanged.

## Method — distinct-iteration counters, not wall-clock inference

Every iteration advances two independent monotonic counters that are recorded, not inferred:
- software **`row`** (emitted-iteration counter in the daemon's live-state JSON), and
- fabric **`axi_write_count`** CSR `0x60040800` (**+3 per iteration**).

`Δaxi_write_count == 3 × Δrow` held exactly on every run, so a rate is `Δrow / Δt` from the
counters themselves. The daemon also stamps `t_ns` (CLOCK_MONOTONIC_RAW elapsed) into the JSON;
a persistent on-kit heartbeat samples the JSON every 30 s and appends a wall-clock-stamped line
to eMMC `heartbeat.log` — the evidence of record, which survives host disconnect, operator
session exit, and reboot.

Engineering note (config selection): the daemon's live-state JSON is kept on **tmpfs**, not
eMMC. On eMMC the per-iteration JSON rewrite (~1.7 ms) throttled the loop to ~536 Hz, whose
~1.87 ms period straddles the 2 ms fabric watchdog and produced ~165 trips in 12 s. On tmpfs
the loop runs ~3.3 kHz (~299 µs period, ~6.7× under the 2 ms deadline) with zero trips. Only
the 30 s heartbeat touches eMMC, so soak-long eMMC wear is negligible.

## Measured numbers

| quantity | value | basis |
|---|---|---|
| free-running ceiling (no logging) | **~9.07 kHz** (period median 107 µs) | finite 10 000-row burst |
| **sustained MSS-paced rate (soak config)** | **~3.3 kHz** | daemon, tmpfs live-state, distinct counters |
| per-iteration period (soak-config proxy) | median 328 µs, p95 394 µs, p99 472 µs, max 3.21 ms | 60 s daemon burst |
| V250 inference time | 32 µs median (31–33 µs) | per-row `v250_ns` |
| watchdog trips (soak config, 12 s probe) | 0 | trip_count stable |
| counter agreement | `Δaxi = 3 × Δrow` exact | every run |

### Sustained rate over ≥10 min + laptop-disconnected (item 2a/2b)

One continuous daemon (started 2026-07-02T11:14:16Z, pid 516) served both. Over a 14.6-min
window (`heartbeat.log`, 30 samples, 30 s cadence):

- **Sustained rate 3329.8 Hz**, per-sample 3321.4–3338.1 Hz (**±0.5 %**) — steady, no droop.
- **2 911 944 steps**, `row` strictly monotonic; `Δaxi_write_count = 8 735 832 = 3 × steps`
  **exactly** (the "not wall-clock inference" guarantee).
- **Laptop-disconnected:** the host (spark1) issued zero ssh/scp to the kit for 13.4 min
  (11:15:28Z→11:28:53Z); the loop advanced ~2.75 M iterations standalone and the on-kit
  heartbeat logged ~26 autonomous, wall-clock-stamped samples to eMMC in that window; both
  daemon and heartbeat were still alive on reconnect. Continuity proven from monotonic
  counters + persistent on-kit telemetry.
- **1 transient watchdog trip** in 2.91 M steps (recovered, `bit0`→0, row kept advancing);
  MemFree flat (Δ 2372 kB); no daemon exit. Summarizer VERDICT=PASS.

### Daytime soak — 8 h, PASS (item 3; harvested 2026-07-02T19:15Z)

The identical daemon (same pid 516, never restarted) ran on as the daytime soak against
criteria **pre-registered in the log header before the run** (`soak_header.txt`). Harvest at
8.01 h (957 heartbeat samples, 30 s cadence, zero missed):

| pre-registered criterion | result |
|---|---|
| duration ≥ 8 h | **8.01 h** (28,829 s) |
| no permanent stall; row strictly increasing | **95,681,736 steps**, monotonic, 957/957 samples alive |
| sustained rate within ±10 % of ~3345 Hz | **3318.9 Hz** overall (−0.8 %); per-sample 3295.9–3338.1 |
| watchdog trips transient-only | **5 trips / 95.7 M steps (0.05 ppm)**, every one recovered (`bit0`→0, row advancing) |
| memory stable | MemFree Δ 12.3 MB over 8 h, non-monotonic — no leak |
| **VERDICT** | **PASS** |

Counter integrity end-to-end: `Δaxi_write_count = 287,045,208 = 3 × steps` **exactly** over
the full 8 h. Claim this licenses:

> "Kit-resident MSS-paced V250→PID loop soak: **95.7 M steps over 8.01 h at 3319 Hz sustained,
> zero stalls, 5 transient >2 ms scheduling stalls all caught and recovered by the 2 ms fabric
> watchdog, memory flat**. **[HW]**"

Evidence: `libero/reports/2026-07-02-mss-paced/{heartbeat_8h.log, soak_summary_8h.txt,
heartbeat.log (item-2 30-sample window), soak_summary_at_item2.txt, run_notes.md,
burst_freerun_excerpt.txt, daemon_burst_excerpt.txt, soak_header.txt}`.

## Honest caveats

- **Not fabric-resident, not real-sensor** — see boundary above; both remain NOT-YET-SHOWN.
- **Period tail:** the loop period has a userspace-scheduling tail (p99 ≈ 472 µs, rare >2 ms
  stalls). Each >2 ms stall trips the fabric watchdog and is recovered on the next cycle
  (row keeps advancing; `bit0` returns to 0) — the watchdog doing its designed job. These are
  transient, not loop failures.
- **Rate is the daemon-config rate**, deliberately not the free-running ceiling: the tmpfs
  live-state write and per-step CSR I/O set the cadence. The ~9 kHz ceiling is a capability
  bound, the ~3.3 kHz is what is sustained (and soaked).
- Environment: benchtop, room temperature, Linux userspace — same posture as all other on-kit
  numbers in this repo.

## Claim language this licenses

> "Kit-resident **MSS-paced V250→PID closed loop, ~3.3 kHz sustained on silicon**, proven to
> run standalone with the host laptop disconnected (≥10 min, monotonic counters + on-kit
> telemetry). **Stimulus still injected (replayed vector), not fabric-resident.** **[HW]**"

Downstream updates made with this measurement: README, fix-list row `EV-MSS-PACED`, and the
TVW INVENTORY addendum + daily log. The external contact **deck** item-2 template (slide 4 MSS-paced
bullet + slide 5 NYS #2 softening, boundary box + cover subtitle kept — still not
fabric-resident) is **handed to a separate session** and is NOT applied here.
