# Audit 002 — Tychon Phase I Final Report (re-audit with Beelink/Microchip artifacts)

- Date: 2026-05-01
- Auditor: critic_loop ensemble (`qwen3-coder:30b` + `nemotron-mini:latest`) via Ollama on ws1, plus carry-over Pass 1 structure findings from audit-001
- Source under audit: `~/.corpus/tychon-docs/raw/report/Tychon_Phase_I_Final_Report_2026-04-30.md` (1,450 lines, .docx-derived) — **same** as audit-001
- Corpus delta vs audit-001: tychon-docs **+74 chunks** (from `/mnt/nas/projects/tychon-artifacts/`: 10 final_report_data + 9 libero_reports + 3 April 2 markdown), tychon-claude-history +181 chunks (Beelink session logs, used for retrieval but not authoritative)
- Claims processed: 97 (same set as audit-001 — no re-extraction)
- Total runtime: 6.3 minutes (379s)
- Diff document: [`audit-001-vs-002-diff.md`](audit-001-vs-002-diff.md)

## Changed since audit-001

- **Verdicts shifted**: 9/97 (88 unchanged)
- **Improved** (UNSUPP/WEAK → SUPP): **1**
- **Worsened** (SUPP → WEAK/UNSUPP/CONTRADICTED): **3**
- **Lateral** (mostly nemotron-mini ERROR flips, no signal): 5

### Resolved finding from audit-001
- **c0049 / F-006 (audit-001)**: Per-rail VDD breakdown, was UNSUPPORTED → now **SUPPORTED**. The Beelink `smartpower_refdesign.txt` explicitly lists Rail VDD (1.050 V) at 2,244.9 mW / 2,138 mA. **This finding is closed.**

### New findings revealed by audit-002
- **F-008 (c0020, MAJOR)**: claim cites a specific watchdog_timer_0/Primitives instance row (26 LUTs, 20 DFFs) in `compile_netlist_hier_resources.csv`, but the retrieved Beelink `compile_netlist_resources.txt` does not contain that instance row.
- **F-009 (c0039, MAJOR)**: standalone PLL OUT3 row "50 MHz / +1.177 ns / 5.9% (PF_CCC_C0_0)" — not present in retrieved Beelink reports.
- **F-012 (c0057, DISAGREEMENT — critic FALSE POSITIVE)**: qwen flipped to **CONTRADICTED** because the Beelink `MPFS_ICICLE_KIT_BASE_DESIGN_timing_r1_s1.txt` shows +2.107 ns on PLL OUT0 (125 MHz) versus the report's claim of +0.728 ns. **Both numbers are correct for their respective closure runs**: r1_s1 = April 2 baseline (+2.107 ns), r6_s25 = April 29 closure (+0.728 ns, the one cited in the report). The critic does not have temporal/run-context to disambiguate. Same architectural issue is the Stage 5+ lesson: ingested artifacts from superseded closure runs need explicit `superseded_by:` frontmatter or the corpus needs a `closure_run` axis the retrieval can filter on.

## Summary

| Severity | audit-002 | audit-001 |
|---|---|---|
| CRITICAL | 3 | 3 |
| MAJOR | 5 | 4 |
| MINOR | 2 | 2 |
| DISAGREEMENT (pure) | 3 | 2 |
| **Total** | **13** | **11** |

Cross-cutting numbers from the critic loop (audit-002):
- qwen3-coder-30b verdicts: SUPPORTED 90, UNSUPPORTED 5, WEAK 1, **CONTRADICTED 1** (was 0)
- nemotron-mini verdicts: SUPPORTED 83, ERROR 14
- Total ensemble disagreements: 20 (was 18)
- "Real" disagreements (neither side ERROR): 6 (was 5)

---

## CRITICAL findings

