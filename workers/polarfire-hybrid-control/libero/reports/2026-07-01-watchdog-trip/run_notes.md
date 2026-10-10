# Watchdog clear→trip measurement — run notes (2026-07-01 evening)

Executed per `docs/watchdog_trip_runbook_2026-07-01.md` after the re-plug
inventory (`docs/kit_replug_inventory_2026-07-01.md`) verified all
preconditions. Raw tool output: `watchdog_trip_run1.log` (this directory,
fetched verbatim from the kit at `/root/bringup/wdt-2026-07-01/`).

## Environment

- Kit: `mpfs-icicle-kit`, kernel `6.18.17-linux4microchip-2026.04.1`, fresh
  boot 2026-07-01 ~19:10 ET, reached via `ssh icicle` (192.168.x.x).
- Resident image: the 2 ms watchdog two-slot build (r13_s32 lineage),
  persistent-programmed 2026-06-21 — confirmed by `csr_version=0x00010000`
  and fresh-boot watchdog signature `0x00000003` (timeout=1, trip_count=1).
  No reprogramming performed.
- Tool: `firmware/linux/watchdog_trip.c` at commit `389699f` (repo HEAD
  `84b3f6c` at run time), cross-compiled on bee. Deviation from the runbook's
  `make` line: MSYS2 non-interactive ssh has no `make`, so the Makefile rule
  was invoked directly — identical flags:
  `riscv64-unknown-linux-gnu-gcc -O2 -Wall -static watchdog_trip.c -o watchdog_trip -lm`
  (SmartHLS toolchain + cygwin PATH exactly as the Makefile header specifies).
  Output: static RISC-V ELF, 453,552 bytes; deployed to kit via ws1.

## Pre-checks (all passed)

1. No-stimulus observer smoke: `watchdog_trip 1 3` → correct header, correct
   `csr_version`, clean wall-timeout exit 3, zero events (nothing feeding
   the heartbeat).
2. V250 probe / stimulus one-shot:
   `./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 1 0 odmr_v250_rows.csv`
   → row 0 `nn_out0=-2.538894653`, `v250_ns=33000` — bit-identical to the
   2026-06-21 finite smoke (`../2026-06-21-v250-pid-loop/`); watchdog
   observed cleared during the run (`0x00000002`, timeout=0) and re-tripped
   after (`0x00000005`, trip_count 1→2).

## Measurement commands (exact)

Shell A (observer, started first, background):

```
/root/bringup/watchdog_trip 120 300 > /root/bringup/wdt-2026-07-01/watchdog_trip_run1.log 2>&1 &
```

Shell B (stimulus, one V250 heartbeat per ~100 ms + process-startup spacing):

```
cd /root/bringup && for i in $(seq 1 140); do
  ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 1 0 odmr_v250_rows.csv > /dev/null 2>&1
  sleep 0.1
done
```

Observer reached 120/120 events and exited 0 before the stimulus loop
finished. No `taskset`/`chrt` pinning was used (not needed — see spread).

## Result

```
collected=120/120        (trip_count_delta = 1 on every event — 120 real, distinct trips)
trip_ns  min=1978000  median=2000000  p95=2003000  p99=2026000  max=2032000
expected: 250000 cycles @ 125 MHz = 2.000 ms = 2000000 ns
```

**Median 2.000000 ms — equal to the design value at the tool's 1 µs rdtime
resolution.** PASS per the runbook acceptance (median within a few µs).

Spread attribution: per-event `poll_gap_max_ns` ranged 4–39 µs (Linux
preemption of the userspace poll loop); the worst deviations (−22 µs /
+32 µs) are the same order as the recorded poll gaps, so the tails are
measurement jitter, not fabric behavior. Deviations occur in both directions
because a poll gap can straddle either edge (late-observed clear shortens
the measured interval; late-observed trip lengthens it).

## Tag upgrade

Watchdog trip-time 2 ms: **[DESIGN] → [HW]** (fix-list row `EV-WDT-TRIP`).
Write-up: `docs/watchdog_trip_measured_2026-07-01.md`.
