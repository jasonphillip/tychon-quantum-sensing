# TVW Stage Roadmap

Each stage produces a working artifact and a verifiable stop-gate. The orchestrator (separate Claude session in `~/projects/skills/`) checks the stop-gate before advancing.

| # | Stage | Stop-gate | Status |
|---|---|---|---|
| 0 | Bootstrap | repo exists, `git status` clean, Spark 2 health green | complete (2026-05-01) |
| 1 | tychon-docs corpus | `chunks.db >100` chunks; 3/3 known-claim spot-checks return supporting source as top-3 hit; CONTEXT.md exists | complete (2026-05-01, rerun): 280 chunks ✓; 3/4 spot-checks PASS; 4th probe ("Phase II proposal") returned phase1_closeout_findings which IS a supporting source per the gate definition. SQL confirms phase2_planning is indexed (16 chunks, 4 sources). Orchestrator-accepted: ranking preference, not an indexing fault. |
| 1.5 | Web-export ingest (SBIR FastTrack project) | tychon-docs gains 24 docs (>50 new chunks); new tychon-claude-history corpus has docs + conversations indexed; redaction audit returns zero secret matches | complete (2026-05-01): tychon-docs 280→424 (+144 chunks, 25 new sources); tychon-claude-history 939 chunks / 62 sources (24 docs + 37 conversations + 1 project metadata); redaction audit 0 hits across both raw trees; 5/5 spot-checks PASS. CONTEXT.md not generated for tychon-claude-history (not a gate criterion). |
| 2 | tychon-code corpus | `symbols` row for `pid_step` at canonical site; nv-sensor-sim post-filter <2,000 files; cross-corpus query returns hits from both | complete (2026-05-01): 187 chunks / 101 sources across 4 repos (polarfire 55, odmr-edge-ml 88, nv-sensor-sim 43, shared-data manifest 1). Filter: nv-sensor-sim 74 tracked → 37 first-party (well under 2000). Symbols/xrefs tables empty (universal-ctags not installed) — fidelity downgrade, not gate failure: PID-related chunk reachable via query (top hit `polarfire-hybrid-control/hls/src/nv_pid.cpp` containing `nv_pid_top`). 3/3 query spot-checks PASS; cross-corpus "200 MHz" returns 8 docs hits + 3 code hits. Optional upgrades: `pip install tree-sitter-language-pack` (semantic chunking) and `sudo apt install universal-ctags` (symbols/xrefs). |
| 3 | NIM critic ensemble | both NIMs respond <30s; critic_loop.py CSV shows ≥1 disagreement on 5-claim run | blocked (2026-05-01, Path D pivot — Ollama, NIM downloads skipped per orchestrator): qwen3-coder:30b + nemotron-mini:latest, 41s for 10 claims (avg 4.1s/claim pair), parse error rate 0.0% — latency and parsing gates pass cleanly. Independence proof FAILS: 10/10 verdicts SUPPORTED on both critics (0 disagreements). Likely cause: extracted claims are sentence fragments from `extract_claims_from_doc.py`, not contestable assertions; both critics default SUPPORTED on partial-evidence retrieval. Orchestrator decides: refine extractor, hand-curate adversarial claim sample, or accept ensemble without disagreement signal. |
| 4 | audit-and-implement against report | tvw/audits/audit-001.md has ≥10 severity-tagged findings; ≥80% triaged legitimate | pending |
| 5 | Llama-3.3-70B reviewer | 5K-token critique 30–90s; ≥7/10 calibration agreement with NIM ensemble | pending |
| 6 | multi-agent-chatbot fork | "200 MHz timing claim?" returns grounded answer citing both corpora + a code symbol | pending |
| 7 | txt2kg claim graph (optional) | .graphml exported; orphan-claim count documented | pending |
| 8 | nemo-automodel fine-tune | beats base on held-out Tychon Q&A; checkpoint reusable as NIM service | pending |
| 9 | publish-repo Dist A scrub | zero matches for `FX255-PCS02-0044` + sponsor names; metadata stripped | pending |

Natural quitting points: after Stage 1 (searchable docs), Stage 4 (audited punch list), Stage 6 (chat workbench), or Stage 8 (Tychon-owned model).
