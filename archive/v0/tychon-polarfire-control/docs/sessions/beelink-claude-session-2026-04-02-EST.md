# Beelink Claude Session — 2026-04-02 (EST)

> **Historical note (added 2026-10-12).** This summary records what was believed on 2026-04-02, after a Libero integration session on the Windows build host. Later work changed several of its conclusions. The text below is unchanged.
> - **Target silicon.** The build set the die to production `MPFS250T` because Libero 2025.2 had no package data for the `MPFS250T_ES` engineering-sample die. The kit on the bench carried ES silicon, and programming a production-target image failed on 2026-05-18 with an IDCODE class mismatch (branches `polarfire/bringup/part-A-FAILED-2026-05-18` and `polarfire/bringup/part-A-FAILED-2026-05-18-attempt-2`). A production kit replaced it, and the package designator was corrected to FCVG484E. See [`silicon_production_confirmed_2026-06-02.md`](../../../../../workers/polarfire-hybrid-control/docs/silicon_production_confirmed_2026-06-02.md) and [`orchestrator/INVENTORY.md`](../../../../../orchestrator/INVENTORY.md), section 2.
> - **VectorBlox size.** "No need to downsize to V250" did not hold. The programmed images went V500 (rung A, 2026-06-15) and then V250 (the shipped image). See [`rung_f_v250_on_silicon_results_2026-06-16.md`](../../../../../workers/polarfire-hybrid-control/docs/rung_f_v250_on_silicon_results_2026-06-16.md).
> - **PID placement.** Five attempts to attach the PID to the FIC_0 interconnect failed here, so the PID went to the top level. The two-slot design of 2026-06-17 made the PID registers reachable from the MSS over the fabric bus (M0 gains slave and M1 `pid_csr`, read and written bit-exact on silicon). See [`two_slot_demo_scope_2026-06-18.md`](../../../../../workers/polarfire-hybrid-control/docs/two_slot_demo_scope_2026-06-18.md).
> - **Timing and clocks.** The +0.165 ns worst slack and the 100 MHz / 200 MHz clocks describe this 2026-04-02 design only. The shipped two-slot image runs the PID at 125 MHz and the V250 at 200 MHz with about +1 ns of slack on each clock. See `orchestrator/INVENTORY.md`, section 4.1.
> - **Next steps.** The list at the end was superseded by the bring-up record in [`track0_bringup_runbook.md`](../../../../../workers/polarfire-hybrid-control/docs/track0_bringup_runbook.md) and by [`docs/case-study.md`](../../../../../docs/case-study.md).

## Goal
Libero SmartDesign integration: MSS + CoreVectorBlox + SmartHLS PID controller on MPFS250T Icicle Kit, targeting synthesis/P&R reports for Phase I SBIR deliverable.

---

## Decision: Use Icicle Kit Reference Design (not blank project)

**Context:** Originally planned to start from a blank MPFS250T-FCSG536 project. Changed plan when Jason confirmed he has the physical Icicle Kit board (MPFS250T_ES, FCVG484 package).

**Decision:** Use the bundled Icicle Kit reference design at:
```
C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\
```
With `VECTORBLOX MSS_BAREMETAL` flags to get VBX + bare-metal MSS pre-configured.

**Why:** Reference design has MSS already configured, all Icicle Kit pin constraints, VectorBlox subsystem wiring, and synthesis/P&R settings. Saves hours of manual configuration.

---

## Problem: Reference Design Incompatible with Libero 2025.2

The reference design (from 2023_02) was built for engineering sample silicon and older IP versions. Five patches were required:

### Patch 1: COREAXI4INTERCONNECT version (FIC0_INITIATOR_VBX.tcl)
- **File:** `script_support/additional_configurations/Vectorblox/FIC0_INITIATOR_VBX.tcl`
- **Change:** `COREAXI4INTERCONNECT:2.8.103` → `COREAXI4INTERCONNECT:2.9.100`
- **Why:** Old IP version not in Libero 2025.2 vault; v2.9.100 was downloaded successfully

### Patch 2: COREAXI4INTERCONNECT version (vectorblox_axi_resize.tcl)
- **File:** `script_support/additional_configurations/Vectorblox/components/vectorblox_axi_resize.tcl`
- **Change:** `COREAXI4INTERCONNECT:2.8.103` → `COREAXI4INTERCONNECT:2.9.100`
- **Why:** Same as above — VBX AXI resize component uses same IP

