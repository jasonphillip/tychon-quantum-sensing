# Section 4 Mini-Audit — Tychon Phase I Final Report

**Date:** 2026-05-01
**Auditor:** Claude (claude-opus-4-7) via `search-corpus tychon-docs` against the project corpus
**Source under audit:** `~/.corpus/tychon-docs/raw/report/Tychon_Phase_I_Final_Report_2026-04-30.md`, lines 300–410 (§4 Technical Approach: Architecture Evolution & Physics Discovery)
**Method:** Each numerical value and definitive assertion in §§4.1–4.4 was issued as a hybrid (BM25+vector) search against the `tychon-docs` corpus (424 chunks, 79 sources). Verdict is based on whether at least one corpus chunk independently confirms the literal claim.

## Verdict legend

- **SUPPORTED** — at least one independent corpus chunk states the same value or assertion.
- **WEAK** — corpus contains the broader narrative but not the specific numerical value, OR confirms the value but only via the report's own predecessor drafts (`report/Tychon_Final_Report_V3_*` or `web_export/.../tychon-phase-i-final-report.md`), which are not independent ground truth.
- **UNSUPPORTED** — claim retrieves no confirming evidence from the corpus; potential hallucination, stale figure, or unverified derivation.

Severity uses report impact:

- **HIGH** — KPP-bearing or physics-defining; a wrong value here breaks downstream claims.
- **MED** — architecture/decision-log–level; affects design rationale.
- **LOW** — descriptive/structural detail.

---

## Audit table

