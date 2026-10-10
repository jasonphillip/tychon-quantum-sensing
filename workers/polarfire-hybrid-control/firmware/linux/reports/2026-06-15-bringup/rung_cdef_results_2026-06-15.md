# Linux on-target bring-up — rungs C / D / E / F results (2026-06-15)

On-silicon execution of the Linux/Yocto MSS path (decision DLOG-053) against the seed_7
hybrid-PID + CoreVectorBlox-V250 bitstream already programmed on the Production MPFS250T
(rung A, DLOG-054). Host: ws1 (flash + orchestration). Target reached over SSH at
`192.168.x.x` (eth0, DHCP) and the CP2108 serial console on bee.

## Summary

| Rung | Result | One-line |
|---|---|---|
| C — boot Linux from SD | **PASS** | Linux 6.18.17-2026.04.1 booted from the SD card, marker-verified |
| D — MMUART→COM mapping | **PASS** | MMUART0 = COM8 (HSS); MMUART1 = COM10 (U-Boot + Linux login) |
| E — PID AXI loopback | **BLOCKED (bitstream)** | PID slave read path non-responsive → hard CPU wedge; "eavesdropper severed read path" confirmed on silicon |
| F — V250 inference | **PARTIAL** | V250 control plane alive + model loads + START accepted, but NPU never advances (compute clock/enable not closed) |

Both blockers are seed_7 **bitstream-integration gaps**, not Linux/runtime problems. The
Linux/Yocto path itself is validated end-to-end.

---

## Rung C — Boot Linux from SD — PASS

- Image: `mchp-base-image-mpfs-icicle-kit.rootfs-20260430113402.wic` (linux4microchip-2026.04),
  flashed to the microSD on ws1 (`dd`, 653 MB, gz sha256 `87bde545…c430d` verified pre- and post-pull).
- Boot chain (from `boot_capture_cold_2026-06-15.log`):
  `HSS 0.99.40-v2024.02` → `Trying to get boot image via MMC … Attempting to select SDCARD … Passed`
  → `U-Boot 2025.07-linux4microchip-2026.04` → FIT kernel → `Linux 6.18.17-linux4microchip-2026.04.1`.
- Boot source proven **SD, not eMMC**, three ways:
  1. `/etc/tychon-sd-image-marker` (planted on the SD rootfs at flash time) reads back token
     `TYCHON-RUNG-CDEF-SDBOOT-20260615` (rc=0).
  2. `findmnt / → /dev/mmcblk0p3 ext4`.
  3. Kernel cmdline `root=/dev/mmcblk0p3`, kernel build `Apr 29 2026`.
- Login reached: `mpfs-icicle-kit login:` on ttyS1. Root password was **expired** (forced change
  on first login) — set to a bring-up password over serial.
- HSS-version [NC] retired: the factory HSS (2024.02) chainloads the 2026.04 U-Boot/kernel from SD
  cleanly — **no eNVM HSS reflash needed**.

## Rung D — MMUART → COM mapping — PASS

| MMUART | Role | CP2108 iface | COM |
|---|---|---|---|
| MMUART0 | HSS console + monitor heartbeat | Interface 0 | **COM8** |
| MMUART1 | U-Boot + Linux console / login (ttyS1) | Interface 1 | **COM10** |

(Interfaces 2/3 → COM9/COM7.) Note: the HSS prints a periodic `loop N took … ticks` monitor
heartbeat on MMUART0 for the life of the boot — it is **not** a separate bare-metal app; Linux
runs on MMUART1.

## Rung E — PID AXI register loopback — BLOCKED by the bitstream

- Tool: `pid_poke r 0x14` (read Kd at PID base `0x60001000`, an "eavesdropper-clean" offset).
- Observed: the process **hangs with no return and no error**. A `/dev/mem` permission failure
  would error instantly; this is a non-completing AXI read.
- Kernel view (serial console): the issuing U54 core hard-wedges —
  `rcu: rcu_sched kthread starved … OOM is now expected behavior`, `Tainted:[L]=SOFTLOCKUP`,
  `BUG: workqueue lockup - pool cpus=1 … stuck for 143s!`. Recoverable only by power-cycle.
- Conclusion: the PID slave at `0x60001000` **does not respond to reads** — FIC_0 has no decode
  timeout, so the load never retires. This is the **"eavesdropper `pid_io_block` severed read
  path"** the 2026-06-02 strategy audit predicted, now confirmed on silicon. The README's
  "0x14/0x18/0x1C round-trip cleanly" assumption is **false for this bitstream**; the read channel
  is severed for the slave. A UIO fallback cannot help (same physical address, same hang).
- Path to PASS: the **clean two-slot SmartDesign integration**
  (`docs/smartdesign_two_slot_canvas_runbook.md`) — a re-synth/re-program (new bitstream).

