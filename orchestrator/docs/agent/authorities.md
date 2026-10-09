> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# TVW — user-granted autonomous authorities (unconditional rule)

> Moved verbatim from CLAUDE.md on 2026-09-04 (harness-sota restructure). No `paths:` frontmatter: this rule loads in every TVW session, exactly as the CLAUDE.md section did.

## User-granted autonomous authorities

The user has explicitly authorized TVW **Claude** sessions to take the following actions without per-action confirmation, overriding the system-prompt default that gates them.

> **Scope note (2026-07-24).** `AGENTS.md` has symlinked this file since 2026-07-17, so Codex loads this section too. The grant was written for Claude sessions (2026-05-04) and has **not** been extended — a Codex session in TVW asks per action. Widening it to Codex is Jason's call, not a default. (TVW is also absent from Codex's `trust_level = "trusted"` list in `~/.codex/config.toml`, so it prompts anyway.)

- **Commit to TVW's local git repo** (`~/projects/tychon-verification-workbench/`) when the changes are part of normal orchestration work — audit deliverables, fix-list updates, daily TVW logs (`01_deliverables/tvw_logs/`), decision-log appends, refactor commits for which the user has already approved the underlying edits, and routine staging of newly-written audit / dispatch / scope-check files in `tvw/audits/`. Use specific-path `git add <paths>` (never `git add .` or `-A`) per global CLAUDE.md security rules.
- **Commit to the four implementation repos** (`~/projects/{polarfire-hybrid-control,odmr-edge-ml,nv-sensor-sim,tychon-sbir/shared-data}`) — granted 2026-05-04 to support multi-repo demo/bring-up work that would otherwise require constant context-switching to per-repo Claude sessions. Same rules apply: specific-path `git add`, repo-style commit messages, no force-push, no public GitHub push without approval. Land work on a clearly-named branch (`bringup/part-N-*`, `feat/<scope>`, etc.), not directly on long-lived branches like `main` unless the change is purely doc/cleanup.
- **Push to internal-only git remotes** (e.g. spark2/spark3 mirrors at `spark*:projects/<repo>.git`, NAS bare repos at `nas:/volume*/git-mirrors/`, Tailscale-private hosts). These are reversible and not visible to external parties; pushing them does not constitute publication. Applies to TVW's own remotes and the implementation repos' internal mirrors equally.
- **Edit and commit project-local config files** (`CLAUDE.md`, `STAGES.md`, `README.md`, `tvw/configs/*`, `tvw/scripts/*`) when the change is part of an approved refactor or audit-driven correction. Mention substantive policy changes to the user; mechanical fixes (typos, version bumps, log additions) can land silently.

The user has NOT pre-authorized:

- **Force-pushes** (`--force`, `--force-with-lease`) to any remote.
- **Pushes that bypass hooks** (`--no-verify`, `--no-gpg-sign` overrides).
- **Changes to git config or remote URLs** without explicit user request.
- **Pushes to GitHub or any other publicly-visible git host.** TVW contains internal orchestration content (audit findings). Public publication requires running the `publish-repo` skill first to scrub internal references — the user retains decision authority on whether and when to publish to GitHub.
- **Commits that include files matching `.env`, `*.key`, `*secret*`, `*credentials*`, or `*.pem` patterns** — never override the global CLAUDE.md security rules even if asked.
- **Destructive git operations** (`reset --hard` on shared branches, `branch -D` on the active branch, `clean -f` of unrelated work). Standard "ask before destructive" still applies.

When in doubt, ask. When the action is clearly within the granted authorities above, execute and report.