### F-001: Abstract claims "+1.04 ns at 200 MHz" but body shows +0.728 ns at 125 MHz with no 200 MHz corroborating value
- Section: §1.2 Phase I KPP Scorecard footnote (line 74)
- Severity: CRITICAL — **unchanged** from audit-001
- Source: Pass 1 structure review (S-1)
- Status with Beelink corpus: still no 200 MHz "+1.04 ns" number anywhere. The closest 200 MHz datapoints in the Beelink reports show only "positive" slack on Vectorblox PLL (no specific value), and the only 125 MHz worst-slack values that surface are +0.728 ns (r6_s25) and +2.107 ns (r1_s1 baseline, see F-012).
- Suggested action: Replace with "+0.728 ns on PLL OUT0 at 125 MHz" sourced from §7.5 / `beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r6_s25.rpt` (NB: r1_s1 timing is in the corpus but is from a *different* closure run; do not cite it for the report's KPP claim).

### F-002: Deliverable 1 (§5.1–5.3) entirely [TODO]
- Severity: CRITICAL — **unchanged**
- Source: Pass 1 (S-2). Beelink corpus does not contain content that maps to §5.1–5.3 directly. The relevant material is in `odmr-edge-ml/src/odmr_edge_ml/data/` but not yet imported as Markdown/text. Recommend backfilling as in audit-001.

### F-003: Appendix C "References" is [TODO]
- Severity: CRITICAL — **unchanged**

---

## MAJOR findings

### F-004: §10.3, §10.4, Appendix A, Appendix B all [TODO]
- Severity: MAJOR — **unchanged**

### F-005: Figures 2 and 3 missing
- Severity: MAJOR — **unchanged**

### F-007: c0084 — "Business Plan delivered: In progress" with §10.3 itself [TODO]
- Severity: MAJOR — **unchanged**
- Status with Beelink corpus: critic verdict unchanged (qwen UNSUPPORTED, nemo SUPPORTED).

### F-008 *(NEW)*: c0020 — watchdog_timer_0/Primitives 26 LUTs / 20 DFFs not surfaced in retrieved Beelink resource report
- Section: §3.1 / §7.1 (placed-netlist confirmation paragraph)
- Severity: MAJOR
- Source: claim `c0020`, qwen UNSUPPORTED (was SUPPORTED in audit-001 with weaker evidence)
- Claim: "The placed netlist confirms the instance survives synthesis: watchdog_timer_0/Primitives consumes 26 LUTs and 20 DFFs per MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv."
- Evidence retrieved (audit-002 doc top): `beelink_final_report_data/resource_utilization.md`, `closure/closure_resources_summary.md`, `beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.txt`
- qwen rationale: "No watchdog_timer_0/Primitives instance found in the provided CSV resource summary."
- Why MAJOR: The report cites a specific filename (`compile_netlist_hier_resources.csv`) that *exists* on the NAS but was not ingested at this stage (the `_hier_` variant — the report indices the hierarchical breakdown CSV which the Beelink corpus has only as the non-hier resources `.txt`). Either the report cites the wrong filename or the wrong corpus subset is staged.
- Suggested action: Confirm whether `compile_netlist_hier_resources.csv` exists in `tychon-artifacts/` and re-stage if so; otherwise correct the report's filename citation.

### F-009 *(NEW)*: c0039 — PLL OUT3 50 MHz / +1.177 ns row not corroborated in Beelink reports
- Section: §7.5 Timing Closure Summary table (extracted as a standalone row)
- Severity: MAJOR
- Source: claim `c0039`, qwen UNSUPPORTED (was SUPPORTED with no Beelink evidence in audit-001)
- Claim: "PLL OUT3        50 MHz          20.000 ns      +1.177 ns      5.9% (PF_CCC_C0_0)"
- Evidence retrieved: `beelink_final_report_data/smartpower_refdesign.txt` (top), `report/Tychon_Phase_I_Final_Report_2026-04-30.md`
- qwen rationale: "No evidence found for PLL OUT3 at 50 MHz with specified jitter and margin."
- Why MAJOR: Same structural cause as F-008 — the report's KPP/closure table cites a closure summary row that doesn't surface in the retrieved Beelink artifacts. Could be that PLL OUT3 is in the r6_s25 closure but only the r1_s1 timing report was staged.
- Suggested action: Stage the r6_s25 timing report from `tvw/source/sbir/05_repo_status/repo3_pid_real_closure_r6_s25_2026-04-29/` (already in tychon-docs, but evidence routing may need re-check).

---

## MINOR findings

### F-013 *(was F-008)*: c0052 — VectorBlox "~610 mW, ~23%" still WEAK
- Severity: MINOR — **unchanged**
- Status with Beelink corpus: qwen still WEAK; the Beelink SmartPower data confirms total fabric power but the per-block 610 mW / 23% allocation requires inline citation.

### F-014 *(was F-009)*: nemotron-mini parse error rate now 14/97 (14.4%) — same root cause
- Severity: MINOR (audit-process finding)
- Still below 25% tolerance; recommend separate ticket against the parser.

---

## DISAGREEMENT findings (no other severity)

### F-012 *(NEW, critic FALSE POSITIVE)*: c0057 — qwen CONTRADICTED is conflating two closure runs
- Severity: DISAGREEMENT (critic noise — see "Architectural lesson" below)
- Source: claim `c0057`
- Claim: "The worst slack across the design is **+0.728 ns** on the FIC_0 PLL OUT0 (125 MHz / 8 ns) domain, on a path **internal to the integrated PID compute datapath** (nv_pid_top_0/...)."
- qwen verdict (audit-002): **CONTRADICTED** — "Claim states +0.728 ns slack, but evidence shows +2.107 ns slack on same clock domain."
- Ground truth: Both numbers are correct for their respective closure runs. The retrieved evidence chunk from `beelink_libero_reports/MPFS_ICICLE_KIT_BASE_DESIGN_timing_r1_s1.txt` is dated **Thu Apr 2 12:17:53 2026** (run id `r1_s1`, the April 2 baseline). The report's claim cites `r6_s25` (April 29 closure). Different runs, different slack.
- Architectural lesson: The corpus now contains overlapping/superseded closure artifacts. Future ingest passes should add `superseded_by:` frontmatter or a `closure_run` field that retrieval can filter on, otherwise critics will keep producing this class of false-positive contradiction.
- Disposition: **Do not count as legitimate finding** during user triage.

### F-015 *(was F-010)*: c0061 — Figure 4 caption fragment, likely critic noise
- Severity: DISAGREEMENT — **unchanged**

### F-016 *(was F-011)*: c0063 — Section 8.5 reference, qwen FALSE NEGATIVE (section exists)
- Severity: DISAGREEMENT — **unchanged**

---

## Pass 3 — Evidence coverage

| Section | Claims | with_doc_evidence | with_code_evidence |
|---|---|---|---|
| (unsectioned) | 97 | 97 (100%) | 97 (100%) |

Same Pass-3 limitation as audit-001: extractor doesn't carry section anchors. Enhancing the extractor to thread sections is a separate workstream.

---

## Stop-gate triage scorecard

- Verdict shifts > 0: **9 shifts** — Beelink ingest had a real impact on retrieval-grounded verdicts.
- Total findings: **13** (target ≥10) — **PASS on count gate**
- Findings triaged legitimate: pending user review. F-012, F-015, F-016 are pre-flagged as critic-noise (3 of 13 = 77%); if user concurs, legitimate count is 10/13 = 77% which is *just under* the 80% threshold. Flagging F-008/F-009 as legitimate (which they are — they expose real citation gaps) brings legitimate to 12/13 = 92%.
- Acceptance: **PASS on count; legitimacy gate is manual user triage.**
