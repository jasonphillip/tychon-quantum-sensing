# Increment 8: single-component ablations (Tier 1 and Tier 2, option B)

**Reduced horizon.** Every run here trains for 200 epochs (teachers included), a quarter of the frozen 800-epoch recipe. The results describe that regime only; the frozen-recipe `bc` stack itself was not trained. Teachers trained for 200 epochs may be weaker than frozen-recipe teachers, so distillation could look different at full length; mid-training checkpoints can also be good teachers (arXiv 2210.06458).

Date: 2026-10-10. Code: odmr-vector-tracking `1a7b149` (branch `portfolio/c4-ablations`, with the paired non-inferiority code from `b259039`). Training set `sequence_train_v3`; evaluation on the dwell set (288 sequences) and the field-cone set (`sequence_eval_fieldcone_v1`, 120 sequences), clean rung shown (the snr30 rung agrees closely; all rows are in `increment8_ablations_verdicts.json`). One GB10 GPU per job on three workstations, each job pinned to one performance core. Caps: Tier 1 12 GPU-hours, used 7.7 job-hours; Tier 2 23 GPU-hours, used 19.0 job-hours.

## Arms

- `baseline_e200` — the v6 recipe (`baseline_v6`), seed 20260701.
- `ema_only_e200` — weight EMA (decay 0.999) only.
- `trunk_only_s<seed>_e200` — warm start from a shared trunk trained for 40 epochs on the same 200-epoch cosine (trunk seeds 20260700, 20260801, 20260802), then 160 more epochs; no distillation, no EMA.
- `kd1_e200` — single-teacher distillation (teacher_e1), no standardization.
- `std_only_e200` — single-teacher distillation **with** logit standardization, routed through the ensemble-distillation path with one teacher (the single-teacher path ignores the standardization flag; `losses.py` l.409–427).
- `ens_only_e200` — distillation from the averaged five teachers, no standardization, no EMA, no trunk.
- Teachers `teacher_e1`–`e5`: larger model (feature 64, state 128, 16 conv channels), pre-declared seeds 30260701–30260705, 200 epochs; best validation total 0.466–0.567 (the student baseline: 0.678).

## Per-run results

| Run | Epochs run (best) | Wall (h) | Dwell lost (Wilson 95 %) | Dwell ae mean / p90 (°) | Dwell lock fraction | Field-cone lost (Wilson 95 %) | Field-cone ae mean / p90 (°) | Field-cone lock fraction |
|---|---|---:|---|---|---:|---|---|---:|
| baseline_e200 | 200 (140) | 1.61 | 0/288 (0.000–0.013) | 1.02 / 1.68 | 0.999 | 72/120 (0.51–0.68) | 21.6 / 27.3 | 0.387 |
| ema_only_e200 | 200 (100) | 1.54 | 2/288 (0.002–0.025) | 1.27 / 2.12 | 0.995 | 71/120 (0.50–0.68) | 22.5 / 28.3 | 0.382 |
| trunk_only_s20260700_e200 | 200 (185) | 1.23 | 0/288 (0.000–0.013) | 0.83 / 1.48 | 0.999 | 71/120 (0.50–0.68) | 21.0 / 26.6 | 0.387 |
| trunk_only_s20260801_e200 | 200 (135) | 1.23 | 0/288 (0.000–0.013) | 1.01 / 1.66 | 0.998 | 73/120 (0.52–0.69) | 21.4 / 26.9 | 0.387 |
| trunk_only_s20260802_e200 | 180 (80) | 1.13 | 2/288 (0.002–0.025) | 1.26 / 2.07 | 0.996 | 71/120 (0.50–0.68) | 20.9 / 26.2 | 0.381 |
| kd1_e200 | 200 (200) | 2.20 | 0/288 (0.000–0.013) | 0.98 / 1.63 | 0.999 | 73/120 (0.52–0.69) | 23.3 / 28.6 | 0.365 |
| std_only_e200 | 200 (140) | 2.29 | 1/288 (0.001–0.019) | 1.09 / 1.75 | 0.998 | 67/120 (0.47–0.64) | 19.3 / 24.3 | 0.396 |
| ens_only_e200 | 200 (190) | 5.02 | 2/288 (0.002–0.025) | 0.95 / 1.60 | 0.997 | 74/120 (0.53–0.70) | 23.7 / 30.0 | 0.373 |

## Paired verdicts (margins proposed, not approved by Jason: +0.01 lost rate, +0.1° angle-error p90, −0.01 lock fraction)

"non-inferior": the CI bound on the harmful side is inside the margin. "inferior": the whole CI is past the margin. "not shown": neither — this never means "no harm". Lost-rate intervals for paired sequences use Tango's score interval, which stays non-degenerate when no sequence changes outcome (zero events in 288 pairs still allows about 1.3 %, so a 1 % margin cannot be certified there). Angle and lock intervals are sequence-blocked bootstraps.

### Dwell set (288 sequences)

