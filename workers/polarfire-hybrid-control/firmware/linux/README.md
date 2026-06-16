# Icicle Kit — Linux bring-up runbook (rungs C–G)

Copy-paste guide to take the **already-programmed** seed_7 bitstream (rung A, PROGRAM
PASS 2026-06-15) to a Linux userspace that pokes the fabric PID and runs V250 inference.
Per the **2026-06-15 Linux/Yocto decision** (`docs/track0_bringup_runbook.md`).

**Goal: your only hands-on steps are _flash SD_, _insert SD_, _set boot for SD_, _press
RESET_, and _read a COM port_.** Everything buildable was pre-staged on bee + NAS.

---

## 0. What is already staged (verified 2026-06-15)

| Asset | Where | Verify |
|---|---|---|
| seed_7 bitstream | **already on silicon** (rung A) + `.job` on bee + NAS | fabric digest `0769…C03DF8` matched on program |
| Linux image `mchp-base-image-mpfs-icicle-kit.rootfs-20260430113402.wic.gz` (linux4microchip-2026.04, ~117 MB) | bee `~/icicle-linux/` | sha256 `87bde5454c6d951665ba12883f38b8d9da1274484900d5f33a79945b874c430d` |
| `pid_poke`, `vnnx_smoke` (RISC-V Linux ELFs) | bee `firmware/linux/` + NAS `backups/bee-polarfire-hybrid-control/` | `pid_poke`=static, `vnnx_smoke`=dynamic, both "for GNU/Linux" |
| `fcnn_v2_residual_dataset_a.vnnx` (V250, 12.5 KB) | bee + spark1 `models/` | sha256 `6c5cd21a…512eb` (DLOG-048) |
| `seed7_vbx_pid.dtso` (DT overlay) | `firmware/linux/` | exposes V250 `0x60030000` + PID `0x60001000` |

**Confirmed (F.1, 2026-06-15):** the seed_7 MSS config has **eMMC/SD enabled**
(`EMMC_SD_SWITCHING ENABLED_SD`, DDR50), **eNVM present**, and **MMUART0 (HSS) +
MMUART1 (Linux) enabled** — so this bitstream *can* boot Linux from SD.

---

## 1. Rebuild the tools (only if you change the source)

The bundled cross-GCC is a **Cygwin** build — it exits 127 silently unless `cygwin1.dll`
is on PATH. On bee (MSYS):

```bash
SHLS=/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS
export PATH="$SHLS/swtools/binutils/riscv-gnu-toolchain/bin:$SHLS/dependencies/lib/cygwin:$PATH"
cd ~/dev/projects/polarfire-hybrid-control/firmware/linux
# `make` is NOT on bee's MSYS PATH — invoke gcc directly (the Makefile documents the flags):
riscv64-unknown-linux-gnu-gcc -O2 -Wall -static pid_poke.c -o pid_poke -lm
VBX=/c/Microchip/VectorBlox-SDK
riscv64-unknown-linux-gnu-gcc -O2 -Wall -DVBX_SOC_DRIVER -DMSS_DDR -DUSE_INTERRUPTS=0 \
  -I$VBX/drivers/vectorblox vnnx_smoke.c \
  $VBX/drivers/vectorblox/vbx_cnn_api.c $VBX/drivers/vectorblox/vbx_cnn_model.c \
  -o vnnx_smoke -lm -lpthread
```

---

## 2. Flash the SD card  ⚠️ HANDS-ON

The `.wic.gz` is a full GPT image (U-Boot + kernel + rootfs). **Decompress first** —
Microchip warns a `.wic.gz` written directly can corrupt the boot. On a host with an SD
writer (bee, or your laptop):

```bash
gunzip -k mchp-base-image-mpfs-icicle-kit.rootfs-20260430113402.wic.gz   # -> .wic
# then ONE of:
#   GUI: USBImager (https://bztsrc.gitlab.io/usbimager/) -> pick .wic -> pick SD -> Write
#   CLI: sudo dd if=mchp-base-image-...wic of=/dev/sdX bs=4M conv=fsync status=progress
```
⚠️ Double-check `/dev/sdX` is the SD card, not a system disk.

---

## 3. Boot from SD  ⚠️ HANDS-ON + DECISION

The boot chain is **HSS (eNVM) → U-Boot → Linux**. The seed_7 `.job` programmed
fabric+sNVM only, so the **factory HSS in eNVM is intact** (untouched by rung A).

1. Set the kit to boot from **SD** (not eMMC). On Icicle this is a fabric SDIO de-mux
   (`fabric_sd_emmc_demux_select`, FIC3) + an HSS boot-medium selection — the exact
   jumper/switch is in the **Icicle Kit User Guide** (not in our corpus). At the HSS
   `>>>` prompt over MMUART0 you can also type `mmc` then pick SDCARD.
2. Open serial terminals on **COM7–COM10** at **115200 8N1** (the production CP2108
   ports). **HSS banner = MMUART0; Linux console/login = MMUART1.** Note which COM is
   which (this also resolves the rung-D MMUART0 question).
3. **Press RESET.** Expect: HSS banner → U-Boot → Linux login (`root`, no password on the
   minimal image).

> **DECISION / [NC] — HSS version match.** The `.wic` is linux4microchip-2026.04; the
> factory HSS may be older. If U-Boot/Linux fails to boot, the HSS likely needs reflashing
> to a matching release into **eNVM** — that is a separate FlashPro/Libero **eNVM program
> (PROGRAM_INFLASH-class)**, which is **gated on your approval** (ASK-FIRST). Try the
> factory HSS first (non-destructive); only reflash if boot fails. Do not reflash eNVM
> without a go-ahead.

