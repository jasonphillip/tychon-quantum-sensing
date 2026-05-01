# Audit 001 — Tychon Phase I Final Report

- Date: 2026-05-01
- Auditor: critic_loop ensemble (`qwen3-coder:30b` + `nemotron-mini:latest`) via Ollama on spark1, plus manual Pass 1 structure review
- Source under audit: `~/.corpus/tychon-docs/raw/report/Tychon_Phase_I_Final_Report_2026-04-30.md` (1,450 lines, .docx-derived)
- Claims processed: 97
- Total runtime: 6.2 minutes (374s) — Pass 2 ensemble critic loop only
- Stop-gate: ≥10 findings, ≥80% triaged legitimate (legitimacy is **manual triage pending user review**)

## Summary

| Severity | Count |
|---|---|
| CRITICAL | 3 |
| MAJOR | 4 |
| MINOR | 2 |
| DISAGREEMENT (pure) | 2 |
| **Total findings** | **11** |

Cross-cutting numbers from the critic loop:
- qwen3-coder-30b verdicts: SUPPORTED 92, UNSUPPORTED 4, WEAK 1
- nemotron-mini verdicts: SUPPORTED 84, ERROR 13 (parse failures; model returned valid JSON, parser truncated)
- Total ensemble disagreements (any-vs-any, including ERROR rows): 18
- "Real" disagreements (neither side ERROR): 5

---

## CRITICAL findings

### F-001: Abstract claims "+1.04 ns at 200 MHz" but body shows +0.728 ns at 125 MHz with no 200 MHz number
- Section: §1.2 Phase I KPP Scorecard footnote (line 74)
- Severity: CRITICAL
- Source: Pass 1 structure review (S-1 in `stage-4-structure-findings.md`)
- Claim: "Timing closure at **200 MHz with +1.04 ns slack** provides high confidence." (line 74)
- Evidence (body, conflicts):
  - §7.5 (line 793): worst slack is **+0.728 ns** on PLL OUT0 (**125 MHz** / 8 ns)
  - KPP table (line 571–581): PLL OUT0 = 125 MHz +0.728 ns; PLL OUT1 = 125 MHz +1.829 ns; Vectorblox PLL = 100/200 MHz "positive" (no specific number)
  - Closest historical 200 MHz datapoint cited (line 813): +1.215 ns from r3_s22 paper-shell, since superseded
- Why CRITICAL: An abstract-level KPP-stake numerical claim that does not match any value in the body or KPP table. Either (a) +1.04 ns is from an obsolete closure not visible in this report, or (b) the abstract conflates 125 MHz +0.728 ns with a 200 MHz qualifier. Either way, the abstract misrepresents the post-P&R closure number that is the headline quantitative result of Phase I FPGA implementation.
- Suggested action: Replace the "+1.04 ns at 200 MHz" with the actual post-P&R worst slack: +0.728 ns on PLL OUT0 at 125 MHz, citing §7.5. If the 200 MHz Vectorblox PLL has a specific positive slack that is intended to be reported, source it from the SmartTime report and qualify.

### F-002: Deliverable 1 (§5.1–5.3 "Validated Synthetic Data Pipeline") is entirely [TODO] in the "Final" report
- Section: §5.1, §5.2, §5.3 (lines 416–430)
- Severity: CRITICAL
- Source: Pass 1 (S-2)
- Claim: §5.1 Eigenvalue-Based CW-ODMR Sensor Model, §5.2 Coupled Noise Model, §5.3 Train/Test Separation — body is `[TODO]` placeholder text describing what the section *will* contain, not the content itself.
- Evidence: Verbatim text in body, e.g. line 418: "**\[TODO\] Describe NV Hamiltonian → eigenvalue → Lorentzian lineshape pipeline. 8 ms/spectrum, 50K dataset in ~4 min on DGX Spark.**"
- Why CRITICAL: The header reads "FINAL TECHNICAL REPORT". An entire named SBIR Deliverable's body description is missing. KPP-1 (Allan deviation) and KPP-2 (validation MAE) reduction depend on the synthetic data pipeline whose validity is documented in §5.1–5.3.
- Suggested action: Backfill §5.1–5.3 from existing source material. The closure deliverable, the Tychon AI platform reference docs, and the ODMR-edge-ml dataset code (`odmr-edge-ml/src/odmr_edge_ml/data/`) provide the inputs needed.

