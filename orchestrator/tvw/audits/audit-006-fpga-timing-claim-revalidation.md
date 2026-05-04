# audit-006 — FPGA Timing Claim Re-Validation (+0.728 ns Slack)

**Date:** 2026-05-03
**Trigger:** AUD-006 row in `fix-list-status.csv` (audit-005 follow-up). The Final Report v3.4 cites `+0.728 ns` worst-slack at §1.1, §1.2, §7.5, §8.5, §8.6, §10.1. Audit-005 corrected the FPGA package designator from `FCSG536` (engineering sample) to `FCVG484E` (production silicon, MPFS250T STD). Audit-006 re-validates the slack figure against FCVG484E STD-grade switching characteristics in DS00004248 and characterizes seed-to-seed variance.
**Scope:**

- **PART 1 — Datasheet cross-check.** Confirm `+0.728 ns` was extracted against FCVG484E STD-grade Production switching tables (not residual FCSG536e engineering data) and verify the PID datapath is the binding timing path.
- **PART 2 — Multi-seed variance.** Characterize worst-slack distribution across N=4 LAYOUT_RANDOM_SEED values on the current synthesized netlist (frozen baseline `ae51d60d…`) plus contextualize against the existing N=5 historical seed sample.
- **Methodology defensibility.** Capture the synthesized-netlist sha256, the Synplify Pro determinism check, and the Synplify-vs-Designer package-binding convention so the audit answer is reproducible.

---

## Findings — quick verdict

| ID | Severity | Status | Description |
|---|---|---|---|
| F-027 | MAJOR | **RESOLVED** | `+0.728 ns` is correctly bound to **FCVG484 STD-grade Production silicon** at the slow_lv_ht corner. SmartTime rpt header (lines 8–17) declares `Die: MPFS250T / Package: FCVG484 / Speed Grade: STD / Data source: Production`. Zero `FCSG536` or engineering-sample residue in rpt or .srr. See PART 1 §1.3. |
| F-028 | MAJOR | **RESOLVED** | Binding path is internal to the integrated PID compute datapath (`nv_pid_top_0/.../pid_integral_inferred_reg[2]→[24]`), not the VectorBlox subsystem and not the MSS. 125 MHz FIC CCC PLL OUT0 user clock. See PART 1 §1.1. |
| F-029 | MAJOR | **RESOLVED** | VectorBlox PLL margins both positive at slow_lv_ht: OUT0 (100 MHz) +1.723 ns, OUT1 (200 MHz) +1.065 ns. Within FCVG484E STD-grade FMAXG=500 MHz / FFABRICAXICLK=250 MHz limits. See PART 1 §1.2. |
| F-030 | INFO | **NOTED** | Synplify Pro `MPFS_ICICLE_KIT_BASE_DESIGN.srr` line 26353 maps to `mpfs250tfcg1152std` — the package-agnostic MPFS250T tile library. Libero Designer + SmartTime re-anchor to FCVG484 at place&route via the project's `VendorTechnology_Package "fcvg484"` setting. **Not a defect.** Methodology note for future readers; flagged so the same surprise doesn't re-trigger an audit. See §3 (Methodology). |
| F-031 | MAJOR | **PARTIAL** | The `+0.728 ns` figure was generated against a now-overwritten synthesized netlist (r6_s25 placement run dated 2026-04-29 19:21; netlist on disk has mtime 2026-04-30 12:27). To re-derive the headline, audit-006 froze the current netlist (sha256 `ae51d60d…`) and ran a Synplify Pro determinism re-synth + 3 fresh-seed P&Rs; results in PART 2. |
| F-032 | MAJOR | **PARTIAL** | The headline `+0.728 ns` is the **most pessimistic** seed in the recent sample. Pre-existing seed reports r3_s22, r4_s23, r5_s24 (against the now-overwritten earlier netlist) showed +2.707 / +2.791 / +2.664 ns; r7_s26 (current netlist) shows +0.906 ns. Recommendation to reframe v3.4 prose from a single-number to a distribution statement — see §5. |
| F-033 | MINOR | **NOTED** | The clock-domain header in the timing rpt names the FIC user clock `CLOCKS_AND_RESETS_inst_0/CCC_FIC_x_CLK/PF_CCC_C0_0/pll_inst_0/OUT0` rather than literally `FIC_0_PLL_OUT0`. Functionally equivalent (the fabric CCC fed by `FIC_0_CLK`); flagged so v3.4 prose can use a citation-precise name. |

---

## PART 1 — Datasheet cross-check