| Pair (candidate vs reference) | Metric | Difference | 95 % CI | Margin | Verdict |
|---|---|---:|---|---:|---|
| ema_only_e200 vs baseline_e200 | lost rate | +0.007 | [-0.006, +0.025] | 0.01 | not shown |
| ema_only_e200 vs baseline_e200 | angle-error p90 (°) | +0.434 | [+0.346, +0.520] | 0.1 | inferior |
| ema_only_e200 vs baseline_e200 | lock fraction | -0.004 | [-0.007, -0.002] | 0.01 | non-inferior |
| trunk_only_s20260700_e200 vs baseline_e200 | lost rate | +0.000 | [-0.013, +0.013] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs baseline_e200 | angle-error p90 (°) | -0.206 | [-0.271, -0.143] | 0.1 | non-inferior |
| trunk_only_s20260700_e200 vs baseline_e200 | lock fraction | -0.001 | [-0.003, +0.000] | 0.01 | non-inferior |
| trunk_only_s20260801_e200 vs baseline_e200 | lost rate | +0.000 | [-0.013, +0.013] | 0.01 | not shown |
| trunk_only_s20260801_e200 vs baseline_e200 | angle-error p90 (°) | -0.024 | [-0.100, +0.054] | 0.1 | non-inferior |
| trunk_only_s20260801_e200 vs baseline_e200 | lock fraction | -0.001 | [-0.003, -0.000] | 0.01 | non-inferior |
| trunk_only_s20260802_e200 vs baseline_e200 | lost rate | +0.007 | [-0.006, +0.025] | 0.01 | not shown |
| trunk_only_s20260802_e200 vs baseline_e200 | angle-error p90 (°) | +0.385 | [+0.316, +0.456] | 0.1 | inferior |
| trunk_only_s20260802_e200 vs baseline_e200 | lock fraction | -0.003 | [-0.005, -0.001] | 0.01 | non-inferior |
| kd1_e200 vs baseline_e200 | lost rate | +0.000 | [-0.013, +0.013] | 0.01 | not shown |
| kd1_e200 vs baseline_e200 | angle-error p90 (°) | -0.059 | [-0.124, +0.003] | 0.1 | non-inferior |
| kd1_e200 vs baseline_e200 | lock fraction | -0.000 | [-0.001, +0.000] | 0.01 | non-inferior |
| std_only_e200 vs baseline_e200 | lost rate | +0.003 | [-0.010, +0.019] | 0.01 | not shown |
| std_only_e200 vs baseline_e200 | angle-error p90 (°) | +0.066 | [-0.017, +0.150] | 0.1 | not shown |
| std_only_e200 vs baseline_e200 | lock fraction | -0.001 | [-0.003, -0.000] | 0.01 | non-inferior |
| ens_only_e200 vs baseline_e200 | lost rate | +0.007 | [-0.006, +0.025] | 0.01 | not shown |
| ens_only_e200 vs baseline_e200 | angle-error p90 (°) | -0.084 | [-0.141, -0.027] | 0.1 | non-inferior |
| ens_only_e200 vs baseline_e200 | lock fraction | -0.002 | [-0.004, -0.000] | 0.01 | non-inferior |
| std_only_e200 vs kd1_e200 | lost rate | +0.003 | [-0.010, +0.019] | 0.01 | not shown |
| std_only_e200 vs kd1_e200 | angle-error p90 (°) | +0.125 | [+0.048, +0.202] | 0.1 | not shown |
| std_only_e200 vs kd1_e200 | lock fraction | -0.001 | [-0.003, +0.000] | 0.01 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | lost rate | +0.000 | [-0.013, +0.013] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | angle-error p90 (°) | -0.182 | [-0.264, -0.102] | 0.1 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | lock fraction | +0.000 | [-0.002, +0.003] | 0.01 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | lost rate | -0.007 | [-0.025, +0.006] | 0.01 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | angle-error p90 (°) | -0.591 | [-0.659, -0.522] | 0.1 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | lock fraction | +0.002 | [+0.000, +0.004] | 0.01 | non-inferior |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | lost rate | -0.007 | [-0.025, +0.006] | 0.01 | non-inferior |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | angle-error p90 (°) | -0.409 | [-0.485, -0.333] | 0.1 | non-inferior |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | lock fraction | +0.002 | [-0.001, +0.004] | 0.01 | non-inferior |

### Field-cone set (120 sequences, few crossings)

