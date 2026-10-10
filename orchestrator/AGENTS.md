> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09, edited for publication; the live file was kept outside version control).

# Tychon Orchestration Workbench (TVW) — Claude Project Context

TVW is the ORCHESTRATION lane for the Tychon hardware build. TVW verifies report claims, drives the fix list, dispatches to the five worker lanes, and acquires external ground truth into corpora. Detail: `docs/claude/mission-and-program.md`. Scope lists: `docs/claude/scope.md`.

## Hard rules

1. **LLM critic inference is air-gapped.** The audit pipeline's critics (Stage 3 NIM/Ollama ensemble, Stage 5 Llama-3.3-70B reviewer) MUST resolve to `localhost`, `127.0.0.1`, `ws2`, or `192.168.*` (ws1 removed — decommissioned 2026-07-05; `192.168.*`/CX7 covers ws3 if used as a critic host). Any cloud LLM (Anthropic API, OpenAI, Gemini, Perplexity, Scite, etc.) is forbidden **as an audit critic** under the project's CUI risk posture. The harness model running TVW is itself cloud-hosted — Claude, or Codex since `AGENTS.md` began symlinking this file 2026-07-17 — and that is the harness, not a critic, and not a violation. **The distinction is role, not vendor.** What *is* forbidden, and is the live exposure: **delegating audit, critic, verification, or claim-adjudication work out of a TVW session to any cloud model** — this explicitly includes the `codex:rescue` subagent, the `second-opinion` skill, and blind re-verdict passes. Those must run on the local endpoints above. (The "Codex blind re-verdict" pattern used in the corpus program is out-of-bounds for anything entering TVW's claims table.)
2. **NIM-first for critic inference.** Primary critics: `qwen/qwen3-32b-dgx-spark` and `nvidia/nvidia-nemotron-nano-9b-v2-dgx-spark`. Heavyweight reviewer (Stage 5): `meta/llama-3.3-70b-instruct` quantized Q4_K_M via llama.cpp built with `-DCMAKE_CUDA_ARCHITECTURES="121"`. NIM embedding containers fail on ARM64 Blackwell — keep the existing Qwen3-Embedding-4B service on Spark 2 as the embedder.
3. **Symlinked sources are read-only.** `tvw/source/repos/*` and `tvw/source/sbir/*` are symlinks into the user's actual repos. Never `git add` to them via TVW; never modify their contents through the symlinks. (Editing the underlying canonical files at their real paths — e.g., `~/projects/tychon-sbir/docs/...` — is permitted and expected for fix-list orchestration.)
4. **Never read or commit secrets.** `.env`, credentials, API keys are off-limits. Use `$VAR` references in commands.
5. **The infrastructure lives in `~/projects/skills/`.** TVW invokes scripts from there but does not duplicate them. Exact script invocations (code corpus build/search, claim extraction, critic loop, doc corpus build): `docs/claude/pipeline-reference.md`.
6. **Audit files are living documents — cite the addendum, never the filename.** Files under
   `tvw/audits/` accrete dated addenda after creation; the filename records only the origin date.
   `audit-dwell-program-2026-07-07.md` carries **19 addenda (A–S) spanning 2026-07-07 → 07-14** in
   820 lines. Before quoting or dating any passage from an audit file, seek up to its `## Addendum`
   header and cite that letter + date. A keyword-anchored read window will usually open *below* the
   header and show no date at all — that is the trap. (Same failure applies to the DLOG and any
   other append-only record.) Global evidence-grading rules: `~/.claude/CLAUDE.md` §Reporting findings.

## User-granted autonomous authorities

The user has explicitly authorized TVW **Claude** sessions to take the following actions without per-action confirmation, overriding the system-prompt default that gates them.

> **Scope note (2026-07-24; corrected 2026-09-04; compacted 2026-09-11, old wording in git history).** `AGENTS.md` symlinks this file, so Codex loads this section too. The grant was written for Claude sessions (2026-05-04) and has **not** been extended to Codex. Codex in TVW runs with `trust_level = "trusted"` (`~/.codex/config.toml`), so it does not prompt; Hard rule 1's air-gap is enforced by the rule, not by an approval prompt. Widening the grant or removing that TOML entry is Jason's call.

- **Commit to TVW's local git repo** (`~/projects/tychon-verification-workbench/`) when the changes are part of normal orchestration work — audit deliverables, fix-list updates, daily TVW logs (`01_deliverables/tvw_logs/`), decision-log appends, refactor commits for which the user has already approved the underlying edits, and routine staging of newly-written audit / dispatch / scope-check files in `tvw/audits/`. Use specific-path `git add <paths>` (never `git add .` or `-A`) per global CLAUDE.md security rules.
- **Commit to the four implementation repos** (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`) — granted 2026-05-04 to support multi-repo demo/bring-up work that would otherwise require constant context-switching to per-repo Claude sessions. Same rules apply: specific-path `git add`, repo-style commit messages, no force-push, no public GitHub push without approval. Land work on a clearly-named branch (`bringup/part-N-*`, `feat/<scope>`, etc.), not directly on long-lived branches like `main` unless the change is purely doc/cleanup.
- **Push to internal-only git remotes** (e.g. ws2/ws3 mirrors at `spark*:projects/<repo>.git`, NAS bare repos at `nas:/volume*/git-mirrors/`, Tailscale-private hosts). These are reversible and not visible to external parties; pushing them does not constitute publication. Applies to TVW's own remotes and the implementation repos' internal mirrors equally.
- **Edit and commit project-local config files** (`CLAUDE.md`, `STAGES.md`, `README.md`, `tvw/configs/*`, `tvw/scripts/*`) when the change is part of an approved refactor or audit-driven correction. Mention substantive policy changes to the user; mechanical fixes (typos, version bumps, log additions) can land silently.

The user has NOT pre-authorized:

- **Force-pushes** (`--force`, `--force-with-lease`) to any remote.
- **Pushes that bypass hooks** (`--no-verify`, `--no-gpg-sign` overrides).
- **Changes to git config or remote URLs** without explicit user request.
- **Pushes to a publicly-visible git host, and any change of a repo's visibility.** A push to a PRIVATE GitHub repo is allowed without asking (global CLAUDE.md, "Private GitHub"; applied here on Jason's word 2026-10-04). Check first: `GH_TOKEN=$GITHUB_PAT ~/bin/gh repo view <owner>/<repo> --json visibility` must print `PRIVATE`. TVW contains internal orchestration content (audit findings). Public publication requires running the `publish-repo` skill first to scrub internal references — the user retains decision authority on whether and when to publish.
  ⊘ superseded 2026-10-04 → the old wording was "Pushes to GitHub or any other publicly-visible git host." It also blocked pushes to private GitHub repos; the newer global rule allows those.
- **Commits that include files matching `.env`, `*.key`, `*secret*`, `*credentials*`, or `*.pem` patterns** — never override the global CLAUDE.md security rules even if asked.
- **Destructive git operations** (`reset --hard` on shared branches, `branch -D` on the active branch, `clean -f` of unrelated work). Standard "ask before destructive" still applies.

When in doubt, ask. When the action is clearly within the granted authorities above, execute and report.

## Every session
1. Read `STAGES.md` for the current stop-gate. Stop at the gate; the orchestrator session in `~/projects/skills/` advances stages.
2. Fix-list work: re-read the fix list first. Report = v3.4 `.md` under `01_deliverables/final_report/`; edit the `.md`, never the `.docx` (`tvw/scripts/render_report.sh` renders it). Code-repo edits land in the canonical working copies, never through the symlinks. Full constraints: `docs/claude/fix-list-orchestration.md`.
3. Before any Stage that touches corpora: `curl -sf http://ws2:8000/health`. Failure means abort — silent fallback to 768-d Ollama corrupts the sqlite-vec index.
4. Cross-lane work goes through `tvw/scripts/dispatch.sh send <to-lane> "<title>" --file <body.md> --predict h,sessions,p`, never pasted prompts. Bodies follow `tvw/scripts/dispatch-template.md`. End every cross-lane next-step with the dispatch id + the one-liner Jason relays. Detail: `docs/claude/dispatch.md`.
5. When Jason signals end-of-day ("wrapping up", "EOD"): offer `tvw/scripts/eod_close.sh` once. Run only on an explicit yes; do not re-ask if declined. Detail: `docs/claude/session-rituals.md`.

## Context map — read on demand
| Need | Read |
|---|---|
| Mission detail, program state, pivot history | `docs/claude/mission-and-program.md` |
| Scope lists (in / out) | `docs/claude/scope.md` |
| dispatch.sh commands, envelope, ack ritual | `docs/claude/dispatch.md` |
| Fix-list constraints, external-knowledge routing | `docs/claude/fix-list-orchestration.md` |
| Session start / stop-gate / EOD close | `docs/claude/session-rituals.md` |
| Corpus paths, scripts, critic loop | `docs/claude/pipeline-reference.md` |
| Shared-folder layout | `docs/claude/sbir-folder-layout.md` |
| TVW tree (`tvw/{configs,audits,scripts,services,source}`) | `docs/claude/repo-layout.md` |
| Rename history | `docs/claude/naming-history.md` |
