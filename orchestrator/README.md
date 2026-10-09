# Tychon Orchestration Workbench (TVW)

> Formerly "Tychon Verification Workbench." The directory is still
> `tychon-verification-workbench/` for git/symlink compatibility, but the
> role has expanded.

Orchestration session for the Tychon SBIR Phase I deliverables and the active forward path (methodology and FPGA-stack portfolio). TVW:

1. **Verifies** factual claims in the Phase I final technical report against project ground truth via the audit harness (Stages 1–4).
2. **Drives** the May 1, 2026 document fix list — direct edits to the SBIR shared folder, planned diffs against the four implementation repos.
3. **Acquires** external ground truth (Microchip portal docs, IEEE / arXiv / DOI lookups, distributor BoM data) into local corpora.
4. **Dispatches** committable changes to the four implementation repos' own Claude sessions.

- **Project context for any Claude session here:** see `CLAUDE.md`.
- **Current stage and stop-gates:** see `STAGES.md`.
- **Reusable infrastructure (libs + skills):** lives in `~/projects/skills/`, not duplicated here.

The audit pipeline's LLM critics resolve only to local endpoints (`localhost` / `spark*` / `192.168.*`) under the project's CUI risk posture. The base Claude model running TVW itself is cloud-hosted — that's the harness, not a critic.
