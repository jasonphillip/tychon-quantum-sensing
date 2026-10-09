> Original: claude.ai project document, created 2026-04-04. Edited for publication: names of other people and business details removed.

# Tychon AI — Gemini Integration Tracker & TODO List

**Date:** April 4, 2026
**Purpose:** Track all repo improvements driven by Gemini April 2-3 deep-think outputs, audit findings from Claude Code, and deferred work items.
**Status:** ACTIVE — update throughout today's session

---

## Quick Reference: Repo Name Mapping

| Role | Repo Name | Package Name |
|------|-----------|-------------|
| Repo 1: NV physics sim | `nv-sensor-sim` | `nv_sensor_sim` |
| Repo 2: ML training/export | `odmr-edge-ml` | `odmr_edge_ml` |
| Repo 3: FPGA control | `polarfire-hybrid-control` | N/A (C/C++) |

---

## Gemini Source Documents (April 2-3)

| Doc # | Title | Primary Impact |
|-------|-------|----------------|
| 1 | Section 8 Insert — Operational Impact (CEP/Endurance/Bandwidth) | Final Report Section 8.2 |
| 2 | Three-Persona Review (Program Manager, ML Scientist, GNC Engineer) | All 3 repos + Final Report |
| 3 | Numbered Issue List (Editorial QA) | Final Report cleanup |
| 4 | Circle Criterion Re-Derivation at ±30% Authority | Repo 3 safety docs + Final Report Section 3 |
| 5 | Platform-Level Necessity of AI Control in Quantum Sensing | Final Report Section 10.2 |

---

## PART 1: TODAY'S REPO WORK (April 4, 2026)

### Repo 1 (`nv-sensor-sim`) — COMPLETE

#### Audit Results

| Prompt | Finding | Severity | Status |
|--------|---------|----------|--------|
| 1: Unit Chain | Clean — B-fields in Tesla, manifest has units dict, no µT/nT ambiguity | None | CLOSED |
| 2: Noise Model | 8 sources implemented with citations; 6 real-world sources not modeled | Low | CLOSED — document in report limitations |
| 3: Dataset Contract | **Anti-inverse-crime: DOCUMENTED BUT NOT IMPLEMENTED** | **CRITICAL** | **FIXED** |
| 4: Adapter Pattern | NV-specific with ~40 hardcoded constants; CPU smoke path works | Low (follow-on) | CLOSED — no action |

#### Repo 1 Code Changes Completed

| # | Task | Gemini Source | Status | Notes |
|---|------|--------------|--------|-------|
| R1-1 | Implement shifted test-set parameter distributions in `generate_dataset()` | Doc 2 (ML Scientist: anti-inverse-crime praised) | **DONE** | `_shift_range()` helper: +12.5% mean, +20% width, floor clamp. 4 new params on `generate_dataset()`. `shift_test_ranges=True` enables auto-shift; explicit overrides also supported. |
| R1-2 | Update manifest JSON to record test-specific ranges | Doc 2 | **DONE** | 5 new fields on `DatasetManifest`: `inverse_crime_shift`, `test_p1_concentration_range_ppm`, `test_temperature_range_K`, `test_b1_gradient_range`, `test_b_perp_range_T`. Backward-compatible defaults. |
| R1-3 | Add test verifying train/test distribution non-overlap | Doc 2 | **DONE** | `test_shifted_test_ranges_no_overlap` — end-to-end generation + verification that test-split parameter means exceed train-split means |
| R1-4 | Update anti-inverse-crime docstrings to match implementation | Doc 2 | **DONE** | `docs/dataset-contract.md` rewritten: two-layer separation (seeds always enforced, distribution shift opt-in) |
| R1-5 | Fix `b_perp_range_T` comment ambiguity (cosmetic) | Audit P1 | DEFERRED | Low priority, can do later |

**Files changed:** `batch_generate.py`, `schema.py`, `dataset-contract.md`, tests (6 new)
**Test results:** 55/55 passing, all backward-compatible
**Key design choice:** `inverse_crime_shift` is a manifest-level flag so downstream ML consumers (Repo 2) can programmatically check whether test data was generated under shifted distributions

