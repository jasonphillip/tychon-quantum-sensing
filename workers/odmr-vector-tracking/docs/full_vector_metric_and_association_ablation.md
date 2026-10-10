# Full-vector metrics and the association-loss ablation

Date: 2026-10-10. Code: odmr-vector-tracking `64fd20f` (branch `portfolio/c3-full-vector`). Evaluation set: `data/sequence_eval_fieldcone_v1` (120 sequences × 256 frames; content hash `819d9ac0a2b0`), rungs clean and snr30. Training set: `sequence_train_v2` (config hash `3341810ccda0`, the matched baseline's own set). Cap: 8 GPU-hours (two runs); used 4.8 job-hours (2.9 h + 1.9 h wall, one GPU each).

## Metrics (per sequence, then averaged)

- **rmse_T** — RMS of |B_est − B_true| over frames where both are finite, Tesla. All 120 sequences had finite frames in every cell (n_valid_sequences = 120), so no sequence was dropped.
- **mag_err** — |B_est| − |B_true| per frame (signed; the row's mean is the magnitude bias, its p90 is taken over |error|).
- **bias** — mean of B_est − B_true per axis.
- **ae** — angle between B_est and B_true, degrees.
- **Full-vector lock** — a frame is locked when the magnitude error is within 5 % of |B_true| **and** the angle error is at most 5°. The 5 % tolerance is proposed by this plan; 5° is the repo's existing `LOSS_DEG`. A NaN or near-zero estimate is never locked. A sequence is **lost** when, after first acquisition, it stays unlocked to the end, or never acquires.

## Runs

| Label | Recipe | w_assoc | Seed | Epochs run (best) | Wall |
|---|---|---:|---:|---|---:|
| assoc | existing `increment2c/v2_gated_linear_snr10` (gated core, linear association) | 1.0 | 20260701 | 330 (230) | 3.2 h |
| noassoc | same recipe, association losses off | 0.0 | 20260701 | 330 (310) | 2.9 h |
| s2 | same recipe as assoc, second seed | 1.0 | 20260702 | 240 (140) | 1.9 h |

All three use the 800-epoch cosine schedule; the new runs stop at epoch 330 (`--epochs 800 --stop-epoch 330`) so their learning-rate schedule matches the baseline's, which stopped at 330 by patience. Early stopping uses the validation total loss; with `w_assoc = 0` that loss has no association term, so the two arms select checkpoints by slightly different criteria.

## Results (field-cone, clean; snr30 agrees to the third digit)

| Label | rmse mean / p90 (mT) | ae mean / p90 (°) | magnitude bias (mT) | lock fraction | lost (Wilson 95 % CI) |
|---|---|---|---:|---:|---|
| assoc | 2.565 / 4.331 | 44.8 / 83.4 | 0.188 | 0.100 | 108/120 (0.83–0.94) |
| noassoc | 2.110 / 3.702 | 34.4 / 65.2 | 0.256 | 0.100 | 108/120 (0.83–0.94) |
| s2 | 2.510 / 3.754 | 44.0 / 72.3 | 0.208 | 0.100 | 108/120 (0.83–0.94) |

Paired differences (second minus first, 95 % sequence-blocked bootstrap, 10 000 draws, n = 120):

| Pair | rmse (mT) | ae mean (°) | lock fraction | lost |
|---|---|---|---|---|
| assoc → noassoc (ablation) | −0.456 [−0.650, −0.276] | −10.4 [−14.9, −6.2] | +0.0002 [+0.0001, +0.0004] | 0 [0, 0] |
| assoc → s2 (seed spread) | −0.056 [−0.185, +0.065] | −0.9 [−3.1, +1.2] | +0.00003 [0, +0.0001] | 0 [0, 0] |

## Answer

The association losses do not earn a field-accuracy benefit on this set: removing them lowers the vector RMSE by 0.46 mT and the mean angle error by 10.4°, with both confidence intervals wholly below zero. The difference between two seeds of the same recipe is about one eighth of that and its intervals include zero, so the ablation effect is larger than the seed spread measured here (one extra seed; not a full seed study).

What the association losses do buy: the association head itself. Without them its anchor-level accuracy collapses (validation 0.13 against 0.99), while the physical line-identity accuracy is unchanged (median per sequence 0.979 against 0.969). The full-vector lock does not separate the arms: about 10 % of frames lock and 108 of 120 sequences end lost in every arm, so on this field-cone set the tracker rarely holds a field estimate inside 5 % and 5°.

Each arm is one training run (plus one extra baseline seed), so the intervals cover sequence noise, not the full seed-to-seed variance (arXiv 1806.08295).
