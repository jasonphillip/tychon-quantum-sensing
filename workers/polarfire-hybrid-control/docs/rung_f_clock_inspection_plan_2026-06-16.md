# Rung F — V250 Compute-Clock Inspection & Fix Plan (2026-06-16)

**Status: prepared while bee is offline.** This doc front-loads the Beelink session so it
executes (grep + one SmartDesign edit) instead of discovers. The on-silicon symptom is fully
captured (`firmware/linux/reports/2026-06-15-bringup/rung_cdef_results_2026-06-15.md`); the fix
is a seed_7 **design-side** investigation that can only run on bee (Libero + the seed_7 project
at `~/libero_seedsweep/seed_7/`; the NAS holds only the `.job` + ELF artifacts, not
the project source). **Blocker (RESOLVED 2026-06-16 ~08:27 EDT — bee powered on):** inspection executed.

> ## ⚠️ UPDATE 2026-06-16 — INSPECTION COMPLETE. THE CLOCK HYPOTHESIS BELOW IS **FALSIFIED**.
>
> The on-bee netlist inspection found the V250 `clk`/`clk_2x`/`resetn` are **correctly
> integrated and timing-clean**. The "compute clock/enable not closed" root cause in
> DLOG-055 / the memory / the runbook was an *inference from the silicon symptom*, and it
> is **wrong**. See **FINDINGS** immediately below; the original hypothesis is retained
> afterward only as the falsified prior. The real direction is the V250 **M_AXI
> data-master → MSS DDR** path (network-BLOB fetch), not the clock.

---

## FINDINGS — on-bee netlist inspection (2026-06-16) — clock/reset RULED OUT

**Conclusion: the V250 clock and reset are correctly wired, enabled, configured at the
proper 1×/2×, constrained, and timing-clean. The clock is NOT the rung-F fault.** Evidence
chain (all from the seed_7 project on bee, `~/libero_seedsweep/seed_7`):

1. **Wiring** (`component/work/Vectorblox_ss/Vectorblox_ss.v`): `core_vectorblox_C0.clk_2x`
   ← `aclk_net_0` ← `PF_CCC_C1.OUT1_FABCLK_0` (lines 444, 523); `.clk` ← `aclk_control_net_0`
   ← `PF_CCC_C1.OUT0_FABCLK_0` (443, 522). Distinct nets, same CCC, paired OUT0/OUT1 —
   **exactly Handbook Note 1**. Not dangling, not tied to `clk`.
2. **CCC config** (`PF_CCC_C1/PF_CCC_C1.cxf`): `GL0_0` (→OUT0→`clk`) = **100 MHz**,
   `IS_USED=true`, `FABCLK_USED=true`, DIV=12; `GL1_0` (→OUT1→`clk_2x`) = **200 MHz**,
   `IS_USED=true`, `FABCLK_USED=true`, DIV=6. Same VCO (1200 MHz). Clean 2×, both enabled.
3. **SDC** (`PF_CCC_C1_..._PF_CCC.sdc`): `create_clock -period 20` on REF_CLK (50 MHz);
   `create_generated_clock -multiply_by 2` → OUT0 (100 MHz); `-multiply_by 4` → OUT1
   (200 MHz). Both are real, constrained generated clocks at the correct 1×/2×.
4. **Timing** (winning closure `MPFS_ICICLE_KIT_BASE_DESIGN_timing_r6_s25.rpt`):
   - `Vectorblox_ss_0/PF_CCC_C1_0/.../OUT0` — 100 MHz — **Worst Slack +1.723 ns (MET)**
   - `Vectorblox_ss_0/PF_CCC_C1_0/.../OUT1` — 200 MHz — **Worst Slack +1.065 ns (MET)**
   The 200 MHz `clk_2x` domain is analyzed and meets timing with healthy positive slack at
   the slow corner. A `mindelay_repair_report.rpt` exists → Handbook Note 2 was satisfied.
5. **Reset**: core `resetn` = `slow_reset_FABRIC_RESET_N` (1× CORERESET, gated by PLL_LOCK +
   INIT_DONE). Control slave (reset by `resetn`, Handbook §5.4) is alive on silicon → `resetn`
   is deasserted. The 2×-domain `fast_reset` (gates the AXI-resize bridge `ARESETN`) is on the
   *running* 200 MHz clock, gated by PLL_LOCK + INIT_DONE → releases.

