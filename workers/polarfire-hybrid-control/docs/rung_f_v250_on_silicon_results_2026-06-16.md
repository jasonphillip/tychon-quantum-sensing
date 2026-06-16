# Rung F — V250 inference on silicon: PASS + Linux fabric-PCIe boot-loop (2026-06-16)

**Headline (CONFIRMED, live silicon):** the CoreVectorBlox **2.0.1 / V250** rebuild bitstream runs
V250 inference **to completion** on the Production MPFS250T. The original rung-F stall
(`CTRL` latched `0x02` forever) is **fixed** — it was the wrong NPU IP (`1.1.12/V500`) in the
rung-A seed_7 bitstream. Closes the open blocker in `docs/rung_f_decerr_handoff_2026-06-16.md` §7.2.

**One caveat (CONFIRMED, new this session):** the same rebuild's bitstream has a **broken fabric
PCIe controller @ `0x3000000000`**; the Linux `microchip-pcie` driver **hangs** probing it, which is
why the kit was unreachable after the power-cycle (silent boot → 28 s watchdog → boot-loop). The
V250/FIC path is unaffected. A boot-time **PCIe-node disable** is the working workaround.

Evidence labels per the ground-truth contract (`docs/agent_ground_truth_contract.md`).

---

## 1. V250 IP swap took on silicon — CONFIRMED

VERSION register `0x60030028` read two independent ways:
- **E51 / HSS** (`DEBUG HEXDUMP 0x60030000 0x40` at the HSS `>>` CLI, COM8): word @ +0x28 = **`0x20000000`**.
- **Linux runtime** (`vbx_probe`, via `/dev/uio2` = `vbx@60030000`): `VER=0x20000000` (every stage, every run).

Decode (HB0919 Rev 2.0 Table 4): bits[31:28]=Major=**2**, bits[15:8]=Size=**0 = V250**. ERROR `0x60030004`=0.
- Old/wrong (rung-A seed_7, 1.1.12/V500): `0x10010100` → Major 1 / V500.
- New (2.0.1/V250 rebuild): `0x20000000` → Major 2 / V250. ✅ exactly the predicted gate.

Programmed fabric digest `22A40FC1…964D5974` (job sha256 `4e3323e8…0ad0ccfb4af8e`), per
`docs/rung_f_v250_post_program_handoff_2026-06-16.md`.

## 2. Inference completes — CONFIRMED (reproducible 3/3)

`/root/bringup/vbx_probe fcnn_v2_residual_dataset_a.vnnx` (stock SDK 2.0.x runtime, bounded ≤600 polls):

```
[after_init ] CTRL=0x00000000 ERR=0x00000000 ... VER=0x20000000
vbx_cnn_model_start ret=0
[after_start] CTRL=0x00000004 ERR=0x00000000 MODEL=0xc8000400 IO=0xc8000000 VER=0x20000000
poll ended: iters=1 last_poll_ret=0
[final      ] CTRL=0x00000000 ERR=0x00000000 ...
error_val=0
RESULT: INFERENCE COMPLETED          ← 3/3 runs identical
```

- **Discriminator met:** `CTRL` advances `0x00` → **`0x04` (RUNNING)** after start, then poll returns done
  (`last_poll_ret=0`) with `error_val=0`. Versus the old `1.1.12/V500`: `CTRL=0x02` held across the
  whole poll → STUCK (`docs/rung_f_decerr_handoff_2026-06-16.md` §1).
- **Latency:** completes within the first poll interval → **< ~5 ms** (5 ms poll granularity; the FCNN is
  tiny, true latency is far lower). First *measurable* on-silicon completion.

`vnnx_smoke` (timeout-wrapped; its poll loop is otherwise infinite):
```
V250 control plane alive (vbx_cnn initialized).
model: 1 input(s), 1 output(s)
inference complete.
out[0] len=1 scale=0.022873 zp=1: -2.9506
```
**Dequantized output = −2.9506** (q-scale 0.022873, zero-point 1) for the model's baked test input.
Model `fcnn_v2_residual_dataset_a.vnnx` (12,832 B, sha256 `6c5cd21a…512eb`, DLOG-048).

## 3. Linux boot blocker — fabric PCIe probe hang — CONFIRMED root cause

**Symptom:** after the power-cycle the kit was unreachable; serial showed Linux start then COM10 went
silent "after early kernel init"; 28 s reboot-loop.

**Diagnosis (byte-level, vs the known-good 2026-06-15 boot
`firmware/linux/reports/2026-06-15-bringup/boot_capture_cold_2026-06-15.log`):**
- The `[0.019] printk: legacy bootconsole [ns16550a0] disabled` "stop" is **only a console blackout** —
  with `keep_bootcon` the kernel is seen booting normally far past it (SMP `[0.116]`, PLIC `[0.532]`, …).