### Patch 3: Die name (main script)
- **File:** `MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl` line 116
- **Change:** `-die {MPFS250T_ES}` → `-die {MPFS250T}`
- **Why:** Libero 2025.2 has no package data for MPFS250T_ES (only `tpp/` directory, no `.ddf` files). Production `MPFS250T` with FCVG484 package works and is bitstream-compatible with ES silicon.

### Patch 4: MSS config DIE (baremetal config)
- **File:** `script_support/MPFS_ICICLE_MSS_baremetal.cfg` line 502
- **Change:** `DIE MPFS250T_ES` → `DIE MPFS250T`
- **Why:** MSS component generated for ES die cannot be imported into a non-ES project

### Patch 5: MSS config eMMC speed mode (baremetal config)
- **File:** `script_support/MPFS_ICICLE_MSS_baremetal.cfg` line 508
- **Change:** `EMMC_SPEED_MODE HIGH_SPEED_400_ES` → `EMMC_SPEED_MODE HIGH_SPEED_400`
- **Why:** ES-specific eMMC mode not valid for production die target

### Files NOT patched (comments only, harmless)
Many `.tcl` files have `# Part Number: MPFS250T_ES-FCVG484E` in comments — these are informational and don't affect functionality.

---

## What Worked

### 1. Reference design build with VECTORBLOX MSS_BAREMETAL ✅
After all 5 patches, the script ran successfully:
```
Ctrl+U → MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl → Arguments: VECTORBLOX MSS_BAREMETAL
```
Created project `MPFS_ICICLE_Vectorblox` with:
- MSS (bare-metal) configured for Icicle Kit
- CoreVectorBlox v1.1.12 (PRESET:1 = V1000) on FIC_0 slave 2
- VBX DMA through FIC_2
- Full Icicle Kit peripherals (PCIe, GPIO, PWM, I2C, UART, DMA, SRAM)
- All pin constraints for FCVG484 package

### 2. SmartHLS PID RTL import ✅
```
Ctrl+U → create_hdl_plus_nv_pid_top_top.tcl (no arguments)
```
Imported `nv_pid_top_top` as HDL+ core with AXI4 target bus interface defined.

### 3. PID instantiation at top level ✅
```
Ctrl+U → 05_add_pid_to_design.tcl (no arguments)
```
PID instantiated in `MPFS_ICICLE_KIT_BASE_DESIGN` with:
- Clock connected to `FIC_0_CLK` (shared with VBX control domain)
- Reset promoted as top-level port `PID_RESET`
- All AXI4 target signals promoted to top-level I/O (prevents optimization)
- Direct ports promoted: `PID_error`, `PID_u_AI_in`, `PID_ai_watchdog_timeout`, `PID_actuator_out_write_en`, `PID_actuator_out_write_data`

---

## What Did NOT Work

### 1. Attempt: Add PID inside FIC_0_PERIPHERALS with AXI2AXI bridge ❌
- Created COREAXITOAXICONNECT bridge for addr/ID width adaptation
- **Failed:** `sd_connect_pins` bus-level connection between `AXI2AXI_TO_PID:AXI4_MASTER` and `nv_pid_top_0:axi4target` — "not compatible" error
- **Root cause:** Likely VLNV mismatch between COREAXITOAXICONNECT bus interface and SmartHLS-generated HDL+ core bus interface

### 2. Attempt: Add 4th slave to FIC0_INITIATOR with `sd_configure_core_instance` ❌
- Tried to reconfigure existing COREAXI4INTERCONNECT to change NUM_SLAVES from 3 to 4
- **Failed:** `Error: Core ':::' is missing from the vault`
- **Root cause:** `sd_configure_core_instance` cannot change structural parameters (NUM_SLAVES) that affect port count

### 3. Attempt: Delete/recreate FIC0_INITIATOR with 4 slaves, signal-level wiring ❌
- Successfully deleted and recreated FIC0_INITIATOR with NUM_SLAVES:4 ✅
- Created modified `FIC0_INITIATOR_VBX_WITH_PID.tcl` with SLAVE3 at 0x60040000
- **Failed:** Signal-level wiring (`FIC0_INITIATOR:SLAVE3_AWADDR` etc.) — "Parameter 'to' is missing"
- **Root cause:** COREAXI4INTERCONNECT doesn't expose individual SLAVE3_* signal pins; they're grouped in `AXI4mslave3` bus interface. Also, clock pin `S_CLK3` doesn't exist when SLAVE3 has CLOCK_DOMAIN_CROSSING:false

