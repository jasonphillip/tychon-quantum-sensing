# VectorBlox V250 Deployment Reference (2026-06-02)

Consolidated, citation-grounded reference for deploying the hybrid stack on real MPFS250T silicon — both the **supported Linux path** and the **bare-metal port requirements** — plus the SDK/kit/silicon/OS compatibility matrix. Sourced from the VectorBlox SDK on bee, the control corpora, and web (paid APIs: exa + tavily; firecrawl MCP not connected this session). Companion to `docs/rung_f_vectorblox_inference_research_2026-06-02.md` (the F1/F2 architecture) and `docs/whole_process_strategy_audit_2026-06-02.md` (the strategy).

**Verification legend:** **[V]** verified from a fetched/read source · **[NC]** needs-check.

---

## 1. Compatibility matrix (SDK × core IP × kit × silicon × OS)

| SDK | Core IP | Kit | Silicon | OS | Status |
|---|---|---|---|---|---|
| **2.0.3** | core_vectorblox **2.0.1** | **Icicle** | **MPFS250T (prod)** | **Yocto Linux only** | Validated Mar 2026, V500/V250 [V, #000017296] |
| 2.0.3 | 2.0.1 | Video Kit | MPF300T | Linux **or bare-metal** | bare-metal MiV demo exists (§4) [V] |
| 3.0 | 3.0.001 | **Video Kit only** | MPF300T | Yocto Linux | "3.0 SDK only supports the Video Kit" [V, SDK README] |
| 3.0 | 3.0.001 | Icicle | — | — | **NOT supported** (no first-party flow) [V, by exclusion] |

- **Compatibility rule (Microchip staff, SDK issue #27):** *"Any 2.0.X core is compatible with any 2.0.X SDK."* Our pin (SDK 2.0.3 + core 2.0.1, `-c V250`) is the **correct supported pairing** for Icicle. [V]
- **Load-bearing constraint:** a `.vnnx` compiled for V1000 will **NOT** run on Icicle — must be V250 or V500. Our `-c V250` is correct. [V]
- **Caveat [NC]:** the published Icicle validation used **V500**; V250 is supported-by-spec but not separately demonstrated in #000017296.

---

## 2. The supported Linux path (recommended for F/G, likely C–G)

### Boot chain [V]
HSS (in eNVM, on E51) → U-Boot (on a U54) → Linux SMP. HSS finds its payload on a GPT partition with type GUID `21686148-6449-6E6F-744E-656564454649`. **The stock Icicle reference design boots HSS→U-Boot→Linux by default; enabling Linux needs no MSS/bitstream change** (you only re-program when you change the fabric, which you do to add the V250 — that's your change, not a Linux-enablement step). [V] **[NC]:** confirm the seed_7 VectorBlox merge didn't disable MMC/eNVM-HSS.

### UART mapping under Linux [V] — important, differs from bare-metal
- **HSS prints to MMUART0**; **U-Boot + Linux print to MMUART1**. Both on the J11/CP2108 (115200 8N1, no flow control). This affects rung D: under Linux the *login console* is MMUART1, not MMUART0.

### Prebuilt image (avoids a Yocto build) [V]
- The old `polarfire-soc/meta-polarfire-soc-yocto-bsp` is **ARCHIVED** → use **`linux4microchip/meta-mchp`**.
- Latest release **`linux4microchip-2026.04`**: `mchp-base-image-mpfs-icicle-kit.rootfs-20260430113402.wic.gz` (SMP). Pairs with **HSS 2026.04.1 + icicle-kit-reference-design `v2026.04`**, kernel 6.18.17, U-Boot 2026.04. **[NC]:** match the HSS version in our kit's eNVM to the chosen `.wic` (mismatch → HSS reflash).

### Write to SD (non-destructive, fastest iteration) [V]
1. `gunzip` the image (write the **uncompressed** `.wic`, never the `.gz`).
2. `sudo dd if=...rootfs.wic of=/dev/sdX bs=1M conv=fsync` — OR `bmaptool copy` (faster, with the matching `.wic.bmap`) — OR USBImager (GUI).
3. Insert SD, power-cycle. **SD takes precedence over eMMC**, so the factory eMMC is never touched.
- *(eMMC alt, persistent/slower: halt HSS at `>>`, `mmc` then `usbdmsc` exposes eMMC over the USB-OTG J16, write `.wic`, `Ctrl-C`, `boot`.)*

### Expose the V250 to userspace [V]
1. **generic-uio** for the control window — DT node `vbx@<FIC0 base> { compatible = "generic-uio"; reg = <0x0 0x60030000 0x0 0x1000>; interrupts = <124>; }` → appears as `/dev/uioN`; userspace `mmap`s the register page. (Our base `0x60030000` per the rung-F doc.)
2. **u-dma-buf** (ikwzm/udmabuf) for DMA tensor buffers — a `reserved-memory { compatible="shared-dma-pool"; no-map; }` pool → `/dev/udmabufN`; physical address from `/sys/class/u-dma-buf/udmabufN/phys_addr`. The VectorBlox runtime uses the **non-cached** `udmabuf-ddr-nc0`. **[NC]:** confirm a `udmabuf` region is present in the 2026.04 image (else add it / `modprobe u-dma-buf`).
3. **Runtime overlay (no kernel rebuild):** `make overlay` compiles `mpfs_vbx.dtso`→`.dtbo`, then configfs: `mkdir /sys/kernel/config/device-tree/overlays/vbx && cat my.dtbo > .../vbx/dtbo`. **Re-run every boot.**

### Run a custom .vnnx [V, #000017296]
In `VectorBlox-SDK-release-v2.0.3/example/soc-c`: set `kit = icicle` in the Makefile; edit `run-model.cpp` device → `/dev/udmabuf-ddr-nc0` and zero the `0x3000000000` PDMA src offset; `export VBX_UIO=/dev/uio3`; `make clean && make overlay && make`; then `./run-model <firmware.bin> <model>.vnnx TEST_DATA` (validate via CHECKSUM vs the host `sim-c`). For our 1000-row ODMR CSV: add a small loop feeding rows through `vbx_cnn_model_start`/`poll`/`wfi` with `rdcycle` timestamps.

### Realistic setup time [V]: ~½–1.5 days (SD + prebuilt image); +1–3 days only if forced to build Yocto (shouldn't be needed).

---

## 3. Bare-metal port requirements (if F2 stays bare-metal)

The runtime's `#else` branch already stubs the hooks; the port must supply:

1. **DDR bring-up** — lives in `mpfs-hal` (`nwc/mss_ddr.c`, `ddr_state_machine`/`ddr_setup`), callable bare-metal, but **only compiled when `IMAGE_LOADED_BY_BOOTLOADER == 0`**; when HSS boots the payload it already did DDR/L2/clock/IO/PMP init. The `mpfs-hal-ddr-demo` proves a pure bare-metal app can own DDR training. [V]
2. **Non-cached DDR — via the SEG address aliases, NOT page tables.** PolarFire SoC harts have no per-page DDR cacheability bit; cacheability = *which physical alias* you use (SEG0/SEG1 at APB `0x20005D00`/`0x20005E00`): **cached `0x80000000`**, **non-cached `0xC0000000`**, non-cached+WCB `0xD0000000` (32-bit; 64-bit aliases `0x10_…`/`0x14_…`/`0x18_…`). Place all V250 buffers in the **`0xC0000000` non-cached alias** → no flush/invalidate needed, no coherency hazard. (The Linux path does exactly this: `udmabuf-ddr-nc0` lands at phys `0xC8000000`, inside the 256 MB non-cached window.) [V]
3. **FIC0 MPU/PMP (mandatory).** At reset no non-CPU master can touch MSS memory until its MPU region is opened. Fabric masters use per-master MPUs: **MPU1 = FIC0 (16 PMP regions), APB base `0x20005000`.** Program a FIC0 PMP region covering the V250's DDR buffer or every V250 AXI access is rejected. [V]
4. **2 MB firmware staging.** `fw/firmware.bin` (2,097,152 B = `VBX_INSTRUCTION_SIZE`) is the instruction blob; copy it into the reserved non-cached DDR region and pass its address at init. [V]
5. **Polling, not interrupts** (drop the UIO IRQ wait). [V]

### Cache coherency — what Microchip DOES vs DOES NOT document (the risk surface) [V]
- **Documented:** the L2 is a *directory-based coherency manager* for the **U54/E51 core complex only** (the coherent TileLink switch). Fabric AXI masters reach DDR via **FIC0 → the separate, partially-connected AMBA I/O switch** (distinct from the coherent switch). The CoreAXI4DMAController UG §1.10 states verbatim: *"Cache coherence is not handled by CoreAXI4DMAController and remains the responsibility of the Firmware application."* The L2 `Flush64`/`Flush32` registers (`CACHE_CTRL_BASE 0x02010000`) flush **one block per write** — no range-invalidate; loop over 64-byte lines or use `fence`. `WAY_MASK_AXI4_SLAVE_PORT_0..3` control which L2 ways a fabric master may evict (affinity), **not** snoop/coherency.
- **NOT documented:** Microchip nowhere states a fabric AXI master on FIC0 snoops / is kept coherent with L2/L1. There is **no ACE/ACE-Lite/coherent fabric port** on PolarFire SoC (contrast Xilinx Zynq US+ ACP). So **CoreVectorBlox over FIC0 is non-coherent by construction** — the structural + §1.10 evidence is the strongest available confirmation.
- **Net:** coherency mechanics are the *same* on both paths (neither gets HW coherency); Linux just packages "use the non-cached alias" as `udmabuf-ddr-nc0`. Bare-metal must reproduce DDR training + FIC0 MPU + non-cached placement. The risk is **the absence of any Microchip guarantee of fabric-master snoop** — any design using the *cached* alias is unsupported and must hand-roll Flush64 maintenance.

---

## 4. Bare-metal reference that DOES exist (Video Kit only) [V]

The older `github.com/Microchip-Vectorblox/VectorBlox-Video-Kit-Demo` (release v2.0.3, Aug 2025) runs a **MiV soft-CPU bare-metal demo**: firmware + nets stored in **SPI flash**, the MiV executes inference with **no Linux**. This is the closest reference for an Icicle bare-metal port (adapt the firmware-load + AXI4-Lite control onto the MSS), but **no Microchip reference does VectorBlox bare-metal on Icicle/MPFS250T** — it would be net-new.

---

## 5. CoreVectorBlox control registers (bare-metal protocol) [V]

From the SDK `drivers/vectorblox/vbx_cnn_api.c` `#else` branch (`read_register(a,off) = ((volatile uint32_t*)a)[off]`):

| Symbol | Word off | Byte | Meaning |
|---|---|---|---|
| `CTRL_OFFSET` | 0 | 0x00 | status/control: SOFT_RESET, START, RUNNING, OUTPUT_VALID, ERROR bits |
| `ERR_OFFSET` | 1 | 0x04 | error register (`vbx_cnn_err_e`) |
| `MODEL_OFFSET` | 4 | 0x10 | model blob physical address |
| `IO_OFFSET` | (see src) | — | IO-buffer-array physical address |
| `VERSION_OFFSET` | 10 | 0x28 | IP version |

Init: `write(CTRL, SOFT_RESET); write(CTRL, 0);` then read version + size-conf (`VBX_CNN_SIZE_CONF_V250 = 0`). Exact `CTRL_REG_*` bit masks: read from the SDK source / the version-matched **`CoreVectorBlox_IP_Handbook.pdf`** on bee at F1 time. The state decode (`vbx_cnn_get_state`) and the run sequence are in the rung-F doc.

---

## 6. The #000017296 article content (preserved — JS/Salesforce-gated, exa-extracted 2026-06-02)

The single most load-bearing external doc ("Porting and Validation steps of VectorBlox 2.0.3 SDK on PolarFire SoC Icicle Kit with example") is behind a Salesforce JS gate that a plain downloader cannot fetch. Key extracted facts (attributed to the article, via exa):
- Based on a **Yocto `.wic` image on Icicle Kit (MPFS250T)**; validated ~March 2026 with MobileNetV2 on **V500**.
- FPGA design: icicle-kit-reference-design **v2025.07** with the `VECTORBLOX` arg (CNN wired to **FIC_0 for control, FIC_2 for CNN data**); swap `core_vectorblox:1.1.12`→**`2.0.1`**; keep **128-bit AXI_M**; size config **V500** (V250 valid); CoreAXI4Interconnect resize **ID width 3→4, address width →32**; leave interrupt disconnected; **slow VBX clocks 100/200→75/150 MHz** to close timing; program with FlashPro Express (HSS 0.99.49-v2025.07).
- On-target: Yocto (kernel `6.12.48-linux4microchip`), build libjpeg, edit `run-model.cpp` (device `/dev/udmabuf-ddr-nc0`, zero PDMA offset), Makefile `kit=icicle`, `make overlay && make` every boot, `export VBX_UIO=/dev/uio3`, `udmabuf` phys `0xC8000000`.
- The article cautions future GitHub releases may supersede it.

**These deployment specifics (esp. the FIC_2-for-data wiring and the 75/150 MHz de-rate) [NC] must be reconciled against the seed_7 design**, which may differ from the reference design the article uses.

---

## 7. Sources ingested into the corpus

See the ingestion runs (extending `polarfire-control-corpus`): VectorBlox-SDK runtime/soc-c/dts, the #000017296 content (this doc §6), `CoreVectorBlox_IP_Handbook.pdf` + `VectorBloxPG.pdf` (bee, version-matched), CoreAXI4DMAController_HB §1.10, `linux4microchip/meta-mchp` releases, U-Boot mpfs_icicle, polarfire-soc-documentation (updating-linux, dma-benchmarking, mpfs-memory-hierarchy), the DT-overlay support article, ikwzm/udmabuf, the Video-Kit bare-metal demo, and the CartPole/F1TENTH FPGA-control benchmark. Search: `/search-corpus polarfire-control-corpus "<query>"`.
