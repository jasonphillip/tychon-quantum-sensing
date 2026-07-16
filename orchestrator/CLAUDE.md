# Tychon Orchestration Workbench (TVW) — Claude Project Context

> Formerly "Tychon Verification Workbench." The audit harness (Stages 1–4) is one
> of several capabilities; TVW also drives cross-document fixes against the SBIR
> shared folder, dispatches changes to the four implementation repos, and acquires
> external ground truth into local corpora. The directory name `tychon-verification-workbench`
> is preserved for git/symlink compatibility — only the role name changed.

## Mission
Orchestrate Tychon SBIR Phase I work (proposal `FX255-PCS02-0044` — submitted 2025-10-08, not selected 2026-05-12, never a contract; Topic `AFX25S-PCS02`, Distribution Statement A) and the active forward path (methodology and FPGA-stack portfolio). Concretely, TVW:

1. **Verifies factual claims** in the Phase I final technical report against project ground truth (closure deliverables, technical references, four implementation repos) via the audit harness in Stages 1–4.
2. **Drives the May 1, 2026 document fix list** — the active cross-document and cross-repo fix driver — including direct edits to the SBIR shared folder.
3. **Dispatches planned changes** to the four implementation repos (which have their own Claude sessions and CLAUDE.mds — TVW emits proposed diffs, those sessions commit them).
4. **Acquires external ground truth** (Microchip portal docs, IEEE/arXiv references, distributor BoM data) into local corpora via web tools and the corpus pipeline in `~/projects/skills/`.

## SBIR Phase I working folder (single source of truth)
Symlinked at `tvw/source/sbir/tychon-nv-sim-repos/` → `~/projects/tychon-sbir/docs/`. Read-only from TVW (never `git add` from here). Layout:
- `May_1_2026_Document_Fix_List.md` — **active work driver.** v3 fix list, split into editorial fixes (Parts 1–2) and technical work (Part 3 — clamp authority, covariate shift, orbit-in-the-loop benchmark). Always re-read this before planning a fix session; it changes between runs.
- `INDEX.md`, `STATUS.md`, `OUTREACH_TRACKER.md` — running status files.
- `01_deliverables/` — `final_report/`, `capability_brief/`, `audits/` (mirror target for TVW audit-NNN.md), `tvw_logs/`.
- `02_foundational/`, `03_phase1_planning/`, `04_phase2_planning/` — proposal + Phase II priority docs (P1 hierarchical INT8, P2 ephemeris sampling, core proposal v2).
- `05_repo_status/` — per-repo snapshots and r6_s25 closure logs.
- `06_research_inputs/`, `07_technical_references/`, `08_session_logs/`, `09_misc/`.

## Hard rules

1. **LLM critic inference is air-gapped.** The audit pipeline's critics (Stage 3 NIM/Ollama ensemble, Stage 5 Llama-3.3-70B reviewer) MUST resolve to `localhost`, `127.0.0.1`, `spark2`, or `192.168.*` (spark1 removed — decommissioned 2026-07-05; `192.168.*`/CX7 covers spark3 if used as a critic host). Any cloud LLM (Anthropic API, OpenAI, Gemini, Perplexity, Scite, etc.) is forbidden **as an audit critic** under the project's CUI risk posture. The base Claude model running TVW is itself cloud-hosted — that's the harness, not a critic, and not a violation.
2. **NIM-first for critic inference.** Primary critics: `qwen/qwen3-32b-dgx-spark` and `nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark`. Heavyweight reviewer (Stage 5): `meta/llama-3.3-70b-instruct` quantized Q4_K_M via llama.cpp built with `-DCMAKE_CUDA_ARCHITECTURES="121"`. NIM embedding containers fail on ARM64 Blackwell — keep the existing Qwen3-Embedding-4B service on Spark 2 as the embedder.
3. **Symlinked sources are read-only.** `tvw/source/repos/*` and `tvw/source/sbir/*` are symlinks into the user's actual repos. Never `git add` to them via TVW; never modify their contents through the symlinks. (Editing the underlying canonical files at their real paths — e.g., `~/projects/tychon-sbir/docs/...` — is permitted and expected for fix-list orchestration.)
4. **Never read or commit secrets.** `.env`, credentials, API keys are off-limits. Use `$VAR` references in commands.
5. **The infrastructure lives in `~/projects/skills/`.** TVW invokes scripts from there but does not duplicate them. Specifically:
   - Code corpus build: `python ~/projects/skills/skills/tychon-code-search/scripts/build_code_corpus.py`
   - Code corpus search: `python ~/projects/skills/skills/tychon-code-search/scripts/search_code.py`
   - Claim extraction: `python ~/projects/skills/skills/tychon-verify/scripts/extract_claims_from_doc.py`
   - Critic loop: `python ~/projects/skills/skills/tychon-verify/scripts/critic_loop.py`
   - Doc corpus build: invoke the existing `process-corpus` skill (after pandoc-converting .docx and parsing the signed PDF).