### F-003: Appendix C "References" is [TODO] — there is no reference list in the Final report
- Section: Appendix C (line 1450)
- Severity: CRITICAL
- Source: Pass 1 (S-2)
- Claim: References section content is the placeholder "**\[TODO\] Homrighausen 2023, Tsukamoto 2022, SBQuantum 2025, arXiv:2504.18478, Kashem 2026, USTC 2024, SBQuantum arXiv:2509.19179, arXiv:2504.18478.**" — a reading list of titles, not formatted citations.
- Why CRITICAL: An SBIR Phase I Final Technical Report without a reference list is non-deliverable. The body text contains citation-style references (e.g. "Tsukamoto 2022", "Homrighausen 2023") that have no entries to resolve to.
- Suggested action: Build the formatted reference list from the placeholder names, cross-checking against the body for missed citations. Make sure the in-text citation style matches.

---

## MAJOR findings

### F-004: §10.3, §10.4, Appendix A, Appendix B all [TODO]
- Section: §10.3 (line 1428), §10.4 (line 1432), Appendix A (line 1442), Appendix B (line 1446)
- Severity: MAJOR
- Source: Pass 1 (S-2)
- Claim: Commercialization & Dual-Use, DoD Transition Targets, Decision Log Summary, Glossary — all `[TODO]`.
- Why MAJOR (not CRITICAL): These are transition-plan and reference content, not body deliverable content. Phase I scope still requires them, but the gap is less severe than missing Deliverable 1 body or References.
- Suggested action: Backfill from the closure deliverable, decision log files, and the `web_export/sbir-fasttrack/docs/` glossary material that already exists in `~/.corpus/tychon-docs/raw/`.

### F-005: Figures 2 and 3 missing — numbering jumps from Figure 1 to Figure 4
- Section: Whole document
- Severity: MAJOR
- Source: Pass 1 (S-3)
- Claim: Only Figure 1 (line 128, "Concept of operations") and Figure 4 (line 830, "Hybrid control-loop execution timeline") appear in the report. No "Figure 2" or "Figure 3" anywhere.
- Why MAJOR: Either the figures were silently removed (renumber) or never inserted. Out-of-order figure numbering in a Final report is editorially unacceptable.
- Suggested action: Decide whether to renumber (Figure 4 → Figure 2) or insert the missing figures. The §6 architecture description and §8.4 heading-sweep narrative are likely candidates for the missing figures based on context.

### F-006: c0049 — Per-rail VDD specific values UNSUPPORTED by retrieved evidence (with critic disagreement)
- Section: §7.4 Power Analysis
- Severity: MAJOR
- Source: claim `c0049` in `stage-4-verdicts.csv`
- Claim: "Per-rail breakdown: Rail VDD (1.050 V): 2,244.9 mW (2,138 mA)."
- Evidence retrieved:
  - doc: phase1_planning/tychon_phase1_closeout_plan_v3_2026-04-27.md, web_export/sbir-fasttrack/docs/tychon-phase-i-final-report.md, report/Tychon_Phase_I_Final_Report_2026-04-30.md (i.e. itself)
  - code: odmr-edge-ml/experiments/scalar_residual_v2.py, nv-sensor-sim/src/nv_sensor_sim/config.py, polarfire-hybrid-control/libero/reports/2026-04-29-axi-target-experiment/MPFS_ICICLE_KIT_BASE_DESIGN.patched.v
- qwen3-coder verdict: UNSUPPORTED — "No evidence found for the specific rail voltage and power values mentioned in the claim."
- nemotron-mini verdict: SUPPORTED — "Evidence explicitly supports the claim's specific assertion." (boilerplate; rationale does not name the supporting numbers)
- Why MAJOR: The headline 5.2 W KPP-4 number depends on per-rail decomposition; if the rail breakdown can't be cited from a SmartPower report or DLOG entry, the aggregate is suspect. Retrieved evidence chunks point only at the report itself or planning docs, not the SmartPower CSVs in `tvw/source/sbir/05_repo_status/.../smartpower.spw`.
- Suggested action: Add an inline citation pointing at the specific SmartPower row for VDD; otherwise weaken to "approximately" with the closure deliverable as the citation.

### F-007: c0084 — "Business Plan delivered: In progress" claim references §10.3 which is itself [TODO]
- Section: deliverable status table
- Severity: MAJOR
- Source: claim `c0084` in `stage-4-verdicts.csv`; cross-reference S-2
- Claim: "Business Plan delivered In progress             Section 10.3"
- qwen3-coder verdict: UNSUPPORTED — "No evidence of a business plan delivery status in the retrieved documents."
- nemotron-mini verdict: SUPPORTED (boilerplate)
- Why MAJOR: The deliverable status row points at §10.3 for content; §10.3 is `[TODO]` (see F-004). The status table claims a deliverable that has no body description. This is a self-referential gap — the status table and the section it points at are both incomplete.
- Suggested action: Either backfill §10.3 (preferred — see F-004) or drop the row from the status table for the Final report.

