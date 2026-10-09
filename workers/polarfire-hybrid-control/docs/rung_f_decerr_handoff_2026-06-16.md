# Rung F — DECERR Handoff (2026-06-16)

> **✅ SUPERSEDED / RESOLVED — see `docs/rung_f_v250_on_silicon_results_2026-06-16.md`.** The §7.2
> root cause (wrong NPU IP `1.1.12/V500`) was correct: the `2.0.1/V250` rebuild makes inference run
> to completion on silicon (VERSION `0x20000000`; `vbx_probe` INFERENCE COMPLETED; `vnnx_smoke`
> out −2.9506). The DECERR/clk_2x leads in §3/§7.1 are moot. New finding: the rebuild broke the
> fabric PCIe @ `0x3000000000` (Linux boot-loop; workaround = disable the PCIe DT node).

Status snapshot for the next session. **Root-cause is NOT yet settled — do not treat the DECERR
read as confirmed.** This file records only facts + the one open question. (Companion analysis,
not yet reconciled with this: `docs/rung_f_clock_inspection_plan_2026-06-16.md`.)

Symptom: on the seed_7 bitstream (Production MPFS250T, rung A), the CoreVectorBlox V250 control
plane is alive but inference never advances — `CTRL` latches `0x02` (START), RUNNING/OUTPUT_VALID
never assert, V250 error register `0x60030004` = 0.

---

## 1. Known-good facts (confirmed this session)

- **Stock runtime also sticks.** `vbx_probe` (built against the UNMODIFIED stock SDK runtime
  `drivers/vectorblox/vbx_cnn_api.c` + `vbx_cnn_model.c`, following `run-model.cpp`'s TEST_DATA
  sequence, bounded poll) on the kit: `vbx_cnn_model_start ret=0`, then **CTRL=`0x00000002`,
  ERR=`0x00000000` held across the whole bounded poll → RESULT: STUCK.** So this is NOT a
  vnnx_smoke/custom-tool bug — it's a hardware/bitstream stall. (run-model itself can't cross-build
  on bee: no `libjpeg` in the riscv sysroot; kit has the cached udmabuf + `dma-proxy0..3` it needs.)
- **Model is sane.** `model_check_sanity` = **0** (sane); 1 input / 1 output.
  - `fcnn_v2_residual_dataset_a.vnnx`, **12,832 bytes**, sha256
    `6c5cd21ae9d4ce9793f8bc143c2c53d564140bde3df1fda1ec08a5a1602512eb` (DLOG-048). It is an **FCNN**
    (fully-connected residual), not a CNN; `.vnnx` = VectorBlox-compiled (`-c V250`) artifact.
- **Kit devices.** UIO: `uio0=fpga_lsram`, `uio1=dma-controller@60010000`, **`uio2=vbx@60030000`**,
  `uio3=pid@60001000`. udmabuf: `/dev/udmabuf-ddr-c0` (cached), **`/dev/udmabuf-ddr-nc0` phys
  `0x00000000C8000000`, size `0x02000000` (32 MB)**, `/dev/udmabuf-ddr-nc-wcb0`. `/dev/dma-proxy0..3`
  present. V250 control page (idle): VERSION `0x60030028` = `0x10010100`.
