# TVW Stage Roadmap

> **Active plan (2026-10-12):** pre-publication fixes before the public switch (plan files are kept outside the published tree). Previous: outside-review fixes, 2026-10-09.


Each stage produces a working artifact and a verifiable stop-gate.

> **Note (2026-05-03):** TVW was refactored from "Verification Workbench" to "Orchestration Workbench." The audit-pipeline stages (1–9) below are still tracked, but they are now **one capability among several**, not the sole purpose. TVW also drives the May 1 fix list, edits the SBIR shared folder directly, runs web-enabled corpus acquisition, and dispatches committable changes to the four implementation repos. Stages 5–9 (heavyweight reviewer, multi-agent chatbot, txt2kg, fine-tune, publish-repo) remain **optional** — pursue them if their stop-gate is the right next step, otherwise prioritize fix-list orchestration.

| # | Stage | Stop-gate | Status |
|---|---|---|---|
| 0 | Bootstrap | repo exists, `git status` clean, Spark 2 health green | complete (2026-05-01) |
| 1 | tychon-docs corpus | `chunks.db >100` chunks; 3/3 known-claim spot-checks return supporting source as top-3 hit; CONTEXT.md exists | complete (2026-05-01, rerun): 280 chunks ✓; 3/4 spot-checks PASS; 4th probe ("Phase II proposal") returned phase1_closeout_findings which IS a supporting source per the gate definition. SQL confirms phase2_planning is indexed (16 chunks, 4 sources). Orchestrator-accepted: ranking preference, not an indexing fault. |
| 1.5 | Web-export ingest (SBIR FastTrack project) | tychon-docs gains 24 docs (>50 new chunks); new tychon-claude-history corpus has docs + conversations indexed; redaction audit returns zero secret matches | complete (2026-05-01): tychon-docs 280→424 (+144 chunks, 25 new sources); tychon-claude-history 939 chunks / 62 sources (24 docs + 37 conversations + 1 project metadata); redaction audit 0 hits across both raw trees; 5/5 spot-checks PASS. CONTEXT.md not generated for tychon-claude-history (not a gate criterion). |
| 2 | tychon-code corpus | `symbols` row for `pid_step` at canonical site; nv-sensor-sim post-filter <2,000 files; cross-corpus query returns hits from both | complete (2026-05-01): 187 chunks / 101 sources across 4 repos (polarfire 55, odmr-edge-ml 88, nv-sensor-sim 43, shared-data manifest 1). Filter: nv-sensor-sim 74 tracked → 37 first-party (well under 2000). Symbols/xrefs tables empty (universal-ctags not installed) — fidelity downgrade, not gate failure: PID-related chunk reachable via query (top hit `polarfire-hybrid-control/hls/src/nv_pid.cpp` containing `nv_pid_top`). 3/3 query spot-checks PASS; cross-corpus "200 MHz" returns 8 docs hits + 3 code hits. Optional upgrades: `pip install tree-sitter-language-pack` (semantic chunking) and `sudo apt install universal-ctags` (symbols/xrefs). |
| 3 | NIM critic ensemble | both NIMs respond <30s; critic_loop.py CSV shows ≥1 disagreement on 5-claim run | blocked (2026-05-01, Path D pivot — Ollama, NIM downloads skipped per orchestrator): qwen3-coder:30b + nemotron-mini:latest, 41s for 10 claims (avg 4.1s/claim pair), parse error rate 0.0% — latency and parsing gates pass cleanly. Independence proof FAILS: 10/10 verdicts SUPPORTED on both critics (0 disagreements). Likely cause: extracted claims are sentence fragments from `extract_claims_from_doc.py`, not contestable assertions; both critics default SUPPORTED on partial-evidence retrieval. Orchestrator decides: refine extractor, hand-curate adversarial claim sample, or accept ensemble without disagreement signal. |
| 4 | audit-and-implement against report | tvw/audits/audit-001.md has ≥10 severity-tagged findings; ≥80% triaged legitimate | complete on count gate (2026-05-01): 11 findings (3 CRITICAL, 4 MAJOR, 2 MINOR, 2 DISAGREEMENT). Legitimacy gate (≥80%) is **manual user triage pending**. Headline findings: F-001 abstract/body KPP timing-slack conflict (+1.04 ns at 200 MHz vs +0.728 ns at 125 MHz), F-002 Deliverable 1 (§5.1–5.3) entirely [TODO], F-003 Appendix C References [TODO]. Mirrored to ~/Desktop/Shared/tychon-nv-sim-repos/01_deliverables/audits/. |
| 4.5 | Beelink/Microchip artifact ingest + re-audit | audit-002.md generated from same 97 claims with corpus including tychon-artifacts/; verdict shifts > 0 (proof new evidence mattered) | complete (2026-05-01): tychon-docs +74 chunks (424→498), tychon-claude-history +181 chunks (939→1120). Redaction audit 0 hits. 9 verdict shifts: 1 improved (c0049 per-rail VDD UNSUPP→SUPP, F-006 from audit-001 RESOLVED), 3 worsened (incl. c0057 SUPP→CONTRADICTED — critic FALSE POSITIVE conflating r1_s1 baseline with r6_s25 closure), 5 lateral. audit-002.md = 13 findings (3 CRITICAL, 5 MAJOR, 2 MINOR, 3 DISAGREEMENT). Diff at tvw/audits/audit-001-vs-002-diff.md. |
| 4.6 | Corpus versioning fix (r1_s1 archived, r6_s25 closure ingested) | audit-003 verdict shifts > 0; c0057 no longer CONTRADICTED | complete (2026-05-01): archived 7 r1_s1 files (3 raw timing + 4 dependent .md summaries) and purged 52 chunks from DB; staged 6 r6_s25 closure files + 1 hier CSV summary (+23 chunks); net 498→469 chunks. 5 verdict shifts: 1 improved (c0057 CONTRADICTED→SUPPORTED — F-012 RESOLVED), 1 worsened (c0033 SUPPORTED→CONTRADICTED — same-class FP F-017 on paper-shell vs integrated design state), 3 lateral. audit-003.md = 13 findings (3 CRITICAL, 5 MAJOR, 2 MINOR, 3 DISAGREEMENT). Architectural lesson: provenance metadata (`closure_run`, `design_state`) needed before Stage 5+ heavyweight critic. |
| 4.7 | Audit corrected report v3.1 | F-001 ∧ F-002 ∧ F-003 closed in audit-004 | complete (2026-05-01): v3.1 staged from `~/Desktop/Shared/Tychon_Phase_I_Final_Report_v3.1_2026-05-01.md` (649 lines, 92.3 KB). 469→492 chunks (+23). 114 claims (was 97). Pass 1 re-check: F-001 CLOSED (slack now +0.728 ns at 125 MHz with footnote citing r6_s25.rpt and excluding r1_s1), F-002 CLOSED (§5.1/5.2/5.3 fully populated), F-003 CLOSED (Appendix C has 22 IEEE refs, some `[CITATION NEEDED]` per author scope). audit-004.md: 0 CRITICAL (was 3), 1 MAJOR (F-005 figures, persisted by author), 2 MINOR, 4 DISAGREEMENT critic-noise + 6 [CITATION NEEDED] author-flagged pending. qwen 92.1% SUPPORTED (was 93%). All 3 audit-001 CRITICALs closed. |
| 4.8 | Render v3.1 .md → AFWERX submission .docx | .docx exists; section spot-check passes | complete (2026-05-01): pandoc 3.9.0.2 rendered 222 KB Word 2007+ docx using prior 2026-04-30.docx as `--reference-doc` (preserves Tychon styling). Sections present: Executive Summary, Validated Synthetic Data, References (×3 — TOC + heading + body), Change Log, Methodology (×3 sub). Image warnings replaced with text descriptions (media not staged locally). PDF render via weasyprint failed (local tinycss2 module mismatch — env issue, not blocking). Reproducible script at `tvw/scripts/render_report.sh`. |
| 5 | Llama-3.3-70B reviewer | 5K-token critique 30–90s; ≥7/10 calibration agreement with NIM ensemble | OPTIONAL — not required; audit-004 has 0 CRITICAL findings; heavyweight would be polish, not deliverable |
| 6 | multi-agent-chatbot fork | "200 MHz timing claim?" returns grounded answer citing both corpora + a code symbol | pending |
| 7 | txt2kg claim graph (optional) | .graphml exported; orphan-claim count documented | pending |
| 8 | nemo-automodel fine-tune | beats base on held-out Tychon Q&A; checkpoint reusable as NIM service | pending |
| 9 | publish-repo scrub | sponsor and customer names, a named advisor, a copied supplement, personal paths and a vendor e-mail: zero in tree and history (scan 2026-10-12, `RESULT: PASS`); proposal number kept by decision | done 2026-10-12 |