- The **true hang** is at `[0.82] irq: IRQ46: trimming hierarchy from :soc:interrupt-controller@c000000`,
  i.e. the very next step is the `microchip-pcie 3000000000.pcie` host-bridge probe. In the good boot,
  `IRQ46` is immediately followed by `[0.166] microchip-pcie 3000000000.pcie: host bridge … ranges:` →
  PCIe enumerates → `[0.364] printk: legacy console [ttyS1] enabled` → … → login. In the new bitstream,
  the `microchip-pcie` probe **hangs before its first print** (AXI read to the fabric PCIe never returns).
- Because the hang is **before** `[0.364] ttyS1` console registration, the real serial console never comes
  up → the COM10 blackout. The 28 s `mpfs_wdt` (`timeout 28 sec (nowayout=true)`) then resets → loop.
- **The 2026-06-15 reference (old 1.1.12/V500 bitstream) enumerated this PCIe fine** → the 2.0.1/V250
  rebuild **regressed the fabric PCIe** at `0x3000000000`. Scope is narrow: `dma-controller@60010000`
  (uio1) and the V250 (`0x60030000`, FIC_0) probe/respond normally — only PCIe is broken.
- HSS, OpenSBI, U-Boot are healthy on this bitstream (stable U-Boot prompt; `DEBUG SM` shows clean u54
  hand-off; `DEBUG HEALTHMON` shows no MPU/EDAC/PLL faults).

**HYPOTHESIS (not yet tested):** whether the PCIe hang is reset-class-dependent is **untested** — every
reset this session was warm (HSS `RESET` + watchdog). Jason's original *cold* power-cycle also went
silent/no-login (Codex evidence), which is consistent with the same PCIe hang, suggesting it is a
bitstream property rather than warm-reset-specific. A clean cold power-cycle would confirm.

## 4. Workaround that boots Linux — disable the PCIe DT node

The V250 inference path does not use PCIe, so disabling the fabric PCIe node lets Linux boot:
1. Interrupt U-Boot (the kit autoboot-loops; hold CR over MMUART1 to catch the 2 s window → `RISC-V #`).
2. Manual staged bootm with the node disabled (boot.scr's own `run design_overlays` proves `fdt` edits
   between `prep` and `go` reach the kernel DTB):
   ```
   setenv bootargs "earlycon root=/dev/mmcblk0p3 rootwait uio_pdrv_genirq.of_id=generic-uio"
   load mmc 0:1 0x8e000000 fitImage
   bootm start 0x8e000000#conf-microchip,mpfs-icicle-kit.dtb
   bootm loados
   bootm prep
   fdt set /fabric-pcie-bus@3000000000/pcie@3000000000 status disabled
   bootm go
   ```
3. Linux reaches `mpfs-icicle-kit login:`; eth0 link up 1 Gbps; DHCP `192.168.x.x`; mDNS resolves.
4. Apply the V250 runtime overlay in userspace (it is NOT in the base DT on this manual boot):
   ```
   mkdir -p /sys/kernel/config/device-tree/overlays/seed7
   cat /root/bringup/seed7_vbx_pid.dtbo > /sys/kernel/config/device-tree/overlays/seed7/dtbo
   ```
   → `/dev/uio2 = vbx@60030000` (addr `0x60030000`, size `0x1000`). Then run `vbx_probe`/`vnnx_smoke`.

> **Note:** the manual `bootm` above was the initial (ephemeral) validation. The disable has since been
> **made persistent** at boot — see §6 — so a power-cycle/reset now recovers autonomously.

**Persistent options:**
- **(a) Make PCIe-disable persistent — ✅ DONE 2026-06-16 (see §6).** Cheapest path to a stable kit;
  V250 inference needs no PCIe.
- **(b) Fix the bitstream** — investigate why the 2.0.1/V250 rebuild broke the fabric PCIe at
  `0x3000000000` (suspect the SmartDesign cascade re-gen / re-P&R disturbed the PCIe controller or its
  interconnect) and re-synth with PCIe intact. Proper long-term fix **if PCIe is ever needed**; heavier.
- **(c) Cold-cycle check** — a full power-off/on would still settle the §3 reset-class hypothesis.

## 5. Access + method reference (this session)
- **Kit:** `ssh icicle` → `mpfs-icicle-kit.local` = **192.168.x.x**, eth0 MAC `00:04:a3:xx:xx:xx`,
  kernel `6.18.17-linux4microchip-2026.04.1`. (Creds/serial map: `~/Desktop/Shared/fpga-icicle-access.md`.)
- **bee serial:** COM8/HSS/MMUART0 = `/dev/ttyS7`; COM10/Linux/MMUART1 = `/dev/ttyS9`; 115200 8N1.
  Read/write with `stty raw 115200 -echo` on a single read-write fd (Windows COM = exclusive-open).
