# Scalar stress test: does the direct estimator's gain survive realistic conditions? (2026-10-14)

Short answer: **no.** On clean, narrow-line spectra the frozen direct-magnitude estimator (11.10 µT INT8) ties a prior-aware classical two-line fit (10.94 µT); under realistic line width, noise and background slope it degrades to 25–34 µT, worse than the 13.04 µT training-mean constant; the PID proxy fails outright there (~810 µT) and the residual models fail with it. A dev-only diagnostic points at the background slope as the main cause. The pre-declared criterion failed. Synthetic data throughout; nothing deployed changed.

## Setup (protocol fixed before any new data was scored)

Protocol `experiments/scalar_stress_test/PROTOCOL.md` (sha256 `39cde896ef333889806d176e3e162af645608de9c02a59310b9884925f746072`), run by Jason's Codex session; independent review of the protocol and the generator, the freeze check and the recomputation below by the orchestrating session. Single-orientation production recipe (one NV axis, two transitions; the earlier four-pair comparator idea was inapplicable and withdrawn), same 100-point 2.82–2.92 GHz grid, magnitude uniform on [20, 70] µT, isotropic direction. Seven cells on the vector protocol's condition definitions:

| Cell | Intrinsic FWHM (MHz) | Contrast | Reference SNR | End-to-end slope | Frequency offset (MHz) |
|---|---:|---:|---:|---:|---:|
| clean | 1.5 | 0.030 | ∞ | 0 | 0 |
| realistic_anchor | 5 | 0.015 | 10 | +0.02 | +0.3 |
| wide_lines | 7 | 0.015 | 10 | +0.02 | +0.3 |
| low_snr | 5 | 0.015 | 3 | +0.02 | +0.3 |
| negative_slope | 5 | 0.015 | 10 | −0.02 | +0.3 |
| negative_offset | 5 | 0.015 | 10 | +0.02 | −0.3 |
| higher_contrast | 5 | 0.030 | 10 | +0.02 | +0.3 |

Partitions dev 16 / val 128 / final 256 rows per cell (master seeds 202610140/1/2, disjoint from every earlier set); within a partition all cells share field vectors and nuisance draws. Candidates frozen before the final read (`scalar_stress_test_2026-10/FROZEN_CHOICES.public.json`, derived from the original with sha256 `5e54c8f9fe223217cdd8e5566f0665724c3fa230395092b733f1a6b79f63790f`): the three direct-magnitude models from the target-repair experiment (FP32 and their existing INT8 exports) and the three full-residual models with new rank-calibrated INT8 exports (`calibration-repair/`: on the original validation split that export change takes B from 13.83 to 10.82 µT INT8 against 10.81 float — the export, not the model, had been the loss). Baselines: training mean (45.064 µT) and median, the PID proxy, the two-line projection fit, and prior-aware versions of both (|Bz| → conditional median under the declared U[20,70] prior; a prior-dependent estimator, not exact recovery; failures and support violations counted). The PID estimate and lock bin are computed on each stressed row. Final was read once (`receipts/FINAL_ACCESS.json`).

## Results (final partition, 256 rows per cell, MAE in µT; model rows average three fixed seeds)

| Cell | Direct INT8 | Direct FP32 | Residual rank-INT8 | Prior-aware fit | Training mean | PID |
|---|---:|---:|---:|---:|---:|---:|
| clean | 11.096 | 11.000 | 11.358 | 10.941 | 13.043 | 16.746 |
| realistic_anchor | 33.575 | 38.469 | 824.786 | 25.097 | 13.043 | 809.656 |
| wide_lines | 14.797 | 14.763 | 833.717 | 24.984 | 13.043 | 801.292 |
| low_snr | 31.847 | 38.355 | 650.352 | 24.002 | 13.043 | 631.024 |
| negative_slope | 25.703 | 28.306 | 777.236 | 25.014 | 13.043 | 755.192 |
| negative_offset | 31.820 | 34.941 | 827.919 | 24.871 | 13.043 | 809.585 |
| higher_contrast | 24.767 | 25.892 | 826.429 | 25.020 | 13.043 | 799.026 |

Pre-declared criterion — direct INT8 below both the training mean and the prior-aware fit with paired upper 95 % bounds below zero in both primary cells (clean, realistic_anchor): **failed**. Clean: direct INT8 − prior-aware fit, paired 95 % interval [−0.036, +0.343] µT (no significant difference). Realistic anchor: the direct estimator is 2.6× worse than the constant. PID produces out-of-training-range estimates on 251 of 256 realistic rows (median 865 µT), which is why every residual estimator collapses there. Every number above was recomputed by the orchestrating session from the saved per-row predictions (`results-final/*_predictions.npz`; `orchestrator_recompute_2026-10-14.txt`) and matches the experiment's summary exactly; the experiment's own checker (`independent-verification/`) recomputed 1,326 comparisons with zero discrepancies.

## Why (dev partition only, n = 16; diagnostic, not a deployment gain)

`mechanism-diagnostic/REPORT.md`: on the realistic cell the direct FP32 estimator's error is 37.8 µT; giving it a clean oracle lock bin alone leaves 55.0 µT; subtracting the known background slope and recomputing the lock brings it to 14.8 µT; both together 14.9 µT. The background slope, not the anchor, is the main cause. A four-minute dev-only pilot of a slope estimate from fixed outer bins is reported separately when complete.

## What follows

Nothing from the narrow-line training recipe survives realistic conditions, and the classical prior-aware fit does not either (≈ 25 µT under stress). The next step is background handling in preprocessing (and realistic line widths and noise in the training data), tested on a new sealed set — not more training on the existing recipe. Jason decides on compute. This final partition is consumed. Nothing deployed changed; the kit's clamp and slew limit still bound any correction; no hardware or sensor measurement is involved.

Files: protocol, generator, evaluator and the prior-aware estimator with its tests under `experiments/scalar_stress_test/`; summaries, per-cell metrics and predictions, receipts, data manifests, the independent verification, the mechanism diagnostic, the calibration-repair report and this session's recomputation under `scalar_stress_test_2026-10/`.