#### Repo 1 Items Deferred (Not Today)

| # | Task | Why Deferred |
|---|------|-------------|
| R1-D1 | Add shot noise model | Follow-on — most impactful missing noise source |
| R1-D2 | Add 1/f electronics noise model | Follow-on — affects baseline wander |
| R1-D3 | Parameterize hardcoded NV constants for multi-sensor support | Follow-on — adapter refactor |
| R1-D4 | Add formal ABC for adapter interface (replace duck typing) | Follow-on — code quality |

---

### Repo 2 (`odmr-edge-ml`) — Audit Complete, Fixes Dispatched

#### Audit Results

| Prompt | Finding | Severity | Status |
|--------|---------|----------|--------|
| 1: Residual Target Range | Consistently ±2.25 µT (4.5% of 50 µT). Clamp not embedded in QAT graph — applied pre-training and post-inference. Widening to ±15 µT costs 6.7× resolution (17.6→117.6 nT/level). Per-channel weight quant already implemented. | **INFO** | CLOSED — clamp decision deferred (D-1) |
| 2: Model Statefulness | Genuinely memoryless — no recurrent layers, no history buffers, no temporal side-channels. 2-channel FCNN uses PID Gaussian anchor (spatial, not temporal). Rebuttal paragraph drafted. | None | CLOSED — rebuttal ready for report |
| 3: ops_guard / VBX Compat | All 3 architectures pass V250. ReLU only. Kaiming He exists but must be called externally (risk). Export chain complete for FCNN only (Keras rebuild workaround). | **LOW** | Action items below |
| 4: Training Config | Curriculum training NOT IMPLEMENTED (single-pass). Sign folding in experiment scripts only, not core loop (fragile). Angular error metric IS tracked. CompositeAngularHuberLoss 70/30 split. | **MED** | Action items below |

#### Repo 2 Code Changes — Today

| # | Task | Gemini Source | Status | Notes |
|---|------|--------------|--------|-------|
| R2-1 | Sector clamp consistency | Doc 3, Issue #1 | **RESOLVED** | Audit confirmed: consistently ±2.25 µT everywhere. No inconsistency in code — the ±2.5/±5% variants were report-side only. |
| R2-2 | ±15 µT clamp quantization impact | Doc 2, Doc 4 | **DEFERRED (D-1)** | Clamp expansion decision pending. Audit quantified the tradeoff: 6.7× resolution loss. No code change today. |
| R2-3 | Move Kaiming He init into model constructors | Doc 2 (dead ReLU risk) | **DONE** | `init_weights: bool = True` param added to all 3 model constructors. Auto-calls `init_weights_kaiming_he()`. Set False when loading pretrained. |
| R2-4 | Create `docs/design_decisions.md` with statefulness rebuttal | Doc 2 (ML Scientist question) | **DONE** | Section 1: full rebuttal. Also documents scalar residual choice, Conv2d-only constraint, FCNN head design. |
| R2-5 | Move sign folding into core training loop | Earlier Gemini (training loop) | **DONE** | `fold_sign: bool = True` in `TrainConfig`. `fold_bz_sign()` flips negative-Bz rows. Gated on dim≥3, scalar residual unaffected. |
| R2-6 | Angular error metric | Doc 2 (GNC reviewer) | **RESOLVED** | Already tracked: `angle_err_deg` is the primary checkpoint selection metric. |
| R2-7 | Add comment at CLAMP_UT explaining ±15 µT tradeoff | Doc 4, audit findings | **DONE** | 4-line comment referencing Gemini Circle Criterion analysis and INT8 resolution trade-offs. |
| R2-8 | ONNX export promoted to src/ | Audit finding (ad-hoc in experiments/) | **DONE** | New `export/onnx_export.py` with ops_guard pre-check. `scalar_residual_v2.py` delegates to canonical module. |

**Repo 2 final status:** 87/87 tests (76 unit + 8 contract + 3 smoke). All changes committed.

---