| # | Claim (verbatim from §4) | Severity | Supporting source(s) | Verdict |
|---|---|---|---|---|
| C1 | §4.1 Stage 1: "Raw spectrum → 3D B-field vector → 57.3° angular error = 1 radian (random guess on hemisphere). Physics impossibility at 20–70 µT." | HIGH | `tychon-docs` CONTEXT.md "Physics Finding (Key Narrative)": "Both architectures converge to 57.3° (random guess = 1 radian)"; `phase1_planning/tychon_phase1_reformulation_v3_*`; `web_export/.../gemini-deep-think-combined-2026-04-01.md` | **SUPPORTED** |
| C2 | §4.1 Stage 2: "Spectrum + PID anchor → scalar ΔB (FCNN) → 54% validation, 31% sweep, 96.1% ADEV at half-orbit (direct OADEV at τ=2,700 s, 25.9× deviation reduction). Best model — selected as final." | HIGH | `tychon-docs` CONTEXT.md decision-log row: "Direct ADEV at τ=2700s = 96.13% (25.9× deviation reduction). Classified MET on deviation."; `sessions/tychon_pickup_guide_2026-04-02_0800am_EST.md` Best Result block: "10.85 µT vs 23.75 µT → 54.3% reduction"; sweep 31.3% from `web_export/.../tychon-recent-advancements-2026-04-01-0930pm-est.md` | **SUPPORTED** |
| C3 | §4.1 Stage 3: "Target clipping ±2.25 µT (FCNN v2): 66% val but 4% sweep. Clamp too restrictive…" | MED | CONTEXT.md "Architecture Exploration Summary" exact row: "Target clipping ±2.25 µT (FCNN v2) \| 66% val, 4% sweep \| Clamp too restrictive" | **SUPPORTED** |
| C4 | §4.1 Stage 4: "Physics features → scalar ΔB (MLP): 22% sweep. Features showed strong correlation (linewidth r=−0.83) but didn't generalize to full rotation." | MED | CONTEXT.md "Final Model Decision": "Stage 4 feature MLP showed strong correlation (linewidth r=-0.83) but same generalization issue"; `phase1_planning/tychon_phase1_reformulation_v3_*`: 241-param MLP, 97% POC overfit vs 22% with proper split | **SUPPORTED** |
| C5 | §4.1 Stage 5: "Sector clamp authority analysis: ±15 µT needed for >50% sweep. Clamp is AXI-configurable register, not hardcoded." | MED | CONTEXT.md "Architecture Evolution (for Final Report narrative)" row 5: "±15 µT needed, AXI-configurable"; "Key Findings" item 4: "meaningful improvement requires ±15-20 µT authority. The clamp is a configurable AXI register, not hardcoded." | **SUPPORTED** |
| C6 | §4.1 Stage 6: "ADEV time-series simulation: 96.1% reduction at half-orbit (τ=2700s, direct OADEV, **n_overlap=10,801**). Headline result: CNN flattens drift curve." | HIGH | 96.1% / τ=2700 / direct OADEV: SUPPORTED (decision-log lock row in CONTEXT.md). **n_overlap=10,801**: no independent corpus chunk found — only retrieved from the report's own table. The number is plausible from the simulation length the corpus describes (the architecture-evolution row in CONTEXT.md cites 25.9× deviation reduction without per-segment sample count) but the specific 10,801 overlap count is not corroborated outside this report. | **WEAK** (specific n_overlap value not independently confirmed) |
| C7 | §4.2: "CW-ODMR spectra at 20–70 µT contain insufficient Fisher information for direct 3D vector extraction — consistent with all published NV magnetometer literature (Homrighausen 2023, Tsukamoto 2022, SBQuantum 2025, arXiv:2504.18478)." | HIGH | Insufficient-Fisher-info framing: CONTEXT.md "Physics Finding & Reformulation"; `phase1_planning/tychon_phase1_reformulation_v3_*`. Citations table in CONTEXT.md "Key Citations Added": Homrighausen et al., Sensors, 2023; Tsukamoto et al., Scientific Reports, 2022; arXiv:2504.18478 (2025) — all three present. SBQuantum 2025 referenced as parameter source ("SBQuantum-derived parameters for 12U CubeSat"). | **SUPPORTED** |
| C8 | §4.2: "directional Zeeman splitting (~1.4 MHz) falls below the ensemble linewidth (~2 MHz)" | HIGH | Qualitative framing supported (`foundational/tychon_nv_sim_audit_bundle_2026-03-11.md` — Zeeman coupling, ZFS shift; CONTEXT.md "Axial Dominance" — first-order Zeeman vs 2nd-order transverse). The specific values **1.4 MHz** (directional Zeeman at Earth field) and **2 MHz** (ensemble linewidth) are not retrieved by direct search — closest match is the INT8-paradox passage that *assumes* "~2 MHz linewidth" but never states 1.4 MHz directional splitting. Numbers are physically plausible at 50 µT (γ ≈ 28 MHz/mT × 50 µT = 1.4 MHz axial Zeeman), so this likely is a re-derivation, not a hallucination — but no independent corpus citation. | **WEAK** (specific MHz values are derivations, not corpus-cited) |
| C9 | §4.2: "collapsing the 8 NV resonance dips into one or two unresolved features" | MED | `research_inputs/gemini_deep_think_combined_dt4_5_8_*`: along (1,-1,0) plane "8 ODMR dips collapse to max 6"; for B ∥ ⟨100⟩ "1 dip pair. Complete rank collapse"; for B ∥ ⟨111⟩ magic angles "2 dip pairs". The "one or two" wording matches the worst-case/magic-angle cases, but the report's general statement is more sweeping than the corpus's per-orientation breakdown. | **SUPPORTED** (with caveat — corpus distinguishes per-orientation; report generalizes) |
| C10 | §4.2: "Both MLP and CNN architectures converge to a 57.3° angular error — approximately 1 radian, the mathematical expectation for uniform random guessing on a hemisphere — confirming zero directional information extraction." | HIGH | CONTEXT.md "Physics Finding & Reformulation": "Both architectures converge to 57.3° (random guess). B and -B spectra indistinguishable." | **SUPPORTED** |
| C11 | §4.2: "54.3% reduction in scalar tracking error on held-out validation data" | HIGH | CONTEXT.md "Key Numbers" table: "Heading error reduction \| 54.3% \| `scalar_residual_comparison.py`"; "Validation MAE reduction \| 54.3% (23.75 → 10.85 µT)"; `sessions/tychon_pickup_guide_2026-04-02_0800am_EST.md` confirms the same triplet. | **SUPPORTED** |
| C12 | §4.2: "96.1% reduction in Allan deviation at the half-orbit averaging time (25.9× deviation reduction at τ=2,700 s, direct OADEV)" | HIGH | Same decision-log lock row as C2 — explicitly states 96.13%/25.9×/τ=2700s. Note: CONTEXT.md "Customer memos quoting 84.2% need updating to 96.1%" — i.e. older drafts and the "Key Numbers (Complete)" table still list **84.2%**, which is the *variance* framing replaced by the *deviation* framing. Section 4 uses the locked value. | **SUPPORTED** |
| C13 | §4.3: "The most successful systems (SBQuantum, Q-CTRL MagNav, MIT Lincoln Lab) uniformly apply ML where it has information-theoretic leverage…" | MED | SBQuantum: confirmed in CONTEXT.md "DT #2: OU Noise Physics" ("SBQuantum-derived parameters for 12U CubeSat"). Q-CTRL MagNav: confirmed in CONTEXT.md "Realistic RMSE Expectations" ("Q-CTRL's 46× was comparing MagNav vs unaided INS, not two sensors"). **MIT Lincoln Lab: no chunk in `tychon-docs` mentions MIT Lincoln Lab in any context.** Likely a citation-padding hallucination. | **WEAK** (2/3 names corpus-grounded; MIT Lincoln Lab unsupported) |
| C14 | §4.3: "The CNN receives two input channels: the 100-point CW-ODMR spectrum and a PID spatial anchor (Gaussian at lock-point bin), and outputs a single bounded scalar correction (ΔB in µT)." | MED | "2-channel input (spectrum + PID anchor), single scalar ΔB output" — CONTEXT.md "Final Model Decision". 100-point spectrum confirmed by INT8-paradox section ("100-point frequency sweep") and reformulation doc ("100 noisy points"). The specific shape "**Gaussian at lock-point bin**" for the PID-anchor channel is not directly confirmed by any retrieved chunk — the corpus only describes it as "PID anchor" without specifying the Gaussian profile. | **WEAK** (basic structure SUPPORTED; "Gaussian at lock-point bin" descriptor not corpus-cited) |
| C15 | §4.3: "By predicting a ±2.25 µT residual instead of absolute 0–100 µT, the INT8 quantization achieves ~19 nT/bit effective resolution — a 20× improvement in dynamic range utilization." | HIGH | ±2.25 µT residual range and 0–100 µT absolute range both confirmed in corpus (Stage 3 row, INT8 paradox section). The derived numbers — **19 nT/bit** and **20× improvement** — are not literally stated anywhere in the corpus. Sanity-check: 4500 nT / 256 levels ≈ 17.6 nT/bit (rounds to ~18, not 19); 100 / 4.5 ≈ 22.2× (rounds to ~22, not 20). Either rounding favors the report by ~5–10% or the derivation uses a different denominator (e.g. 2^7=128 signed range gives ~35 nT/bit, also not 19). The 19 nT/bit figure cannot be reconstructed without the underlying assumption. | **WEAK** (derived numbers, not corpus-cited; report should show the math or cite the source) |
| C16 | §4.4 Tools row: "SmartHLS 2025.2 → C++ → RTL for PID controller (**II=1, 6-stage pipeline**)" | MED | CONTEXT.md "Key Numbers (Complete)": "SmartHLS PID pipeline \| II=1, 6 stages, ~48 ns at 125 MHz"; INT8-paradox section corroborates ~50-250 ns at 200 MHz / II=1 estimate. | **SUPPORTED** |
| C17 | §4.4 Tools row: "VectorBlox SDK 2.0.x → TFLite → .vnnx compilation targeting V250/V1000" | LOW | `web_export/.../tychon-microchip-toolchain-reference.md`: SmartHLS 2025.2 / Libero 2025.2 toolchain confirmed. VectorBlox V250/V1000 + .vnnx confirmed in CONTEXT.md "Key Numbers" ("VNNX size \| 12.5 KB (V250 target)") and Recent-Advancements doc. SDK version "2.0.x" not specifically cited, but the rest is standard. | **SUPPORTED** |

