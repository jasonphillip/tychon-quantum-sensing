# Kit re-plug inventory — 2026-07-01 evening (pre-measurement familiarization)

The Icicle Kit was re-plugged into the Beelink 2026-07-01 ~19:10 ET after being
disconnected since the June sessions. Physical USB ports / Ethernet drop may have
changed. This is the read-only inventory taken **before** any 48-hour-list
measurement work (EV-WDT-TRIP etc.), so the measurement session starts from
verified ground truth instead of June assumptions.

All probes were passive reads. The only state-touching action was one attempted
`pac1934` driver re-bind on the kit (failed identically to the boot-time probe;
no configuration changed). The golden idfix2 / 2 ms resident image was not
touched and needs no reprogramming.

## Verdict in one line

Items 1–3 of the 48-hour list are GO with zero hardware surprises; item 4
(board power) is a **DROP** — the PAC1934 does not answer on any I²C bus.

## Connectivity — matches the 2026-06-21 documented state exactly

| What | Expected (Jun-21 docs) | Found 2026-07-01 | Status |
|---|---|---|---|
| Kit Linux over Ethernet | `ssh icicle` → `mpfs-icicle-kit.local` | resolves; kit up, `eth0 = 192.168.x.x/24` (same DHCP lease as June) | OK |
| FlashPro6 programmer | serial `F31E000A`, VID 1514 PID 200B | present, Status OK | OK |
| CP2108 quad UART | COM8=MMUART0/HSS · COM10=Linux console · COM9 · COM7 (serial `…53AD19C`) | identical mapping, all four Status OK | OK |
| Ghost devices | old FlashPro `065D9ACD`, CP2108 `…854E5A3` → COM3–6 | still enumerated, still Status Unknown (ghosts) | ignore |

Windows keys COM assignments to the device serial number, not the physical USB
port — so even if the headers moved to different ports/hubs, COM7–10 held.
Nothing needs re-mapping.

Kit identity: hostname `mpfs-icicle-kit`, kernel
`6.18.17-linux4microchip-2026.04.1`, clock correct (UTC; 23:18 UTC = 19:18 ET at
check). Resources: 56 G free on `/dev/root`, `/tmp` is 775 M **tmpfs** (soak
logs go under `/root/bringup/`, not `/tmp`, to survive a reboot), 1.5 G RAM.

## Resident image — confirmed the 2 ms watchdog build, fresh-boot signature

Read via `devmem2` ~4 min after power-on, before any inference:

- `0x60040804` (csr_version) = `0x00010000` — matches the runbook precondition.
- `0x60040854` (watchdog raw) = `0x00000003` — bit0 = 1 (timeout LIVE, nothing
  has fed the heartbeat since boot — the expected power-on state) and
  bits[31:1] = **trip_count baseline = 1** (the power-on trip). Record this
  baseline; `trip_count_delta` in the measurement starts from here.

No reprogram, no cold-cycle needed. Runbook precondition #2 and #3: satisfied.

## On-kit assets — all June-21 tooling survived

`/root/bringup/`: `v250_pid_loop` (Jun-21 18:57 **daemon-capable** build, plus
`.pre_daemon` / `.pre_odmr_rows` backups), `pid_ctl`, `pid_latency`, `pid_poke`,
`vbx_probe`, `vnnx_latency`, `vnnx_smoke`, `fcnn_v2_residual_dataset_a.vnnx`,
`odmr_v250_rows.csv` (120 held-out rows), dtbo/dtso, `sdboot-backup-2026-06-16/`.
`devmem2` on PATH. Missing (expected): `watchdog_trip` — built on bee and scp'd
as measurement step 1 per `docs/watchdog_trip_runbook_2026-07-01.md`.

Bee side: repo checkout at `42f26ac` (has 389699f tooling), RISC-V cross-gcc
present at the SmartHLS path in the runbook. Untracked on bee:
`libero/reports/2026-06-21-workload-power/` raw dumps (sibling-session leftover;
left alone).

Known-good stimulus invocation (from
`libero/reports/2026-06-21-v250-pid-loop/v250_pid_loop_odmr_rows_smoke.log`):
positional args `<model.vnnx> <rows> <warmup> [input.csv]`, e.g. one heartbeat
per cycle for the trip measurement:

```
/root/bringup/v250_pid_loop fcnn_v2_residual_dataset_a.vnnx 1 0 /root/bringup/odmr_v250_rows.csv
```

(The runbook's `--rows 1` placeholder is spelled positionally; smoke log shows
~32 µs per V250 completion and the watchdog visibly clearing, `timeout=0`.)

## Readiness per 48-hour-list item

1. **Watchdog trip [HW] — GO.** Every precondition verified above. Remaining:
   build `watchdog_trip` on bee (runbook step 1), scp, two-shell run, N≥100
   events. Nothing else stands in the way.
2. **Kit-resident MSS-paced loop — mostly already built.** `v250_pid_loop
   --daemon --state <json> --pid-file <pid>` is the MSS-resident continuous
   loop (atomically refreshes state JSON per row; the dashboard start/stop
   wraps it). Remaining work is measurement + evidence, not construction:
   sustained step-rate number (note: image reports `rdcycle=0`, `rdtime` @
   1 MHz timebase → rate resolution 1 µs, fine for Hz-level claims),
   laptop-disconnected run with telemetry-only capture. Gotcha to honor: the
   M0 inner-clamp setup write at `0x60040020` must be done (dashboard/pid_ctl
   flow) or the AI term is silently clamped to zero.
3. **Overnight soak — GO once 1+2 land.** Disk/clock verified; write logs +
   pidfile under `/root/bringup/soak/`; nohup + heartbeats per long-job rules.
4. **Board power — DROP.** PAC1934 probe fails at boot
   (`-ETIMEDOUT reading 0x1C`, probe error -110), manual driver bind at
   t+504 s fails identically, and the chip does not ACK: `i2cdetect -r`
   shows `--` at 0x10 on **all three** buses (0, 1, 2). DT node `1-0010` and
   kernel driver are present, so software is not the blocker — the device is
   electrically absent/held (board-level: jumper routing or a held bus;
   chasing that is schematic work outside the 48 h software path). The only
   other sensor is `hwmon0 = mpfs_tvs` (on-die temp/voltage) — not board rail
   power, not a substitute for the deck's "board-measured X W [HW]" line.
   Per the plan's own pre-flight rule: drop item 4 from the window.
5. / 6. Not kit-gated (5 = ws2 training) / buffer-only (6 = resynthesis,
   guardrail says leave the golden image alone). Unaffected by this inventory.

## Guardrail compliance

- Golden idfix2 / 2 ms bitstream: untouched (reads only; image confirmed
  resident by CSR signature, not by reprogramming).
- Claims-map gate: no deck numbers produced by this inventory; the trip_count
  baseline and stimulus invocation recorded here are measurement inputs, not
  claims.
- Coordination: uses the 389699f tooling as staged; nothing duplicated.
