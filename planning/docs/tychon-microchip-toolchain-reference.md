> Original: claude.ai project document, created 2026-04-01. Edited for publication: names of other people and business details removed.

# Tychon AI — Microchip FPGA Toolchain Reference

**Compiled:** March 20, 2026  
**Author:** Jason Phillip (Tychon AI) — AI-assisted compilation  
**Plan:** 90-day build plan  
**Hardware context:** Beelink GTI15 (i9-285H, 64GB, Win11 Pro), PolarFire SoC Icicle Kit (MPFS250T), target RTPF500ZT, dual DGX Sparks (Arm/Blackwell)

---

> **⚠️ PLAN SDK SCOPE NOTE (added 2026-04-01):** This plan targets **VectorBlox SDK v2.0.3** (not v3.0). The CoreVectorBlox IP available in MegaVault is v2.0.1. Using SDK v3.0 to generate .vnnx binaries for IP core v2.0.1 creates risk of silent AXI bus deadlocks due to potential V-ISA instruction set or header format changes across the major version boundary. The v3.0 information below is retained as reference material for later-stage evaluation when Microchip releases a matching v3.x IP core. For this plan build and export scripts, always use SDK v2.0.3. See Repo 3 architecture decision and DLOG entry for full rationale.

---

## Version Summary Table

