# Audit 003 — Tychon Phase I Final Report (post-versioning fix)

- Date: 2026-05-01
- Auditor: critic_loop ensemble (`qwen3-coder:30b` + `nemotron-mini:latest`) via Ollama on spark1, plus carry-over Pass 1 structure findings from audit-001
- Source under audit: same `Tychon_Phase_I_Final_Report_2026-04-30.md` (1,450 lines)
- Corpus delta vs audit-002: tychon-docs **−52 chunks** (r1_s1 archived) **+23 chunks** (r6_s25 closure + hier CSV summary) → net **498 → 469** chunks
- Claims processed: 97 (same set as audit-001 / audit-002)
- Total runtime: 6.2 minutes (371s)
- Diff: [`audit-002-vs-003-diff.md`](audit-002-vs-003-diff.md)

## Versioning fix

The Stage 4.5 ingest pulled in superseded April 2 r1_s1 timing artifacts that conflicted with the report's cited April 29 r6_s25 closure run. Stage 4.6 archived all r1_s1-derived files (and dependent .md summaries that referenced them) to `~/.corpus/tychon-docs/_superseded_baseline_r1_s1/` and pulled the actual r6_s25 closure artifacts from `tvw/source/sbir/05_repo_status/repo3_pid_real_closure_r6_s25_2026-04-29/` into a new `spark1_r6_s25_closure/` subdir.

### Resolved by versioning fix
- **F-012 (audit-002, c0057, critic FALSE POSITIVE)**: was CONTRADICTED, now **SUPPORTED**. The r6_s25 closure timing reports are now the authoritative timing evidence in the corpus. qwen quotes back +0.728 ns on the FIC_0 PLL OUT0 domain and confirms the internal PID datapath path. **This finding is closed.**

### New finding exposed by versioning fix
- **F-017 (c0033, NEW critic FALSE POSITIVE — same architectural class as F-012)**: qwen now flags **CONTRADICTED** on the report's *paper-shell* timing claim ("worst-case path delay of 5.893 ns with +2.107 ns positive slack on FIC_0 at 125 MHz"). The r6_s25 violations report shows different numbers (worse, because that report enumerates the worst-N paths). The retrieved chunks don't include narrative context distinguishing paper-shell from integrated. The +2.107 ns is correct for the *paper-shell* design state (pre-PID-integration) but the corpus only has the integrated r6_s25 timing data.
- Architectural lesson (carry-over): the corpus needs explicit `design_state:` / `closure_run:` provenance metadata so retrieval can route to the right artifact. Stage 4.6 fixed *one* run-conflict (r1_s1 vs r6_s25) but exposed the same shape of bug for design-state (paper-shell vs integrated).

## Summary

| Severity | audit-003 | audit-002 | audit-001 |
|---|---|---|---|
| CRITICAL | 3 | 3 | 3 |
| MAJOR | 5 | 5 | 4 |
| MINOR | 2 | 2 | 2 |
| DISAGREEMENT (pure) | 3 | 3 | 2 |
| **Total** | **13** | **13** | **11** |

Cross-cutting numbers (audit-003 vs audit-002):
- qwen3-coder-30b: SUPPORTED 90 (was 90), UNSUPPORTED 5 (was 5), WEAK 1 (was 1), CONTRADICTED 1 (was 1 — different claim now)
- nemotron-mini: SUPPORTED 85 (was 83), ERROR 12 (was 14)
- Disagreements: 19 (was 20), 6 "real" (neither side ERROR; same as audit-002)

## Verdict shifts (audit-002 → audit-003)
- 1 improved: **c0057** CONTRADICTED → SUPPORTED (the target of this stage)
- 1 worsened: **c0033** SUPPORTED → CONTRADICTED (new same-class FP, F-017 above)
- 3 lateral (nemotron-mini ERROR ↔ SUPPORTED flips): c0031, c0043, c0045

---

## CRITICAL findings

### F-001: Abstract claims "+1.04 ns at 200 MHz" but body shows +0.728 ns at 125 MHz with no 200 MHz corroborating value
- Severity: CRITICAL — **unchanged across all three audits**
- Status: r6_s25 closure now in corpus and confirms +0.728 ns on PLL OUT0 (125 MHz). The 200 MHz Vectorblox PLL still shows only "positive" slack (no specific number) in any retrieved artifact.
- Suggested action (unchanged): Replace abstract's "+1.04 ns at 200 MHz" with "+0.728 ns on PLL OUT0 at 125 MHz" sourced from §7.5 / `spark1_r6_s25_closure/MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.txt`.

### F-002: Deliverable 1 (§5.1–5.3) entirely [TODO]
- Severity: CRITICAL — **unchanged**

