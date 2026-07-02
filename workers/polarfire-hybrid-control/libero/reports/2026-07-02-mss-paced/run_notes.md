# MSS-paced loop — sustained-rate + laptop-disconnected measurement — run notes (2026-07-02)

Item 2 of the external contact-deck 48h list: the `v250_pid_loop --daemon` on-kit closed loop
already IS the MSS-paced loop; this session measured (a) its sustained iterations/sec and
(b) laptop-disconnected continuity, then left the same daemon running as the item-3 soak.
Mirrors the item-1 evidence pattern (`../2026-07-01-watchdog-trip/run_notes.md`).

## Environment

- Kit: `mpfs-icicle-kit`, kernel `6.18.17-linux4microchip-2026.04.1`, fresh boot
  2026-07-02 (~10:43 UTC), reached via `ssh icicle` (192.168.x.x / mDNS).
- Resident image: the 2 ms watchdog two-slot idfix2 GOLDEN build (r13_s32 lineage),
  persistent-programmed 2026-06-21 — confirmed `csr_version=0x00010000`. **No reprogramming;
  no bitstream programming of any kind this session.**
- Tool: `firmware/linux/v250_pid_loop` (kit copy dated 2026-06-21, daemon build), unchanged.
  Loop maps only the idfix2 SLOT3 page `0x60040000`; writes M0 gains/limits/inner-clamp/start
  + M1 error/u_ai; reads actuator/watchdog from M1; never touches `0x60001000`. Inner-clamp
  `0x60040020=0.045` is set by the tool on init (the documented setup gotcha — handled
  internally, verified by a live non-zero clamped actuator).
- Storage: `/root/bringup` on eMMC (`/dev/mmcblk0p3` ext4, 56 GB free); `/tmp` is tmpfs (775 MB).

## Step 0 — resident-image confirmation (exact)

    ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 1 0 odmr_v250_rows.csv

→ row 0 `nn_out0=-2.538894653`, `nn_q=-110`, `v250_ns=34000` — **bit-identical** to the
2026-07-01 item-1 stimulus one-shot and the 2026-06-21 finite smoke. Watchdog `0x5→0x4`
(the single V250 completion cleared bit0; trip_count stable). `csr_version=0x00010000`.

## Distinct-iteration counters (the "not wall-clock inference" basis)

Every loop iteration advances two independent monotonic counters:
- **software `row`** (emitted-iteration counter, in the live-state JSON), and
- **fabric `axi_write_count` CSR** `0x60040800` (+3 per iteration — 3 AXI writes: error, u_ai,
  acc_start pulse).
Across every run below, `Δaxi_write_count == 3 × Δrow` **exactly**, so the rate is proven by
hardware+software distinct-iteration counters, not by wall-clock division.

## Measurement A — free-running ceiling + per-iteration period distribution

Finite run (no daemon, no per-iteration JSON), stdout→eMMC file:

    ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 10000 2 odmr_v250_rows.csv > burst_freerun.log

- rc=0, 10000 rows in 1.9946 s wall; rows 0→9999 t_ns span 1.101991 s.
- **Ceiling rate ≈ 9.07 kHz** (mean period 110.2 µs; median-based 9.35 kHz).
- Per-iteration period (t_ns deltas, N=9999): min 104 / **median 107** / p90 113 / p95 139 /
  p99 163 / max 324 µs. Tail (≤324 µs, ~3× median) = userspace scheduling jitter; V250
  inference itself is a tight 31–33 µs (median 32 µs, max 165 µs outlier).
- `axi_write_count` 0x87→0x75b4 (Δ=29997=3×9999). Watchdog held cleared: single value 0x6
  (bit0=0, trip_count=3), `watchdog_timeout=0` every row.

## Measurement B — daemon config selection (why tmpfs live-state)

The daemon rewrites its live-state JSON every iteration. Two 12 s daemon probes,
stdout→/dev/null, free-running:

| `--state` location | sustained rate | watchdog trips in window |
|---|---|---|
| eMMC `/root/bringup/...json` | **~536 Hz** | **+165 trips / 12 s** (trip_count 10→175) |
| tmpfs `/tmp/v250_state.json` | **~3345 Hz** | **0 trips** (trip_count 176→176 stable) |

The eMMC JSON write (fopen/fprintf/rename ≈ 1.7 ms synchronous per iteration) throttles the
loop to ~536 Hz, whose ~1.87 ms period straddles the 2 ms fabric watchdog → frequent trips.
tmpfs live-state runs at ~3.3 kHz (period ~299 µs, ~6.7× under the 2 ms deadline) with zero
trips. **Chosen soak config: live-state JSON on tmpfs; persistent evidence (30 s heartbeat)
on eMMC `/root/bringup`.** This is also the tool's own default (`/tmp`). Both probes: Δaxi =
3 × Δrow exactly.

## Measurement C — soak-config per-iteration period distribution