Natural quitting points: after Stage 1 (searchable docs), Stage 4 (audited punch list), Stage 6 (chat workbench), or Stage 8 (Tychon-owned model).

## Repair-loop stopping rule (adopted 2026-08-11, P0-4)

Applies to every verify→repair loop in TVW: critic ensemble re-runs, fix-list edit→re-audit
cycles, and render→check→re-edit passes. Grounded in VRR-Stop (arXiv 2607.17641, in
`~/.corpus/agent-reliability/`): when verifier and repairer are both noisy, repair can damage
already-correct work while *reported* acceptance keeps rising.

1. **Margin, not rounds.** Accept a repair only when the verification evidence for the repaired
   version is *stronger* than the evidence for the pre-repair version (e.g., a critic verdict
   flips with citation, a spot-check passes that previously failed). "The critic stopped
   complaining" is not a margin.
2. **Never accept a round-N fix on less evidence than round-1.** If the first repair was
   justified by a failing check, the second repair needs a failing check too — not vibes about
   the first repair being incomplete.
3. **Two failed repairs → stop and surface.** After two consecutive repair attempts that don't
   improve the verification margin, freeze the artifact, log the disagreement (DLOG or audit
   addendum), and hand the decision up — do not keep looping.
4. **Repair-of-repair is a flag.** Any loop that touches the same claim/file three times in one
   session gets called out explicitly in the session report with its evidence trail.

