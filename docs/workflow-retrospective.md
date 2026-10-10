# Agent workflow retrospective

This retrospective covers the review and dispatch records kept in this repository. It uses records only. It adds no new measurements.

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
