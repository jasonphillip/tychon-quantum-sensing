# Paired non-inferiority re-verdict

**Proposed analysis, not approved by Jason.** This is a retrospective audit, not a policy reselection.
The legacy verdict scripts and their pre-declared rules remain historical records.

A 95% sequence-blocked paired bootstrap uses 10,000 draws and common sequence IDs across seed strata.
A guard is non-inferior only when the upper CI for candidate minus baseline is below its margin.
A CI wholly below zero is superior. Other comparisons are inconclusive; at least 30 distinct sequences are required.

| Metric | PROPOSED margin (not approved) | Rationale |
|---|---:|---|
| lock loss | +0.01 rate | At most one extra lost sequence per 100. |
| misassociation | +0.01 rate | At most one extra wrong collision frame per 100. |
| IDSW/opportunity | +0.01 rate | At most one extra switch per 100 opportunities. |
| post-crossing angular error | +0.1 degree mean | Smaller than the reported angular differences of concern. |

## Wave-1 levers

Source: archived `matrix_2c_final.json`; old decisions: `docs/increment2c_results.md`.
The matrix preserves the same sequence order and fixed noise realization for each tracker.

| Lever | Guard | Old verdict | New verdict | Paired evidence |
|---|---|---|---|---|
| soft_targets | lock_loss | accepted as neutral/better | inconclusive | 6/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.233 |
| soft_targets | ae_post | accepted as neutral/better | inconclusive | 9/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.440 |
| soft_targets | misassoc | regression | inconclusive (missing matched arrays) | no per-sequence data |
| soft_targets | idsw_opp | accepted as neutral/better | inconclusive (missing matched arrays) | no per-sequence data |
| sinkhorn | lock_loss | accepted as neutral/better | inconclusive | 6/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.133 |
| sinkhorn | ae_post | regression | inconclusive | 11/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.374 |
| sinkhorn | misassoc | regression | inconclusive (missing matched arrays) | no per-sequence data |
| sinkhorn | idsw_opp | accepted as neutral/better | inconclusive (missing matched arrays) | no per-sequence data |
| scheduled_sampling | lock_loss | regression | inconclusive | 12/12 inconclusive; 8 CIs exclude zero on worse side; max upper CI +0.967 |
| scheduled_sampling | ae_post | regression | inconclusive | 12/12 inconclusive; 4 CIs exclude zero on worse side; max upper CI +7.705 |
| scheduled_sampling | misassoc | regression | inconclusive (missing matched arrays) | no per-sequence data |
| scheduled_sampling | idsw_opp | regression | inconclusive (missing matched arrays) | no per-sequence data |

Old wave-1 decision: **all three eliminated**. New decision: **none qualifies as non-regressing across all guards**.
IDSW/opportunity lacks per-sequence event and opportunity arrays; its old neutral calls cannot be confirmed.

## Increment-7 arms

Source: archived arm, v6, and old-verdict JSON files.
Matched training-seed suffixes and sequence ordinals retain the paired design.

| Arm | Guard | Old verdict | New verdict | Paired evidence |
|---|---|---|---|---|
| 7a | PRIMARY held misassoc | does not clear | does not clear | paired inconclusive; 2/2 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.032; every-seed retained |
| 7a | GUARD-A directed zero | pass | pass | exact zero rule; 24 sequences/seed |
| 7a | GUARD-A off-cone dwell lock | accepted as neutral/better | inconclusive | pooled counts only; no paired rows |
| 7a | GUARD-B standing lock | accepted as neutral/better | inconclusive | 10/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.153 |
| 7b | PRIMARY held misassoc | does not clear | does not clear | paired superior; 0/2 inconclusive; 0 CIs exclude zero on worse side; max upper CI -0.043; every-seed retained |
| 7b | GUARD-A directed zero | pass | pass | exact zero rule; 24 sequences/seed |
| 7b | GUARD-A off-cone dwell lock | accepted as neutral/better | inconclusive | pooled counts only; no paired rows |
| 7b | GUARD-B standing lock | accepted as neutral/better | inconclusive | 10/12 inconclusive; 0 CIs exclude zero on worse side; max upper CI +0.135 |
| 7c | all | not evaluated | inconclusive (no arm results) | no rows |

Old increment-7 decision: **keep nothing, escalate**. New decision: **keep nothing**.
The old claim that evaluated arms cleared every acquisition guard is no longer supported:
GUARD-A off-cone dwell is inconclusive without sequence-level outcomes.
These proposed margins do not revise the contractual deployable default.

## Decision changes

The top-level choices do not change: no wave-1 lever survives and increment-7 keeps no arm.
The supporting guard verdicts do change. Several old neutral/better calls are inconclusive
under the proposed paired rule, including both arms' off-cone dwell and standing-lock guards.
Wave-1 misassociation and IDSW/opportunity have no matched arrays in the archived matrix.
No new non-regression claim is certified from pooled Wilson overlap.