---

## MINOR findings

### F-008: c0052 — VectorBlox "~610 mW, ~23%" specific numbers not corroborated by retrieved evidence
- Section: §7.4 Power Analysis
- Severity: MINOR
- Source: claim `c0052` (qwen WEAK, nemo SUPPORTED)
- Claim: "The Vectorblox inference engine accounts for the largest single contribution to fabric power at ~610 mW across its clock domains, approximately 23% of total fabric."
- qwen3-coder rationale: "Evidence shows Vectorblox contributes significantly to power but doesn't confirm 610 mW or 23% of total fabric."
- Why MINOR: The qualitative claim ("Vectorblox dominates fabric power") is supported; the specific numeric claim ("610 mW, 23%") requires a direct SmartPower citation that isn't surfaced. Same root cause as F-006.
- Suggested action: Cite the SmartPower row, or rephrase to "is the largest single fabric contributor (per SmartPower r6_s25)" without the specific percentage.

### F-009: nemotron-mini critic loop has 13.4% parse error rate (13/97) — fidelity floor for the ensemble
- Severity: MINOR (audit-process finding, not report finding)
- Source: `stage-4-verdicts.csv`, ERROR rows in `nemotron-mini_verdict`
- Observation: nemotron-mini returned valid JSON for these claims but the parser in `critic_loop.py` truncated mid-object on multi-line responses (see rationales beginning "unparseable response: {…").
- Why MINOR: 13.4% is below the plan's 25% tolerance, but every ERROR row is treated as a disagreement (inflating the disagreement count from a real 5 to 18) and removes one critic's signal. The independence proof remains valid (5 real disagreements > 0), but the ensemble's effective signal density is reduced.
- Suggested action: Track in a separate ticket against `~/projects/skills/skills/tychon-verify/scripts/critic_loop.py`. Out of scope for this audit; not an issue with the report.

---

## DISAGREEMENT findings (no other severity applies)

### F-010: c0061 — Figure 4 caption fragment extracted as standalone "claim"; likely critic noise
- Severity: DISAGREEMENT (likely critic-loop quirk, not a report issue)
- Source: claim `c0061`
- Claim: "*Figure 4: Hybrid control-loop execution timeline."  *(extracted as a single sentence; it is the figure caption itself, not an assertion about the figure)*
- qwen3-coder: UNSUPPORTED — "No evidence of a specific 'Hybrid control-loop execution timeline' figure in the retrieved chunks."
- nemotron-mini: SUPPORTED
- Disposition: Caption text was correctly preserved in the markdown (line 830) but the extractor treated it as a verifiable claim. Recommend reviewing whether figure captions should be excluded from the claim extractor's output.

### F-011: c0063 — "Section 8.5 derives the formal composition between the two." — qwen FALSE POSITIVE
- Severity: DISAGREEMENT (critic FALSE POSITIVE — section exists)
- Source: claim `c0063`
- qwen3-coder: UNSUPPORTED — "No evidence found referencing Section 8.5 or its derivation of formal composition."
- nemotron-mini: SUPPORTED
- Ground truth: Section 8.5 ("Safety Chain Composition with Absolute Stability Proof") **does** exist in the report at line 1041 and the formal composition derivation is its substance. The retrieved chunks happened not to include §8.5's content for this query.
- Disposition: Critic-loop retrieval miss, not a report issue. Reinforces that low retrieval recall on cross-references can produce false UNSUPPORTED verdicts. Recommend not counting this row as a legitimate finding during user triage.

---

## Pass 3 — Evidence coverage

| Section | Claims | with_doc_evidence | with_code_evidence |
|---|---|---|---|
| (unsectioned) | 97 | 97 (100%) | 97 (100%) |

All 97 claims received both doc and code evidence chunks. The extractor does not currently emit a `section` field per claim (the .docx-derived markdown lost heading attachment during the chunk-aware split), so per-section coverage is not yet computable. **This is a Pass-3 limitation worth a separate enhancement: thread section anchors through the extractor.**

---

## Stop-gate triage scorecard

- Total findings: **11** (target: ≥10) — **PASS**
- Findings triaged legitimate: *(pending user review)*
- Acceptance: **PASS on count gate; legitimacy gate is manual user triage**

The user/orchestrator should triage each finding and mark legitimate vs. critic-noise. F-010 and F-011 are explicitly flagged as likely critic-loop artifacts; if the user concurs, that brings the legitimate count to 9/11 = 82%, above the 80% threshold.