### 4. Attempt: Direct bus connection PID ↔ FIC0_INITIATOR slave 3 ❌
- Tried `sd_connect_pins {"FIC0_INITIATOR:AXI4mslave3" "nv_pid_top_0:axi4target"}`
- **Failed:** Same "not compatible" bus interface error
- **Root cause:** Same VLNV mismatch issue as attempt 1

---

## Decision: PID at Top Level (Not on FIC Interconnect)

**What we chose:** Instantiate PID directly in `MPFS_ICICLE_KIT_BASE_DESIGN` with inputs tied to GND constants, outputs marked unused, and `syn_preserve` attribute to prevent optimization. No I/O pins consumed, no interconnect wiring.

**Why this is sufficient for Phase I:**
- `syn_preserve` ensures all PID internal logic (LUTs, registers, MACCs) is kept in synthesis
- Synthesis reports will show accurate resource utilization with both VBX and PID in the fabric
- Timing analysis will include PID logic on the FIC_0_CLK domain
- SmartPower will estimate PID power contribution
- AXI interconnect integration is Phase II work (when firmware needs to communicate with PID)

### 5. Attempt: Promote all PID ports as top-level I/O ❌
- Promoted ~40 AXI signals + direct ports as top-level I/O pins
- **Failed:** `Error: Number of I/O modules (383) exceeds the limit (144) of the selected device`
- **Root cause:** FCVG484 package only has 144 fabric I/O pads; PID AXI signals alone added ~240 pins
- **Fix:** Don't use I/O pins at all. Tie inputs to GND, mark outputs unused, use `syn_preserve`

**What's deferred to Phase II:**
- Wire PID AXI4 target to FIC_0 or FIC_1 interconnect (requires solving VLNV compatibility)
- May need to use SmartHLS `SMARTHLS` flag integration mechanism (but it conflicts with VECTORBLOX — they both use FIC0_INITIATOR slave 2)
- Consider emailing [vendor support e-mail withheld] for the correct Tcl commands per Microchip's recommendation

---

## RAG/Notebook LLM Findings

Queried Jason's grounded notebook LLM twice:

### Query 1: How to manually wire SmartHLS module to FIC0 interconnect
- **Finding:** No exact Tcl syntax available in corpus
- **Recommended:** Use the `SMARTHLS` flag in the reference design script for automated integration
- **Caveat:** SMARTHLS and VECTORBLOX share FIC0_INITIATOR slave 2 — mutually exclusive

### Query 2: AXI4 bus interface compatibility rules
- **Finding:** Compatibility is determined by Bus Interface Definition VLNV, not signal widths
- **Finding:** COREAXI4INTERCONNECT handles width adaptation internally — bridge not needed
- **Finding:** Can wire signal-by-signal to bypass VLNV checks (but pin naming was wrong)
- **Recommendation:** Contact [vendor support e-mail withheld] or local FAE for exact Tcl commands

---

## VectorBlox Configuration (for reference)

- **IP:** `Microchip:SolutionCore:core_vectorblox:1.1.12`
- **Preset:** 1 (V1000 — decided to keep as-is; switch to V250 if synthesis fails on resources)
- **M_AXI_DATA_WIDTH:** 128 bits
- **Clock:** PF_CCC_C1 PLL → 100 MHz (clk) + 200 MHz (clk_2x) from 50 MHz ref
- **FIC_0 slave 2:** VBX S_control (0x60030000-0x60030FFF)
- **FIC_2:** VBX AXIM (DMA to DDR)

---

## PID Module Interface (for reference)

- **Top module:** `nv_pid_top_top`
- **AXI4 target:** 5-bit addr, 1-bit ID, 64-bit data
- **Direct ports:**
  - `error[63:0]` — input, NV center frequency error
  - `u_AI_in[31:0]` — input, AI model output
  - `ai_watchdog_timeout` — input, watchdog flag
  - `actuator_out_write_en` — output, actuator valid
  - `actuator_out_write_data[31:0]` — output, actuator command