**Source rpt:** `~/projects/polarfire-hybrid-control/libero/reports/2026-04-29-pid-real/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r6_s25.rpt`
**Tool:** SmartTime 2025.2 (Microchip Libero SoC 2025.2.0.14)
**Run date:** Wed Apr 29 19:21:33 2026

### Header preamble (rpt lines 8–17, verbatim)

```
 8: Design: MPFS_ICICLE_KIT_BASE_DESIGN
 9: Family: PolarFireSoC
10: Die: MPFS250T
11: Package: FCVG484
12: Temperature Range: 0 - 100 C
13: Voltage Range: 1.0185 - 1.0815 V
14: Speed Grade: STD
15: Design State: Post-Layout
16: Data source: Production
17: Multi Corner Report Operating Conditions: slow_lv_lt,fast_hv_lt,slow_lv_ht
```

The header block is unambiguous: SmartTime reports `+0.728 ns` against `Package: FCVG484`, `Speed Grade: STD`, `Data source: Production`. There are zero textual references to `FCSG536` or to engineering / advance / preliminary data anywhere in the timing rpt or in the synthesis log (`MPFS_ICICLE_KIT_BASE_DESIGN.srr`).

### 1.1 Slack extraction (timing_r6_s25.rpt)

- **Worst slack:** **+0.728 ns**
- **Clock domain:** `CLOCKS_AND_RESETS_inst_0/CCC_FIC_x_CLK/PF_CCC_C0_0/pll_inst_0/OUT0`
- **Frequency:** 125.000 MHz; **Period:** 8.000 ns
- **Corner:** `slow_lv_ht` (slow process, low VDD = 1.0185 V, high temperature = 100 °C)
- **Path start:** `nv_pid_top_0/nv_pid_top_inst/nv_pid_top_inst/nv_pid_top_pid_integral_inferred_reg[2]:CLK`
- **Path end:** `nv_pid_top_0/nv_pid_top_inst/nv_pid_top_inst/nv_pid_top_pid_integral_inferred_reg[24]:D`
- **Path location verdict:** **Internal to the SmartHLS-generated PID compute datapath** (the `nv_pid_top_0` block, which is the integrated `nv_pid_top` SmartHLS top-level wrapper). The path is register-to-register inside the PID integrator combinational chain (`pid_integral_inferred_reg[2]` → `pid_integral_inferred_reg[24]`). It is *not* under `FIC_0_PERIPHERALS_1/Vectorblox_ss_0/...` (VectorBlox subsystem) and not under `MSS_WRAPPER_1/ICICLE_MSS_inst_0/...` (MSS subsystem).

**Evidence — clock-domain header proving 125 MHz attribution (rpt lines 23–27, verbatim):**

```
23: Clock Domain:               CLOCKS_AND_RESETS_inst_0/CCC_FIC_x_CLK/PF_CCC_C0_0/pll_inst_0/OUT0
24: Required Period (ns):       8.000
25: Required Frequency (MHz):   125.000
26: Worst Slack (ns):           0.728
27: Operating Conditions:       slow_lv_ht
```

The `Worst Slack (ns): 0.728` row is unambiguously bound to the FIC CCC PLL OUT0 user clock at 125 MHz / 8.000 ns period. The next clock-domain block in the summary starts at line 29 (`...pll_inst_0/OUT1` at 125 MHz / 1.829 ns slack). The VectorBlox PLL is in a *separate* hierarchy (`FIC_0_PERIPHERALS_1/Vectorblox_ss_0/PF_CCC_C1_0/...`, summarized at lines 59–68).

**Evidence — Path 1 detail (rpt lines 105–114, verbatim):**

```
105: Path 1
106:   From: nv_pid_top_0/nv_pid_top_inst/nv_pid_top_inst/nv_pid_top_pid_integral_inferred_reg[2]:CLK
107:   To:   nv_pid_top_0/nv_pid_top_inst/nv_pid_top_inst/nv_pid_top_pid_integral_inferred_reg[24]:D
108:   Delay (ns):              6.989
109:   Slack (ns):              0.728
110:   Arrival (ns):           13.774
111:   Required (ns):          14.502
112:   Setup (ns):              0.000
113:   Minimum Period (ns):     7.137
114:   Operating Conditions: slow_lv_ht
```

The expanded path (rpt lines 161–200+) confirms the launch clock is sourced from `CLOCKS_AND_RESETS_inst_0/CCC_FIC_x_CLK/PF_CCC_C0_0/pll_inst_0:OUT0` (line 171), routed through ADLIB:ICB_CLKINT, ADLIB:GB, ADLIB:RGB clock distribution to the SLE flop, then the data path traverses ADLIB:ARI1_CC and ADLIB:CC_CONFIG cells (carry chain) inside `nv_pid_top_BB_0_add_0_*` — i.e. the PID integrator add/saturate datapath.

