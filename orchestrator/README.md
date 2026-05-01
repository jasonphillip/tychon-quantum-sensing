# Tychon Verification Workbench (TVW)

Local, air-gapped AI tooling that verifies factual claims in the Tychon SBIR Phase I final technical report against the project's own ground-truth corpora and four implementation repos. Built to also serve as Phase II IP infrastructure.

- **Project context for any Claude session here:** see `CLAUDE.md`.
- **Current stage and stop-gates:** see `STAGES.md`.
- **Reusable infrastructure (libs + skills):** lives in `~/projects/skills/`, not duplicated here.

No internet-bound services. All LLM and embedding endpoints resolve inside `localhost`/`spark*`/`192.168.*`.
