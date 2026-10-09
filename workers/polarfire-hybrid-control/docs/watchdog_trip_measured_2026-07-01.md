# Watchdog trip-time — measured on silicon, 2026-07-01

**Result: the fabric watchdog's clear→trip time on the resident two-slot 2 ms
image is median 2.000 ms (N=120 trips; min 1.978, p95 2.003, p99 2.026,
max 2.032 ms) — matching the 250,000-cycle @ 125 MHz design value at the
measurement's 1 µs resolution. Tag upgrade: [DESIGN] → [HW].**

Raw evidence: `libero/reports/2026-07-01-watchdog-trip/` (verbatim tool log +
run notes with exact commands). Method + tool: `firmware/linux/watchdog_trip.c`
(commit `389699f`), runbook `docs/watchdog_trip_runbook_2026-07-01.md`.

## Method (why this is a self-contained measurement)

A single userspace process tight-polls the M1 watchdog CSR (`0x60040854`:
bit0 = timeout LIVE, bits[31:1] = trip count) over `/dev/mem` and timestamps
**both** edges of bit0 with `rdtime` (1 MHz timebase):

- `1→0` — a V250 completion pulse cleared the watchdog (t_clear),
- `0→1` — the fabric counter reached timeout (t_trip),
- trip_time = t_trip − t_clear.

Both edges are seen by the same poll loop, so there is no cross-process or
cross-host clock sync in the measurement. The tool performs **no register
writes**. Stimulus was a separate process firing one V250 inference
(`v250_pid_loop … 1 0 odmr_v250_rows.csv`) every ~100 ms — each cycle
produces exactly one (clear, trip) pair. `trip_count_delta=1` on all 120
events confirms each measured pair corresponds to exactly one hardware trip.

## Distribution (N=120)

| statistic | value |
|---|---|
| min | 1.978 ms |
| median | **2.000 ms** |
| p95 | 2.003 ms |
| p99 | 2.026 ms |
| max | 2.032 ms |
| expected (design) | 2.000 ms = 250,000 cycles @ 125 MHz |

## Honest caveats

- **Resolution / jitter:** poll period is sub-µs but Linux preemption produced
  per-event `poll_gap_max_ns` of 4–39 µs; the distribution tails (−22/+32 µs)
  match those gaps in magnitude, so they are attributable to the *observer*,
  not the fabric. No `taskset`/`chrt` pinning was needed for a clean median.
- **What this measures:** the fabric watchdog timeout interval — heartbeat
  clear to trip assertion as visible in the CSR. It does not measure the
  downstream bumpless-transfer settling (that behavior was demonstrated
  separately in the 2026-06-21 post-program checks).
- **Stimulus cadence** (~100 ms + process startup) is far above the timeout,
  so every cycle yields one clean trip; no back-to-back-trip regime was
  exercised.
- Environment: benchtop, room temperature, Linux userspace observer — same
  posture as all other on-kit numbers in this repo.

## Claim language this licenses

> "Fabric watchdog trip-time **measured on silicon: median 2.000 ms over 120
> trips (min 1.978 / max 2.032 ms, tails bounded by observer poll jitter)**,
> matching the 250,000-cycle @ 125 MHz design value. **[HW]**"

Downstream updates made with this measurement: README safety/measured-bounds
lines, `docs/skeptic_qa_honest_claims.md` (§6, §8, summary, dashboard-fix
list), fix-list row `EV-WDT-TRIP` → closed, TVW INVENTORY addendum, external contact
deck slides 4/5/6 + NYS + TRL-4 row per the NEXT_48H_PLAN templates.