**`[NC]` 75/150 MHz de-rate — resolved:** the design runs **100/200 MHz** and closes STA with
+1.065 ns at the slow corner. No de-rate to 75/150 was applied or needed. The de-rate also does
not explain the symptom (a too-fast compute clock corrupts results / errors; it does not produce
a clean "never asserts RUNNING").

### Corrected root-cause direction — V250 M_AXI → MSS DDR (network-BLOB fetch)

With a good clock, "START latches (`CTRL=0x02`) but RUNNING/OUTPUT_VALID/ERROR never assert"
best fits the core **stalling on its first M_AXI read** — it cannot fetch the network BLOB from
the model pointer (`0xc8000000`, in `udmabuf-ddr-nc0`) over its data master, so it never reaches
RUNNING and never times out (no ERROR). Same *class* as the rung-E severed-AXI hang — a fabric
AXI path that doesn't complete.

M_AXI path traced (structurally present in RTL): `core_vectorblox_C0` M_AXI (128-bit) →
`vectorblox_axi_resize_0` (128→64-bit data + 200→100 MHz CDC, `ARESETN=fast_reset_FABRIC_RESET_N`)
→ `Vectorblox_ss.SLAVE0_*` (`AXIM`, 64-bit/38-bit-addr) → `FIC_0_PERIPHERALS` `AXIM_SLAVE0` port
→ top-level `FIC_0_PERIPHERALS_1_VBX_AXIM_*` nets. `FIC_1` is present and clocked
(`CLOCKS_AND_RESETS_FIC_1_CLK`).

**Record-grounded leading cause (mined 2026-06-16 from `docs/vectorblox_deployment_reference_2026-06-02.md`):**
Our PID patches touch only `FIC_0_PERIPHERALS_1_AXI4mslave0` (the MSS→fabric PID slot) — **none
touch the V250 data master / FIC_1 / FIC_2 / MSS MPU** (confirmed: `libero/scripts/patch_smartdesign_*.py`
+ git log). The V250 data path is inherited from the `MPFS_ICICLE_Vectorblox` base design (canonical
reference on bee: `/c/Microchip/Libero_SoC_2025.2/SmartHLS/SmartHLS/reference_designs/Icicle_SoC/ref_design/MPFS_ICICLE_Vectorblox/`).
The deployment reference already specified the V250-data requirements and flagged `[NC]` that seed_7
may differ — neither was reconciled (first silicon, inference never ran):

1. **FIC MPU window — MANDATORY; prime suspect (matches the symptom exactly).** Deployment ref
   §FIC0-MPU/PMP `[V]`: *"At reset no non-CPU master can touch MSS memory until its MPU region is
   opened … Program a FIC0 PMP region covering the V250's DDR buffer or every V250 AXI access is
   rejected."* If seed_7's MSS MPU has no fabric→DDR window over `0xC8000000`, the V250 BLOB fetch
   is rejected → core stalls before RUNNING, no timeout → exactly the silicon symptom. MSS MPU regs
   at APB `0x20005000` — **potentially runtime-fixable from Linux with no re-synth**; testable today.
2. **Data-FIC routing.** The Microchip reference wires CNN **data on FIC_2** (control on FIC_0).
   Confirm which FIC the seed_7 V250 data master (`VBX_AXIM`/`AXI4mmaster0`) actually uses and that
   it reaches DDR. (Deployment ref line 101 explicitly flagged this `[NC]`.)
3. **Non-cached alias** — software already correct (`udmabuf-ddr-nc0` @ `0xC8000000`, inside the
   `0xC0000000` 256 MB non-cached window; deployment ref §non-cached-DDR `[V]`).

**Next steps (cheap → decisive):**
- (a) **On bee:** diff seed_7's V250 data-master FIC routing + MSS MPU config against the canonical
  reference design (which FIC carries `VBX_AXIM`; does the MSS MPU open a fabric→DDR window?).
- (b) **On silicon (read-only):** read the seed_7 MSS MPU register state at APB `0x20005000` to see
  if the fabric→DDR window is open (needs the MPU register layout — MSS TRM DS60001702, in corpus).
