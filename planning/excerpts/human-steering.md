# Human steering

This page collects moments where Jason set direction, asked for challenge, or accepted correction, with links to exchanges and outcomes.
It presents evidence, not self-assessment.
A search of his own typed instructions did not find him originating the baseline-first or freeze-before-scoring rules.
Those rules came from models and reviewers, and he adopted them.

**Editorial note.** Context, outcomes, and learning arcs below are editorial summaries.
Quotes retain source spelling; […] marks cuts.
Sources are private export, not published, except where an existing public excerpt is linked.
For exported web chats: model version not recorded in the export.
The quoted session headers record claude-opus-4-6 on April 2, claude-fable-5 on July 3, and claude-opus-5-5 on October 9.

## Direction set

- **July 28, 2025:** Jason asked for room-temperature operation instead of 77 K; the [proposal exchange](00-proposal-2025.md#4-refactor-the-proposal-for-room-temperature--july-28-2025) records the refactor and links proposed targets to measured results.
- **March 8, 2026:** Jason requested “not marketing optimism”; the [cross-sensor review](playbook-creation-2026-03.md#p6) left the build scoped to NV-diamond sensing.
- **March 9, 2026:** Jason requested one consolidated version 4 against Claude's recommendation to add another addendum; the [exchange](playbook-creation-2026-03.md#p8) links the resulting playbook.

## Asked for research or challenge

### Stop speculative patching

**Date and context.** April 2, 2026. Repeated vendor-tool errors prompted Jason to ask for research.

**Jason**

> […] maybe we need to take a step back nad do some research […]

**What happened next.** The [exchange and later evidence](05-research-and-verification.md#1-stop-speculative-patching-and-ask-for-research) show research, a grounded-tool request, and further failed integration attempts.

<a id="push-back"></a>
### Ask the model to push back

**Date and context.** July 3, 2026. Jason asked the FPGA session to check a claim before changing a presentation.

**Jason**

> […] please make sure you dont just take my word and push back where needed. DOnt make ay changes ot the deck just do some research

**Claude Code session in polarfire-hybrid-control**

> Good challenge — let me actually research this rather than agree by reflex. […]

**What happened next.** Claude began research; the [vector problem statement](../../workers/odmr-vector-tracking/docs/design/00_problem.md) records the bias-field trade-off.
That document supports the technical context, not a measured effect of this prompt.

<a id="learning-story"></a>
### Ask for an honest critique of the learning story

**Date and context.** October 9, 2026. Jason questioned how prominently to present his learning history.

**Jason**

> […] putting the learning part so prominant? give me an hoest critique

**Claude Code session in tychon-verification-workbench**

> My honest view: don't make the learning story prominent. Use it as a short, dated supporting section, not a headline.

**What happened next.** The [method page](../../docs/method.md#how-i-came-up-to-speed) contains a short dated learning table.
Acceptance is inferred from the published outcome; no explicit acceptance turn was located.

## Corrected a model

- **April 27, 2026:** Jason corrected the model's assumption about his timeline; [Claude reversed its recommendation](building-additional-selections-2026.md#b4).
- **May 1, 2026:** Jason identified repeated errors and stopped trusting AI as its own verifier; the [exchange](building-additional-selections-2026.md#b1) links the workbench created that day, with causation explicitly marked as inferred.

## Where Jason's own work was wrong

- The proposal promised more than tenfold noise suppression; the [March review](playbook-creation-2026-03.md#p4) narrowed that claim to slow drift.
- A control-loop visual discussed alongside the proposal needed correction; the [January exchange](learning-and-waiting-2025-26.md#a4) clarified the signal-processing roles.

## Learning arcs

- **Praise to push-back — medium evidence, inferred:** Gemini called the proposal “exceptionally strong” in [August 2025](00-proposal-2025.md#5-ask-for-flaws-and-number-checks--august-1-2025); Jason asked for [push-back](#push-back) in July 2026.
  The link is inferred from the topic; Jason never cites the earlier praise.
- **Grounded tools — medium evidence, inferred:** the [2025 tool discussions](learning-and-waiting-2025-26.md#a1) precede his April 2 request for “a prompt for that fgrounded noteook llm”.
  The [existing exchange](05-research-and-verification.md#1-stop-speculative-patching-and-ask-for-research) and [workbench account](../../orchestrator/README.md#why-the-critics-stay-local-and-off-the-web) support continued use, not proof that those chats first taught him the method.
  The coding model had already suggested the grounded tool in that April session.

Back to the [conversation record](README.md).