- **Already ruled out (design side):**
  - **Clock.** `core.clk` ← PF_CCC_C1 OUT0 = 100 MHz (`aclk_control_net_0`); `core.clk_2x` ← OUT1 =
    200 MHz (`aclk_net_0`). SDC: `create_generated_clock` ×2 (100) / ×4 (200) off the 50 MHz ref.
    Timing-clean in winning closure r6_s25: OUT0 **+1.723 ns**, OUT1 **+1.065 ns**. (clk_2x physical
    toggling on silicon NOT directly measured — would need FHB.)
  - **Reset.** Active-Probe read **high (deasserted)** for both `slow_reset_FABRIC_RESET_N` (V250
    core resetn) and `fast_reset_FABRIC_RESET_N` (resize-bridge ARESETN).
  - **MPU.** `mpu_fic2` all 16 regions `PMP=0xFFFFFFFFF`, `MODE=0x1F` (R/W/X, NAPOT, not disabled) —
    identical to `mpu_fic0`/`mpu_fic1` → **wide open** (so DECERR ≠ permission denial).
  - **Routing.** V250 M_AXI (128-bit) → `vectorblox_axi_resize` (128→64b, ID 3→4, CDC) →
    `VBX_AXIM` → MSS **`FIC_2_AXI4_TARGET`** (matches the Microchip reference's "CNN data on FIC_2").
    FIC2 interface clocking consistent: MASTER0 (V250 side) CDC on `M_CLK0`=100 MHz; FIC2-facing
    slave port + `FIC_2_ACLK` both on `ACLK`=200 MHz.

## 2. JTAG / SmartDebug facts

- **Chain verify PASSED.** Programmer `F31E000A` (Embedded FP6, Version EF9B). `read_device_status`:
  **IDCode = `1F81A1CF`**, Design Name `MPFS_ICICLE_KIT_BASE_DESIGN`, Design checksum `9F8A`,
  cycle count `2`.
- **Probe DB (built by `GENERATEDEBUGDATA` off the existing layout — no re-synth, no re-program):**
  `~/libero_seedsweep/seed_7/designer/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_probe.db`
  (376 MB). Also `…_live_probe_status.txt`, `…/run_prober.tcl`.
- **SmartDebug scripts/logs on bee:** inner `~/sd_probe.tcl` (broad) and
  `~/sd_probe2.tcl` (targeted); outer `~/sd_outer.tcl` /
  `sd_outer2.tcl`; logs `~/sd_run.log` / `sd_run2.log`. Invocation:
  `~/bin/libero SCRIPT:~/sd_outer2.tcl`; probes via `run_tool -name {SMARTDEBUG}
  -script {…}`; selection by wildcard `select_active_probe -name {*pat*}` then `read_active_probe`.
- **Exact Active-Probe points read (stuck-at-START), value = state of the named FF:**
  | Signal (net) | Backing FF | Value |
  |---|---|---|
  | `…/vectorblox_axi_resize_0/vectorblox_axi_resize_0/slaveARVALID[0]` | `…/MstConvertor_loop[0].mstrconv/rgsl/genblk2.arrs/currState[1]:Q` | **low** |
  | `…/slaveRVALID[0]` | `…/SlvConvertor_loop[0].slvcnv/rgsl/genblk3.rrs/currState[1]:Q` | **low** |
  | `…/slaveRREADY` | `…/MstConvertor_loop[0].mstrconv/rgsl/genblk3.rrs/currState[0]:Q` | **high** |
  | `…/int_masterARREADY` | `…/SlvConvertor_loop[0].slvcnv/rgsl/genblk2.arrs/currState[0]:Q` | **high** |
  | `…/slaveRRESP[1]` | `…/SlvConvertor_loop[0].slvcnv/rgsl/genblk3.rrs/sDat[3]:Q` | **high** |
  | `…/slaveRRESP[0]` | `…/SlvConvertor_loop[0].slvcnv/rgsl/genblk3.rrs/sDat[2]:Q` | **high** |
  | `FIC_0_PERIPHERALS_1/Vectorblox_ss_0/slow_reset_FABRIC_RESET_N` | `…/slow_reset/CORERESET_PF_C0_0/dff_15[0]:Q` | **high** |
  | `…/fast_reset_FABRIC_RESET_N` | `…/fast_reset/CORERESET_PF_C0_0/dff_15[0]:Q` | **high** |

  (All under hierarchy `FIC_0_PERIPHERALS_1/Vectorblox_ss_0/vectorblox_axi_resize_0/vectorblox_axi_resize_0/`.)
- **Reset values both high** (deasserted) — reset not holding the core or bridge.
- **RRESP snapshot:** `slaveRRESP[1:0]` = `0b11` = **DECERR** (AXI: 00 OKAY, 01 EXOKAY, 10 SLVERR,
  11 DECERR). Backing FFs `…/slvcnv/rgsl/genblk3.rrs/sDat[3]` and `sDat[2]`. **Why interpreted as
  DECERR:** `sDat` is the R-channel register-slice **data register** — written only when an R beat
  passes through the slice, resets to 0 → holding `11` implies a real R beat with DECERR propagated
  back toward the V250 (i.e., a read transaction completed with "address not decoded").

## 3. Caveats

- **Single async snapshot.** SmartDebug Active Probe is asynchronous; the stuck state is static, but
  `RRESP` when `RVALID=0` is nominally don't-care — the DECERR reading leans on register-slice latch
  semantics, not a captured-at-`RVALID` value. Not yet confirmed.
- **Exact boundary nets not directly probeable (NOTFOUND):** the top-level `*VBX_AXIM_ARVALID*` etc.,
  the V250's own `core_vectorblox_C0_0_M_AXI_ARVALID` / `…_RLAST`, and `PF_CCC_C1_0_PLL_LOCK_0` are
  not fabric flip-flops (IP boundary / hard-block outputs) → all the above is inferred from the
  adjacent resize-bridge channel registers, not the V250's own M_AXI pins.
- **Fabric digest representation mismatch.** `read_device_status` reports Fabric Digest
  `4c6f90cac75987fe50a54af23e02165d de6c073b294a6409bf400be4425fb256`, sNVM
  `9f52e797920f672e0c2cb60c39a11fe2 6c0ba3198c7d4d44d011e394de95a7f0` — do **not** match the
  rung-A-recorded `0769…C03DF8` / `EBF8…D32507`. IDCODE + design name + the exact seed_7 hierarchy
  confirm it IS seed_7, but the digest representation (or which digest field rung A captured) needs
  explaining.

## 4. Static address-decode facts

- **`vectorblox_axi_resize` SLAVE0 (FIC2-facing) decode window = `0x0`–`0xFFFFFFFF`** → `0xC8000000`
  is **inside** the bridge window, so the resize interconnect itself should not DECERR `0xC8000000`;
  the DECERR most likely originates **downstream at the MSS FIC2 → DDR decode** (to be confirmed).
- **TRM:** FIC2 is the path for **fabric-master access to non-cached DDR**.
- **SDK/runtime currently passes `udmabuf-ddr-nc0` phys `0xC8000000`** as the model/IO pointers
  (on-silicon readback: MODEL `0xc8000400`, IO `0xc8000000`).

## 5. Current untracked files (repo)

- `docs/rung_f_clock_inspection_plan_2026-06-16.md` (prior analysis; the "clock" framing in it is
  superseded by the ruled-out findings above — left as-is per instruction)
- `firmware/linux/vbx_probe.c` (temporary stock-runtime A/B probe; delete after root-cause settled)
- `docs/rung_f_decerr_handoff_2026-06-16.md` (this file)
- *Session artifacts on bee* (not in repo): `~/{sd_probe,sd_probe2,sd_outer,sd_outer2}.tcl`,
  `{sd_run,sd_run2}.log`, `vbx_probe.c`, `vbx_probe`; probe DB path in §2.
  *On kit:* `/root/bringup/vbx_probe`.

## 6. Open question (next session starts here)

**Is the DECERR caused by (a) MSS/FIC2 DDR decode / address aliasing, (b) a stale/misread RRESP
snapshot, or (c) a software pointer/address convention mismatch?**

- (a) MSS FIC2→DDR decode: does the MSS decode `0xC8000000` from a FIC2 fabric master to DDR, or
  does the fabric master need a different DDR alias (cf. SEG aliases, the PDMA `0x3000000000`
  64-bit-alias convention)? Static-checkable in the MSS config + corpus.
- (b) Confirm/refute the DECERR live: FHB-instrumented branch bitstream (event-counter/capture on
  the AR channel + `RRESP`-at-`RVALID`, frequency monitor on `aclk_net_0`) — re-synth, branch-only.
- (c) Address convention: should the runtime hand the V250 a different physical/alias address than
  the CPU-side `0xC8000000`?

---

## 7. Rank-1 read-only diagnosis — findings (2026-06-16, session 2)

**Method.** Read-only `/dev/mem` register reads on the kit (Linux `6.18.17-linux4microchip-2026.04.1`;
MSS-APB access at `0x20005000`/`0x20002000` is permitted — region not driver-claimed in `/proc/iomem`,
`STRICT_DEVMEM` allows non-RAM IO). Decoded against MSS TRM **DS60001702R** (Tables 3-41/3-42 PMP+MODE,
3-44/3-45 SEG, 6-1/6-2 FIC, 3-35 slave decode, §3.4.3) and the authoritative `mss_sysreg.h`
(SoftConsole 2022.2 mpfs_hal; the SYSREG bit map is silicon-fixed). Plus read-only RTL/source greps on
bee. Labels per the wiki evidence-discipline rule (2026-06-16); ground-truth = live registers + primary docs.

**Live-silicon register reads (priority-1 evidence):**

| Register | Addr | Raw | Decode |
|---|---|---|---|
| MPU3 (FIC2) PMPCFG0..7 | `0x20005200`+ | each `0x1f00000fffffffff` | MODE `0x1f` = R/W/X, NAPOT, unlocked; PMP = whole 38-bit space |
| MPU3 (FIC2) **STATUS** | `0x20005280` | `0x0` | **Failed=0 — no denied access ever latched** |
| MPU1 (FIC0)/MPU2 (FIC1) | `0x20005000`/`100` | open, STATUS=0 | context |
| SEG1[2] NC `0xC0000000` | `0x20005E08` | `0x00007f40` | AddrOff −192 → `0xC8000000`→DDR phys `0x08000000` (valid, in 2 GB) |
| SEG0[0] cached `0x80000000` | `0x20005D00` | `0x00007f80` | AddrOff −128 → `0x80000000`→DDR `0x0` (cross-check ✓) |
| SUBBLK_CLOCK_CR | `0x20002084` | `0x1fcdffef` | FIC2 bit26=1 → **FIC2 clock ENABLED** (FIC0/1/3 on too) |
| SOFT_RESET_CR | `0x20002088` | `0x00000000` | FIC2 bit26=0 → **FIC2 OUT of soft-reset** |

**FALSIFIED / CONFIRMED:**
- **FALSIFIED — "FIC2 MPU denies the V250."** MPU3 @ `0x20005200` (TRM-correct FIC2 block, 8 regions)
  wide-open + `STATUS.Failed=0`. The prior "mpu_fic2 16 regions" datum read a 16-region block (=FIC0/MPU1
  @ `0x20005000`) → that earlier reading is **STALE/RISKY**; FIC2/MPU3 is now read & decoded correctly.
  (TRM §3.4.3: an MPU denial *does* emit DECERR 2'b11, so a closed MPU3 *would* fit the symptom — but
  STATUS proves it never fired.)
- **CONFIRMED — SEG1 correct** (`0xC8000000`→DDR `0x08000000`).
- **CONFIRMED — `0xC8000000` is the right fabric address convention** (fabric→Seg1→S7 DDR-NC, decodes
  `0xC0000000–0xDFFFFFFF`). Raw-offset `0x08000000` disfavored (not in S7's window).
- **CONFIRMED — model/IO are 32-bit-confined** (`vbx_cnn_model_start` casts both to `(uint32_t)`; no MSB
  write on the non-TSNP FCNN path) → 64-bit aliases unreachable. (Answers original Q3.)
- **FALSIFIED — "MSS FIC2 not clock-enabled / in reset."** `SUBBLK_CLOCK_CR.FIC2`=1, `SOFT_RESET_CR.FIC2`=0.
- **FALSIFIED — "probe omits a firmware.bin instruction blob."** `run-model.cpp:151` takes `argv[1]` as the
  `.vnnx` model; arg2=`TEST_DATA`/image. No separate firmware arg. (Deployment-ref `<firmware.bin> <model>`
  ordering was an inaccurate extraction.) → `vbx_probe`/`vnnx_smoke` are faithful.
- **FALSIFIED — resize-bridge address mangling.** `vectorblox_axi_resize` `ADDR_WIDTH=38` (matches FIC2's
  38-bit `[37:0]` port); top-level `VBX_AXIM_ARADDR` is a full `[37:0]` wire → `0x00_C8000000` unmangled.

**Net (CONFIRMED):** the whole MSS-side FIC2→DDR path (routing, address convention, SEG1 translation, FIC2
MPU permission, FIC2 clock+reset) is **healthy at the register level. No `/dev/mem`-fixable cause found.**

**Narrowed live HYPOTHESIS (next session):** the V250 M_AXI read does not complete — either never issues
(stalls before AR) or issues with no response (hang in the V250 data master / the 100↔200 MHz CDC / the
resize-bridge↔FIC2 handshake). The single async `RRESP=0b11` is now **STALE/RISKY**: with all downstream
config CONFIRMED healthy a *real* DECERR has no plausible source, so `sDat=11` is most likely a stale
register-slice value (the §3 caveat), not a captured DECERR beat. Same *class* as the rung-E AXI hang.

**Proposed next discriminator (cheapest, avoids re-synth) — NEEDS APPROVAL (MSS write):**
- **MPU3 deny-all "address logger".** Save MPU3's 8 PMPCFG, write MODE=0 (disable) to all → FIC2 MPU denies
  every access. Re-run `vnnx_smoke`, read MPU3 STATUS `0x20005280`: **Failed=1** → V250 *does* issue a read,
  STATUS[37:0]=exact address (+R/W,ID) → reveals if it's the expected `0xC800_0x00` or wrong, **no bitstream/
  SmartDebug**. **Failed=0** → V250 *never* issues → stalls before the data master (pivot off the AXI path).
  Restore saved PMPCFG after. *Safety:* MPU3 gates only FIC2 (the already-dead V250); CPU/Linux use other
  MPUs → cannot affect Linux; fully reversible. Still a register write → presented, not executed.
- If the logger shows a valid in-range address that still hangs → **Rank 4 FHB-instrumented branch bitstream**
  (capture AR-handshake + `RRESP`-at-`RVALID` + whether any R beat returns) is the definitive next step.

### 7.1 MPU3 deny-all address-logger — EXECUTED 2026-06-16 (session 2, approved, reversible)

**Procedure (all guardrails honored):** saved MPU3 PMPCFG0..7 (`0x1f00000fffffffff` ×8) + STATUS (`0x0`)
before any write; wrote MODE=0 (Match=OFF, **LOCKED never set**) to all 8 MPU3 regions only → FIC2 deny-all
(verified MODE=0x00 on all 8); ran `vbx_probe` bounded (≤600 polls + `timeout 20` + subprocess 35 s — *not*
`vnnx_smoke`); read MPU3 STATUS immediately after; `try/finally` restored MPU3 and re-read. No SEG/PID/other
writes; no bitstream/Libero/SmartDebug.

**Raw result:**
- `vbx_probe` under deny-all: `init OK`, MODEL=`0xc8000400`, IO=`0xc8000000`, sanity=0, START latched
  (CTRL=`0x02`), **600 polls all CTRL=`0x02` ERR=`0x00` → STUCK** — *identical* to the open-MPU behavior.
- **MPU3 STATUS after run = `0x0` (Failed=0)** — no denied access latched.
- Restore verified: PMPCFG0..7 back to `0x1f00000fffffffff`, STATUS `0x0`, `RESTORED_OK`.

**Interpretation (evidence contract):**
- **Hypothesis tested:** the V250 issues an M_AXI read that fails/hangs at the FIC2→DDR boundary.
  **Prediction:** deny-all → MPU3 STATUS.Failed=1 with Addr ≈ `0xC800_0x00`.
- **FALSIFIED.** STATUS stayed 0 **and** the symptom was invariant to the MPU state (open vs deny-all) →
  two independent indicators that **no V250 M_AXI transaction reaches the FIC2 MPU.**
- **CONFIRMED (HIGH):** the prior `RRESP=0b11` DECERR was **not** a real beat (no transaction occurred) →
  it was a stale register-slice value. The entire MSS-side FIC2→DDR path is exonerated.
- **New localization:** the fault is **upstream of FIC2** — in the V250 core or the resize-bridge 100↔200 MHz
  CDC. Register-level diagnosis is now exhausted.
- **Caveat:** assumes the MPU3 STATUS latch is functional (couldn't be positively fired — only the V250 masters
  FIC2, so no independent control transaction is possible); symptom-invariance corroborates independently.

**Re-opened live HYPOTHESIS:** `clk_2x` (compute clock, `aclk_net_0`, 200 MHz) not *physically toggling* on
silicon. The clock-plan doc FALSIFIED this at the **netlist** level (wiring/CCC/SDC/STA all clean) but
explicitly never measured silicon toggling. "Control slave + M_AXI on `clk` (running) work, but the compute
sequencer on `clk_2x` never steps → never issues the M_AXI fetch" fits this result exactly.

**Next falsifier (needs hardware — gated, NOT executed):** (1) Rank 3 SmartDebug (read-only): re-probe the
resize-bridge **master-side** (V250-facing) AR FSM/address on a fresh run — does the V250 ever assert AR?
(distinguishes "V250 never issues" from "AR stuck in CDC before the MPU"). (2) Rank 4 FHB branch bitstream:
frequency-monitor `aclk_net_0` to confirm/refute `clk_2x` toggling + an AR-handshake event counter.

### 7.2 ROOT CAUSE — wrong CoreVectorBlox IP version **and** size in the seed_7 bitstream (2026-06-16, session 2)

**The bitstream's NPU is CoreVectorBlox `1.1.12` / size `V500`. The entire software stack targets `2.0.1` / `V250`.**

**CONFIRMED facts (two independent ground-truth sources agree):**
- *Generated artifact* — `…/seed_7/component/work/core_vectorblox_C0/core_vectorblox_C0.cxf`:
  `<componentRef library="SolutionCore" name="core_vectorblox" vendor="Microchip" version="1.1.12"/>`
  (file ref `…/SolutionCore/core_vectorblox/1.1.12/…`). Only `1.1.12` is in the seed_7 project vault.
  IP config: `M_AXI_DATA_WIDTH=128`, `PRESET=1`, `m_axi_araddr [31:0]`. [priority-2]
- *Live silicon* — VERSION reg `0x60030028` = `0x10010100`, decoded vs HB0919 Rev 2.0 Table 4
  (bits[15:8]=Size: 0=V250/1=V500/2=V1000; bits[31:28]=Major): **ProductID=0 ✓, Size=1=V500, Major=1 (v1.x).** [priority-1]
- *Stack* — SDK **2.0.3** runtime (`vbx_cnn_api.c`); `.vnnx` compiled **`-c V250`** (sha256 `6c5cd21a…`).
  Supported pairing (CLAUDE.md / deployment-ref): SDK 2.0.x ↔ core **2.0.1** ↔ matching-size `.vnnx`.
  Porting guide #000017296 (deployment-ref §6) lists **"swap `core_vectorblox:1.1.12`→`2.0.1`"** as required — **never applied**.
- *Fix feasible* — core_vectorblox **2.0.1** is present in the Libero 2025.2 **MegaVault**
  (`…/MegaVault/…/core_vectorblox/{1.0.2,1.1.12,1.1.15,2.0.1}`); just not imported into seed_7.

**Evidence contract:**
- **Symptom:** control plane works (init/VER/START, CTRL=0x02), but no RUNNING/OUTPUT_VALID/ERROR and — per §7.1 — **no M_AXI transaction reaches FIC2.**
- **Hypothesis:** a 1.1.12/V500 NPU cannot execute a model built for 2.0.1/V250 — the AXI4-Lite control map is
  compatible enough for init/START, but the model/instruction format is not, so the sequencer never begins
  fetching → no M_AXI, no RUNNING, no ERROR.
- **Prediction → Test → Raw result:** the instantiated IP would not be 2.0.1/V250 → read `.cxf` + live VER + vault → `1.1.12`, Size=V500, Major=1; vault only 1.1.12.
- **Confidence:** **CONFIRMED** that the bitstream NPU is 1.1.12/V500 vs the stack's 2.0.1/V250 (artifact + silicon agree). **HIGH** that this is the cause of the stall (explains every symptom incl. §7.1; matches the documented mandatory swap; no contradicting evidence). Causal link is INFERRED, not yet directly proven.
- **Next falsifier (= the fix):** rebuild seed_7 with core_vectorblox **2.0.1** + size **V250**, re-synth/P&R/`.job` on a branch, reprogram (rollback verified), re-run `vbx_probe` → expect RUNNING/OUTPUT_VALID + dequantized outputs. Still stuck → mismatch was not the sole cause.

**Supersedes** the §7.1 "clk_2x not toggling" lead: the no-M_AXI result is explained by the wrong-IP, and clk_2x
almost certainly toggles (OUT0=`clk` from the same locked CCC/PLL runs the working control plane). clk_2x is now a
tertiary check only if the fix fails.

**Also corrects a STALE/RISKY project belief:** CLAUDE.md / rung-A docs assert "CoreVectorBlox V250 2.0.1 in fabric
by construction." Live silicon + the generated `.cxf` show **1.1.12 / V500**. (The rung-A *fabric-digest* match only proves
the programmed bitstream == the seed_7 closure byte-for-byte; it never proved the closure contained the *intended* IP.)

**Fix plan (re-synth + reprogram — gated; rollback CONFIRMED):**
- Rollback: `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job`, sha256
  `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a` (✓ matches documented), program via
  `libero/scripts/program_kit.tcl`; rung-A PASS evidence in `libero/reports/2026-06-15-program/`.
- Fix: import 2.0.1 from MegaVault → reconfigure instance (size **V250**, 128-bit M_AXI, ID/addr to match the resize
  bridge) → regenerate `Vectorblox_ss` → re-synth/P&R/export `.job` on a branch → program → re-run.
- Design fork: **V250** (matches the existing `-c V250` `.vnnx` + CLAUDE.md intent — recommended) vs **V500**
  (the Microchip-*demonstrated* Icicle size; would instead require recompiling the `.vnnx` `-c V500`).

### 7.3 FIX EXECUTION — CoreVectorBlox 2.0.1 + V250 rebuild (2026-06-16, session 2; approved) — BUILD IN FLIGHT

Working on an **isolated clone** (rung-A seed_7 untouched): `~/libero_seedsweep/seed7_vbx201_v250`
(project `MPFS_ICICLE_Vectorblox.prjx`, ProjectLocation self-path rewritten to the clone).

Steps completed (all Libero batch Tcl, logs on bee `~/recfg_*.log`, `build_vbx201.log`):
1. **Vault:** global Libero vault pointed at the MegaVault (`change_vault_location` → `…/MegaVault/Libero_SoC_v2025.2_MegaVault`) — it has 2.0.1; the active Common vault had only 1.1.12. **TO REVERT** to `C:/Microchip/Common/vault` after.
2. **Core swap:** `delete_component core_vectorblox_C0` → `create_and_configure_core … core_vectorblox:2.0.1 -params {"M_AXI_DATA_WIDTH:128" "PRESET:0"}`. **Gate #4 PASSED:** generated `core_vectorblox_C0.cxf` → `version="2.0.1"`, `PRESET value="0"` (=V250), `M_AXI_DATA_WIDTH=128`.
3. **Resize fix:** the 2.0.1 core M_AXI ID is **4-bit** (`arid/rid[3:0]`) vs 1.1.12's 3-bit → reconfigured `vectorblox_axi_resize` (COREAXI4INTERCONNECT 2.9.100) `ID_WIDTH:3→4` (recipe extracted from generated `.v`, single-param sub). Matches deployment-ref §6 "resize ID 3→4".
4. **SmartDesign rewire:** `open_smartdesign` + `sd_update_instance` for the stale instances at each level, regenerated bottom-up — Vectorblox_ss (core+resize), FIC_0_PERIPHERALS (Vectorblox_ss_0), MPFS_ICICLE_KIT_BASE_DESIGN (FIC_0_PERIPHERALS_1) + `build_design_hierarchy` — **all rc=0, no non-benign errors**. (The `AXIM RID[0-8]` vs resize `SLAVE0_RID[0-3]` ID-width-truncation warning is **pre-existing in the rung-A baseline** `Vectorblox_ss_DRC.xml` → benign.)
5. **Build IN FLIGHT:** `run_tool SYNTHESIZE → PLACEROUTE → VERIFYTIMING → GENERATEPROGRAMMINGDATA → export_prog_job` (job `polarfire_hybrid_control_vbx201_v250`, export dir `…/seed7_vbx201_v250/export`). V250 < V500 (which already closed at 100/200 MHz), so timing expected to close; **will verify the timing report before programming.**

**Pre-program checkpoint (prepared; gates per the approval):**
- **Rollback artifact CONFIRMED:** `/mnt/nas/backups/bee-polarfire-hybrid-control/polarfire_hybrid_control.job`, sha256 `d5f3eb4ebd713d687f2b7dae566537c128262bb4cb20831c0e5524c7cc29e53a` (✓ matches documented). Rollback command: the operator-mode flow in `libero/scripts/program_kit.tcl` (PROGRAM action only).
- **New `.job`:** path `…/seed7_vbx201_v250/export/polarfire_hybrid_control_vbx201_v250.job` (sha256 + timing-pass PENDING build completion).
- **No boot-media risk:** programming will use **PROGRAM action only** (FPGA fabric) — does NOT touch eMMC/sNVM/SPI/HSS/U-Boot/Linux (satisfies hard-stop #5).
- **Post-program plan:** read VERSION `0x60030028` first (expect **major=2, size_config=0/V250**); bounded `vbx_probe` (≤600 polls); if it advances → bounded `vnnx_smoke` + record dequantized outputs.

**Outcome: PENDING** (synthesis/P&R running on bee, ~50 min).