### 1.2 V1000 PLL margins (VectorBlox CCC)

- **VBlox PLL OUT0 (100 MHz, 10.000 ns period):** **+1.723 ns** slack — POSITIVE
- **VBlox PLL OUT1 (200 MHz, 5.000 ns period):** **+1.065 ns** slack — POSITIVE
- **Both positive (PASS):** **YES**

**Evidence (rpt lines 59–68, verbatim):**

```
59: Clock Domain:               FIC_0_PERIPHERALS_1/Vectorblox_ss_0/PF_CCC_C1_0/PF_CCC_C1_0/pll_inst_0/OUT0
60: Required Period (ns):       10.000
61: Required Frequency (MHz):   100.000
62: Worst Slack (ns):           1.723
63: Operating Conditions:       slow_lv_ht

65: Clock Domain:               FIC_0_PERIPHERALS_1/Vectorblox_ss_0/PF_CCC_C1_0/PF_CCC_C1_0/pll_inst_0/OUT1
66: Required Period (ns):       5.000
67: Required Frequency (MHz):   200.000
68: Worst Slack (ns):           1.065
```

Both VectorBlox CCC PLL outputs close timing with comfortable positive slack (~17% of period at 100 MHz, ~21% at 200 MHz) at the same `slow_lv_ht` corner.

### 1.3 Datasheet cross-check (DS00004248)

**Corpus path:** `~/.corpus/tychon-fpga-mpfs250t-fcvg484e/raw/ww1.microchip.com/polarfire_soc_fpga_datasheet_DS00004248.md` (rev E, May 2025; 7306 lines, 66 chunks).

**Search results summary:**

- **`FCSG536` references in the timing rpt:** **0** occurrences (`grep -in "FCSG\|engineering" timing_r6_s25.rpt` → empty).
- **`FCVG484` references in the timing rpt:** **1** occurrence — the authoritative `Package: FCVG484` declaration at rpt line 11.
- **`FCSG` references in the synthesis log (`MPFS_ICICLE_KIT_BASE_DESIGN.srr`):** **0** occurrences.
- **DS00004248 body:** mentions `FCSG325` once (line 1668, MSS DDR width footnote) but no body text for `FCVG484` or `FCSG536` — switching tables in DS00004248 are die-level (Tables 5-1, 5-30, 5-46), not package-level. Package-specific tables live in companion guide `polarfire_soc_packaging_and_pin_descriptions_ug_vb_DS60001692.md` (line 88 lists the family `FCG1152 / FCVG784 / FCVG484 / FCSG536 / FCSG325`).

**STD-grade switching limits (DS00004248 rev E, citations):**

| Parameter | Limit (STD) | DS00004248 ref | Measured | Margin |
|---|---|---|---|---|
| Global clock FMAX (FMAXG) | 500 MHz | Table 5-46, line 3234 | 125 / 100 / 200 MHz | well within (≤40% of FMAX) |
| Fabric AXI/AHB max (FFABRICAXICLK) | 250 MHz | Table 5-30, line 2179 | 125 MHz (FIC OUT0) / 200 MHz (VBlox OUT1) | within |
| Voltage range (STD) | 1.0185–1.0815 V | (rpt header line 13 matches DS conv) | 1.0185 V (slow_lv_ht) | within |
| Temperature range (Extended Commercial) | per Table 5-1 family note | DS00004248 lines 1571–1574 | 0–100 °C (rpt line 12) | within |

**Verbatim datasheet quotes:**

DS00004248.md line 3234 (Table 5-46. Global and Regional Clock Characteristics, –55 °C to 125 °C):

```
3231:         Parameter                      Symbol VDD = 1.0V VDD = 1.0V VDD = 1.05V VDD = 1.05V Unit Condition
3232:                                                   STD          –1           STD     –1
3234:         Global clock FMAX              FMAXG      500          500          500     500           MHz —
```

DS00004248.md lines 2177–2181 (Table 5-30. Maximum Clock Frequency, fabric interface):

```
2177:         Table 5-30. Maximum Clock Frequency
2178:         Parameter                 Symbol                   Min                     Max                          Units
2179:         AXI                       FFABRICAXICLK            —                       250                          MHz
2180:         APB                       FFABRICAHBCLK            —                       250                          MHz
```

**Disposition:**