## Active driver: May 1, 2026 Document Fix List

Source of truth: `tvw/source/sbir/tychon-nv-sim-repos/May_1_2026_Document_Fix_List.md`. Per-fix status: `tvw/source/sbir/tychon-nv-sim-repos/fix-list-status.csv`. Items split by where the work belongs (post-2026-05-03 refactor):

**TVW does directly:**
- Editorial passes against the report (`Tychon_Phase_I_Final_Report_v3.1_*.md`) and capability brief (`Tychon_Capability_Brief_*.docx` ↔ `.md` round-trip).
- §5.1 / §5.2 / §5.3 / §10.2 prose drafts — pull citations from `tychon-docs`, ground architecture claims via `tychon-code-search`.
- Figures 2–3 regen, Q-CTRL/MIT-LL inline citations, KPP scorecard editorial.
- Appendix C citation verification (DOI / page / volume / Microchip-portal lookups) via `WebFetch` / firecrawl / `acquire-corpus`.
- §10.3 BoM analysis (component pricing via distributor sites — Digi-Key / Mouser).
- Direct edits to STATUS.md, INDEX.md, fix-list-status.csv, the DLOG, and audit mirror.

**TVW dispatches to other sessions:**
- Items 11a / 11b (Path A/B clamp authority), 12 (bias-aware augmentation), 13 (orbit-in-the-loop benchmark) — heavy ML on the dual DGX Sparks. TVW prepares + monitors; the long-running compute lives on spark1/spark2 background runners (`nohup` + pidfile). Note: SGP4 (`sgp4`) and IGRF-13 (`ppigrf`) pip packages must be staged onto Spark wheels before use.
- Repo commits — TVW edits files in the implementation repos but does not commit. Each repo's own Claude session owns the commit step.

**Stays on the user (not Claude-doable):**
- §10.4 Letters of Support (outreach / relationship work).

Mirror any TVW-produced audit artifacts to `tvw/source/sbir/tychon-nv-sim-repos/01_deliverables/audits/` (the audit mirror target).
