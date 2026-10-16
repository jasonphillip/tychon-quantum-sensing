# Agent workflow retrospective

This retrospective covers the review and dispatch records kept in this repository. Sections 1 to 5 use records only and add no new measurements. Their review counts and tables are unchanged since the earlier review.
An activity audit dated October 16, 2026 is added at the end, in [Activity-count methodology](#activity-count-methodology).

The [case study](case-study.md#how-i-ran-it) explains why I built the workbench without the planned specialists. The [proposal crosswalk](proposal/README.md#work-extended-beyond-the-phase-i-feasibility-plan) records three extensions into areas deferred to Phase II, including a failed model experiment.

## 1. What was measured and what was not

This retrospective is mostly qualitative. Two quantitative inputs are thin or missing.

- The dispatch calibration has only three acknowledged dispatches with both a predicted and an actual hour count.
- No cost-per-change record exists. Nothing links model tokens, owner time or GPU time to a single accepted change.

What exists is a review inventory. It covers 50 markdown files under `tvw/audits/` (the claim-evaluation subfolder was excluded). It lists 156 numbered findings, and 62 of them carry written evidence of action. These counts are a floor, not a rate. Several files hold findings that were never numbered, and the inventory did not follow commits outside each file. The inventory is capped at 50 files, so 11 files in the audit folder are not counted.

## 2. Prediction calibration

The dispatch tool reports calibration with this command: `dispatch.sh stats --full`. Its output, verbatim, in `dispatch-stats.txt`:

| Dispatch | Predicted | Actual | Actual / predicted | Outcome |
|---|---|---|---|---|
| Dataset integration and provenance fixes | 6 h | 2 h | 0.33 | success |
| Toolchain upgrade decision brief | 4 h | 1 h | 0.25 | success |
| Hardware actuator bench | 1.5 h | 0.4 h | 0.27 | success |

The stats command reports n=3. It reports a geometric-mean ratio of actual to predicted hours of 0.28, which it labels "over-estimating". It reports a p_success Brier score of 0.042 (n=3) and three successful outcomes, none partial, none failed. It also says the report "firms up at n>=20". One more record was skipped because its hours were missing or not positive.

Self-forecasts of AI-assisted work are known to be biased. In arXiv 2507.09089, developers forecast a speedup and measured a 19 % slowdown. At n=3 the ratio above is therefore descriptive. It is not a calibration, and it must not be used to scale future estimates.

Older dispatch bodies carry no prediction. The audit folder holds 16 dispatch bodies. None of them states a predicted hour count. One further completed dispatch record has actual hours but no prediction, so it cannot enter the ratio.

## 3. Errors caught before shipping

The table lists the review files that hold numbered findings. "Acted on" counts findings with written evidence of a fix, a resolution or an applied edit. Dates come from the first dated heading. Where a heading carries no date, the date is the first date in the body and is marked "body". Files with addenda are cited by addendum letter and date.

| Review type | Date | Findings | Acted on | File |
|---|---|---|---|---|
| Audit of the final technical report | body 2026-05-01 | 11 | 4 | `audit-001.md` |
| Re-audit with build artifacts | body 2026-05-01 | 13 | 6 | `audit-002.md` |
| Re-audit after a versioning fix | body 2026-05-01 | 13 | 5 | `audit-003.md` |
| Re-audit of the revised report | body 2026-05-01 | 7 | 0 | `audit-004.md` |
| Structure and flow pass | body 2026-04-30 | 3 | 2 | `stage-4-structure-findings.md` |
| Claim check of one report section | body 2026-05-01 | 5 weak claims of 17 | 0 | `section-4-mini-audit.md` |
| Device package correction | body 2026-05-03 | 9 | 7 | `audit-005-fpga-package-correction.md` |
| Timing claim re-validation | body 2026-05-03 | 7 | 3 | `audit-006-fpga-timing-claim-revalidation.md` |
| Soft-narrative verification | body 2026-05-03 | 5 | 3 | `audit-007-soft-narrative-verification.md` |
| Design review of the sequence program | body 2026-07-01 | 35 | 17 | `design-review-odmr-vector-2026-07-01.md` |
| Program outcome audit | 2026-07-07, addenda A to S through 2026-07-14 | 3 | 3 | `audit-dwell-program-2026-07-07.md` |
| Review of a model's self-audit | 2026-08-21, addenda A to C (all 2026-08-21) | 9 | 5 | `composer-self-audit-review-2026-08-21.md` |
| Harness architecture review | 2026-08-19 | 7 | 0 | `harness-architecture-review-2026-08-19.md` |
| Harness alignment review | 2026-09-04, addenda A to C (all 2026-09-04) | 8 | 3 | `harness-sota-alignment-2026-09-04.md` |

Four points follow from the table.

- The first four audits track one report across revisions. Audit-004 records that the three critical findings of audit-001 are closed in version 3.1. Audit-004 itself lists no fixes.
- The counts overlap. The same finding appears in several consecutive audits. The sum of the column is not a count of distinct errors.
- The design review of 2026-07-01 lists 35 findings. It marks 17 lines as "Injected" in its fix-state column. One finding showed that a published baseline was a detector artifact.
- The harness architecture review states that nothing was implemented. No later addendum exists in that file.

## 4. Cost per accepted change

Cost per accepted change is not recorded. No field in any dispatch, audit or commit ties a cost to a change.

The only proxy is token use per project from a local usage scan. The scan has no per-change attribution. It cannot say which tokens produced an accepted change and which produced a rejected one.

## 5. What would make the next retrospective quantitative

The next retrospective needs three record fields on every accepted change. They follow the split in arXiv 2608.02582, section 3.1: total cost = LLM cost + human-in-the-loop cost + infrastructure cost.

1. **Model tokens by tier.** Record input and output tokens for each tier: Fable, Opus, Sonnet and Codex. This is the LLM cost.
2. **Owner minutes.** Record the minutes the owner spent on approvals, labels and reviews. This is the human-in-the-loop cost.
3. **GPU-hours and wall time.** Record the GPU-hours used on the local GPU workstations and the elapsed wall time. This is the infrastructure cost.

With these fields, a later retrospective can report cost per accepted change and compare it with the predicted hours. It can do so without relying on the forecaster's own estimate.

## Activity-count methodology

This section describes an activity audit dated October 16, 2026. The aggregate is in [activity-counts-2026-10-16.json](activity-counts-2026-10-16.json). It is separate from the review inventory above.

### Counts

| Measure | Count |
|---|---|
| Submitted interactions | 1,357 |
| Coding sessions and web conversations | 217 |
| Unique activity dates, July 2, 2025 to October 15, 2026 | 113 |

| Source | Submissions | Sessions or conversations |
|---|---|---|
| Claude Code and Codex | 838 | 152 sessions |
| ChatGPT and Claude web (selected) | 321 | 65 conversations |
| Gemini prompt records | 198 | no valid conversation-thread count |

The 1,357 total is 838 + 321 + 198. The 217 total is 152 + 65. Gemini prompt records are not conversations, so they are not in the 217.

### Scope

- All counts are conservative selected subsets of a private archive. They are not exhaustive lifetime totals.
- They include research, proposal and report writing, diagrams, implementation, evaluation, corrections, approvals and pasted handoffs.
- They are not a unique-task count. They do not claim that Jason authored every word.
- Core engineering folders were taken as a group. The mixed verification-workbench folder used a strict technical-vocabulary selection. Generic framework and fleet work and unrelated SBIR topics were excluded.
- Short, context-dependent replies were often omitted. This keeps the subset conservative.

### Coding sessions (Claude Code and Codex)

- Excluded: tool results, meta and sidechain records, compacted summaries, automated continuation and SDK inputs, agent-created or delegated executor sessions, and unrelated work.
- Deduplication used message identity, plus identical timestamp and normalized text. A resubmission at a different time counts as an interaction.
- 488 older top-level user records lack explicit human-origin metadata. Their attribution is inferred from provenance after the exclusions. Samples were inspected.

### Web conversations and Gemini

- Selections were scoped by topic and kept only project-related exchanges.
- Duplicate prompt text was normalized and collapsed, including copies on web branches.
- Both per-turn and whole-conversation export formats were parsed.
- The same text submitted independently to different providers counts separately.
- Gemini counts are prompt records, not conversations.

### Dates

- The 113 dates are the union across sources, not a sum.
- Claude Code, Codex, ChatGPT and Claude web timestamps were converted to Eastern time. For Gemini, the record-header date was checked against the displayed timestamp, not the filename.
- A date with logged activity is not a full workday.

### Time sensitivity (not a headline figure)

| Maximum gap between adjacent user submissions | Logged interaction window |
|---|---|
| 15 minutes | 45.789 hours |
| 30 minutes | 79.845 hours |

- Intervals were joined within each included coding or web session, and overlaps were merged across sessions and providers.
- Isolated submissions count as zero. Gemini is excluded.
- These are logged interaction windows. They are not human work hours, not a confidence interval and not a lower bound on labor.
- They include waiting time and omit reading and offline work.

### Limits

- Private raw records are not published.
- The public aggregate lets a reader check the arithmetic and count the listed distinct dates.
- It does not let a reader reconstruct the source classification or the human attribution.
- This audit makes no conversion from tokens to labor and no claim about cached-token volume.