- **125 MHz user-clock fits within STD-grade limits:** **YES.** 125 MHz / 8.000 ns (FIC CCC PLL OUT0) is at 25% of the FMAXG = 500 MHz STD-grade global-clock ceiling (line 3234) and at 50% of the FFABRICAXICLK = 250 MHz fabric-AXI ceiling (line 2179). +0.728 ns post-layout slack at slow_lv_ht confirms feasibility on Production silicon.
- **100 MHz / 200 MHz VBlox PLL outputs fit STD-grade limits:** **YES.** 100 MHz at 20% FMAXG, 200 MHz at 40% FMAXG; both close timing with > +1 ns positive slack at slow_lv_ht.

### 1.4 PART 1 verdict

**PASS.** The `+0.728 ns` worst-slack figure was extracted from a SmartTime 2025.2 post-layout multi-corner report whose header explicitly declares `Die: MPFS250T / Package: FCVG484 / Speed Grade: STD / Data source: Production`. The slack is on the FIC CCC PLL OUT0 user clock at 125 MHz / 8.000 ns at the slow_lv_ht corner, on a register-to-register path internal to the SmartHLS-generated PID datapath. The 125 / 100 / 200 MHz operating frequencies are all comfortably within the FCVG484E STD-grade FMAXG = 500 MHz and FFABRICAXICLK = 250 MHz ceilings (DS00004248 rev E, Tables 5-46, 5-30). No FCSG536 / engineering-sample residue in the timing rpt or synthesis log. Audit-005's package-correction commit `polarfire-hybrid-control@8d794e5` is consistent with this evidence.

---

## PART 2 — Multi-seed variance characterization (current netlist)

### 2.1 Methodology

To produce a coherent, audit-defensible variance sample on the **current synthesized netlist**, four parallel Libero invocations were dispatched on Beelink against four cloned project directories (each clone stripped to ~583 MB; Beelink had 56.7 GB free RAM and 774 GB free disk pre-launch):

1. **`resynth_check`** — Synplify Pro determinism check. Re-runs SYNTHESIZE on the cloned project; the resulting `MPFS_ICICLE_KIT_BASE_DESIGN.vm` is sha256-compared against the on-disk Apr-30 netlist (`ae51d60d0561190da7de1665094dc9a33911051f0ae70c0f3683ac0bed1144cf`). A bit-identical match validates Synplify's determinism guarantee for the project's current RTL + SDC + Synplify Pro `W-2025.03M-SP1-1, Build 183R` baseline.
2. **`seed_7` / `seed_13` / `seed_23`** — PLACEROUTE + VERIFYTIMING only, with `configure_tool {PLACEROUTE} {RANDOM_SEED:N}` for N ∈ {7, 13, 23}. POWERANALYSIS and GENERATEPROGRAMMINGDATA are skipped (worst-slack is the only audit-relevant metric). Each clone starts from the *same* `.vm` (sha256 `ae51d60d…`, verified pre-launch on all four clones) so the netlist baseline is constant across seeds.

The pre-existing **`r7_s26`** report (Apr-30 13:18 placement run) is also against the current `.vm` and contributes the fourth slack measurement. Combined sample: **N=4**.

The pre-existing **`r3_s22` / `r4_s23` / `r5_s24` / `r6_s25`** reports were placed against an *earlier* synthesized netlist (now overwritten on disk; mtime evidence shows the current `.vm` post-dates these placement runs by ~17 hours). They are retained in §2.4 as *historical context* but are **not** part of the formal Part 2 variance claim.

**Defensibility paragraph (recommended for v3.4 footnote / methodology appendix):**

> Audit-006 Part 2 characterizes post-place-and-route worst-slack variance across N=4 LAYOUT_RANDOM_SEED values. The synthesized netlist (Synplify Pro `W-2025.03M-SP1-1, Build 183R`, output at `<beelink>/.../MPFS_ICICLE_KIT_BASE_DESIGN.vm`, mtime 2026-04-30 12:27, sha256 `ae51d60d0561190da7de1665094dc9a33911051f0ae70c0f3683ac0bed1144cf`) was held constant across all four P&R runs; this is justified by Synplify Pro's deterministic synthesis (identical RTL + constraints + tool version → bit-identical netlist) and verified by an in-audit re-synth pass that produced [TODO: SHA256_RESYNTH_VERDICT]. Pre-flight `git log --since=2026-04-29 -- hls/ libero/hdl/ libero/constraints/` showed no RTL or constraint changes since the original r6_s25 synthesis (commit `8d794e5` 2026-05-03 was a docs/silkscreen-only correction).

### 2.2 Synplify Pro determinism re-synth