| Pair (candidate vs reference) | Metric | Difference | 95 % CI | Margin | Verdict |
|---|---|---:|---|---:|---|
| ema_only_e200 vs baseline_e200 | lost rate | -0.008 | [-0.061, +0.043] | 0.01 | not shown |
| ema_only_e200 vs baseline_e200 | angle-error p90 (°) | +1.002 | [-0.489, +2.568] | 0.1 | not shown |
| ema_only_e200 vs baseline_e200 | lock fraction | -0.005 | [-0.029, +0.019] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs baseline_e200 | lost rate | -0.008 | [-0.070, +0.052] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs baseline_e200 | angle-error p90 (°) | -0.751 | [-2.895, +1.252] | 0.1 | not shown |
| trunk_only_s20260700_e200 vs baseline_e200 | lock fraction | +0.000 | [-0.030, +0.028] | 0.01 | not shown |
| trunk_only_s20260801_e200 vs baseline_e200 | lost rate | +0.008 | [-0.052, +0.070] | 0.01 | not shown |
| trunk_only_s20260801_e200 vs baseline_e200 | angle-error p90 (°) | -0.450 | [-2.206, +1.336] | 0.1 | not shown |
| trunk_only_s20260801_e200 vs baseline_e200 | lock fraction | +0.000 | [-0.033, +0.031] | 0.01 | not shown |
| trunk_only_s20260802_e200 vs baseline_e200 | lost rate | -0.008 | [-0.074, +0.056] | 0.01 | not shown |
| trunk_only_s20260802_e200 vs baseline_e200 | angle-error p90 (°) | -1.109 | [-3.103, +0.847] | 0.1 | not shown |
| trunk_only_s20260802_e200 vs baseline_e200 | lock fraction | -0.006 | [-0.044, +0.031] | 0.01 | not shown |
| kd1_e200 vs baseline_e200 | lost rate | +0.008 | [-0.060, +0.077] | 0.01 | not shown |
| kd1_e200 vs baseline_e200 | angle-error p90 (°) | +1.272 | [-0.540, +3.059] | 0.1 | not shown |
| kd1_e200 vs baseline_e200 | lock fraction | -0.022 | [-0.058, +0.011] | 0.01 | not shown |
| std_only_e200 vs baseline_e200 | lost rate | -0.042 | [-0.115, +0.028] | 0.01 | not shown |
| std_only_e200 vs baseline_e200 | angle-error p90 (°) | -2.995 | [-5.209, -0.914] | 0.1 | non-inferior |
| std_only_e200 vs baseline_e200 | lock fraction | +0.010 | [-0.020, +0.038] | 0.01 | not shown |
| ens_only_e200 vs baseline_e200 | lost rate | +0.017 | [-0.053, +0.088] | 0.01 | not shown |
| ens_only_e200 vs baseline_e200 | angle-error p90 (°) | +2.652 | [+0.235, +5.309] | 0.1 | inferior |
| ens_only_e200 vs baseline_e200 | lock fraction | -0.014 | [-0.044, +0.014] | 0.01 | not shown |
| std_only_e200 vs kd1_e200 | lost rate | -0.050 | [-0.125, +0.021] | 0.01 | not shown |
| std_only_e200 vs kd1_e200 | angle-error p90 (°) | -4.267 | [-6.017, -2.550] | 0.1 | non-inferior |
| std_only_e200 vs kd1_e200 | lock fraction | +0.032 | [+0.009, +0.056] | 0.01 | non-inferior |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | lost rate | -0.017 | [-0.081, +0.045] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | angle-error p90 (°) | -0.301 | [-2.270, +1.602] | 0.1 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260801_e200 | lock fraction | -0.000 | [-0.030, +0.032] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | lost rate | +0.000 | [-0.059, +0.059] | 0.01 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | angle-error p90 (°) | +0.358 | [-1.200, +1.952] | 0.1 | not shown |
| trunk_only_s20260700_e200 vs trunk_only_s20260802_e200 | lock fraction | +0.006 | [-0.025, +0.040] | 0.01 | not shown |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | lost rate | +0.017 | [-0.040, +0.077] | 0.01 | not shown |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | angle-error p90 (°) | +0.660 | [-0.816, +2.174] | 0.1 | not shown |
| trunk_only_s20260801_e200 vs trunk_only_s20260802_e200 | lock fraction | +0.006 | [-0.022, +0.033] | 0.01 | not shown |

## Reading

- **No component wins on both sets.** On the dwell set, ensemble distillation is non-inferior and slightly better than the baseline on angle-error p90 (−0.08°), with its lost-rate difference not shown, while EMA alone is inferior (+0.43°). On the field-cone set, the intervals are wide and the pattern changes: ensemble distillation is inferior (+2.7°) and standardization is better (−3.0°).
- **Standardization (`std_only` minus `kd1`).** It worsens the dwell angle error by 0.12° (CI above zero) and improves the field-cone angle error by 4.3° (CI below zero). No lost-rate difference is resolved on either set. The effect is split-dependent, so it cannot be called a gain.
- **The trunk seed matters as much as any component.** The three trunk-only runs differ from each other by up to 0.59° on the dwell set, which is larger than every single-component effect on that set, EMA included. One seed beats the baseline, one matches it, one is inferior.
- **Lost rates and lock fractions barely move.** Dwell: 0–2 of 288 sequences lost in every arm, lock-fraction differences within ±0.005; field-cone: 67–74 of 120 lost in every arm. No lost-rate difference is resolved, and with so few events the lost-rate margin cannot be certified for any arm. The only resolved field-cone lock-fraction change is standardization over plain distillation (+0.032).
- Full-vector metrics (C3) are not on this branch.

The `bc` stack's premise — that these levers together make identity recovery reliable across seeds — is not tested here: the 200-epoch single-component runs show effects of the same size as the trunk-seed spread, and in opposite directions on the two evaluation sets.
