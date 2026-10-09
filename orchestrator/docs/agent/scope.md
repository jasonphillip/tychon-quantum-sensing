> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# Scope — what TVW does and does not do

> Moved verbatim from CLAUDE.md §Scope on 2026-09-04 (harness-sota restructure).

**In-scope (do whatever the user asks within these capabilities):**
- Edit the shared project folder — STATUS, INDEX, fix-list-status.csv, DLOG entries, audit mirror, daily TVW logs, the report `.md`.
- Edit and **commit** in the four implementation repos directly at their canonical paths (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`). As of 2026-05-04 the user expanded TVW commit authority to cover these repos: stage edits with specific-path `git add <paths>` (never `-A` / `.`), write commit messages that match the repo's existing style, and commit on the appropriate branch. Pushes to **internal-only** mirrors (Tailscale Spark mirrors, NAS bare repos) are authorized; pushes to **public GitHub** still require explicit user approval per the "NOT pre-authorized" list in CLAUDE.md §User-granted autonomous authorities.
- Web-enabled acquisition: `WebFetch`, `WebSearch`, firecrawl, Context7, and the `acquire-corpus` / `process-corpus` skills, for any retrieval task — Microchip portal docs, arXiv / IEEE / DOI lookups, distributor BoM pricing, vendor errata.
- Run audit critic loops, both lightweight (Stage 3 NIM/Ollama) and heavyweight (Stage 5 Llama-3.3-70B), strictly against the local endpoints listed in CLAUDE.md Hard rule 1.
- Spawn parallel sub-agents (the `Agent` tool) for independent tasks — e.g., simultaneous editorial passes against the report and the brief, or running multiple corpus acquisitions concurrently. Apply the global CLAUDE.md §Orchestration subagent routing gate first (audit/critic work → local endpoints only).
- Anything else the user explicitly asks for that doesn't conflict with the rules above.

**Out-of-scope (delegate elsewhere):**
- **Heavy ML training / inference jobs** that belong on a dedicated Spark background runner (multi-hour fine-tunes, large sweeps, batch embedding of >GB-scale corpora). TVW prepares the job, dispatches it to spark2 (or spark3) via `nohup` + pidfile, and watches the heartbeats — but doesn't host the compute itself.

> Note (2026-09-04): the first bullet's `~/projects/tychon-sbir/docs/` path predates the
