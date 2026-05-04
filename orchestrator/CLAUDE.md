# Tychon Orchestration Workbench (TVW) — Claude Project Context

> Formerly "Tychon Verification Workbench." The audit harness (Stages 1–4) is one
> of several capabilities; TVW also drives cross-document fixes against the SBIR
> shared folder, dispatches changes to the four implementation repos, and acquires
> external ground truth into local corpora. The directory name `tychon-verification-workbench`
> is preserved for git/symlink compatibility — only the role name changed.

## Mission
Orchestrate Tychon SBIR Phase I deliverables (Proposal `FX255-PCS02-0044` (not selected 2026-05-12, never a contract), Topic `AFX25S-PCS02`, Distribution Statement A) and Phase II preparation. Concretely, TVW:

1. **Verifies factual claims** in the Phase I final technical report against project ground truth (closure deliverables, technical references, four implementation repos) via the audit harness in Stages 1–4.
2. **Drives the May 1, 2026 document fix list** — the active cross-document and cross-repo fix driver — including direct edits to the SBIR shared folder.
3. **Dispatches planned changes** to the four implementation repos (which have their own Claude sessions and CLAUDE.mds — TVW emits proposed diffs, those sessions commit them).
4. **Acquires external ground truth** (Microchip portal docs, IEEE/arXiv references, distributor BoM data) into local corpora via web tools and the corpus pipeline in `~/projects/skills/`.

## SBIR Phase I working folder (single source of truth)
Symlinked at `tvw/source/sbir/tychon-nv-sim-repos/` → `~/projects/tychon-sbir/docs/`. Read-only from TVW (never `git add` from here). Layout:
- `May_1_2026_Document_Fix_List.md` — **active work driver.** v3 fix list, split into editorial fixes (Parts 1–2) and Phase II technical work (Part 3 — clamp authority, covariate shift, orbit-in-the-loop benchmark). Always re-read this before planning a fix session; it changes between runs.
- `INDEX.md`, `STATUS.md`, `OUTREACH_TRACKER.md` — running status files.
- `01_deliverables/` — `final_report/`, `capability_brief/`, `audits/` (mirror target for TVW audit-NNN.md), `tvw_logs/`.
- `02_foundational/`, `03_phase1_planning/`, `04_phase2_planning/` — proposal + Phase II priority docs (P1 hierarchical INT8, P2 ephemeris sampling, core proposal v2).
- `05_repo_status/` — per-repo snapshots and r6_s25 closure logs.
- `06_research_inputs/`, `07_technical_references/`, `08_session_logs/`, `09_misc/`.

## Hard rules

1. **LLM critic inference is air-gapped.** The audit pipeline's critics (Stage 3 NIM/Ollama ensemble, Stage 5 Llama-3.3-70B reviewer) MUST resolve to `localhost`, `127.0.0.1`, `spark1`, `spark2`, or `192.168.*`. Any cloud LLM (Anthropic API, OpenAI, Gemini, Perplexity, Scite, etc.) is forbidden **as an audit critic** under Phase II CUI risk posture. The base Claude model running TVW is itself cloud-hosted — that's the harness, not a critic, and not a violation.
2. **NIM-first for critic inference.** Primary critics: `qwen/qwen3-32b-dgx-spark` and `nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark`. Heavyweight reviewer (Stage 5): `meta/llama-3.3-70b-instruct` quantized Q4_K_M via llama.cpp built with `-DCMAKE_CUDA_ARCHITECTURES="121"`. NIM embedding containers fail on ARM64 Blackwell — keep the existing Qwen3-Embedding-4B service on Spark 2 as the embedder.
3. **Symlinked sources are read-only.** `tvw/source/repos/*` and `tvw/source/sbir/*` are symlinks into the user's actual repos. Never `git add` to them via TVW; never modify their contents through the symlinks. (Editing the underlying canonical files at their real paths — e.g., `~/projects/tychon-sbir/docs/...` — is permitted and expected for fix-list orchestration.)
4. **Never read or commit secrets.** `.env`, credentials, API keys are off-limits. Use `$VAR` references in commands.
5. **The infrastructure lives in `~/projects/skills/`.** TVW invokes scripts from there but does not duplicate them. Specifically:
   - Code corpus build: `python ~/projects/skills/skills/tychon-code-search/scripts/build_code_corpus.py`
   - Code corpus search: `python ~/projects/skills/skills/tychon-code-search/scripts/search_code.py`
   - Claim extraction: `python ~/projects/skills/skills/tychon-verify/scripts/extract_claims_from_doc.py`
   - Critic loop: `python ~/projects/skills/skills/tychon-verify/scripts/critic_loop.py`
   - Doc corpus build: invoke the existing `process-corpus` skill (after pandoc-converting .docx and parsing the signed PDF).

## Scope — what TVW does and does not do