## Rung F — V250 inference smoke — PARTIAL (control plane alive, NPU inert)

What works (on silicon):
- `seed7_vbx_pid.dtso` overlay applies → `uio2 = vbx@60030000`, `uio3 = pid@60001000`.
- `/dev/udmabuf-ddr-nc0` present (no base-DTS rebuild needed); kernel cmdline carries
  `uio_pdrv_genirq.of_id=generic-uio`.
- `vbx_cnn_init` succeeds → **"V250 control plane alive."** `SOFT_RESET`, register reads/writes
  all respond instantly (196,247 reads over 4 s, **zero hangs** — the V250 control AXI slave is
  on the FIC clock and is solid, unlike the PID slave).
- Model loads: `fcnn_v2_residual_dataset_a.vnnx` (sha256 `6c5cd21a…`, DLOG-048) → 1 input, 1 output.
- `vbx_cnn_model_start` writes the IO + model pointers into the V250 (readback: CTRL+0x10 =
  `0xc8000400`, CTRL+0x18 = `0xc8000000`, i.e. into the udmabuf-ddr-nc0 pool at 0xc8000000) and
  asserts START.

What fails:
- The completion poll `while(vbx_cnn_model_poll>0)` spins forever in benign userspace **state R**
  (not a wedge — process is killable, system healthy).
- High-rate sampling of CTRL (`0x60030000`) during a live run: **every one of 196,247 samples =
  `0x00000002` (START)**. RUNNING (`0x04`), OUTPUT_VALID (`0x08`), and ERROR (`0x10`) **never
  assert**.
- CTRL bits (per `vbx_cnn_api.c`): SOFT_RESET 0x01, START 0x02, RUNNING 0x04, OUTPUT_VALID 0x08,
  ERROR 0x10.

Root cause: CTRL is frozen at exactly the value software last wrote (START). The hardware-driven
bits (RUNNING/OUTPUT_VALID/ERROR) are set by the NPU state machine; they never change → the NPU
**compute datapath is not advancing**. The control AXI interface (FIC clock) works, but the V250
core does not react to START — the signature of the **V250 compute clock not running, or the core
held in reset/not enabled**, in the seed_7 closure. The V250 is *present in fabric by construction*
but **not functionally clocked/enabled**. This is the `[NC]` V250-clock obligation, now diagnosed
on silicon. (No inference latency is quoted — the engine never ran.)

Path to PASS: confirm the V250 1×/2× clock + reset/enable wiring in the seed_7 Libero design
(CCC → CoreVectorBlox), fix the connection, re-synth + re-program (new bitstream). The on-silicon
symptom (START latched, no RUNNING ever) tells the design fix exactly what to close.

---

## [NC] resolutions (this session)

| [NC] item | Outcome |
|---|---|
| HSS version vs 2026.04 image | **Retired** — factory HSS 2024.02 boots the 2026.04 SD image; no reflash |
| `/dev/udmabuf-ddr-nc0` present? | **Yes** — shipped by the base DT (`udmabuf-ddr-nc0 @ 0xc8000000`); no base-DTS edit |
| `/dev/mem` strict (CONFIG_STRICT_DEVMEM)? | **Not strict** — mmap of fabric addresses succeeds (the PID hang is an AXI non-response, not a permission denial; V250 reads/writes work) |
| V250 clock / latency | **Diagnosed as the rung-F root cause** — NPU compute clock/enable not closed; latency not quotable |

## Next steps

1. **V250 datapath (rung F):** inspect the seed_7 CCC → CoreVectorBlox clock + reset/enable in
   Libero on bee; close the wiring; re-synth + re-program on a branch. Re-run `vnnx_smoke`.
2. **PID read path (rung E):** execute the clean two-slot SmartDesign integration
   (`docs/smartdesign_two_slot_canvas_runbook.md`); re-synth + re-program; re-run `pid_poke`.
3. Both are bitstream changes — keep on a branch; do not disturb the rung-A-verified seed_7
   programming until a replacement closure is digest-verified.

## Reproduce

```
# host (ws1): flash already done; tools pre-staged at /root/bringup on the SD
ssh -i ~/.ssh/id_ed25519 root@192.168.x.x
cd /root/bringup
dtc -@ -O dtb -o seed7_vbx_pid.dtbo seed7_vbx_pid.dtso -Wno-reg_format -Wno-avoid_default_addr_size
mkdir -p /sys/kernel/config/device-tree/overlays/seed7
cat seed7_vbx_pid.dtbo > /sys/kernel/config/device-tree/overlays/seed7/dtbo   # uio2=vbx, uio3=pid
./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx    # "V250 control plane alive" + model load; poll spins (NPU inert)
# DO NOT run `pid_poke r/w` against 0x60001000 — it wedges a core (severed read path); power-cycle to recover.
```
