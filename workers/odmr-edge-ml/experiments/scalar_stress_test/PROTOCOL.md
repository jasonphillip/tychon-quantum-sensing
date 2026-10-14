# Scalar stress test: protocol fixed before new data scoring

Date: 2026-10-14. Scope: software-only, single-NV-orientation synthetic spectra.

## Question and fixed candidates

Does the frozen direct field-magnitude estimator retain its advantage under broader lines, shot noise, baseline slope, and instrument offset?

Use all three previously frozen C_direct seeds (42, 20261014, 20261015), FP32 and existing INT8 exports. Also report the three B_full_residual FP32 models and their independently fixed rank-calibrated INT8 exports from scalar-calibration-repair. Average errors across seeds; do not average predictions or select a seed. No retraining or model selection occurs in this study.

Baselines are the original training mean (45.064080128749545 µT), median (44.90404360960018 µT), unchanged PID proxy, existing two-line fit, and prior-aware versions of PID and that fit. The prior-aware estimate is sqrt(70 * max(20, clip(abs(projection), 0, 70))) µT. It is the conditional median under an isotropic direction and uniform magnitude on [20,70] µT, conditional on an exactly observed axial projection. A noisy fitted projection does not satisfy that ideal observation assumption; report this limitation. Support violations are counted. Failed fits use the fixed training mean and remain in every metric. Report fit failure fraction. No row truth enters a baseline.

The production recipe is single orientation. A four-axis/eight-line S2b comparator is not applicable. Do not describe its two-line spectra as an ensemble of four orientations. A correct four-axis comparison would require a separate data and model study.

## Data

Retain 100 frequencies from 2.82 to 2.92 GHz, spherical directions, magnitude uniform on [20,70] µT, no nitrogen, no optics, and the production stochastic OU/B1 recipe. Replace P1 concentration by a fixed value solving the source compute_linewidth law for each specified intrinsic FWHM. Spatial and temporal microwave power broadening remain active. Save the resulting rendered-width ranges. Use the archived test B1-gradient range; retain the archived OU parameters. Do not add a four-orientation renderer.

| Cell | Intrinsic FWHM MHz | Contrast | Reference SNR | End-to-end slope | Frequency offset MHz |
|---|---:|---:|---:|---:|---:|
| clean | 1.5 | 0.030 | infinity | 0 | 0 |
| realistic_anchor | 5 | 0.015 | 10 | 0.02 | 0.3 |
| wide_lines | 7 | 0.015 | 10 | 0.02 | 0.3 |
| low_snr | 5 | 0.015 | 3 | 0.02 | 0.3 |
| negative_slope | 5 | 0.015 | 10 | -0.02 | 0.3 |
| negative_offset | 5 | 0.015 | 10 | 0.02 | -0.3 |
| higher_contrast | 5 | 0.030 | 10 | 0.02 | 0.3 |

Apply contrast scaling per spectrum to its deepest noiseless dip, then frequency interpolation with endpoint fill, then linear slope, then fixed-seed Gaussian photon shot noise using the source function. The nominal SNR reference depth is 0.30 times contrast; this is a declared convention, not a measured faintest-line depth. These factor values come from the vector study, but the scalar cohort and SNR reference are separate. Never pool the studies.

Partitions: dev 16 rows/cell, validation 128 rows/cell, final 256 rows/cell. Master seeds: 202610140, 202610141, 202610142 respectively. Within a partition, cells share field vectors, nuisance trajectories and noise draws. Across partitions, sample seeds are disjoint. Exclude original train/val/test sample seeds from archived metadata and prior scalar holdout sample seeds from saved-prediction metadata only. Never reopen the consumed holdout spectra or score a model on it.

Generate and hash new data; final files and directory have no write bits. Save source revisions, parameters, and hashes. A metadata-only sealing worker must not report model scores, label summaries, or baseline scores. No final read occurs before the candidate manifest, comparator implementation, evaluator, and this protocol are hashed and sent to the coordinator.

## Access and scoring

Dev permits implementation checks. New validation permits one fixed-candidate check of interface/finite-output behavior; no threshold, fit, model or calibration tuning. Final is read once in one campaign after the freeze. An exclusive receipt is created before opening final data. Existing output/receipt refuses another campaign. If correctness fails, disclose the failure and retire any accessed final set; do not silently reuse it.

Per cell report full-magnitude MAE, RMSE, median absolute error, p90 absolute error, signed bias, fit failure/support-violation counts, INT8 endpoint occupancy, FP32/INT8 disagreement, and measured CPU inference time. Preserve all predictions. Report per-seed model metrics and mean seed errors separately. Compute paired row-bootstrap 95% intervals (10,000 draws, seed 202610143) for C_INT8 minus mean, C_INT8 minus prior-aware fit, C_INT8 minus prior-aware PID, and C_INT8 minus repaired B_INT8. Intervals are conditional on the fixed nuisance trajectories; they do not cover simulator uncertainty or nuisance-path variation.

Primary cells are clean and realistic_anchor. Evidence that the original gain survives these tests requires lower C_INT8 MAE than both the training mean and prior-aware fit, with upper paired interval below zero, in both primary cells. Otherwise report that this criterion was not met and name the failing cells. Secondary cells diagnose sensitivity and cannot rescue a failed primary criterion. No state-of-the-art, experimental sensor, controller stability, or hardware performance claim follows.

The old runtime correction limit is not applied to a reported field estimate. No controller setting, deployed artifact, or hardware image changes.

## Budget and portability

At most 60 minutes for this bounded parallel lane, local compute only. No paid calls, hardware runs, or training. Data generation stops after 20 minutes cumulative wall time. All paths are command-line arguments; Python scripts run where the existing scientific environment is installed. Execute on Spark2; save reports on the Mac. Coordinator owns source integration and publication.