60 s daemon burst, tmpfs live-state, stdout→eMMC file (a conservative proxy — the soak's
stdout→/dev/null runs marginally faster with fewer tail stalls):

- 181638 rows / 61.164 s span = **2969.7 Hz**.
- Period (t_ns deltas, N≈181637): min 319 / **median 328** / p90 368 / p95 394 / p99 472 /
  p99.9 626 µs / max 3213 µs; mean 336.7 µs.
- **6 periods > 2 ms** (max 3.213 ms) → exactly **6 watchdog trips** (trip_count 177→183),
  and **`rows_with_bit0_set = 0`**: every emitted row had the watchdog already cleared, i.e.
  the loop recovered from each trip on the next cycle. This is the "M trips all recovered
  bumpless" behavior — >2 ms userspace scheduling stalls caught by the fabric watchdog and
  recovered. The soak config (stdout→/dev/null) had 0 trips in the 12 s tmpfs probe.

## Item 2a — sustained rate over ≥10 min  &  Item 2b — laptop-disconnected

Single continuous daemon (= the item-3 soak), started detached (proven to survive session
exit: `setsid nohup … </dev/null & disown`):

    cd /root/bringup
    setsid nohup ./v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 10000 2 odmr_v250_rows.csv \
      0.001 0.015625 0 --daemon --state /tmp/v250_state.json \
      --pid-file /root/bringup/mss_paced/loop.pid </dev/null >/dev/null 2>.../loop.err & disown
    # + persistent on-kit heartbeat logger (30 s cadence -> eMMC), also detached:
    setsid nohup sh -c 'echo $$ >.../hb.pid; exec sh mss_paced_heartbeat.sh /tmp/v250_state.json \
      /root/bringup/mss_paced/heartbeat.log /root/bringup/mss_paced/loop.pid 30' </dev/null & disown

- Soak/daemon start (kit UTC): **2026-07-02T11:14:16Z**, daemon pid 516, heartbeat pid 527.
- First heartbeat sample 11:14:34Z: row=57386, axi=0xdf1eb, wd=0x170, daemon_t_ns=17.24e9,
  MemFree=1446 MB.
- **Disconnected window:** the host (spark1) issued NO ssh/scp to the kit from **11:15:28Z**
  to **11:28:53Z** (**13.4 min**, spark1 clock — no ssh command was run against the kit in
  that interval). During the window the daemon ran standalone and the on-kit heartbeat logged
  autonomously to eMMC `heartbeat.log` (~26 samples, 30 s cadence, wall-clock stamped),
  independent of any SSH session. On reconnect both processes were still alive (daemon pid
  516 etime 14:37, heartbeat pid 527).

### RESULTS (from `heartbeat.log` / `soak_summary_at_item2.txt`)

Summarizer over the item-2 window (`mss_paced_soak_summary.sh heartbeat.log`):

    samples=30 na_samples=0
    window: first=2026-07-02T11:14:34Z last=2026-07-02T11:29:08Z
    daemon_uptime=874.5 s (14.6 min)                       # >= 10 min
    row: first=57386 last=2969330 steps=2911944 monotonic=yes
    axi_write_count: delta=8735832 (3x_steps=8735832 agree=yes)   # HW == SW counter, exact
    sustained_rate_hz: overall=3329.8 per_sample min=3321.4 mean=3329.8 max=3338.1
    watchdog: trip_first=184 trip_last=185 trip_delta=1 last_bit0=0
    MemFree_kb: min=1446248 max=1448620 delta=2372
    loop_pid_alive: dead_samples=0 last_alive=1 last_running=true
    VERDICT=PASS

- **Item 2a (sustained rate ≥10 min):** **3329.8 Hz** overall, **±0.5 %** across all 30
  samples (per-sample 3321.4–3338.1 Hz) over 874.5 s (14.6 min). Basis = distinct monotonic
  counters: `Δaxi_write_count = 8 735 832 = 3 × 2 911 944 steps` **exactly** — not wall-clock
  division.
- **Item 2b (laptop-disconnected):** across the 13.4-min host-silent window the loop advanced
  ~2.75 M iterations and the on-kit heartbeat logged ~26 autonomous, wall-clock-stamped samples
  to eMMC; both processes were still alive on reconnect; counters monotonic. Standalone
  continuity proven from on-kit telemetry (`/root/bringup/mss_paced/heartbeat.log`, eMMC).
- **Watchdog:** 1 transient trip in 2.91 M steps (trip_count 184→185, `bit0=0` after, row kept
  advancing) — one >2 ms scheduling stall caught + recovered by the fabric watchdog. 0.34 ppm.
- **Memory:** MemFree flat (Δ 2372 kB over 14.6 min, non-monotonic) — no leak.

## Tag

Kit-resident MSS-paced V250→PID loop, sustained ~3.3 kHz standalone (laptop-disconnected):
**[HW]**. Boundary unchanged: the loop is MSS software (not fabric-resident) and the
error/spectrum input is a replayed vector (not a live sensor).