| Tool | Current Version | Download URL | License Type |
|------|----------------|--------------|--------------|
| VectorBlox SDK | **v3.0** (Feb 10, 2026) | [GitHub Releases](https://github.com/Microchip-Vectorblox/VectorBlox-SDK/releases) | Free (bundled with Libero Silver + CoreVectorBlox license) |
| Libero SoC Design Suite | **v2025.2** | [Download Page](https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga/libero-software-later-versions) | Silver (free, node-locked) covers up to MPF500T/MPFS250T; Gold required for RT PolarFire |
| SmartHLS | **2025.2** (bundled with Libero) | Included in Libero v2025.2 unified installer | Included under Libero license (since v2024.1) |
| CoreVectorBlox IP | Tied to Libero version | Via Libero IP Catalog (MegaVault) | Separate free license — merge with Libero Silver |
| Microchip Power Estimator (MPE) | v2023.1 (for RT PolarFire) | [MPE Spreadsheet (.xlsm)](https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/power-estimator/3-06-00024__polarfire_power_estimator.xlsm) | Free |

---

## 1. VectorBlox SDK

### Version & Download

**Version confirmed:** VectorBlox SDK v3.0 was released **Feb 10, 2026** on GitHub (commit `bff635b`, tagged `release-v3.0`, marked Latest). Release history: v1.4.4 → v1.4.4.1 → v2.0 (Dec 2024) → v2.0.1 (Mar 2025) → v2.0.2 (May 2025) → v2.0.3 (Aug 2025) → **v3.0 (Feb 10, 2026)**.

**GitHub repo:** https://github.com/Microchip-Vectorblox/VectorBlox-SDK  
**GitHub org:** https://github.com/Microchip-Vectorblox (4 repos: SDK, Video-Kit-Demo, SoC-Video-Kit-Demo, assets)  
**Product page:** https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/vectorblox  
**Programmer's Guide PDF:** https://github.com/Microchip-Vectorblox/VectorBlox-SDK/blob/master/docs/VectorBloxPG.pdf

**System requirements:** Ubuntu 20.04, 22.04, or 24.04 (WSL supported — run from home directory with correct permissions). Requires `git` and `git-lfs`.

### Supported Operators (TFLite ops — from project knowledge + SDK docs)

Based on SDK v3.0 and corroborated by the Fast-Track report's analysis:

- `CONV_2D` (use for 1D convolutions as (1×k) kernels)
- `DEPTHWISE_CONV_2D`
- `FULLY_CONNECTED`
- `RELU` / `RELU6`
- `ADD` (for residual connections)
- `MEAN` (for global average pooling)

**Critical constraint:** No native `CONV_1D` operator. Implement 1D convolutions as `CONV_2D` with kernel shape (1×k) on input tensors reshaped to (1×N×channels).

**Action required:** Clone the v3.0 release and read the full supported-ops list end-to-end. The above is derived from research reports and third-party analysis — validate the frozen TFLite graph against the actual ops list BEFORE training at scale. v3.0 may have added operators not in v2.0.x.

### Compilation Flow (vnnx_compile)

The end-to-end flow as documented in the SDK README and tutorials:

1. Start with a trained model (PyTorch, TensorFlow, ONNX)
2. Quantize to INT8 TFLite format
3. Compile: `vnnx_compile` converts `.tflite` → `.vnnx` (Binary Large Object / BLOB) and `.hex`
4. Simulate: Use VectorBlox bit-accurate Python simulator for accuracy validation
5. Deploy: Load `.vnnx` to SPI Flash / DDR on target board

Tutorials in `tutorials/` directory demonstrate the pipeline for various pre-built models.

### Libero Integration

The CoreVectorBlox IP block is instantiated within a Libero SmartDesign project. Integration steps (based on Video Kit reference designs and product documentation):

1. Open Libero SoC Design Suite
2. In IP Catalog (MegaVault), search for "CoreVectorBlox" — download if not present
3. Instantiate CoreVectorBlox in SmartDesign alongside the PolarFire SoC MSS
4. Connect via AXI interface to a Fabric Interface Controller (FIC) port
5. The `.vnnx` binary is loaded into DDR memory at runtime; CoreVectorBlox reads it from there

**Reference designs to study:**
- `VectorBlox-SoC-Video-Kit-Demo` (GitHub) — shows SmartDesign integration with MSS + VectorBlox
- `VectorBlox-Video-Kit-Demo` (GitHub) — PolarFire FPGA (non-SoC) variant
- Icicle Kit reference design: https://github.com/polarfire-soc/icicle-kit-reference-design

**CoreVectorBlox license:** Separate free license required — generate from the Microchip website, then merge with your Libero Silver license per section 7.3 of the Libero quick-start guide.

### Device Compatibility

| Device | SDK Support | Notes |
|--------|-------------|-------|
| PolarFire SoC Video Kit | **Official target** for SDK v2.0.x | Full on-board execution supported |
| PolarFire SoC Icicle Kit (MPFS250T) | **Not officially listed** as SDK target | Icicle Kit is not the Video Kit — different device, fewer LEs. Needs verification. |
| RT PolarFire SoC (RTPF500ZT) | **Not supported in this plan** | Same fabric as commercial PolarFire. This plan: use simulator + Libero resource reports. Later: on-board execution. |

**strategy:** Use VectorBlox bit-accurate simulator for inference validation. Use Libero resource utilization reports (post-synthesis) for FPGA sizing on RTPF500ZT. Full on-board execution deferred to later work.

### Key Technical Notes

- VectorBlox core uses ~60,000 LEs (~12.5% of RTPF500ZT's 481K LEs)
- AI inference power: <5W claimed by Microchip
- All VNNX models (<4 KB each) can reside simultaneously in 33 Mb LSRAM
- Model-swap latency is in the clock-cycle regime (no reconfiguration needed)
- The SDK includes a bit-accurate simulator that validates hardware accuracy in software

---

## 2. Libero SoC Design Suite

### Version & Download

**Current version:** v2025.2  
**Download page:** https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga/libero-software-later-versions  
**Release notes (PDF):** https://ww1.microchip.com/downloads/aemdocuments/documents/FPGA/swdocs/libero/libero_soc_v2025_2_release_notes.pdf  
**Online release notes:** https://onlinedocs.microchip.com/oxy/GUID-D6BA99C6-E1C8-44EB-9669-702FBBAA3897-en-US-26/index.html  
**Online help docs (v2025.2):** https://onlinedocs.microchip.com/oxy/GUID-AFCB5DCC-964F-4BE7-AA46-C756FA87ED7B-en-US-19/index.html

### System Requirements (Windows)

- **Windows 11 required** — v2025.1 was the last release to support Windows 10
- 64-bit operating system
- **32 GB RAM recommended** for MPF500T, MPFS460T, and RT PolarFire FPGA/SoC devices
- 16 GB minimum for other devices
- Administrative privileges required for installation
- FlexLM v11.19 daemons for licensing

**Also supported:** Red Hat Enterprise Linux (RHEL), AlmaLinux, Ubuntu (64-bit). ModelSim/QuestaSim ME on Ubuntu requires additional libraries — Libero provides `check_linux_req.sh` script.

### Device Support

| Device | Libero v2025.2 Support | Notes |
|--------|----------------------|-------|
| RTPF500ZT/TS/TL/TLS | **Yes** (introduced in v2024.1) | Full synthesis, P&R, timing, power |
| RTPFS460ZT/TS/TL/TLS | **Yes** (RT PolarFire SoC) | FC1509 package introduced in v2025.1 |
| RTPFS160ZT/TS/TL/TLS | **Yes** (RT PolarFire SoC) | |
| MPFS250T (Icicle Kit) | **Yes** | Long-standing support |
| MPFS460T/TS/TL/TLS | **Yes** | |
| MPF500T (commercial PolarFire) | **Yes** | |

### License Setup (Node-locked Silver)

1. Go to https://www.microchipdirect.com and search for "LIB" licenses
2. Select "Libero Silver 1Yr Floating License for Windows/Linux Server" (free)
3. Generate license tied to your machine's MAC ID
4. For CoreVectorBlox: separately request the free CoreVectorBlox license from the VectorBlox product page
5. **Merge the two licenses** per Section 7.3 of the Libero Software Quick-Start Guide

**Silver license covers:** All PolarFire, PolarFire SoC, SmartFusion2, IGLOO2, ProASIC3, Fusion devices. **Gold license required** for RT PolarFire and large-density devices — check with Microchip support whether a free evaluation Gold license is available.

### Bundled Tools (Unified Installer, v2025.2)

Starting with v2025.2, the unified installer bundles:

- **Libero SoC Design Suite** (project management, SmartDesign, IP Catalog/MegaVault)
- **SmartHLS 2025.2** (C++ → Verilog HLS compiler)
- **Synplify Pro ME** (Synopsys synthesis engine, upgraded to W-2025.03M-SP1-1)
- **ModelSim ME / QuestaSim ME** (Siemens simulation — QuestaSim replaces ModelSim going forward)
- **SmartTime** (static timing analysis)
- **SmartPower** (post-P&R power analysis with VCD activity factors)
- **SmartDebug** (on-chip debugging for PolarFire SoC, PolarFire, SmartFusion2, IGLOO2, RTG4)
- **FlashPro Express** (device programming without full Libero install)
- **MegaVault** (IP core catalog)
- **Identify ME** (Synopsys debug tools)
- **Programming and Debug Tools**

### Key Technical Notes

- v2025.2 adds TMR synthesis support for selective flip-flop hardening (critical for RT PolarFire rad-tolerance)
- No support for Classic Constraint Flow — migration required for legacy projects
- RTPF500ZT was first introduced in Libero v2024.1 (not a new addition in v2025.2)
- v2025.2 adds REF_CLK I/O enablement from Transceiver QUAD4 for RT PolarFire SoC devices
- Enhanced PMP lockdown strategies with Expert Mode for direct register configuration
- Post-layout back-annotated timing simulation for differential input I/O (new in v2025.2)

---

## 3. SmartHLS

### Version & Download

**Current version:** SmartHLS 2025.2  
**Bundled with Libero:** Yes, since v2024.1. No separate download needed.  
**Product page:** https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/smarthls-compiler  
**User guide (online):** https://onlinedocs.microchip.com/v2/keyword-lookup?keyword=fpgahls&redirect=true&version=latest  
**GitHub examples:** https://github.com/MicrochipTech/fpga-hls-examples  
**What's new in 2025.2:** https://onlinedocs.microchip.com/oxy/GUID-AFCB5DCC-964F-4BE7-AA46-C756FA87ED7B-en-US-19/index.html (Section 1.3)

### C++ to Verilog Flow

1. Write design in C++ (functions with SmartHLS pragmas for pipelining, loop unrolling, etc.)
2. Software simulation: compile and test as normal C++ to verify functionality
3. HLS compilation: SmartHLS converts C++ → Verilog, generating AXI-interface IP modules
4. Co-simulation: ModelSim/QuestaSim verifies cycle-accurate hardware behavior matches software
5. Libero integration: SmartHLS-generated IP is imported into SmartDesign as a component
6. Synthesis + P&R: Libero synthesizes the full design targeting the selected PolarFire device
7. SmartHLS auto-generates fMAX and resource utilization reports

**Command-line interface:** `shls` command (add SmartHLS/bin to PATH)  
**IDE launch:** `shls -g`

### C++ Standard Support

- **Default:** C++14 (configurable since SmartHLS 2025.1)
- **C++17:** Set `CXX_STANDARD=17` in the HLS Makefile
- **Compiler framework:** Clang/LLVM 15.0.7 (upgraded from 14.0.6 in SmartHLS 2025.1)

### SmartDesign Integration

SmartHLS generates Verilog IP modules with AXI interfaces that integrate directly into Libero SmartDesign projects alongside other IP blocks (including CoreVectorBlox). Integration paths:

- **AXI4-Target interface:** SmartHLS module acts as a memory-mapped peripheral accessed by the RISC-V MSS
- **AXI4-Initiator interface:** SmartHLS module initiates DMA-style transfers to/from DDR
- **SoC Accelerator flow:** `shls soc_accel_proj_pnr` builds the full bitstream with SmartHLS accelerator integrated into the RISC-V SoC

The SmartHLS + VectorBlox coexistence in one SmartDesign is architecturally straightforward — each connects to a separate FIC port on the PolarFire SoC MSS.

### PID-Relevant Examples & Notes

No direct PID controller example in SmartHLS, but relevant resources:

- **Motor controller example** (SmartHLS docs): Achieves ~2 µs deterministic latency at 200 MHz
- **SmartHLS Training Session 3:** AXI Interfaces to DDR & Mi-V Soft Processor on PolarFire Video Kit (GitHub: fpga-hls-examples)
- **Sobel Filter example:** Demonstrates pipelined datapath with streaming interfaces
- **Canny Edge Detection:** HW/SW co-simulation example

**PID on SmartHLS estimate:** PID = ~3 multiplies, 2-3 adds, 1 accumulation. At 200 MHz with pipelining, expect 50-250 ns per PID update — 600×+ margin over the 150 µs budget.

**SmartHLS 2025.1 key improvement for Tychon:** Improved multiplication splitting with refined Math block characterization. This directly impacts PID timing estimates — tighter, more accurate resource and performance predictions for multiply-heavy control loops.

### Key Technical Notes

- SmartHLS generates automatic fMAX and resource reports — directly supports your Deliverable 3 timing analysis
- Multi-threading API enables concurrent PID computation and sensor I/O
- Co-simulation crash fixes in 2025.1 (Windows-specific buffer flush issue resolved)
- New `FORCED_MATH_BLOCK_PIPELINE_DEPTH` parameter replaces older automatic multiply mode settings
- Automatic on-chip instrumentation (`shls instrument_init`) for hardware debugging with Synopsys Identify

---

## 4. Device Architecture

### RTPF500ZT (RT PolarFire SoC) Overview

**Datasheet:** https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/DataSheets/RT-PolarFire-FPGA-Datasheet-00004122A.pdf  
**Product overview:** https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/ProductBrief/Radiation-Tolerant-PolarFire-FPGA-Product-Overview.pdf  
**AN4903 (RTPF500T vs RTPF500ZT differences):** https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ApplicationNotes/ApplicationNotes/Differences_Between_RTPF500T_and_RTPF500ZT_AN4903.pdf  
**RT PolarFire product page:** https://www.microchip.com/en-us/products/fpgas-and-plds/radiation-tolerant-fpgas/rt-polarfire-fpgas  
**RT PolarFire SoC product page:** https://www.microchip.com/en-us/products/fpgas-and-plds/radiation-tolerant-fpgas/rt-polarfire-soc

| Parameter | RTPF500ZT Value |
|-----------|----------------|
| Logic Elements | 481,000 |
| Embedded SRAM (LSRAM) | 33 Mb |
| DSP Blocks (Math Blocks) | 1,480 |
| SerDes Transceivers | 24 lanes, up to 12.7 Gbps |
| Configuration Technology | SONOS non-volatile (immune to SEU) |
| TID Tolerance | >100 krad (confirmed >300 krad per testing) |
| SEL Threshold | LET >80 MeV-cm²/mg |
| Configuration Upsets | **None** (non-volatile SONOS fabric) |
| Data Upset Rate | Better than 10⁻¹⁰ errors/bit-day (GEO solar minimum with TMR) |
| Qualification | **QML Class Q qualified** (Class V roadmap) |
| Package | Hermetically sealed ceramic 1509-pin CCGA (1.0mm column pitch) |
| RISC-V MSS | 5-core (1×E51 monitor + 4×U54 application), 64-bit, Linux-capable |
| Operating Temp | –55°C to +125°C (Military grade available) |

**RTPF500T vs RTPF500ZT key differences (AN4903):**
- RTPF500ZT has improved SEL GPIO performance
- Enhanced on-orbit programming methodology
- ECC on internal sNVM/pNVM
- System Controller Sleep Mode (SCSM) support
- Supports both JTAG and SPI-target in-flight reprogramming
- RTPF500T is **not recommended for new designs** — RTPF500ZT replaces it

**Engineering samples status:** RT PolarFire SoC engineering samples available since July 2025.

### MPFS250T (Icicle Kit) Overview

**Product page:** https://www.microchip.com/en-us/products/fpgas-and-plds/system-on-chip-fpgas/polarfire-soc-fpgas  
**Icicle Kit page:** Included on PolarFire SoC product page  
**Reference design:** https://github.com/polarfire-soc/icicle-kit-reference-design (updated Jan 2026)  
**PolarFire SoC documentation:** https://github.com/polarfire-soc/polarfire-soc-documentation

| Parameter | MPFS250T Value |
|-----------|---------------|
| Logic Elements | ~254,000 |
| Embedded SRAM | ~18 Mb |
| DSP Blocks | ~784 |
| SerDes | 4×12.7 Gbps |
| RISC-V MSS | Same as RTPF500ZT (1×E51 + 4×U54) |
| Config | SONOS non-volatile |
| Package | Commercial (FCSG536 on Icicle Kit) |
| Kit features | PCIe Gen2, GbE, USB 2.0, CAN, embedded FlashPro6 |

### FIC Port Architecture

PolarFire SoC devices provide **four Fabric Interface Controllers (FIC)** connecting the RISC-V MSS to the FPGA fabric:

| FIC Port | Bus Width | Typical Use |
|----------|-----------|-------------|
| FIC0 | 64-bit AXI4 | High-bandwidth MSS→Fabric (DMA, video, AI accelerator) |
| FIC1 | 64-bit AXI4 | Fabric→MSS (fabric peripherals accessing DDR) |
| FIC2 | 32-bit APB3 | Low-bandwidth control registers |
| FIC3 | 64-bit AXI4 | Additional high-bandwidth path |

**Architecture for Tychon (from Playbook v4, Deliverable 3):**
- **VectorBlox CoreVectorBlox** → FIC0 (dedicated high-bandwidth path for AI inference DMA)
- **SmartHLS PID controller** → FIC1 or FIC3 (separate FIC port to avoid bus contention)
- **Control registers** → FIC2 (APB3 for configuration, status, watchdog)

### Memory Map

The RISC-V MSS provides a memory-mapped view of the FPGA fabric through the FIC ports. Key memory regions:

- **DDR memory:** Shared between MSS and fabric via FIC ports
- **LSRAM:** Direct fabric access for VectorBlox model storage and PID state
- **µSRAM:** 64×12 distributed RAMs for small buffers (FIFOs, LUTs)
- **sNVM:** Secure non-volatile memory for configuration data, keys, IDs

The RISC-V MSS configures the system at boot via the Hart Software Services (HSS) zero-stage bootloader, then the fabric operates autonomously.

### Key Differences (Commercial PolarFire SoC vs RT PolarFire SoC)

| Feature | MPFS250T (Commercial) | RTPF500ZT (RT) |
|---------|----------------------|-----------------|
| Logic Elements | ~254K | 481K |
| SRAM | ~18 Mb | 33 Mb |
| DSP Blocks | ~784 | 1,480 |
| Rad Tolerance | None (commercial) | TID >100 krad, no config upsets |
| SEL | Not rated | LET >80 MeV-cm²/mg |
| TMR Support | Available in Libero | Available + TMR synthesis automation |
| Package | Plastic (commercial packages) | Hermetic ceramic CCGA |
| Qualification | Commercial / Industrial | QML Class Q (Class V roadmap) |
| sNVM ECC | No | Yes (RTPF500ZT) |
| Temperature | –40°C to +100°C (Industrial) | –55°C to +125°C (Military) |
| role | **Dev/prototype platform** | **Target production device** |

---

## 5–7. Deferred Tools (URLs Only)

### 5. Microchip Power Estimator (MPE)

**MPE Spreadsheet download (.xlsm):**  
https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/power-estimator/3-06-00024__polarfire_power_estimator.xlsm

**Note:** The direct download URL above may require authentication. If it does, navigate to the PolarFire product page → Documentation tab → Power Estimator.

**MPE User Guide (PDF):**  
https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/microsemi_polarfire_and_polarfire_soc_fpga_power_estimator_user_guide_ug0897_v5.pdf

**SmartPower User Guide:** Accessible within Libero SoC help documentation or via:  
https://onlinedocs.microchip.com/oxy/GUID-661342AD-346C-44CE-8927-EE521FC8D331-en-US-4/GUID-4961DBC7-EAE1-4441-BD13-6A628AE8C275.html

**RT PolarFire power data:** The RT PolarFire datasheet references "Microchip Power Estimator (MPE) - v2023.1 PolarFire, RT PolarFire and PolarFire SoC" for static and dynamic power data.

### 6. SmartTime (Static Timing Analysis)

SmartTime is bundled with Libero SoC v2025.2. Documentation accessible within Libero help or via the online docs portal:  
https://onlinedocs.microchip.com (search for SmartTime)

### 7. FlashPro6 User Guide

**Programming User Guide (covers FlashPro6):**  
https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_FPGA_and_PolarFire_SoC_FPGA_Programming_User_Guide_VB.pdf

**Programming and Debug Tools v2025.2 Release Notes:**  
https://www.microchip.com/content/dam/mchp/documents/FPGA/swdocs/libero/programming_debug_v2025_2_release_notes.pdf

**Note:** The Icicle Kit has an embedded FlashPro6 programmer (no external programmer needed for development).

---

## Document URLs for Download

### Datasheets
- RT PolarFire FPGA Datasheet: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/DataSheets/RT-PolarFire-FPGA-Datasheet-00004122A.pdf
- PolarFire FPGA Datasheet: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/DataSheets/PolarFire-FPGA-Datasheet-DS00003831.pdf
- RT PolarFire Product Overview: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/ProductBrief/Radiation-Tolerant-PolarFire-FPGA-Product-Overview.pdf

### Application Notes
- AN4903 (RTPF500T vs RTPF500ZT): https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ApplicationNotes/ApplicationNotes/Differences_Between_RTPF500T_and_RTPF500ZT_AN4903.pdf
- AN3782 (TMR and Spatial Separation): Referenced in RT PolarFire docs — search Microchip site
- FPGA Power Comparison Tool: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/campaign/Comparing_FPGA_Power.pdf

### Release Notes
- Libero SoC v2025.2: https://ww1.microchip.com/downloads/aemdocuments/documents/FPGA/swdocs/libero/libero_soc_v2025_2_release_notes.pdf
- Libero SoC v2025.1: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/swdocs/libero/libero_soc_v2025_1_release_notes.pdf
- Libero SoC v2024.1 (RTPF500ZT introduction): https://coredocs.s3.amazonaws.com/Libero/2024_1/Tool/libero_soc_v2024_1_release_notes.pdf
- Programming & Debug v2025.2: https://www.microchip.com/content/dam/mchp/documents/FPGA/swdocs/libero/programming_debug_v2025_2_release_notes.pdf

### User Guides
- MPE User Guide (UG0897): https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/microsemi_polarfire_and_polarfire_soc_fpga_power_estimator_user_guide_ug0897_v5.pdf
- Programming User Guide: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_FPGA_and_PolarFire_SoC_FPGA_Programming_User_Guide_VB.pdf
- Transceiver User Guide: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/UserGuides/PolarFire_FPGA_and_PolarFire_SoC_FPGA_Transceiver_User_Guide_VB.pdf
- SmartHLS User Guide (online): https://onlinedocs.microchip.com/v2/keyword-lookup?keyword=fpgahls&redirect=true&version=latest
- Libero SoC v2025.2 Help (online): https://onlinedocs.microchip.com/oxy/GUID-AFCB5DCC-964F-4BE7-AA46-C756FA87ED7B-en-US-19/index.html

### VectorBlox SDK
- VectorBlox SDK (GitHub): https://github.com/Microchip-Vectorblox/VectorBlox-SDK
- VectorBlox Programmer's Guide (PDF): https://github.com/Microchip-Vectorblox/VectorBlox-SDK/blob/master/docs/VectorBloxPG.pdf
- VectorBlox SDK Releases: https://github.com/Microchip-Vectorblox/VectorBlox-SDK/releases
- SoC Video Kit Demo: https://github.com/Microchip-Vectorblox/VectorBlox-SoC-Video-Kit-Demo

### SmartHLS Examples
- HLS Examples (GitHub): https://github.com/MicrochipTech/fpga-hls-examples

### PolarFire SoC Ecosystem
- Icicle Kit Reference Design: https://github.com/polarfire-soc/icicle-kit-reference-design
- PolarFire SoC Documentation: https://github.com/polarfire-soc/polarfire-soc-documentation
- Video Kit Reference Design: https://github.com/polarfire-soc/polarfire-soc-video-kit-reference-design

### Tools & Power
- MPE Spreadsheet: https://ww1.microchip.com/downloads/aemDocuments/documents/FPGA/ProductDocuments/power-estimator/3-06-00024__polarfire_power_estimator.xlsm
- Libero Download Page: https://www.microchip.com/en-us/products/fpgas-and-plds/fpga-and-soc-design-tools/fpga/libero-software-later-versions
- License Ordering: https://www.microchipdirect.com/product/search/all/LIB

---

## Unresolved Questions

1. **CoreVectorBlox IP version for Libero 2025.2:** Need to check what version of CoreVectorBlox is available in the MegaVault IP catalog with Libero v2025.2 installed. This determines which SDK version is actually compatible with the IP block.

2. **VectorBlox on Icicle Kit (MPFS250T):** The product page states the Video Kit is the evaluation platform. Need to confirm whether VectorBlox can run on the Icicle Kit's MPFS250T (fewer LEs, different resource profile). The Icicle Kit may not have enough LSRAM/LEs for CoreVectorBlox + your PID design.

3. **SmartHLS 2025.2 release notes:** The online docs have a "What's New in SmartHLS 2025.2" section but I could not access the full content. Install Libero v2025.2 and check the bundled release notes for specific 2025.2 improvements (the 2025.1 improvements are documented above).

4. **RT PolarFire SoC datasheet (RTPFS series):** The RT PolarFire FPGA datasheet (DS00004122) covers the FPGA variant. The RT PolarFire SoC devices (RTPFS460ZT, RTPFS160ZT) share the same fabric but add the RISC-V MSS. Need to find the specific RT PolarFire SoC datasheet or confirm it's the same document with SoC-specific addenda.

5. **FIC port bus widths on RTPF500ZT specifically:** The FIC architecture described above is from PolarFire SoC documentation. Need to confirm the same FIC configuration applies to RT PolarFire SoC devices (expected to be identical, but verify).

6. **SmartHLS PID examples:** No PID controller example found in SmartHLS documentation or GitHub examples. The motor controller example is the closest analog. Consider using the OpenCores PID controller (Verilog, 9-cycle, proven on Actel/Microchip fabric) as an alternative starting point.

7. **(Later) Libero Silver vs Gold for RTPF500ZT:** this plan targets MPFS250T (Icicle Kit) and simulator — Silver license is sufficient. For later on-hardware work with RTPF500ZT, confirm whether Gold/Platinum license is required. If so, contact Microchip for a defense evaluation license ahead of later work.

---

## Notes for Next Steps

**Immediate actions after receiving this document:**

1. **Clone VectorBlox SDK v3.0** from GitHub (`release-v3.0` tag). Read the Programmer's Guide PDF and the full supported-ops list end-to-end. This is the hard constraint for your MLP and CNN architectures. Check for any new operators added since v2.0.x.

2. **Install Libero SoC v2025.2** on the Beelink GTI15. Verify RTPF500ZT is available as a target device. Check the MegaVault IP catalog for CoreVectorBlox version.

3. **Generate and merge licenses** (Libero Silver + CoreVectorBlox). Create a test project targeting MPFS250T (Icicle Kit) to confirm your dev environment works end-to-end.

4. **Download the MPE spreadsheet** and run a preliminary power estimate using the resource counts from your Playbook v4 (VectorBlox ~60K LEs, PID <1K LEs + 4 DSPs, RISC-V subsystem ~0.12W, total 5-9W budget).

5. **Prototype the full compilation pipeline:** PyTorch → ONNX → TFLite INT8 → `vnnx_compile` → VectorBlox simulator. Use a toy model first to validate the chain before investing in architecture design.