### Repo 3 (`polarfire-hybrid-control`) — COMPLETE

#### Audit Results

| Prompt | Finding | Severity | Status |
|--------|---------|----------|--------|
| 1: Safety Gaps | **ALL THREE GNC GAPS CONFIRMED AND FIXED.** Slew limiter wired in. Watchdog cooldown added. Bumpless transfer: 0.100 V is correct for original params; 0.076 V validated as second operating point (Ki=0.000019, error=4000). | **FIXED** | CLOSED |
| 2: Clock/Timing | Clock is 200 MHz (PLL output from 125 MHz input). No CDC issue. VBX inference trigger gap documented as follow-on item. | **DOCUMENTED** | CLOSED |
| 3: Power Analysis | Power data external (NAS). Reference note added to README. | **DOCUMENTED** | CLOSED |
| 4: Circle Criterion | safety_architecture.md updated with ±30% analysis and follow-on stability roadmap. | **FIXED** | CLOSED |

#### Repo 3 Code Changes — Completed

| # | Task | Gemini Source | Status | Notes |
|---|------|--------------|--------|-------|
| R3-1 | Wire in slew-rate limiter | Doc 2 (GNC reviewer) | **DONE** | Safety chain: `u_AI_in → sector_clamp → slew_limit → + u_pid → saturate → actuator_out`. `safety_clamps.cpp` added to Makefile. |
| R3-2 | Watchdog cooldown/hysteresis | Doc 2 (GNC reviewer) | **DONE** | `WATCHDOG_COOLDOWN_CYCLES = 1000` (5 µs at 200 MHz). PID-only during cooldown regardless of heartbeat. |
| R3-3 | Clock frequency | Doc 3, Issue #2 | **RESOLVED** | No fix needed — code already correct. 125 MHz refs correctly describe PLL input. |
| R3-4 | Power numbers | Doc 3, Issue #3 | **DONE** | `README.md` updated with key numbers + NAS pointer. Report-side fix separate. |
| R3-5 | Static power contradiction | Doc 3, Issue #4 | **N/A** | Report fix only. |
| R3-6 | Update `safety_architecture.md` | Doc 4 | **DONE** | ±5% conservative → ±30% follow-on operational → ±50% theoretical max. Follow-on subsections: ZOH, derivative filter, IQC. Watchdog cooldown documented. Signal path assumption noted. |
| R3-7 | Clamp expansion comment | Doc 4, audit findings | **DONE** | Included in safety_architecture.md update. |
| R3-8 | Bumpless transfer value | Doc 2, audit P1 | **DONE** | Both validated: Test A = 0.100 V (Ki=0.00002, err=5000), Test B = 0.076 V (Ki=0.000019, err=4000). **Report should use 0.100 V as primary.** |
| R3-9 | VBX inference trigger gap | Audit P2 | **DONE** | TODO added in `nv_pid.cpp`. This plan assumes always-valid. Follow-on work adds valid/ready handshake. |

**Key insight from Claude:** Bumpless transfer delta = Ki × error is an algebraic invariant — mode transitions are voltage-continuous by construction regardless of AI feedforward magnitude. This is the core safety argument.

---

## PART 2: DEFERRED TODO LIST (Post-Today)

### Final Report Updates