**In-scope (do whatever the user asks within these capabilities):**
- Edit the SBIR shared folder (`~/projects/tychon-sbir/docs/`) — STATUS, INDEX, fix-list-status.csv, DLOG entries, audit mirror, daily TVW logs, the report `.md`, the capability brief (`.docx` ↔ `.md` round-tripped via pandoc), customer memos, etc.
- Edit the four implementation repos directly at their canonical paths (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`). Stage edits in the working tree; do NOT `git commit` from TVW — the commit step belongs to those repos' own Claude sessions, which have the right context for messages, hooks, and signing. (Exception: if the user explicitly tells TVW to commit, follow the user.)
- Web-enabled acquisition: `WebFetch`, `WebSearch`, firecrawl, Context7, and the `acquire-corpus` / `process-corpus` skills, for any retrieval task — Microchip portal docs, arXiv / IEEE / DOI lookups, distributor BoM pricing, vendor errata, public SBIR / DAF guidance.
- Run audit critic loops, both lightweight (Stage 3 NIM/Ollama) and heavyweight (Stage 5 Llama-3.3-70B), strictly against the local endpoints listed in Hard rule 1.
- Spawn parallel sub-agents (the `Agent` tool) for independent tasks — e.g., simultaneous editorial passes against the report and the brief, or running multiple corpus acquisitions concurrently.
- Anything else the user explicitly asks for that doesn't conflict with the rules above.

**Out-of-scope (delegate elsewhere):**
- **Heavy ML training / inference jobs** that belong on a dedicated Spark background runner (multi-hour fine-tunes, large sweeps, batch embedding of >GB-scale corpora). TVW prepares the job, dispatches it to spark1/spark2 via `nohup` + pidfile, and watches the heartbeats — but doesn't host the compute itself.

## User-granted autonomous authorities

The user has explicitly authorized TVW Claude sessions to take the following actions without per-action confirmation, overriding the system-prompt default that gates them:

- **Commit to TVW's local git repo** (`~/projects/tychon-verification-workbench/`) when the changes are part of normal orchestration work — audit deliverables, fix-list updates, daily TVW logs (`01_deliverables/tvw_logs/`), decision-log appends, refactor commits for which the user has already approved the underlying edits, and routine staging of newly-written audit / dispatch / scope-check files in `tvw/audits/`. Use specific-path `git add <paths>` (never `git add .` or `-A`) per global CLAUDE.md security rules.
- **Push to internal-only git remotes** (e.g. spark1/spark2 mirrors at `spark*:projects/tychon-verification-workbench.git`, Tailscale-private hosts) when one is configured. These are reversible and not visible to external parties; pushing them does not constitute publication.
- **Edit and commit project-local config files** (`CLAUDE.md`, `STAGES.md`, `README.md`, `tvw/configs/*`, `tvw/scripts/*`) when the change is part of an approved refactor or audit-driven correction. Mention substantive policy changes to the user; mechanical fixes (typos, version bumps, log additions) can land silently.

The user has NOT pre-authorized:

- **Force-pushes** (`--force`, `--force-with-lease`) to any remote.
- **Pushes that bypass hooks** (`--no-verify`, `--no-gpg-sign` overrides).
- **Changes to git config or remote URLs** without explicit user request.
- **Pushes to GitHub or any other publicly-visible git host.** TVW contains internal SBIR Phase I orchestration content (audit findings, customer-pipeline references, Distribution-A reports). Public publication requires running the `publish-repo` skill first to scrub internal references — the user retains decision authority on whether and when to publish to GitHub.
- **Commits that include files matching `.env`, `*.key`, `*secret*`, `*credentials*`, or `*.pem` patterns** — never override the global CLAUDE.md security rules even if asked.
- **Destructive git operations** (`reset --hard` on shared branches, `branch -D` on the active branch, `clean -f` of unrelated work). Standard "ask before destructive" still applies.

When in doubt, ask. When the action is clearly within the granted authorities above, execute and report.

## Layout
```
~/projects/tychon-verification-workbench/
├── CLAUDE.md             this file
├── STAGES.md             stop-gate roadmap
├── README.md             project overview
├── .gitignore
└── tvw/
    ├── configs/          endpoints.yaml, model lineup, MCP wiring
    ├── audits/           audit-NNN.md punch lists, verdict CSVs
    ├── services/         systemd unit drafts for NIMs / llama.cpp
    └── source/
        ├── repos/        symlinks → ~/projects/{4 repos}
        └── sbir/         symlink → ~/projects/tychon-sbir/docs
```

## Corpus locations
- `~/.corpus/tychon-docs/` — prose corpus (built in Stage 1)
- `~/.corpus/tychon-code/` — code corpus (built in Stage 2)
- Both use the existing `~/projects/skills/lib/` pipeline (sqlite-vec FTS5 + Qwen3 embeddings).

## Pre-flight before any Stage that touches corpora
```
curl -sf http://spark2:8000/health
```
Failure means abort — silent fallback to 768-d Ollama corrupts the sqlite-vec index.

## What to do when invoked
1. Read STAGES.md to find the current stop-gate status.
2. If the work concerns the fix list, also re-read `tvw/source/sbir/tychon-nv-sim-repos/May_1_2026_Document_Fix_List.md` — it is revised between sessions.
3. The user will paste a stage-specific prompt that tells you exactly what to build.
4. Stop at the stop-gate; don't bleed into the next stage. The orchestrator (the user's other Claude session in `~/projects/skills/`) decides when to advance.

## Fix-list orchestration constraints (Stage 5+)
When TVW is used to drive fixes against the report or the four code repos:
- The report `.docx` is rendered from `~/Desktop/Shared/Tychon_Phase_I_Final_Report_v3.1_*.md` via `tvw/scripts/render_report.sh`. Edit the `.md`, never the `.docx` directly.
- Code-repo edits happen **in the user's actual repo working copies** (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`), not via the TVW symlinks. TVW emits proposed diffs / planned changes; the user (or a separate session in the repo) applies and commits them.
- External-knowledge tasks (DOI / page / volume lookups, BoM pricing, Letters of Support outreach) are **out of scope for TVW** under the air-gap rule. Hand those to a non-TVW Claude session that has web access; ingest the verified output back into `tychon-docs` so retrieval can ground subsequent fixes.
