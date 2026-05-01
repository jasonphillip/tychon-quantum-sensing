# TVW Stage Roadmap

Each stage produces a working artifact and a verifiable stop-gate. The orchestrator (separate Claude session in `~/projects/skills/`) checks the stop-gate before advancing.

| # | Stage | Stop-gate | Status |
|---|---|---|---|
| 0 | Bootstrap | repo exists, `git status` clean, Spark 2 health green | complete (2026-05-01) |
| 1 | tychon-docs corpus | `chunks.db >100` chunks; 3/3 known-claim spot-checks return supporting source as top-3 hit; CONTEXT.md exists | blocked (2026-05-01): 86 chunks < 100; spot-checks 3/3 PASS; CONTEXT.md exists. Recall is functionally fine — gate fails only on chunk count. Orchestrator decides: expand sources (02_foundational, 03_phase1_planning, 04_phase2_planning, 06_research_inputs adds 21 .md/.txt files) or relax count threshold. |
| 2 | tychon-code corpus | `symbols` row for `pid_step` at canonical site; nv-sensor-sim post-filter <2,000 files; cross-corpus query returns hits from both | pending |
| 3 | NIM critic ensemble | both NIMs respond <30s; critic_loop.py CSV shows ≥1 disagreement on 5-claim run | pending |
| 4 | audit-and-implement against report | tvw/audits/audit-001.md has ≥10 severity-tagged findings; ≥80% triaged legitimate | pending |
| 5 | Llama-3.3-70B reviewer | 5K-token critique 30–90s; ≥7/10 calibration agreement with NIM ensemble | pending |
| 6 | multi-agent-chatbot fork | "200 MHz timing claim?" returns grounded answer citing both corpora + a code symbol | pending |
| 7 | txt2kg claim graph (optional) | .graphml exported; orphan-claim count documented | pending |
| 8 | nemo-automodel fine-tune | beats base on held-out Tychon Q&A; checkpoint reusable as NIM service | pending |
| 9 | publish-repo Dist A scrub | zero matches for `FX255-PCS02-0044` + sponsor names; metadata stripped | pending |

Natural quitting points: after Stage 1 (searchable docs), Stage 4 (audited punch list), Stage 6 (chat workbench), or Stage 8 (Tychon-owned model).