---

## 4. Copy the tools + model onto the target

From bee (or scp from your host) once Linux is up and on the LAN:

```bash
# on the target (replace <ip>): or use a USB stick / the rootfs partition pre-stage
scp pid_poke vnnx_smoke fcnn_v2_residual_dataset_a.vnnx seed7_vbx_pid.dtbo root@<target-ip>:/root/
```
(If no network yet, copy onto the SD rootfs partition before first boot.)

---

## 5. Apply the device-tree overlay (EVERY boot)

The overlay maps the two fabric slaves to `/dev/uioN`. It does **not** persist across
reboots.

```bash
# on the target — compile once, apply each boot:
dtc -@ -O dtb -o seed7_vbx_pid.dtbo seed7_vbx_pid.dtso \
    -Wno-reg_format -Wno-avoid_default_addr_size
mkdir -p /sys/kernel/config/device-tree/overlays/seed7
cat seed7_vbx_pid.dtbo > /sys/kernel/config/device-tree/overlays/seed7/dtbo
ls -l /dev/uio*                          # expect new uio nodes
cat /sys/class/uio/uio*/name             # one should read "vbx"
```

---

## 6. Rung E — poke the PID over AXI

**Current seed_7 status after 2026-06-15:** do **not** run `pid_poke` against
`0x60001000`. A read of the PID slave issued a non-completing AXI transaction
and wedged one U54 core. A UIO fallback does not help because it reaches the
same physical slave. See
`reports/2026-06-15-bringup/rung_cdef_results_2026-06-15.md`.

The intended post-fix smoke test, after the clean two-slot bitstream is
programmed, is:

```bash
./pid_poke w   0x14 0.0625
./pid_poke r   0x14
./pid_poke w   0x18 1.0
./pid_poke r   0x18
```

---

## 7. Rung F — V250 inference smoke test

```bash
./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx
# 2.0.1/V250 rebuild (2026-06-16): "inference complete." -> out[0]=-2.9506 (scale 0.022873, zp 1)
```
Needs `/dev/udmabuf-ddr-nc0` (non-cached DMA pool). **[NC]** if the 2026.04 base image
doesn't ship it: `ls /dev/udmabuf-ddr-nc0`; if missing, add a `udmabuf-ddr-nc0`
(`compatible="ikwzm,u-dma-buf"`, non-cached, `sync-mode=<1>`) reserved-memory node to the
**base** DTS (not the runtime overlay — reserved memory must be reserved at boot).

> **Rung F status — PASS on silicon 2026-06-16.** After the CoreVectorBlox **2.0.1/V250**
> rebuild was programmed, `vbx_probe` → `RESULT: INFERENCE COMPLETED` (3/3; CTRL advances
> `0x00`→`0x04`→done, ERR=0, VERSION `0x60030028`=`0x20000000`=V250/major2, latency <5 ms) and
> `vnnx_smoke` → `inference complete` / `out[0]=-2.9506`. The old `1.1.12/V500` STUCK-at-`0x02`
> is fixed. **Caveat:** the rebuild's bitstream broke the **fabric PCIe @ `0x3000000000`** — the
> Linux `microchip-pcie` probe hangs (silent boot → 28 s watchdog loop). This is now **persistently
> worked around**: the PCIe DT node is disabled at boot via the U-Boot env (`design_overlays` boot-time
> `fdt set … status disabled`, reversible) and the `vbx` overlay auto-applies via `vbx-overlay.service`,
> so a normal `reboot` recovers **autonomously** to an inference-ready kit (verified). V250 needs no PCIe;
> the PCIe defect is independent of rung F (long-term fix only if PCIe is needed = re-synth with PCIe
> intact). Full results + persistence/rollback: `docs/rung_f_v250_on_silicon_results_2026-06-16.md` (§6);
> on the kit see `/root/PCIE-DISABLED-README.md`.

---

## 8. Rung G — ODMR replay (next)

Stream `sim/stimulus/odmr_representative_trace.csv` row-by-row: per row, write the error
inputs via `pid_poke` (or an extended tool), run `vnnx_smoke`'s inference on the same row,
collect `(t, pid_out, vnnx_out)`. Use UART echo-per-row flow control. This is authored in
the reshaped C–G plan (`docs/cg_linux_bringup_plan_2026-06-15.md`).

---

## Open [NC] / decisions (see also the batched checklist in the session summary)
- **HSS version match** → retired 2026-06-15; factory HSS boots the 2026.04 SD image.
- **`/dev/udmabuf-ddr-nc0` presence** → retired 2026-06-15; present at `0xc8000000`.
- **`/dev/mem` strict** → fabric addresses are readable/writable; PID failure is AXI non-response.
- **V250 inference completion** → ✅ RESOLVED 2026-06-16 (2.0.1/V250 rebuild; `vbx_probe` INFERENCE COMPLETED, <5 ms). New open item: **fabric PCIe @ `0x3000000000` broken in the rebuild** → Linux `microchip-pcie` probe hangs (boot-loop); workaround = disable the PCIe DT node. See `docs/rung_f_v250_on_silicon_results_2026-06-16.md`.
- **MMUART0↔COM** → MMUART0/HSS = COM8, MMUART1/Linux = COM10.