---

## FIC_0 Address Map (current)

| Slave | Address Range | Component |
|-------|--------------|-----------|
| 0 | 0x60001000–0x60001FFF | MSS_LSRAM (64KB) |
| 1 | 0x60000000–0x60000FFF | DMA_CONTROLLER |
| 2 | 0x60030000–0x60030FFF | Vectorblox S_control |

*Note: FIC0_INITIATOR was recreated with 4 slaves (SLAVE3 at 0x60040000) during failed attempts. This may need cleanup if Phase II integration starts from this project.*

---

## Operational Notes

- **Libero update prompt:** Declined — don't update mid-workflow to avoid introducing new IP version incompatibilities
- **Tcl console:** Not available until a project is open. Use Ctrl+U (Execute Script) when no project exists. Tcl console appears at bottom of window after project is created.
- **Tcl arguments:** `source script.tcl ARG1 ARG2` doesn't work from interactive console. Instead: `set ARG1 1; set ARG2 1; source script.tcl`
- **Project location:** `C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\MPFS_ICICLE_Vectorblox\`

---

## Synthesis & P&R Results (PASSED)

### Resource Utilization (MPFS250T)
| Resource | Used | Total | % |
|----------|------|-------|---|
| 4LUT | 62,837 | 254,196 | 24.72% |
| DFF | 64,079 | 254,196 | 25.21% |
| User I/O | 65 | 144 | 45.14% |
| uSRAM | 434 | 2,352 | 18.45% |
| LSRAM | 96 | 812 | 11.82% |
| Math/DSP | 164 | 784 | 20.92% |
| PLL | 2 | 8 | 25.00% |
| MSS I/O | 103 | 136 | 75.74% |

### Timing
- **Place & Route:** Passed on first seed (seed 0)
- **Worst Slack:** +0.165 ns (positive = timing met)
- **Multi-pass:** 1 of 20 iterations needed (stopped on first pass)

### Key Takeaway
VBX V1000 + PID + full Icicle Kit design fits comfortably at ~25% LUT utilization with timing closure. No need to downsize to V250.

### Reports Location
Copied to `~\OneDrive\Desktop\libero-reports-2026-04-02\`:
- `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt` — resource utilization
- `MPFS_ICICLE_KIT_BASE_DESIGN_timing_r1_s1.rpt` — timing analysis
- `MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r1_s1.rpt` — max timing violations
- `MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_min_r1_s1.rpt` — min timing violations
- `MPFS_ICICLE_KIT_BASE_DESIGN_iteration_summary.rpt` — P&R iteration summary
- `MPFS_ICICLE_KIT_BASE_DESIGN_fpga_mapper_resourceusage.rpt` — synthesis resource usage
- `synthesis_synplify.log` — full synthesis log

---

## Remaining Next Steps

1. **Run Verify Timing** — SmartTime detailed timing analysis (optional, P&R already shows +0.165ns slack)
2. **Run SmartPower** — Power estimation (optional for Phase I)
3. **Commit reports** — Push to `libero/reports/` in tychon-polarfire-control repo
4. **Phase II:** Wire PID AXI4 to FIC_0 interconnect (requires solving VLNV compatibility or using Microchip FAE guidance)

---

## Files Modified in Libero Installation (patches)

These are in `C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\reference_designs\Icicle_SoC\ref_design\`:

1. `MPFS_ICICLE_KIT_REFERENCE_DESIGN.tcl` — die MPFS250T_ES → MPFS250T
2. `script_support/MPFS_ICICLE_MSS_baremetal.cfg` — DIE and EMMC_SPEED_MODE ES removal
3. `script_support/additional_configurations/Vectorblox/FIC0_INITIATOR_VBX.tcl` — interconnect version
4. `script_support/additional_configurations/Vectorblox/components/vectorblox_axi_resize.tcl` — interconnect version

## Files Created in Project Repo

In `~\dev\projects\tychon-polarfire-control\libero\scripts\`:

1. `05_add_pid_to_design.tcl` — final working script (PID at top level)
2. `FIC0_INITIATOR_VBX_WITH_PID.tcl` — modified interconnect with 4 slaves (unused, from failed attempt)
3. `test_new_project.tcl` — diagnostic script (can be deleted)
