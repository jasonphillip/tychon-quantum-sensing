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

```bash
./pid_poke w   0x14 0.0625    # Kd <- 0x00001000  (CLEAN loopback addr)
./pid_poke r   0x14           # expect 0x00001000 (0.062500)  -> AXI path alive
./pid_poke w   0x18 1.0       # out_min <- 0x00010000 (CLEAN)
./pid_poke r   0x18           # expect 0x00010000 (1.000000)
./pid_poke wraw 0x08 0x1      # acc_start = 1; then `r 0x08` to watch idle->running
```
Use **0x14 / 0x18 / 0x1C** for clean write→read (the eavesdropper aliases 0x08/0x0C/0x10).
If `/dev/mem` is blocked (CONFIG_STRICT_DEVMEM), the overlay's `pid@60001000` UIO node is
the fallback — point `pid_poke` at `/dev/uioN` instead (small edit).

---

## 7. Rung F — V250 inference smoke test

```bash
./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx
# expect: "V250 control plane alive" -> "inference complete" -> dequantized outputs
```
Needs `/dev/udmabuf-ddr-nc0` (non-cached DMA pool). **[NC]** if the 2026.04 base image
doesn't ship it: `ls /dev/udmabuf-ddr-nc0`; if missing, add a `udmabuf-ddr-nc0`
(`compatible="ikwzm,u-dma-buf"`, non-cached, `sync-mode=<1>`) reserved-memory node to the
**base** DTS (not the runtime overlay — reserved memory must be reserved at boot).

> **[NC] — V250 clock / latency.** Microchip de-rated the Icicle V250 to 75/150 MHz; the
> seed_7 closure runs a 125 MHz FIC user clock. **Do not quote inference latency** until
> measured on-silicon (read the V250 1×/2× rate from the seed_7 CCC config first).

---

## 8. Rung G — ODMR replay (next)

Stream `sim/stimulus/odmr_representative_trace.csv` row-by-row: per row, write the error
inputs via `pid_poke` (or an extended tool), run `vnnx_smoke`'s inference on the same row,
collect `(t, pid_out, vnnx_out)`. Use UART echo-per-row flow control. This is authored in
the reshaped C–G plan (`docs/cg_linux_bringup_plan_2026-06-15.md`).

---

## Open [NC] / decisions (see also the batched checklist in the session summary)
- **HSS version match** → may need an eNVM HSS reflash (ASK-FIRST, §3).
- **`/dev/udmabuf-ddr-nc0` presence** in the 2026.04 image → may need a base-DTS node (§7).
- **`/dev/mem` strict** → may need the PID UIO node instead (§6).
- **V250 clock** → measure before quoting latency (§7).
- **MMUART0↔COM** → resolved by watching COM7–10 at first boot (§3) — closes rung D.
