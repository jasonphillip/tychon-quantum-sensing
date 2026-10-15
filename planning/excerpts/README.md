# Conversation record: proposal, learning, building, and review

This record follows selected conversations from the 2025 proposal through publication in October 2026.
It includes model suggestions, Jason's instructions, worker replies, and corrections.
The proposal was not selected; no SBIR award or contract resulted.

**Editorial note.** Context and outcomes are editorial summaries, separate from quoted chat messages.
Quotes preserve source spelling; cuts are marked […].
Relayed model text is labelled.
Exported web chats use the attribution “model version not recorded in the export”; session model identifiers appear only when recorded.
Private source exports and their paths are not published.
A model's claim or report of a passed test is not independent verification.

## Reading order

1. **Proposal, July–August 2025:** [the unfunded proposal](00-proposal-2025.md), with eight selections and the [proposal archive and claim crosswalk](../../docs/proposal/README.md).
2. **Learning and waiting, August 2025–February 2026:** [vendor tools, NV physics, and the delayed decision](learning-and-waiting-2025-26.md).
3. **The 90-day plan, March 4–11, 2026:** [playbook creation and review](playbook-creation-2026-03.md).
4. **Building, March–June 2026:** [01 — build order and interfaces](01-build-order-and-interfaces.md), [02 — OU noise plan and worker feedback](02-ou-noise-wiring-prompt-and-review.md), [03 — external review to repository prompts](03-external-review-to-repo-prompts.md), [04 — correct claims and pause a plan](04-fixing-claims-and-pausing-a-plan.md), [05 — research and verification](05-research-and-verification.md), and [additional selections](building-additional-selections-2026.md).
5. **Orchestration and publication, July–October 2026:** [protocol checks, contract correction, and negative results](orchestration-and-publication-2026.md); the [July steering exchange](human-steering.md#push-back) adds the earlier research request.
6. **Human steering:** [direction, challenge, correction, and inferred learning arcs](human-steering.md).
7. **What the models could not do:** [observations from this project](what-the-models-could-not-do.md), not a general benchmark.

The [conversation index](../conversations-index.md) retains the 86-chat project table and lists the additional sources.
The [engineering decisions](../../docs/engineering-decisions.md) connect selected exchanges to implementation and measured outcomes.

## Existing excerpt qualifications

Selections 01–05 retain their existing filenames and text.
The April 1 and April 29 selections already contain omissions.
The archived April 2 message export includes abbreviated tool-call descriptions and references to screenshots that are not embedded.

The [April 2 selection](05-research-and-verification.md#1-stop-speculative-patching-and-ask-for-research) links the full historical export and its companion summary, including later corrections.

- [02 — OU noise plan and worker feedback](02-ou-noise-wiring-prompt-and-review.md): an agent catches a flaw in the planning model's premise. Later evidence (note added 2026-10-13): the work landed in the first-attempt simulator as commit [69d91d4](https://github.com/jasonphillip/tychon-quantum-sensing/commit/69d91d4), whose message says "32/32 tests pass" where the excerpt's last line says 40/40; commit [762176d](https://github.com/jasonphillip/tychon-quantum-sensing/commit/762176d) later replaced the independent temperature and microwave noise with the cascaded model. How the current generator uses this noise: [synthetic-data walkthrough](../../docs/synthetic-data.md).
- [03 — External review to repository prompts](03-external-review-to-repo-prompts.md): audit findings become implementation work. Later evidence (note added 2026-10-13): the worker replies and the repo 2 and repo 3 prompts are cut from the excerpt. The shifted test distributions landed as simulator commit [9529f61](https://github.com/jasonphillip/tychon-quantum-sensing/commit/9529f61) and the sign folding, initialization and export module as edge-ML commit [474b0a7](https://github.com/jasonphillip/tychon-quantum-sensing/commit/474b0a7), both on 2026-04-04. Claude co-authored both commits, per their trailers. The test counts (55/55, 87/87) come from the [integration tracker](../docs/gemini-integration-tracker-2026-04-04.md), not from the commits.
