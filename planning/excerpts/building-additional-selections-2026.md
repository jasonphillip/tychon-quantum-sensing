# Building: additional conversation selections

These four exchanges record corrections during the build. Quotes retain the source wording and spelling; […] marks cuts. Dates follow the export timestamps. Commentary, context, and outcomes are editorial summaries. A reported check is historical evidence, not a new verification run.

Sources: private export, not published. For the claude.ai project chats, model version not recorded in the export. The May 1 Claude Code session records claude-opus-4-7.

<a id="b1"></a>
## B1. Stop trusting the AI as verifier

**Date and context.** May 1, 2026. Jason said each review of the final drafts exposed another error.

**Jason**

> […] I want to make note that as of today i decided im finding at least one error everytime i recheck the final drafts. This is a good point to stop trusting the AI because something was done wrong at a much earlier part in the process and it is cascading errors to each attempt to move forward. […]

**Claude (claude.ai project)**

> […] your reasoning here is sound, not weak — finding a fresh defect on every recheck *is* the diagnostic. The cascade is real, and the LLM is the wrong tool to break it. […] verification has to leave the loop.

**What happened next.** The [orchestrator account](../../orchestrator/README.md) dates the workbench's start to the same day, to check Jason's report. The causal link to this exchange is inferred from the date, not stated in the export.

<a id="b2"></a>
## B2. A report figure fails a check against its source

**Date and context.** May 1, 2026. The technical report used SBIR Phase I final-report format for a proposal that was not selected.

**Jason — prompt as pasted by Jason**

> Look up what the Phase I final report says about the 200 MHz timing closure achievement using search-corpus tychon-docs "200 MHz timing closure". Then find the actual […] post-place-and-route worst-case slack number from the closure deliverable using search-corpus tychon-docs "worst slack PID datapath". Tell me whether the two numbers are […] consistent and cite the exact source path for each.

**Claude Code session in tychon-verification-workbench**

> **The two numbers are not consistent.** […] The Final Report's **+2.107 ns** figure is ~1.4 ns looser than the actual r6_s25 FIC_0 OUT0 number (+0.728 ns) […] The most plausible explanation, given the closure deliverable's own narrative ("first time this design has produced post-P&R numbers that reflect the actual integrated PID compute datapath rather than a constant-folded paper-shell" and the −541 ps tightening note), is that the report's +2.107 ns is a **stale paper-shell-era number** […]

**What happened next.** The published [May 3 timing audit](../../orchestrator/tvw/audits/audit-006-fpga-timing-claim-revalidation.md) revalidates +0.728 ns on the 125 MHz FIC clock domain. It records the corrected figure; it does not establish that this exchange caused the correction.

<a id="b3"></a>
## B3. Qualifying the April scorecard

**Date and context.** June 1, 2026. Jason asked Claude to answer another model's questions using the source numbers, not the summary table.

**Jason**

> Not let's go over the interesting points but use them against the actually numbers you started and not what the other llm saw which was the table

**Claude (claude.ai project)**

> **Only at τ=2,700 s.** Over the rest of the range it's roughly 25–61% (24.6% at τ=1, 48.8% at τ=1,000, 61.2% at τ=5,400). […]

> **No.** 5.2 W is FPGA fabric + MSS subsystem only, […] So the defensible statement is "5.2 W FPGA+MSS, ~9–10 W full payload, estimated." […]

**What happened next.** The [scorecard note](../docs/status.md#kpp-scorecard-r6_s25) now identifies the April 30 snapshot and these two limits. The quoted power values are estimates; the exchange does not establish measured full-payload power.

<a id="b4"></a>
## B4. Jason corrects the model's assumption

**Date and context.** April 27, 2026, before the May 12 not-selected decision. Jason corrected Claude's assumption that the work had reached final report preparation.

**Jason**

> […] You seem to be under the impression that we should not refacor or improve anuy of the three repos however maybe you misunderstood my timeline

**Claude (claude.ai project)**

> You're right — I was wrong about your timeline. […] my "no repo refactoring" framing was wrong because I had the timeline wrong. […]

**What happened next.** Claude reversed its advice about repository changes in this reply. The [decision log](../docs/decision-log.md) and [historical status file](../docs/status.md) preserve planning context; a later implementation caused by this exchange was not traced.