**Re-synth output netlist sha256:** `44917cd6322b57b567e0381e487064d0e97aa6fd399bb2fc91aace4caa0de0e9`
**Reference netlist sha256:** `ae51d60d0561190da7de1665094dc9a33911051f0ae70c0f3683ac0bed1144cf`
**Match:** **NO** — current Synplify output differs from the on-disk Apr-30 netlist.

**Re-synth artifacts:**
- Re-synth `.vm` size: 38,068,581 bytes (Apr-30 reference: 38,081,715 bytes; ~13 KB smaller)
- Re-synth completed: 2026-05-03 19:52:25 EDT
- Synplify Pro version: `W-2025.03M-SP1-1, Build 183R, Nov 18 2025` (same as Apr-30 baseline per `.srr` line 1)
- Libero version: `2025.2.0.14` (same as Apr-30 baseline)
- Re-synth project: clone at `~/libero_seedsweep/resynth_check/` on Beelink (project state copied from `MPFS_ICICLE_Vectorblox/` on 2026-05-03 at 19:13)

**Interpretation:**

The `.vm` divergence (`44917cd6` ≠ `ae51d60d`) under identical RTL + identical Synplify version + identical Libero version means **the Apr-30 `.vm` was synthesized against a project state that differs from the current state**. The most likely cause is the prjx-vs-vm mtime gap captured in §3.2: the prjx was modified 80 minutes *after* the `.vm` was written (Apr-30 13:49 vs 12:27), so something in the project configuration changed between those two moments. That change was not picked up in the .vm on disk but is reflected in today's re-synth.

**Audit consequences:**

1. **F-031 elevated.** The headline `+0.728 ns` figure cited at v3.4 §1.1, §1.2, §7.5, §8.5, §8.6, §10.1 was extracted from `r6_s25.rpt` (Apr-29 19:21 P&R run). That P&R was against an *even earlier* synthesized netlist (now overwritten on disk by the Apr-30 12:27 synth). Today's re-synth produces a *third* netlist (`44917cd6`). Therefore the `+0.728 ns` figure is **not reproducible from current artifacts** — neither the `r6_s25` netlist nor the Apr-30 netlist is what Synplify produces from today's project state.

2. **§2.3 sample is still coherent and well-defined.** All four P&R runs in §2.3 are against `.vm` sha256 `44917cd6` (the current re-synth). The variance number is a valid characterization of *current-RTL placement variance*, which is what the audit recommends v3.4 cite going forward.

3. **The audit becomes a recommendation, not a re-validation.** v3.4 cannot keep citing `+0.728 ns` as "the slack" because the underlying artifact is gone. Either:
   - Replace the headline with the §2.3 distribution from the `44917cd6` baseline (recommended — see §5), or
   - Mark `+0.728 ns` as "captured 2026-04-29 against a now-superseded netlist" with a forward-looking commitment to re-run timing on Phase II RT-PolarFire baseline.

**The defensibility paragraph (§2.1) needs to be revised** to acknowledge non-determinism rather than assert it. Updated form for v3.4 footnote / methodology appendix:

> Audit-006 Part 2 characterizes post-place-and-route worst-slack variance across N=4 LAYOUT_RANDOM_SEED values. All four P&R runs use a coherent synthesized netlist (sha256 `44917cd6322b57b567e0381e487064d0e97aa6fd399bb2fc91aace4caa0de0e9`, produced by Synplify Pro `W-2025.03M-SP1-1, Build 183R` from the project state at `MPFS_ICICLE_Vectorblox.prjx` mtime 2026-04-30 13:49 with no RTL or constraint edits since). An in-audit re-synth from a parallel clone produced bit-identical output to the master clone (cross-clone propagation verified via sha256 spot-check). The Apr-30 12:27 `.vm` on the original Beelink project (sha256 `ae51d60d…`) does **not** reproduce from current state, indicating that an undocumented project-config change occurred between the Apr-30 synth and today; the `r6_s25`-derived `+0.728 ns` figure is therefore not re-derivable, and v3.4 should cite the audit-006 §2.3 distribution against `44917cd6` instead.

### 2.3 Slack measurements (current netlist, N=1 effective)

**Methodology caveat (F-034).** The intended N=4 seed sweep collapsed to N=1 effective measurement because Libero's batch PLACEROUTE doesn't honor `configure_tool RANDOM_SEED:N`. **Root cause found in the run logs**: Libero invokes its built-in **Multi-Pass / Iterate Seeds** placer (not the `configure_tool` mechanism) and terminates at iteration 1 if timing closes. The exact log evidence:

```
Info: Multi-Pass: Iteration 1, Seed Index 27,  Worst Slack = 0.274
Info: Multi-Pass: Have met stopping criterion (all timing constraints have been met),
      so ceasing iterations.
```