- (c) **If closed + runtime-programmable:** open the FIC MPU DDR window from Linux, re-run
  `vnnx_smoke` → if inference completes, **rung F closes with NO bitstream change**. Only if the MPU
  is bitstream-locked or the data-FIC routing is wrong does this become a re-synth (branch-only).

The fix is therefore **not** a CCC re-config — it is restoring/enabling the V250 fabric-master
DDR access (likely an MSS-config + interconnect/address-map change, possibly convergent with the
rung-E two-slot integration), then re-synth + re-program on a branch.

---

## Original hypothesis (2026-06-16, pre-inspection) — **FALSIFIED, retained as prior**

## Root-cause hypothesis — `clk_2x` not connected/running in seed_7

CoreVectorBlox has **two clock inputs**, per the IP Handbook
(`~/.corpus/polarfire-control-corpus/raw/vectorblox-sdk-docs-bee/CoreVectorBlox_IP_Handbook.md`
§5.1, Table 5-1, DS50003112B):

| Signal | Function | What it clocks |
|---|---|---|
| `clk` | System clock | **Control slave (S_AXI) + data master (M_AXI)** are synchronous to it |
| `clk_2x` | 2× clock | **MathBlocks + LSRAM resources** — i.e. the *compute datapath* — at 2× `clk`. Must be synchronous to and in phase with `clk`. |
| `resetn` | System reset (active low) | All core functions incl. control slave + data master |

Handbook Note 1 (§5.1): `clk` and `clk_2x` **must come from the same CCC** on PolarFire, on a
**paired output set — OUT0+OUT1 _or_ OUT2+OUT3, not one from each pair**. Note 2: P&R must have
**"Repair Minimum Delay Violations"** enabled to fix clk↔clk_2x skew hold violations.

### Symptom → cause mapping (every observation is consistent with `clk_2x` absent)

On-silicon, 2026-06-15 (seed_7 bitstream on the Production MPFS250T):

| Observation | Implication |
|---|---|
| Control slave @ `0x60030000` solid — **196,247 reads, 0 hangs** | `clk` is connected and running ✓ |
| `vbx_cnn_init` ("control plane alive"), SOFT_RESET responds, START latches `CTRL=0x02` | control register path on `clk` works; core is **out of reset** ✓ |
| RUNNING (`0x04`) / OUTPUT_VALID (`0x08`) / ERROR (`0x10`) **never assert** (196k samples all `0x02`) | the compute SM (MathBlocks/LSRAM, on `clk_2x`) **never advances** ✓ |
| **No** ERROR bit ever set | not an error condition — the engine simply isn't being stepped ✓ |