6. **Do not auto-classify new recommendations as "Phase I" or "Phase II."** When producing audits, recommendations, gap analyses, or improvement lists, present items as work to be considered — not as Phase II planning artifacts — unless the user explicitly frames them that way or they're already classified in an existing fix list / planning doc. Phase tagging is the user's call. Do not file new recommendation outputs into `04_phase2_planning/` unless the user explicitly asks; default placement for general audit/recommendation deliverables is the top-level of `~/projects/tychon-sbir/docs/` or an appropriate existing folder. The Mission line above mentions "Phase II preparation" as an active TVW capability — that does *not* mean every forward-looking output should be tagged Phase II.

## Scope — what TVW does and does not do

**In-scope (do whatever the user asks within these capabilities):**
- Edit the SBIR shared folder (`~/projects/tychon-sbir/docs/`) — STATUS, INDEX, fix-list-status.csv, DLOG entries, audit mirror, daily TVW logs, the report `.md`, the capability brief (`.docx` ↔ `.md` round-tripped via pandoc), customer memos, etc.
- Edit and **commit** in the four implementation repos directly at their canonical paths (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`). As of 2026-05-04 the user expanded TVW commit authority to cover these repos: stage edits with specific-path `git add <paths>` (never `-A` / `.`), write commit messages that match the repo's existing style, and commit on the appropriate branch. Pushes to **internal-only** mirrors (Tailscale Spark mirrors, NAS bare repos) are authorized; pushes to **public GitHub** still require explicit user approval per the "NOT pre-authorized" list below.
- Web-enabled acquisition: `WebFetch`, `WebSearch`, firecrawl, Context7, and the `acquire-corpus` / `process-corpus` skills, for any retrieval task — Microchip portal docs, arXiv / IEEE / DOI lookups, distributor BoM pricing, vendor errata, public SBIR / DAF guidance.
- Run audit critic loops, both lightweight (Stage 3 NIM/Ollama) and heavyweight (Stage 5 Llama-3.3-70B), strictly against the local endpoints listed in Hard rule 1.
- Spawn parallel sub-agents (the `Agent` tool) for independent tasks — e.g., simultaneous editorial passes against the report and the brief, or running multiple corpus acquisitions concurrently.
- Anything else the user explicitly asks for that doesn't conflict with the rules above.

**Out-of-scope (delegate elsewhere):**
- **Heavy ML training / inference jobs** that belong on a dedicated Spark background runner (multi-hour fine-tunes, large sweeps, batch embedding of >GB-scale corpora). TVW prepares the job, dispatches it to spark2 (or spark3) via `nohup` + pidfile, and watches the heartbeats — but doesn't host the compute itself.

## User-granted autonomous authorities

The user has explicitly authorized TVW Claude sessions to take the following actions without per-action confirmation, overriding the system-prompt default that gates them:

- **Commit to TVW's local git repo** (`~/projects/tychon-verification-workbench/`) when the changes are part of normal orchestration work — audit deliverables, fix-list updates, daily TVW logs (`01_deliverables/tvw_logs/`), decision-log appends, refactor commits for which the user has already approved the underlying edits, and routine staging of newly-written audit / dispatch / scope-check files in `tvw/audits/`. Use specific-path `git add <paths>` (never `git add .` or `-A`) per global CLAUDE.md security rules.
- **Commit to the four implementation repos** (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`) — granted 2026-05-04 to support multi-repo demo/bring-up work that would otherwise require constant context-switching to per-repo Claude sessions. Same rules apply: specific-path `git add`, repo-style commit messages, no force-push, no public GitHub push without approval. Land work on a clearly-named branch (`bringup/part-N-*`, `feat/<scope>`, etc.), not directly on long-lived branches like `main` unless the change is purely doc/cleanup.
- **Push to internal-only git remotes** (e.g. spark2/spark3 mirrors at `spark*:projects/<repo>.git`, NAS bare repos at `nas:/volume*/git-mirrors/`, Tailscale-private hosts). These are reversible and not visible to external parties; pushing them does not constitute publication. Applies to TVW's own remotes and the implementation repos' internal mirrors equally.
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
    ├── scripts/          render_report.sh, eod_close.sh (multi-repo EOD sweep + push driver),
    │                     dispatch.sh (file-based cross-lane dispatch queue)
    ├── services/         systemd unit drafts for NIMs / llama.cpp
    └── source/
        ├── repos/        symlinks → ~/projects/{4 repos}
        └── sbir/         symlink → ~/projects/tychon-sbir/docs