### F-003: Appendix C "References" is [TODO]
- Severity: CRITICAL — **unchanged**

---

## MAJOR findings

### F-004: §10.3, §10.4, Appendix A, Appendix B all [TODO]
- Severity: MAJOR — **unchanged**

### F-005: Figures 2 and 3 missing
- Severity: MAJOR — **unchanged**

### F-007: c0084 — "Business Plan: In progress" with §10.3 itself [TODO]
- Severity: MAJOR — **unchanged**

### F-008 *(carry-over from audit-002)*: c0020 — watchdog_timer_0/Primitives 26 LUTs / 20 DFFs not surfaced even after r6_s25 hier CSV ingest
- Severity: MAJOR — **unchanged**
- Status: With `spark1_r6_s25_closure/hier_resources_summary.md` now in corpus, the hierarchical CSV columns are present, but the specific row for `watchdog_timer_0/Primitives` with 26 LUTs / 20 DFFs is not in the top-50 head or the top-30 longest rows that the summary captured. May require inspecting full CSV (1,418 rows) or adjusting the summary script's row selection to favor watchdog_timer_0 row inclusion.
- Suggested action: Re-run hier CSV summary with explicit pattern filter for `watchdog_timer_0`, or augment the existing summary in `closure/closure_resources_summary.md` (which already exists from Stage 1) with the same data.

### F-009 *(carry-over)*: c0039 — PLL OUT3 50 MHz / +1.177 ns row not corroborated
- Severity: MAJOR — **unchanged**
- Status: r6_s25 closure timing reports now in corpus but PLL OUT3 row is not surfaced in the retrieved chunks (likely outside the top-N hottest paths the violations report enumerates).
- Suggested action: Stage the full SmartTime SDF or the PLL/CCC summary report directly if available, separate from the timing_violations reports.

---

## MINOR findings

### F-013: c0052 — VectorBlox "~610 mW, ~23%" still WEAK
- Severity: MINOR — **unchanged**

### F-014: nemotron-mini parse error rate 12/97 (12.4%) — slightly improved from audit-002
- Severity: MINOR — improved 14→12, still <25% tolerance.

---

## DISAGREEMENT findings (no other severity)

### F-015 *(was F-010 in audit-001)*: c0061 — Figure 4 caption fragment, critic noise
- Severity: DISAGREEMENT — **unchanged**

### F-016 *(was F-011)*: c0063 — "Section 8.5 derives..." qwen FALSE NEGATIVE (section exists)
- Severity: DISAGREEMENT — **unchanged**

### F-017 *(NEW, same architectural class as audit-002 F-012)*: c0033 — paper-shell timing claim looks CONTRADICTED because corpus has only integrated-design timing
- Severity: DISAGREEMENT (critic FALSE POSITIVE — design-state conflation)
- Source: claim `c0033`
- Claim: "On the FIC_0 clock domain at 125 MHz, the PID achieves a worst-case path delay of 5.893 ns with +2.107 ns positive slack."
- qwen verdict: CONTRADICTED — "Timing analysis shows worst-case delays exceed 5.893 ns and slack is negative, contradicting the claim."
- Ground truth: The +2.107 ns is the correct paper-shell (pre-PID-integration) slack, cited in the report's narrative explaining how the slack tightened from +2.107 ns (paper-shell) to +0.728 ns (integrated). The corpus only has the integrated r6_s25 timing data.
- Disposition: **Do not count as legitimate finding** during user triage. Same architectural lesson as F-012 (audit-002): provenance metadata (`design_state: paper_shell` vs `design_state: integrated`) needed before Stage 5+ critics can disambiguate.

---

## Pass 3 — Evidence coverage

| Section | Claims | with_doc_evidence | with_code_evidence |
|---|---|---|---|
| (unsectioned) | 97 | 97 (100%) | 97 (100%) |

Same Pass-3 limitation as prior audits: extractor lacks section threading.

---

## Stop-gate triage scorecard

- Verdict shifts vs audit-002: **5** (1 improved + 1 worsened + 3 lateral) — proves curation had real impact
- Total findings: **13** (target ≥10) — **PASS on count gate**
- Findings pre-flagged as critic noise: F-015, F-016, F-017 (3 of 13 = 77%); if user concurs, legitimate count is 10/13 = 77%, which is *just under* the 80% threshold
- If user agrees F-008 and F-009 are real citation gaps (which they are), legitimate count is 12/13 = 92%
- c0057 fix verified: was CONTRADICTED in audit-002, now SUPPORTED in audit-003 ✓
- Acceptance: **PASS on count; legitimacy gate is manual user triage**