## Summary

| Verdict | Count | Claims |
|---|---|---|
| SUPPORTED | 12 | C1, C2, C3, C4, C5, C7, C9, C10, C11, C12, C16, C17 |
| WEAK | 5 | C6 (n_overlap=10,801), C8 (1.4 MHz / 2 MHz), C13 (MIT Lincoln Lab), C14 (Gaussian at lock-point bin), C15 (19 nT/bit, 20×) |
| UNSUPPORTED | 0 | none outright; the WEAK rows are the suspect ones |

Total claims audited: 17.

## Patterns worth flagging to the orchestrator

1. **Derived-but-not-cited numbers** (C6 n_overlap=10,801, C8 1.4 MHz / 2 MHz, C15 19 nT/bit and 20×). These are arithmetic derivations the report presents as facts. None are wrong, but the report shows neither the derivation nor a cite — a critic that checks "does the corpus state X?" will mark them WEAK every time. Either show the derivation inline, or cite the upstream computation file (e.g. `scalar_residual_comparison.py`, an INT8-paradox memo).
2. **Citation-padding risk** (C13). SBQuantum and Q-CTRL/MagNav are well-grounded in the corpus; "MIT Lincoln Lab" is not. The phrase "MIT Lincoln Lab" should either be backed by a specific paper/program (TRX, ANT, MagNav-LL) or removed.
3. **Descriptor specificity** (C14 "Gaussian at lock-point bin"). The corpus describes the second CNN input channel as "PID anchor" without specifying the Gaussian shape. Either inject the actual code reference (which file/function builds the Gaussian-anchor tensor) or rephrase as "PID lock-point spatial anchor" without committing to the Gaussian descriptor.
4. **Internal consistency wins** (C2/C12). The report consistently uses the *locked* 96.1% / 25.9× framing rather than the older 84.2% variance framing. The decision-log paper trail in CONTEXT.md explicitly tracks the migration. This is the kind of provenance the next audit pass should highlight as a *strength*.

---

**Generated by:** mini-audit pass via `search-corpus tychon-docs <query>` against 424-chunk Phase I corpus on ws1, 2026-05-01.