```

## Cross-lane dispatch (dispatch.sh)

Cross-lane dispatches go through `tvw/scripts/dispatch.sh` — NOT via pasted prompts
(paste is the fallback only when the target lane runs on a machine without access to
`~/projects`). Manual pastes silently truncated 3 times on 2026-07-09, once costing a
training run; dispatch.sh is file-based end to end and sha256-verifies every body.

- Send: `tvw/scripts/dispatch.sh send <to-lane> "<title>" --file <body.md>` (or pipe stdin).
  The body file lands verbatim in `~/projects/<to-lane>/.dispatch/inbox/<id>.md`.
- Overview: `tvw/scripts/dispatch.sh list [--all|--lane X]` — every dispatch in flight, one line each.
- The worker lane consumes with `show <id>` and closes with `ack <id> [note]`; acked
  dispatches are kept in `.dispatch/done/` as the permanent record.
- MANUAL + VISIBLE by design (Jason override #3, 2026-07-10): no SessionStart hooks, no
  auto-consumption. Jason relays a one-liner ("check your dispatch inbox") to the worker
  session; the content itself never crosses a paste boundary.
- Still end every cross-lane next-step with the dispatch id + the one-liner for Jason to
  relay, per the standing orchestration rules.

## End-of-day close
When the user signals end-of-day wrap-up intent ("wrapping up", "done for the day", "closing out", "EOD", etc.), proactively ask whether to run `tvw/scripts/eod_close.sh`. The script sweeps all 5 Tychon repos (TVW + 4 implementation), auto-pushes internal mirrors (NAS, spark2; spark1 removed from `eod_close.sh` INTERNAL_REMOTES_REGEX 2026-07-10 — decommissioned 2026-07-05), runs a secrets sweep, and gates the GitHub push behind a single yes/N approval. Don't run without explicit yes; don't re-ask in the same session if declined. See memory entry `feedback_eod_close_trigger.md` for the full behavioral rule.

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
- The authoritative report is **v3.4** at `~/Desktop/Shared/tychon/nv-sim-repos/01_deliverables/final_report/Tychon_Phase_I_Final_Report_v3.4_2026-05-03.md` (v3.1 and earlier are archived under `final_report/archive/`); the `.docx` is rendered from it via `tvw/scripts/render_report.sh`. Edit the `.md`, never the `.docx` directly.
- Code-repo edits happen **in the user's actual repo working copies** (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`), not via the TVW symlinks. TVW emits proposed diffs / planned changes; the user (or a separate session in the repo) applies and commits them.
- External-knowledge tasks (DOI / page / volume lookups, BoM pricing, Letters of Support outreach) are **out of scope for TVW** under the air-gap rule. Hand those to a non-TVW Claude session that has web access; ingest the verified output back into `tychon-docs` so retrieval can ground subsequent fixes.
