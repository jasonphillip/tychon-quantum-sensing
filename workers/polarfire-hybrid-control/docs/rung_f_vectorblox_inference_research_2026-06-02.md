# Rung F — VectorBlox V250 Inference: Architecture Research (2026-06-02)

**Purpose:** front-load the rung-F (.vnnx-on-V250) unknowns before plan day so the session executes instead of discovers. Rung F was flagged as the highest-risk item ("genuine unknown, no public bare-metal example"). This document resolves that with primary-source evidence and frames the one architecture decision that collapses the risk.

**Sources:** the VectorBlox SDK 2.0.3 itself on bee (`/c/Microchip/VectorBlox-SDK/`), the `polarfire-control-corpus` + `tychon-fpga-mpfs250t-fcvg484e` corpora, and web (Microchip support article #000017296, the SDK GitHub, the PolarFire SoC Yocto BSP). Every non-obvious claim below is traceable to one of these.

---

## TL;DR — the decision that de-risks the whole plan

The VectorBlox runtime is **dual-path by construction** — it compiles either for Linux (UIO + udmabuf + PDMA) or freestanding bare-metal (`#else` branch, raw register pointer). So bare-metal is *not impossible*. **But there is no documented or known-working bare-metal example anywhere** — every Microchip-published hardware path, including the only one for our exact silicon (MPFS250T, SDK 2.0.3), boots **Yocto Linux**. Bare-metal F2 means hand-rolling DDR bring-up + an uncached allocator + 2 MB firmware staging + cache coherency with zero reference. Linux F2 is the paved road: prebuilt images, in-tree driver, non-destructive SD boot, ~½–1.5 days.

**Recommendation: do F1 (control-plane liveness) cheaply either way, then run F2 (real inference) under Linux unless F1 surfaces a reason not to.** For a demo whose centerpiece is the NN, trading ~1 day of Linux setup to remove the single largest risk in the plan is the right call. The PID safety/real-time story is unaffected — it lives in fabric, not MSS software (see "Architecture implication" below).

---

## The decisive fact: the runtime has a bare-metal `#else` branch

`drivers/vectorblox/vbx_cnn_api.h:11-13`:
```c
#if defined(__riscv) && defined(__linux)
#define VBX_SOC_DRIVER 1
#endif
```
`vbx_cnn_api.c` then forks:
- **`VBX_SOC_DRIVER` (RISC-V + Linux):** finds the core via `/sys/class/uio/.../name == "vbx"`, opens `/dev/uioN`, `mmap`s the control registers, allocates DMA from `/dev/udmabuf-ddr-nc0` (**non-cached** u-dma-buf), waits on the UIO fd for the output-valid interrupt, and copies outputs via the `mchp-dma-proxy` kernel driver (`ioctl`).
- **`#else` (freestanding/bare-metal):** `vbx_cnn_init(ctrl_reg_addr)` takes a **raw register pointer**, writes soft-reset→start, no OS calls. `virt_to_phys` is identity. The DMA allocator is `extern void* ddr_uncached_allocate(size_t)` — **you implement it.**

So "can it run bare-metal?" → the code path exists, but Microchip ships it untested on hardware and undocumented.

---

## V250 control base = `0x60030000` (cross-confirmed — resolves F1's "which slot")

Two independent sources agree:
1. The SDK device-tree overlay `example/soc-c/dts/mpfs_vbx.dtso` binds `vbx@60030000 { compatible = "generic-uio"; reg = <0x0 0x60030000 0x0 0x1000>; interrupts = <124>; }`.
2. Last session's FIC0_INITIATOR.v extraction (`docs/fic_0_address_map_2026-05-18.md`) found `SLAVE2_START_ADDR:0x60030000` on the CoreAXI4Interconnect.

So the V250 S_control window is almost certainly **`0x60030000` (4 KB)** — *not* `0x60001000` (that's the PID slot; Agent-2's earlier conflation). **F1 must verify this once against our seed_7 map, but it's no longer a 3-way TBD.** IRQ 124 is noted for the (optional) interrupt path; bare-metal will poll instead.

---

## F1 — control-plane liveness (CHEAP, low-risk, do regardless of path)

The register protocol, from `vbx_cnn_api.c` (`read_register(a,off)` in the bare-metal branch is just `((volatile uint32_t*)a)[off]` — plain word-indexed MMIO):

| Symbol | Word offset | Byte | Meaning |
|---|---|---|---|
| `CTRL_OFFSET` | 0 | 0x00 | control/status: SOFT_RESET, START, RUNNING, OUTPUT_VALID, ERROR bits |
| `ERR_OFFSET` | 1 | 0x04 | error register (`vbx_cnn_err_e` codes) |
| `MODEL_OFFSET` | 4 | 0x10 | model blob physical address |
| `IO_OFFSET` | (see src) | — | IO-buffer-pointer-array physical address |
| `VERSION_OFFSET` | 10 | 0x28 | IP version register |

`vbx_cnn_init()` does: `write(CTRL, SOFT_RESET); write(CTRL, 0);` then reads version + size. **F1 recipe (≈30 lines, bare-metal OR a one-off `/dev/mem` poke under Linux):**
1. Point `volatile uint32_t* vbx = (volatile uint32_t*)0x60030000`.
2. Read `vbx[10]` (VERSION) — non-zero, plausible = the V250 control plane is alive and reachable over FIC_0.
3. Confirm size-config = `VBX_CNN_SIZE_CONF_V250 (=0)` (the IP reports its configured size).
4. Write SOFT_RESET then 0 to `vbx[0]`; read back `vbx[0]` status + `vbx[1]` error → confirm it accepts the reset/start handshake.

This proves "firmware can talk to the V250" with no DDR, no DMA, no model. It also lets F1 **measure the real memory footprint** (the 2 MB firmware blob is the driver of the DDR requirement — see below) so the bare-metal-vs-Linux call is made on data. Exact `CTRL_REG_*` bit masks: read them from `vbx_cnn_api.c` at F1 time (the `#else` access primitives are at lines 18-28).

---

## F2 bare-metal — what you'd have to build (the undocumented hard path)

The `#else` branch tells you exactly what's missing. A bare-metal port must supply:
1. **DDR up.** The 2 MB firmware blob can't live in LIM/scratchpad. Bring DDR up via the Microchip MSS HAL (`mpfs-hal` DDR init — the Icicle base design already configures DDR; HSS normally runs this, bare-metal calls the HAL). Confirmed required: `fw/firmware.bin` = exactly 2,097,152 B = `VBX_INSTRUCTION_SIZE (2*1024*1024)` = the `instruction_blob`.
2. **`ddr_uncached_allocate(size)`** — an allocator over an **uncached** DDR region (the header warns all blobs "should... not be in the host's cachable memory"; even the Linux path uses `udmabuf-ddr-**nc**0`). Either map a reserved DDR region non-cacheable in the MSS, or `FENCE`+flush/invalidate around every blob/IO buffer.
3. **Firmware staging** — DMA/`memcpy` the 2 MB `firmware.bin` into the reserved DDR region and pass its address at init. (The Linux runtime takes `FIRMWARE.bin` as `run-model`'s first arg and stages it.)
4. **Cache coherency** — the corpus flag is explicit: PolarFire SoC fabric masters are **non-coherent with the U54 L2 by default; no documented coherency protocol**. This is the genuine risk surface — get it wrong and you see stale/garbage results intermittently (the byte-deterministic failure class our debugging rules warn about).
5. **Polling, not interrupts** — drop the UIO IRQ wait; use `vbx_cnn_model_poll()` (the Icicle build already sets `USE_INTERRUPTS=0`).

None of this is documented for bare-metal. Realistic: 2–4 days, high variance, with cache coherency the likeliest multi-day stall.

---

## F2 Linux — the supported, de-risked path

- **In-tree driver, nothing to compile:** the overlay binds the V250 as `compatible = "generic-uio"` → it appears as `/dev/uioN`. No kernel module to write.
- **Prebuilt images exist:** `meta-polarfire-soc-yocto-bsp` releases ship `core-image-...-icicle-kit-es...wic.gz` — no Yocto build needed.
- **SD-card boot is non-destructive + takes precedence over eMMC** — iterate freely without touching eMMC (sidesteps the ASK-FIRST destructive-eMMC concern entirely). Write with `bmaptool copy <img>.wic.gz /dev/sdX`.
- **The Icicle base design boots HSS→U-Boot→Linux by default**; our `MPFS_ICICLE_Vectorblox` derives from it. Confirm (cheap) that the Vectorblox merge didn't disable MMC/eNVM-HSS.
- **Flow:** program bitstream → boot Linux from SD → `make overlay` (DT, every boot) → `make` → `./run-model <firmware.bin> <model.vnnx> TEST_DATA` (validates HW vs simulator via CHECKSUM) → adapt `run-model` to stream our 1000-row ODMR CSV row-by-row with latency capture (a small C loop around `vbx_cnn_model_start`/`poll`).
- **Setup time (newcomer):** ~½ day to 1.5 days via SD + prebuilt image. Only +1–3 days if forced to build Yocto from scratch (shouldn't be needed).
- **Open items to confirm against our base design (~30 min):** (a) reg base `0x60030000` + IRQ 124 in our map (else edit `mpfs_vbx.dtso`); (b) a `udmabuf-ddr-nc` reserved-memory region in the image/DT; (c) HSS version in eNVM matches the `.wic.gz`; (d) MMC still enabled in `MPFS_ICICLE_Vectorblox` MSS cfg.

---

## Canonical inference sequence (same logic both paths — the rung-G template)

From `example/soc-c/run-model.cpp` `main()`:
```
vbx_cnn = vbx_cnn_init(<ctrl base | NULL-for-Linux-UIO>);
model   = vbx_allocate_dma_buffer(...);  fread(.vnnx into it);
for each input i:  io_buffers[i]      = vbx_allocate_dma_buffer(input_len);  memcpy(input);
for each output o: io_buffers[nin+o]  = vbx_allocate_dma_buffer(output_len);
vbx_cnn_model_start(vbx_cnn, model, io_buffers);
vbx_cnn_model_wfi(...) / while(vbx_cnn_model_poll(...) > 0);
// scale outputs: int8 -> fix16 via model_get_output_scale_fix16_value + model_get_output_zeropoint
```
For rung G this becomes: per ODMR CSV row → write input → start → poll → read+scale output → echo `(t, pid_out, vnnx_out)` over UART (or stdout, under Linux) → next row.

---

## Architecture implication if we go Linux (worth weighing at the F1 gate)

If F2 is Linux, **rungs C–E should probably be Linux too** — then the whole demo is one userspace program: poke the PID slot (`0x60001000`) via `/dev/mem` or a UIO node, run V250 inference via the SDK, stream the ODMR CSV. That's *simpler and unified* vs "bare-metal firmware for C–E, then reprogram/reboot to Linux for F–G" (the kit can't boot both at once). **The PID's safety-critical real-time logic is all in fabric** (nv_pid_top HLS hardware, the 200 MHz watchdog counter, sector clamps, slew limiter) — the MSS is supervisory only — so Linux does **not** compromise the bounded-stability story. Net: going Linux likely *shrinks* total C–G effort, not just F.

Counter-point for all-bare-metal: a single self-contained `.elf` is a cleaner "embedded controller" artifact, SoftConsole is already set up, and C–E bare-metal are individually low-risk. The fork is real; decide it with F1's data.

---

## Sources

**Primary (bee SDK):** `drivers/vectorblox/vbx_cnn_api.{c,h}` (dual-path runtime + register protocol), `fw/firmware.bin` (2 MB instruction blob), `example/soc-c/{run-model.cpp,README.md,dts/mpfs_vbx.dtso}` (on-HW flow + UIO binding), `lib/libvbx_cnn_sim.so` (simulator build), `docs/CoreVectorBlox_IP_Handbook.pdf` + `VectorBloxPG.pdf` (register offsets/bit-fields if F1 needs more than the source gives).

**Web:** Microchip support #000017296 "Porting and Validation of VectorBlox 2.0.3 on PolarFire SoC Icicle Kit" (Yocto-only, MPFS250T, the decisive doc); `github.com/Microchip-Vectorblox/VectorBlox-SDK` (runtime + soc-c); `github.com/polarfire-soc/meta-polarfire-soc-yocto-bsp/releases` (prebuilt Icicle .wic); `github.com/polarfire-soc/polarfire-soc-bare-metal-examples` (mpfs-hal DDR init base for a bare-metal port).

**Corpus:** CoreVectorBlox IP Handbook (HB0919), MSS TRM (DS60001702 — DDR + L2), VectorBlox Programmer's Guide. **Known corpus gaps** (need the bee PDFs / source at execution time): exact CTRL_REG_* bit masks, step-by-step bare-metal DDR training, and the (undocumented) fabric-master cache-coherency protocol.
