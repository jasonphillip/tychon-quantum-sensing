# Orchestrator (TVW)

TVW started as the Tychon Verification Workbench. I built it on 2026-05-01 to check my own work: every claim in my technical report, tested against the project's own documents, code and data. Two days later, on 2026-05-03, it became the Tychon Orchestration Workbench, the session that hands work to the worker repositories and checks what comes back. The original folder name, `tychon-verification-workbench`, still shows where it started.

## Why the critics stay local and off the web

The rule that critic models run only on my own machines is in the repository's first commit. The critics also never search the web. They see only corpora built from the project's own files.

I had two reasons. First, I had used NotebookLM for the FPGA manuals (see [docs/method.md](../docs/method.md)). It answers only from the sources you give it. In my use its answers were more truthful than those of tools that searched the web, so I wanted the critics to work the same way. That is my observation, not something I measured. Second, I wanted to use my own hardware more, and local critics keep the project's material on my machines.

Published claim checkers mostly take the other route. [FActScore](https://arxiv.org/abs/2305.14251) checks claims against Wikipedia, and [SAFE](https://arxiv.org/abs/2403.18802) and [VeriScore](https://arxiv.org/abs/2406.19276) check them against Google Search. Here the evidence is the project's own record, so a verdict says whether a claim matches what was built and measured, not whether it matches the web.

## How a claim is checked

1. A prose corpus: the report, design docs and logs, chunked, embedded with Qwen3-Embedding-4B and stored in SQLite with FTS5 and vectors.
2. A code corpus from the worker repositories: chunks plus symbols and cross-references.
3. Claim extraction from the report, one claim per line.
4. Hybrid BM25 and vector search for each claim's evidence in both corpora.
5. Two different local critics, qwen3-coder:30b and nemotron-mini under Ollama, each return a verdict with its rationale and the evidence chunks it used.
6. A stop-gate after each stage ([STAGES.md](STAGES.md)).

The code is in [pipeline/](pipeline/README.md). Each run's verdicts are in `tvw/audits/stage-4*-verdicts.csv`.

## What the first four audits found

All four ran on 2026-05-01.

- **audit-001** had 11 findings. A manual structure review found three critical ones: the abstract and the body disagreed on timing slack, a deliverable section was unfinished, and the reference list was missing.
- **Stale evidence.** In audit-002 a critic marked a timing claim CONTRADICTED. The report was right. The corpus held both an early timing run and the final closure run, and the critic read the early one. I archived the early run (7 files, 52 chunks) and re-ran. In audit-003 the claim was SUPPORTED. The same pass made a new false CONTRADICTED of the same kind on another claim, where a critic mixed up a paper design with the integrated one. The lesson I wrote down: evidence needs version metadata (which run, which design state) before a bigger critic is worth adding. A closed corpus is only as good as its versioning.
- **audit-004** checked the corrected report: 114 claims, no critical findings (audit-001 had 3) and one major one.
- In the first audit the two critics returned identical verdicts 10 times out of 10. I counted that as a failed independence test, not as agreement.

Diffs between the passes: [001 vs 002](tvw/audits/audit-001-vs-002-diff.md), [002 vs 003](tvw/audits/audit-002-vs-003-diff.md), [003 vs 004](tvw/audits/audit-003-vs-004-summary.md).

## Checking the agents as well as the report

- **2026-07-01.** A design review of the vector tracker, with three audit agents in parallel, found that the classical baseline's peak detector returned zero peaks in every frame. I retracted that baseline's headline numbers ([design review](tvw/audits/design-review-odmr-vector-2026-07-01.md), [case study](../docs/case-study.md)).
- **2026-08-21.** A local DeepSeek model audited its own serving setup. TVW re-ran each live check the model cited. Its harness and metrics findings held. Its top recommendation would have reverted a measured fix for no measured gain, and three of its five citations were misread or misattributed.
- **2026-08-28.** Codex wrote a correct brief on a VectorBlox SDK upgrade. Its chat summary of that brief named five commit hashes that do not exist and made three claims the brief contradicts. The rule since then: never relay an agent's summary without reading the file it summarizes.
- [INVENTORY.md](INVENTORY.md) is a per-repository inventory of every number, each tagged with its evidence class (hardware, testbench, model, design or docs). Section 6 lists the claims that would not survive a sharp reviewer.

## Dispatch and spend

Until July 2026 I pasted prompts between sessions by hand. On 2026-07-01 a pasted prompt lost its first three items to truncation, so dispatches moved into files. [dispatch.sh](tvw/scripts/dispatch.sh) followed on 2026-07-10. Each dispatch carries a goal, an acceptance check and a prediction in hours, sessions and probability. The acknowledgment records the actual hours, and `dispatch.sh stats` compares the two. In September it gained atomic IDs, leases and an 18-group test. Example: [dispatch 9](tvw/audits/dispatch-9-increment8-bc-stack-2026-07-11.md).

The cloud training fan-out for the tracker's increment 8 ran under a hard $800 cap and a 48-hour hang watchdog, with the training recipe frozen before results. An arm was dropped only on a watchdog kill or a guard trip, not on the clock. See the [dwell-program audit](tvw/audits/audit-dwell-program-2026-07-07.md), Addenda J to N.

## Files

| Path | What it holds |
|---|---|
| [STAGES.md](STAGES.md) | Stages, stop-gates and the repair-loop stopping rule |
| [INVENTORY.md](INVENTORY.md) | Number inventory with evidence classes; weakest claims in section 6 |
| [AGENTS.md](AGENTS.md) | The orchestrator session's own rules, as the agent read them |
| [docs/agent/](docs/agent/) | Dispatch, scope and session rules |
| [pipeline/](pipeline/README.md) | Corpus build, search, claim extraction and critic loop |
| [tvw/audits/](tvw/audits/) | Audits, dispatches and verdict CSVs |
| [tvw/scripts/](tvw/scripts/) | `dispatch.sh`, its tests and the session scripts |

Audit files are append-only. Each later section is a dated, lettered addendum, so cite the addendum and its date, not the file name's date.