- **HSS CLI** is reachable post-boot on COM8 (Enter → `>>`): `BOOT RESET HELP VERSION UPTIME DEBUG …`;
  `DEBUG HEXDUMP <addr> <len>` reads memory from the E51 (used for the VERSION read with Linux down).
- Raw serial captures for this session are on bee under `/tmp/icicle_serial/` (boot_com8/com10,
  keep_bootcon boot, workaround boot, `p2_*` persistent-disable boot, `p2_env_before.cap` env backup).

## 6. Persistent PCIe-disable — DONE 2026-06-16 (reversible boot-time fdt set)

The §4 disable is now persistent across power-cycles/resets, with **no rebuild/reprogram and no change
to eNVM/HSS/U-Boot binaries** — only the U-Boot **environment** (data) and a rootfs systemd unit.

**Mechanism (smallest reversible change — a boot-time fdt fixup).** The U-Boot env var `design_overlays`
(run by `boot.scr` between `bootm prep` and `bootm go`, where the kernel FDT is addressable) was set to:
```
echo PCIe 0x3000000000 OFF on purpose see PCIE-DISABLED-README.txt; fdt set /fabric-pcie-bus@3000000000/pcie@3000000000 status disabled
```
`saveenv` → `Saving Environment to FAT... OK` (persists to `uboot.env` on the FAT, `mmcblk0p1`). Env var
`pcie_disable_reason` holds the why. **Why replace, not append:** the original `design_overlays` contains
embedded `"` (unsafe to `${design_overlays}`-append) and is a **no-op** on this image (`no_of_overlays`
unset; the vbx overlay is applied in userspace) — the original is preserved verbatim in the backups.

**Overlay auto-apply (so a clean boot is inference-ready).** A reversible systemd oneshot
`vbx-overlay.service` (enabled) runs `/root/bringup/apply-vbx-overlay.sh`, which applies
`seed7_vbx_pid.dtbo` each boot → `/dev/uio2 = vbx@60030000`. (It also creates `uio3=pid@60001000`,
passive generic-uio — **never `pid_poke`** the severed PID slave.)

**Discoverability — the "why" is in many places on purpose:**
- The boot console prints `PCIe 0x3000000000 OFF on purpose see PCIE-DISABLED-README.txt` **every boot**.
- U-Boot: `printenv pcie_disable_reason` and `printenv design_overlays`.
- FAT (`mmcblk0p1`): `PCIE-DISABLED-README.txt`. Rootfs: `/root/PCIE-DISABLED-README.md`.
- Kernel: `cat /proc/device-tree/fabric-pcie-bus@3000000000/pcie@3000000000/status` → `disabled`;
  `dmesg | grep -i pcie` shows no `microchip-pcie` probe.

**Backups (taken BEFORE the change; restoring any reverts fully):**

| Artifact | Location | sha256 |
|---|---|---|
| `boot.scr` (untouched) | `/root/bringup/sdboot-backup-2026-06-16/boot.scr.orig` | `207366415ea97ff47aa52b87de242bfcb24cfae449eff296c7f4c9ec388481d4` |
| `uboot.env` (original) | `/root/bringup/sdboot-backup-2026-06-16/uboot.env.orig` | `614c20479b7ffbd056726425304aaa316e5a9d3b74d96c83fdebd137294f18a6` |
| `uboot.env` (original, FAT-side) | `mmcblk0p1:/uboot.env.orig20260616` | (same as above) |
| full `printenv` text | bee `/tmp/icicle_serial/p2_env_before.cap` | — |

The verbatim original `design_overlays` value (for a precise U-Boot-side restore) is recorded in
`/root/PCIE-DISABLED-README.md`.

**Rollback (re-enables PCIe → returns to the boot-loop until the bitstream is fixed):**
1. **U-Boot:** catch the prompt, `setenv design_overlays '<original>'`, `saveenv`, `reset`; or
2. **Restore the env blob:** mount the FAT rw and `cp uboot.env.orig20260616 uboot.env` (or copy the
   rootfs backup), then reboot.
3. Remove the overlay auto-apply: `systemctl disable --now vbx-overlay.service; rm /etc/systemd/system/vbx-overlay.service`.

> Do NOT just re-enable the PCIe node expecting it to work — it hangs by construction on this bitstream.

**Verification — CONFIRMED twice, incl. an unattended `reboot` (no bee, no U-Boot intervention):**
the kit recovered **autonomously** (uptime 25 s on reconnect), `pcie status=disabled`, `dmesg` 0
`microchip-pcie`, `/dev/uio2=vbx@60030000` (svc active), VERSION `0x20000000`, `vbx_probe` →
`INFERENCE COMPLETED`. The 28 s watchdog boot-loop is gone. IP unchanged: `192.168.x.x`.

**Long-term:** the PCIe defect stays **independent of rung F**. If PCIe is ever actually needed,
re-synthesize the bitstream with the fabric PCIe intact (option (b) above) — not a node re-enable.
