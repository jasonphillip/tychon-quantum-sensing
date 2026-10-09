# Watchdog trip-time measurement — runbook (Phase C; executes when the kit is plugged in)

**Goal:** turn "the watchdog trips at 2 ms" from a design value **[DESIGN]** into a
measured on-silicon number **[HW]** — the highest-leverage single measurement for
the RTA story (INVENTORY.md §3.1; fix-list row `EV-WDT-TRIP`).

**Method (self-contained, no cross-process clock sync):**
`firmware/linux/watchdog_trip.c` tight-polls the M1 watchdog CSR
(`0x60040854`: bit0 = timeout LIVE, bits[31:1] = trip count) and timestamps
both edges of bit0 — the `1→0` edge is the V250-completion heartbeat clearing
the watchdog (t_clear), the `0→1` edge is the trip (t_trip). One measurement
per stimulus cycle; sub-µs poll resolution against a 2 ms target (≈0.05%).
The tool performs **no register writes** and touches only the `0x60040000`
slot-3 page.

## Preconditions

1. **Kit plugged in + powered**, reachable via `ssh icicle`.
2. **The 2 ms image (r13_s32) resident.** It was PROGRAM-PASSED 2026-06-21
   (`libero/reports/2026-06-21-watchdog-2ms/program_2ms.log`; job digest in
   `polarfire_hybrid_control_two_slot_2ms_job.digest`). If the kit has been
   reprogrammed since: re-program via
   `libero/reports/2026-06-21-watchdog-2ms/program_job_2ms.tcl`, then
   **cold power-cycle** (V250 requires POR after fabric programming).
3. Sanity: `csr_version` at `0x60040804` reads `0x00010000`; watchdog raw at
   `0x60040854` reads `timeout=1` when no inference has run since boot.

## Steps

1. **Build on bee** (cross-compile; PATH gotcha per `firmware/linux/Makefile` header):
   ```
   ssh bee
   cd ~/dev/projects/polarfire-hybrid-control/firmware/linux
   SHLS=/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS
   export PATH="$SHLS/swtools/binutils/riscv-gnu-toolchain/bin:$SHLS/dependencies/lib/cygwin:$PATH"
   make CROSS=riscv64-unknown-linux-gnu- watchdog_trip
   scp watchdog_trip root@icicle:/root/bringup/
   ```
2. **Shell A (kit): start the observer** —
   `/root/bringup/watchdog_trip 100 180 | tee /tmp/watchdog_trip_$(date +%Y%m%d).csv`
3. **Shell B (kit): fire one V250 inference every ~100 ms** so the watchdog
   alternates cleared→tripped (each cycle yields one measurement):
   ```
   while true; do /root/bringup/v250_pid_loop --rows 1 <model/args>; sleep 0.1; done
   ```
   *Verify the exact one-shot invocation at execution* — see `v250_pid_loop.c`
   usage and the finite-smoke evidence
   (`libero/reports/2026-06-21-v250-pid-loop/v250_pid_loop_odmr_rows_smoke.log`).
   Any command that produces a single V250 completion works (a `vnnx_smoke`
   run also clears the watchdog, at the cost of process-startup spacing).
4. Collect ≥100 events; the tool prints per-event CSV
   (`event,trip_ns,trip_ticks,trip_count_delta,poll_gap_max_ns`) + min/median/
   p95/p99/max. `trip_count_delta` must be 1 for every event (validates one
   real trip per pair); `poll_gap_max_ns` records worst-case poll jitter
   (preemption) — events whose gap approaches the trip time are suspect.

## Expected + acceptance

- Expected: **2.000 ms** (250,000 cycles @ 125 MHz), spread ≈ poll gap + 1 µs
  rdtime tick. Median within a few µs of 2.000 ms → PASS.
- If the median is ≈2.000 ms but individual maxima are inflated with matching
  `poll_gap_max_ns`, attribute to Linux preemption of the poll loop, not the
  fabric (say so in the doc; optionally re-run pinned via `taskset`/`chrt`).

## Deliverables

- `libero/reports/<date>-watchdog-trip/` — raw CSV + tool stdout + the exact
  stimulus command used.
- `docs/watchdog_trip_measured_<date>.md` — method (both-edges polling),
  distribution table, expected-vs-measured, honest caveats (poll jitter,
  stimulus cadence), and the tag upgrade: watchdog trip-time [DESIGN] → **[HW]**.
- Update: README safety section, `docs/skeptic_qa_honest_claims.md` (Q on
  watchdog), INVENTORY addendum, fix-list row `EV-WDT-TRIP` → closed.