Because the control slave *and* data master are on `clk` (§5.2/§5.3, "synchronous to clk; reset by
resetn"), a live, responsive control slave proves `clk` + `resetn` are fine. The **only** core
sub-block on a *different* clock is the compute path on `clk_2x`. START latching but RUNNING never
asserting is the exact signature of **`clk_2x` not toggling**. This also reconciles the strategy-audit
`[NC]`: the V250 was de-rated to **75/150 MHz** on Icicle — 75 MHz = `clk`, 150 MHz = `clk_2x`.

**Alternatives to rule out during inspection** (the netlist disambiguates):
- `clk_2x` *tied to `clk`* (1× instead of 2×) — core may stall or misbehave; check the driving net.
- `clk_2x` present but **failing hold** (Note 2 not set in P&R) — would more likely produce ERROR or
  garbage than a clean never-advance, but verify the P&R flag and the CCC phase alignment.
- `resetn` held asserted — **excluded** by the responsive control slave (§5.4: control slave is reset
  by resetn; it works), but confirm the net for completeness.

---

## Inspection (on bee, no full GUI — mirror the FIC_0 extraction method)

The FIC_0 address map was resolved by grepping component Verilog, not the Address Editor GUI
(`docs/fic_0_address_map_2026-05-18.md`). Do the same for the V250 clock nets.

```bash
SEED=~/libero_seedsweep/seed_7
# 1. Find the CoreVectorBlox instance + its clk / clk_2x / resetn port connections.
grep -rniE '\.clk_2x|\.clk\b|\.resetn|VECTORBLOX|CoreVectorBlox|vbx' \
     "$SEED/component/work" --include=*.v | grep -iE 'clk_2x|\.clk|resetn|VECTORBLOX' | head -60
# 2. Identify the net on .clk_2x(...) — is it a real CCC OUTx, tied to .clk's net, or dangling/0?
# 3. Find the CCC (PF_CCC) config: which OUT0..OUT3 are enabled, their frequencies + phase, and
#    which outputs route to the V250. Confirm a paired 2x (OUT0/1 or OUT2/3), phase-aligned.
grep -rniE 'PF_CCC|OUT0_FABCLK|OUT1_FABCLK|OUT2_FABCLK|OUT3_FABCLK|_FREQ|PLL' \
     "$SEED/component/work" --include=*.v | head -60
# 4. Confirm the P&R "Repair Minimum Delay Violations" flag for the closure (Note 2).
grep -rniE 'REPAIR_MIN|MinDelay|TDPR|Hold' "$SEED" --include=*.tcl --include=*.xml 2>/dev/null | head
```

**Decision tree from step 2:**
- `clk_2x` net is dangling / tied 0 / tied to `clk` → **confirmed root cause.** Apply the fix.
- `clk_2x` driven by a CCC OUTx → check that OUTx is the **2× of `clk`'s source**, phase-aligned,
  same CCC, paired output. If 1× or wrong CCC → fix the CCC config. If correct → pivot to the
  hold-violation hypothesis (verify Note-2 P&R flag; check timing report for the `clk_2x` domain).

---

## Fix (SmartDesign, on a branch — do NOT disturb the rung-A seed_7 programming)

1. Open the seed_7 Libero project → `MPFS_ICICLE_KIT_BASE_DESIGN` SmartDesign.
2. **CCC:** configure the clock conditioner to emit a paired, phase-aligned 2× output —
   e.g. OUT0 = system clk (the V250 system rate, ~75 MHz per the de-rate), OUT1 = 2× (~150 MHz),
   from the **same CCC**, **OUT0/OUT1** (or OUT2/OUT3) pair (Handbook Note 1). Verify against the
   actual seed_7 system-clock rate before fixing the numbers (the closure ran a 125 MHz FIC user
   clock — confirm what feeds the V250 `clk`).
3. **Wire** the 2× output to CoreVectorBlox `clk_2x`; keep `clk` on the system output; leave
   `resetn` as-is (it works).
4. **P&R:** enable **"Repair Minimum Delay Violations"** (Handbook Note 2) before PLACEROUTE.
5. Regenerate component → confirm the V250 `clk_2x` now sources the 2× CCC output in the Memory
   Map / netlist.
6. Re-synth + P&R + export `.job` on a branch (per `libero/scripts/04_synth_pnr.tcl` /
   `closure_pipeline.tcl`); program via `program_kit.tcl` **on a branch**; back up + digest the new
   `.job`. The rung-A seed_7 closure stays the trusted fallback until the new one is digest-verified.

## Re-verify (on the kit, `ssh icicle`)

```bash
cd /root/bringup && ./vnnx_smoke fcnn_v2_residual_dataset_a.vnnx
# PASS = "V250 control plane alive" -> RUNNING asserts -> "inference complete" -> dequantized outputs.
# Then quote on-silicon latency (the [NC] 75/150 MHz figure becomes measurable for the first time).
```
Do **not** run `pid_poke` against this bitstream (PID read path still severed → core wedge); rung E
needs the separate two-slot integration (`docs/smartdesign_two_slot_canvas_runbook.md`).

## Sources
- CoreVectorBlox IP Handbook §5.1 / Table 5-1 (clk, clk_2x, resetn) + Notes 1–2 — corpus
  `vectorblox-sdk-docs-bee/CoreVectorBlox_IP_Handbook.md:439-461`.
- On-silicon symptom — `firmware/linux/reports/2026-06-15-bringup/rung_cdef_results_2026-06-15.md`.
- FIC_0 extraction method (grep component Verilog, no GUI) — `docs/fic_0_address_map_2026-05-18.md`.
- 75/150 MHz de-rate `[NC]` — `docs/whole_process_strategy_audit_2026-06-02.md`.