| # | Task | Gemini Source | Blocked On | Priority |
|---|------|--------------|-----------|----------|
| FR-1 | Insert Section 8.2 operational impact translation (CEP/Endurance/Bandwidth) | Doc 1 | Verify µT vs nT in report figures | **HIGH** |
| FR-2 | Fix µT-vs-nT unit check in ADEV plots and Section 8 narrative | Doc 1 (sanity check) | None — verify report text matches Tesla units from Repo 1 | **HIGH** |
| FR-3 | Fix KPP 1 framing — 54.3% validation vs 31.3% sweep discrepancy | Doc 2 (Program Manager) | Decision: reframe or re-run with wider clamp | **HIGH** |
| FR-4 | Write Section 5 (Deliverable 1: Data Pipeline) — still TODO | Session summary 4/2 | None — writing only | **HIGH** |
| FR-5 | Write Section 10.2 (Cross-sensor) | Doc 2 (reviewer persona: TODO placeholders) | None — writing only | **HIGH** |
| FR-6 | Remove all [TODO] placeholders, internal notes, editor instructions | Doc 3 (Issues #1-#7 in section 5) | Sections 5, 10 written first | **HIGH** |
| FR-7 | Fix Section 2.2 — remove internal note about incorrect diagram | Doc 3, Narrative #1 | None | **MED** |
| FR-8 | Fix Section 3 — remove "Build the cage before the beast" drafting instruction | Doc 3, Narrative #2 | None | **MED** |
| FR-9 | Fix Section 4.1 — reorder architecture evolution so FCNN baseline comes first | Doc 3, Narrative #3 | None | **MED** |
| FR-10 | Fix Section 7.5 — define FIC_3 clock domain before referencing it | Doc 3, Narrative #5 | None | **MED** |
| FR-11 | Fix Section 8.6 — remove "CAUTION: weakest metric" developer fear text | Doc 3, Narrative #6 | None | **MED** |
| FR-12 | Fix header: date placeholder "[DATE]", contract number S-vs-5 typo | Doc 3, Grammar #1, #6 | None | **MED** |
| FR-13 | Fix "57.3° = exactly 1 radian" → "approximately 1 radian" | Doc 3, Grammar #3 | None | **LOW** |
| FR-14 | Fix Section 3.4 — remove "NOTE: Use annotated block diagram" instruction | Doc 3, Grammar #2 | None | **MED** |
| FR-15 | Reframe all "demonstrated" language for simulation-only results | Doc 3, Section 4 (#1-#3) | None — editorial pass | **HIGH** |
| FR-16 | Add ADEV percentage rounding fix (24.6→24.7%, 37.2→37.3%) | Doc 3, Issue #5 | None | **LOW** |
| FR-17 | Insert Circle Criterion ±30% proof paragraph in Section 3 | Doc 4 (report insert paragraph) | R3-6 done first | **MED** |
| FR-18 | Insert cross-sensor platform necessity argument in Section 10.2 | Doc 5 (5 sensor types × 4 limitations) | None — writing only | **MED** |
| FR-20 | Remove internal "Section Completion Status" table before submission | Doc 3 | All sections complete | **HIGH** |
| FR-21 | Fix "VectorBlox dominates at ~610 mW" — 23% isn't "dominates" | Doc 3, Claims #2 | None | **LOW** |
| FR-22 | Add Microchip vendor benchmark citation for AI latency claim | Doc 3, Claims #3 | Find citation | **MED** |
| FR-23 | Soften TRL 4 claim — no board boot means TRL 3+ at best | Doc 3, Claims #5 | None — editorial | **HIGH** |
| FR-24 | Decide: cut MagNav.jl metric entirely or heavily caveat | Doc 2 (ML Scientist: "it's a trap") | Decision needed | **HIGH** |

### New Report Figures Needed

| # | Figure | Purpose | Source | Blocked On |
|---|--------|---------|--------|-----------|
| FIG-1 | Updated ADEV figure with correct units verified | Section 8.2 | Repo 2 analysis scripts | FR-2 unit verification |
| FIG-2 | Updated heading sweep figure (if re-run with wider clamp) | Section 8.1 | Repo 2 re-run | R2-2 clamp decision |
| FIG-3 | Bode/Nyquist plot at ±15 µT clamp (or annotated block diagram) | Section 3 | Repo 3 analysis | R3-6 |
| FIG-4 | Power breakdown pie/bar chart (if needed for clarity) | Section 7.4 | Repo 3 SmartPower data | R3-4, R3-5 |

### Other Deferred Items

| # | Task | Notes |
|---|------|-------|
| OTH-1 | Regenerate 50K production dataset with anti-inverse-crime shifts | After R1-1 is implemented and tested |
| OTH-2 | Re-train FCNN on shifted dataset and compare metrics | After OTH-1 |
| OTH-3 | Update CLAUDE.md files on all 3 repos if new conventions emerge today | End of session |
| OTH-4 | Update `tychon_phase1_decision_log.md` with DLOG entries for today's decisions | End of session |
| OTH-5 | Upload this tracker + session summary to project knowledge | End of session |

---

## PART 3: SESSION LOG (April 4, 2026)

*Update this section as work completes throughout the day.*

### Completed

| Time | Repo | Item | Notes |
|------|------|------|-------|
| AM | R1 | Audit (all 4 prompts) | 4 parallel explores, all returned clean except anti-inverse-crime |
| AM | R1 | R1-1 through R1-4: Anti-inverse-crime fix | 55/55 tests. 4 files changed, 6 new tests. `shift_test_ranges=True` enables shifted distributions. |
| AM | R2 | Audit (all 4 prompts) | All returned. Key findings: curriculum not implemented, sign folding outside core loop, Kaiming He external-only |
| AM | R3 | Audit (all 4 prompts) | All returned. Key findings: 3 GNC safety gaps confirmed, VBX trigger not implemented, power data not in repo |
| PM | R2 | R2-3,4,5,7,8: All fixes complete | 87/87 tests. Sign folding in loop, Kaiming He auto-init, ONNX export to src/, design_decisions.md, clamp comment |
| PM | R3 | R3-1,2,6,7,8,9: All fixes complete | Slew limiter wired, watchdog cooldown (5 µs), safety_architecture.md ±30% update, bumpless dual-validated (0.100 V primary, 0.076 V secondary), VBX trigger TODO, power ref in README |
| PM | R1 | R1-5: b_perp_range_T comment fix | Dispatched — cosmetic one-liner |

### In Progress

| Repo | Item | Started | Notes |
|------|------|---------|-------|
| — | All repo code work complete | — | Remaining work is report-level |

### Blocked

| Item | Blocked On | Unblock Action |
|------|-----------|---------------|
| R2-2 (clamp widening) | Decision D-1 | Decide on sector clamp value |
| FR-1 through FR-24 | Decisions D-1 through D-4 + writing time | Schedule report session |
| FIG-1 through FIG-4 | Decisions + repo data | After decisions made |
| OTH-1 (regenerate 50K dataset) | R1-1 complete ✓ | Can run anytime on the local DGX Spark node |

### New Report-Level Items Discovered Today

| # | Item | Source | Notes |
|---|------|--------|-------|
| FR-25 | Fix bumpless transfer delta: report says 0.076 V, correct primary value is 0.100 V | R3-8 audit | Use 0.100 V as primary, 0.076 V as second operating point |
| FR-26 | Fix PID clock frequency in report: says 100 MHz and 125 MHz, actual is 200 MHz | R3 audit P2 | 125 MHz is PLL input, 200 MHz is fabric clock |
| FR-27 | Add curriculum training as planned follow-on improvement | R2 audit P4 | Currently single-pass monolithic; 4-phase curriculum designed but not implemented |
| FR-28 | Document missing noise sources (shot, RIN, Johnson, vibration, 1/f, MW phase) in Limitations | R1 audit P2 | 6 real-world sources not modeled — goes in Section 9 |

---

## Decision Points Needed Today

| # | Decision | Options | Impact | Status |
|---|----------|---------|--------|--------|
| D-1 | What sector clamp value to standardize on? | ±2.5 µT, ±5 µT, ±15 µT, or tiered | Affects Repo 2 training, Repo 3 safety proof, report Sections 3, 6, 8 | OPEN |
| D-2 | Cut MagNav.jl metric or heavily caveat? | Cut entirely / Caveat as "plausibility only" | Report Section 8.6 | OPEN |
| D-3 | Reframe KPP 1 or re-run heading sweep with wider clamp? | Reframe narrative / Re-run experiment | Report Section 1, 8.1 | OPEN |
| D-4 | What TRL to claim? | TRL 3 / TRL 3+ / TRL 4 with caveats | Report Section 1, 10 | OPEN |

---

*Last updated: April 4, 2026 — ALL REPO WORK COMPLETE. Remaining work is report-level (Part 2).*

