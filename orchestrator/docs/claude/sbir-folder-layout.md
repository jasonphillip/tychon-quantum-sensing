# SBIR Phase I working folder — layout

> Extracted verbatim from CLAUDE.md (2026-07-17 progressive-disclosure restructure).
> The behavioral rules stay in CLAUDE.md: the folder is symlinked at
> `tvw/source/sbir/tychon-nv-sim-repos/` → `~/projects/tychon-sbir/docs/`, is
> read-only from TVW (never `git add` from here), and the fix list must be re-read
> before planning any fix session.

Layout:
- `May_1_2026_Document_Fix_List.md` — **active work driver.** v3 fix list, split into editorial fixes (Parts 1–2) and technical work (Part 3 — clamp authority, covariate shift, orbit-in-the-loop benchmark). Always re-read this before planning a fix session; it changes between runs.
- `INDEX.md`, `STATUS.md`, `OUTREACH_TRACKER.md` — running status files.
- `01_deliverables/` — `final_report/`, `capability_brief/`, `audits/` (mirror target for TVW audit-NNN.md), `tvw_logs/`.
- `02_foundational/`, `03_phase1_planning/`, `04_phase2_planning/` — proposal + Phase II priority docs (P1 hierarchical INT8, P2 ephemeris sampling, core proposal v2).
- `05_repo_status/` — per-repo snapshots and r6_s25 closure logs.
- `06_research_inputs/`, `07_technical_references/`, `08_session_logs/`, `09_misc/`.