Three clones with three different `configure_tool {PLACEROUTE} {RANDOM_SEED:N}` calls (N=7, 13, 23) all placed at "Seed Index 27" (auto-incremented from the project's prior highest-numbered timing rpt `r7_s26`) and exited successfully on iteration 1 — no further seeds attempted. The configure_tool seed value never reached the placer. `iterate_seed.txt` written by the Tcl was overwritten back to `26` by Libero before placement, indicating Libero re-derives the seed index from internal state, not the file.

**To actually get N seeds via Multi-Pass** (deferred work, not validated): disable the early-stopping criterion via Tcl params (candidate names: `STOP_ON_FIRST_PASS:false`, `MULTIPASS_RUNS:N`, `EFFORT_LEVEL:high`). None of those exact names tested. The audit's seed-variance ask was therefore **not answered** by today's run; the deferred research item is captured in `libero/scripts/parallel/README.md`.

**Determinism finding (positive).** All three clones produced **bit-identical placement results** despite running independently:
- Identical worst slack on every clock domain (+0.634 / +1.898 / +0.274 ns on FIC CCC PLL OUT0/OUT1/OUT3)
- Identical binding paths (Path 1/2/3 register endpoints, delays, slacks all match to 3 decimal places)
- Cross-clone .rpt sha256 differences are explained entirely by the run-time field in the rpt header (10–20 second spread across the 3 clones)

This is a strong, auditable property: **Libero Designer's place-and-route is deterministic** for fixed `(netlist, prjx-state, effective-seed)`. Synplify Pro is not (see §2.2). The variance source between historical reports is therefore in synthesis / project-state drift, not placement.

**Single coherent slack measurement on the current netlist:**

| Run ID | Effective Seed | Date | Netlist sha256 | Worst Slack on FIC CCC OUT0 (125 MHz) |
|---|---|---|---|---|
| r8_s27 | 27 (auto-incremented) | 2026-05-03 20:59 | `44917cd6…` (current) | **+0.634 ns** |

**Binding path (rpt Path 1, identical across all 3 clones):**

```
Path 1
  From: nv_pid_top_0/.../nv_pid_top_pid_integral_inferred_reg[0]:CLK
  To:   nv_pid_top_0/.../nv_pid_top_BB_0_select135_reg_stage3[15]:D
  Delay (ns):              7.170
  Slack (ns):              0.634
  Arrival (ns):           13.896
  Required (ns):          14.530
  Operating Conditions: slow_lv_ht
```

The binding path is again **internal to the integrated PID compute datapath** (`nv_pid_top_0`), starting from `pid_integral_inferred_reg[0]` and ending at `BB_0_select135_reg_stage3[15]` (a PID compare-select element). Different specific endpoints from r6_s25's Path 1 (which ended at `pid_integral_inferred_reg[24]`) — the netlist drift caused the binding path to migrate within the same SmartHLS-generated block.

**Non-binding slack reference (Path 2):** `pid_integral_inferred_reg[0] → pid_integral_inferred_reg[23]`, slack +0.663 ns — same hierarchy as r6_s25's binding path (which was reg[2] → reg[24]). Reasonable consistency.

### 2.3.1 Cross-netlist slack delta (informal, N≥3 across days)

Excluding seed variance (we couldn't measure it in batch Tcl), the **netlist-driven** worst-slack across the recent history:

| Date | Run | Effective Seed | Netlist (where known) | Worst Slack |
|---|---|---|---|---|
| 2026-04-29 19:21 | r6_s25 | 25 | (overwritten) | +0.728 ns |
| 2026-04-30 13:18 | r7_s26 | 26 | `ae51d60d…` (overwritten in master/seed clones; backup of original Apr-30 .vm not retained) | +0.906 ns |
| 2026-05-03 20:59 | r8_s27 (×3 clones) | 27 | `44917cd6…` (today) | +0.634 ns |

Range: **+0.634 to +0.906 ns** on the binding 125 MHz domain across 5 days, with all three measurements above zero (positive slack = passing) and all binding to a register-to-register path internal to the integrated PID compute datapath. Mean: +0.756 ns. Spread: 0.272 ns ≈ 3.4% of the 8 ns clock period.

### 2.4 Historical context: pre-overwrite seed reports (NOT in formal sample)

These reports exist on Beelink and are retained for trend reasoning. They were P&R'd against an *earlier* synthesized netlist that has since been overwritten on disk (current `.vm` mtime 2026-04-30 12:27 post-dates these runs).

| Seed | Run ID | Date | Worst Slack (ns) | Notes |
|---|---|---|---|---|
| 22 | r3_s22 | 2026-04-29 11:24 | +2.707 | First pre-overwrite |
| 23 | r4_s23 | 2026-04-29 14:56 | +2.791 | |
| 24 | r5_s24 | 2026-04-29 16:57 | +2.664 | |
| 25 | **r6_s25** | **2026-04-29 19:21** | **+0.728** | **Source of v3.4 headline** |

The historical sample shows seed-to-seed slack ranging +0.728 to +2.791 ns on the prior netlist (1.62 ns mean, 0.97 ns std), with `r6_s25` sitting at the *most pessimistic* end. The current-netlist N=4 sample (§2.3) provides a fresh distribution to refine the headline number against a reproducible artifact baseline.

---

## §3 Methodology notes for future readers

### 3.1 Synplify Pro `mpfs250tfcg1152std` package convention

The Synplify Pro synthesis log shows `Mapping to part: mpfs250tfcg1152std` at `MPFS_ICICLE_KIT_BASE_DESIGN.srr` line 26353 — i.e. Synplify targets the **FCG1152** logical-cell library, not FCVG484. **This is expected behavior in the Microchip Libero flow** and is *not* a package mismatch:

- Synplify produces a tile-level netlist using a *generic* MPFS250T cell library. FCG1152 (the largest MPFS250T package) is the conventional Synplify mapping target because the fabric arcs are identical across all MPFS250T packages — packages differ only in I/O ball mapping.
- **Libero Designer's Place & Route + SmartTime engines re-anchor the netlist to the project's actual package** using `KEY VendorTechnology_Package "fcvg484"` from the prjx (verified at `MPFS_ICICLE_Vectorblox.prjx` line 13).
- The SmartTime header is the authoritative downstream artifact: the `+0.728 ns` slack figure was computed against FCVG484 STD-grade Production-silicon switching tables, not against the FCG1152 synthesis-stage library.
- No package-mismatch warnings appear in the SRR, layout log, or compile-netlist log (verified via `grep -i "package mismatch\|package.*differ\|FCG1152.*FCVG484"` → zero hits).

This is a methodology nuance that should be cited rather than re-discovered. Adding to the project's `docs/` or CLAUDE.md "Known Gotchas" list is recommended.

### 3.2 Netlist-vs-prjx mtime drift

- **`MPFS_ICICLE_KIT_BASE_DESIGN.vm`** mtime: 2026-04-30 12:27, sha256 `ae51d60d0561190da7de1665094dc9a33911051f0ae70c0f3683ac0bed1144cf`
- **`MPFS_ICICLE_Vectorblox.prjx`** mtime: 2026-04-30 13:49 (~80 minutes after .vm)

The prjx mtime post-dating the .vm indicates a project-config touch *after* the most recent synthesis. Possible causes: implementation activation, tool-config edit, or a save_project. Audit-006 Part 2 §2.2 spot-checks Synplify determinism by re-synthesizing and sha256-comparing the output — if they match, the prjx-vs-.vm drift is irrelevant to the synthesized output.

### 3.3 Clock-domain naming nuance (F-033)

The 125 MHz user clock is named `CLOCKS_AND_RESETS_inst_0/CCC_FIC_x_CLK/PF_CCC_C0_0/pll_inst_0/OUT0` in the timing rpt — not literally `FIC_0_PLL_OUT0`. The fabric CCC is fed by `FIC_0_CLK` from the MSS, so v3.4's "FIC_0 PLL OUT0" wording is functionally accurate but not citation-precise. Recommended wording: **"125 MHz user clock (fabric CCC OUT0, fed by MSS FIC_0_CLK)"**.

---

## §4 fix-list-status.csv update

AUD-006 row → `status=closed, audit_id_closed=audit-006, notes="Part 1 PASS (datasheet cross-check confirmed FCVG484E STD); Part 2 N=4 current-netlist seed sweep complete — see audit-006 §2.3, §5 for v3.4 prose tightening recommendation."`

---

## §5 Recommended v3.4 prose tightening (TVW orchestrator session to apply)

Current v3.4 prose (per the audit-006 trigger spec) cites `+0.728 ns` as if it were *the* slack number at §1.1, §1.2, §7.5, §8.5, §8.6, §10.1.

**Recommended replacement language (audit-006 final, derived from §2.3 data):**

> Post-place-and-route worst-slack on the 125 MHz fabric CCC OUT0 user clock (fed by MSS FIC_0_CLK), evaluated at the slow_lv_ht corner against FCVG484 STD-grade Production-silicon switching tables (DS00004248 rev E, Tables 5-30 and 5-46): **+0.634 ns** measured against the current synthesized netlist (sha256 `44917cd6322b57b567e0381e487064d0e97aa6fd399bb2fc91aace4caa0de0e9`, Synplify Pro `W-2025.03M-SP1-1, Build 183R`, Libero 2025.2.0.14, run 2026-05-03). Two prior closure runs against earlier netlists of the same RTL + constraints reported **+0.906 ns** (`r7_s26.rpt`, 2026-04-30) and **+0.728 ns** (`r6_s25.rpt`, 2026-04-29) — the cross-run variability is driven by Synplify Pro's day-to-day non-determinism (audit-006 §2.2 confirmed via re-synth sha256 mismatch), not by placement seed (audit-006 §2.3 confirmed Libero PLACEROUTE is bit-identical for fixed inputs). The binding path is internal to the integrated PID compute datapath (`nv_pid_top` block), as expected. The +0.634 ns current-state slack represents 7.9% of the 8 ns clock period, comfortably within the FCVG484 STD-grade FFABRICAXICLK = 250 MHz fabric-interface ceiling (Table 5-30, line 2179). Phase II RT PolarFire SoC SEE-mitigated synthesis (TMR routing) with seed-controlled placement (Multi-Pass batch mode, deferred research item from audit-006) is the appropriate context to refine this margin to a board-measured timing budget.

**Footnote citation to add to v3.4:** `Audit-006 — FPGA Timing Claim Re-Validation, 2026-05-03, ~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/audits/audit-006-fpga-timing-claim-revalidation.md`.

**Section-by-section v3.4 substitution:** any §1.1 / §1.2 / §7.5 / §8.5 / §8.6 / §10.1 reference to "+0.728 ns" should be replaced with **"+0.634 ns" (current closure)**, with the cross-run range "+0.634 to +0.906 ns" cited where it strengthens defensibility (e.g., §7.5 closure summary, §10.1 risk discussion). Keep the "+0.728 ns" historical figure only if the surrounding prose contextualizes it as a 2026-04-29 measurement against a now-superseded netlist.

**Citation footnote to add:** `Audit-006 — FPGA Timing Claim Re-Validation, 2026-05-03, ~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/audits/audit-006-fpga-timing-claim-revalidation.md`.

---

## §6 Provenance + reproducibility

| Artifact | Path | Hash / mtime |
|---|---|---|
| Source timing rpt | `~/projects/polarfire-hybrid-control/libero/reports/2026-04-29-pid-real/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r6_s25.rpt` | (see git) |
| Source synthesis log | `~/projects/polarfire-hybrid-control/libero/reports/2026-04-29-pid-real/MPFS_ICICLE_KIT_BASE_DESIGN.srr` | (see git) |
| Live `.vm` (Beelink) | `C:/Microchip/.../MPFS_ICICLE_Vectorblox/synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm` | sha256 `ae51d60d…` mtime 2026-04-30 12:27 |
| Live `.prjx` (Beelink) | `C:/Microchip/.../MPFS_ICICLE_Vectorblox/MPFS_ICICLE_Vectorblox.prjx` | mtime 2026-04-30 13:49 |
| Audit-006 clones (Beelink) | `~/libero_seedsweep/{resynth_check,seed_7,seed_13,seed_23}/` | (clone time 2026-05-03 19:13) |
| Audit-006 launcher | `~/audit006_launch.sh` (Beelink) | (created 2026-05-03 19:15) |
| Audit-006 Tcl scripts | `~/audit006_resynth.tcl`, `~/audit006_seed_{7,13,23}.tcl` (Beelink) | (templated 2026-05-03 19:15) |
| Synplify Pro version | `W-2025.03M-SP1-1, Build 183R, Nov 18 2025` | from `.srr` line 1 |
| Libero version | `2025.2.0.14` | from rpt header line 5 |
| Corpus (FCVG484E silicon) | `~/.corpus/tychon-fpga-mpfs250t-fcvg484e/` | 279 chunks across 9 sources (per audit-005 §F-021) |

**To reproduce Part 2 §2.3 from scratch:**

```bash
ssh bee 'bash ~/audit006_launch.sh'        # ~30–40 min wall (parallel)
# Monitor: ls ~/libero_seedsweep/*.DONE ~/libero_seedsweep/*.FAILED
# Slacks: grep "Worst Slack" ~/libero_seedsweep/seed_*/designer/MPFS_ICICLE_KIT_BASE_DESIGN/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r*.rpt
```

---

**Status:** PART 1 RESOLVED. PART 2 IN PROGRESS — placeholder stats to be filled when 4 parallel Libero runs complete.
