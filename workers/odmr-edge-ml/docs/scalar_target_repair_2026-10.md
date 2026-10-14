# Scalar training-target repair: synthetic results

Date: 2026-10-14.

The predeclared full-residual success criterion passed.
The secondary direct-regression criterion passed.

All models were frozen before model evaluation on the fresh 5,000-row synthetic holdout.
The coordinator exposed the holdout PID baseline and label summary before the freeze. No model scores were exposed.
The original 5,000-row test results are exploratory because that split was already used.

## Total-field mean absolute error

Lower is better. New model rows average the same three fixed training seeds.

| Estimator | Fresh holdout, µT | Original seen test, µT |
|---|---:|---:|
| PID | 22.823007 | 23.535723 |
| training_mean | 12.720257 | 12.333963 |
| training_median | 12.722898 | 12.337598 |
| Deployed INT8, runtime clamp | 21.700023 | 22.381699 |
| Deployed FP32, runtime clamp | 21.685164 | 22.366060 |
| A: clipped targets, FP32 | 21.390886 | 22.098536 |
| A: clipped targets, INT8 CPU | 21.400530 | 22.108928 |
| B: full residual targets, FP32 | 11.131636 | 10.772290 |
| B: full residual targets, INT8 CPU | 13.544071 | 13.854673 |
| C: direct magnitude, FP32 | 10.870284 | 10.555598 |
| C: direct magnitude, INT8 CPU | 10.898340 | 10.559478 |

## Paired differences on the fresh holdout

Negative values favor the first named model. Intervals resample rows, not training seeds or real sensors.

| Comparison | Mean difference, µT | Paired 95% interval, µT |
|---|---:|---:|
| B_minus_A | -10.259250 | [-10.711155, -9.800719] |
| B_minus_training_mean | -1.588621 | [-1.766299, -1.409459] |
| C_minus_B | -0.261353 | [-0.317679, -0.204988] |
| C_minus_training_mean | -1.849974 | [-2.031900, -1.668891] |

## What retaining the runtime limit does

These rows apply PID + clip(predicted field - PID, +/-2.25 µT).
For C, this is a hypothetical bounded correction derived from its direct estimate.

| Arm | FP32 bounded-correction MAE, µT | INT8 bounded-correction MAE, µT |
|---|---:|---:|
| A_clipped | 21.438793 | 21.444098 |
| B_full_residual | 21.212254 | 21.213038 |
| C_direct | 21.202462 | 21.205997 |

## Checkpoints, seed variation, and conversion

The matched control shares the new training settings; it is not an exact historical replay.
Every fit used 100 epochs, the same batches per seed, canonical QAT, and FP32 arithmetic.
Checkpoint selection used only original validation total-field MAE.
Every saved clean checkpoint reproduced its validation predictions exactly after reload.

| Model | Selected epoch | Validation MAE, µT | Fresh FP32 MAE, µT | Fresh INT8 MAE, µT | Keras/Torch max gap, µT |
|---|---:|---:|---:|---:|---:|
| A_clipped_seed42 | 30 | 22.218417 | 21.377929 | 21.393501 | 0.000002325 |
| B_full_residual_seed42 | 80 | 10.796919 | 11.159676 | 13.605371 | 0.000028610 |
| C_direct_seed42 | 90 | 10.451616 | 10.799190 | 10.859702 | 0.000041962 |
| A_clipped_seed20261014 | 20 | 22.223565 | 21.388056 | 21.387718 | 0.000002325 |
| B_full_residual_seed20261014 | 90 | 10.777381 | 11.070088 | 13.434084 | 0.000025749 |
| C_direct_seed20261014 | 100 | 10.448903 | 10.804913 | 10.805597 | 0.000038147 |
| A_clipped_seed20261015 | 30 | 22.240190 | 21.406673 | 21.420372 | 0.000002652 |
| B_full_residual_seed20261015 | 100 | 10.841362 | 11.165144 | 13.592758 | 0.000028610 |
| C_direct_seed20261015 | 80 | 10.524042 | 11.006748 | 11.029721 | 0.000041962 |

## INT8 output encoding

Endpoint occupancy is a saturation indicator; it does not prove that every endpoint value was clipped.

| Model | Output step, µT | Representable output range, µT | Endpoint occupancy on fresh holdout |
|---|---:|---:|---:|
| A_clipped_seed42__int8 | 0.021262 | [-2.551, 2.870] | 0.040% |
| B_full_residual_seed42__int8 | 0.201592 | [-18.748, 32.658] | 20.940% |
| C_direct_seed42__int8 | 0.263537 | [0.000, 67.202] | 0.580% |
| A_clipped_seed20261014__int8 | 0.023119 | [-2.867, 3.029] | 0.080% |
| B_full_residual_seed20261014__int8 | 0.209902 | [-19.521, 34.004] | 19.140% |
| C_direct_seed20261014__int8 | 0.260415 | [0.000, 66.406] | 0.700% |
| A_clipped_seed20261015__int8 | 0.020377 | [-2.425, 2.771] | 0.060% |
| B_full_residual_seed20261015__int8 | 0.198411 | [-19.048, 31.547] | 22.700% |
| C_direct_seed20261015__int8 | 0.268232 | [0.000, 68.399] | 0.920% |
| deployed__int8 | 0.022875 | [-2.951, 2.882] | 0.100% |

## Limits and handoff

- Results use the existing simulator and distribution. They do not establish real-sensor accuracy.
- The new estimates use broad output ranges. The current controller still has its original limit.
- No deployed checkpoint, INT8 artifact, controller setting, or kit image changed.
- INT8 inference was tested on CPU. No new VectorBlox compile or hardware run occurred.
- Training seed 20261015 and the holdout master seed share a number, but use separate RNG streams.
- Fresh sample seeds have zero overlap with all original train, validation, and test sample seeds.
- Training wall time: 29.39 minutes.
- Conversion and evaluation time: 0.12 minutes.
- Independent saved-prediction recomputation checked 466 numeric values and both file hashes.
- Integration and public release belong to the coordinating session.

## Addendum (2026-10-14, post-hoc arithmetic on saved predictions; no new inference)

**Why B's INT8 export loses accuracy.** Clipping each seed's FP32 corrections to that export's INT8-representable interval reproduces 98.94–99.84 % of its fresh-holdout MAE increase (`scalar_target_repair_2026-10/quantization-diagnosis.json`, reproducible with `experiments/scalar_target_repair/diagnose_quantization.py`): the loss is output-range clipping, not the quantization step. About 15 % of holdout rows fall below the lower representable bound and 3–7 % above the upper one (the orchestrating session's independent recount: lower-endpoint occupancy 0.153–0.159, upper 0.038–0.068; `orchestrator_recompute_2026-10-14.txt`). The direct-magnitude arm's export keeps its range (10.90 µT INT8 against 10.87 FP32). Why the first-1,000-row calibration misses B's range is being checked on train/val data only; the study and its results stay frozen.

**Integration note.** Nothing deployed changed. On the kit, any correction passes the fabric sector clamp (outer bound 0.045 × range 2 × 64 = 5.76 µT-equivalent on the feedforward command, inner may bind tighter) and the slew limit, so a broad-range estimator is usable on hardware only as a bounded command or a reported estimate, and no cumulative field-correction claim follows without a plant model (`scalar_target_repair_integration_contract_2026-10.md`).

## Post-hoc diagnostic addendum (train/validation data only; separate from the frozen primary results)

**Why the INT8 calibration missed B's range.** The export calibrates on the first 1,000 training rows. For `B_full_residual_seed42` those rows produce corrections of −18.743 to +32.663 µT, and the TFLite output interval is −18.748 to +32.658 µT; the full training set spans −55.661 to +62.649 µT and validation −55.246 to +59.142 µT, so the actual INT8 bounds exclude 9,035 of 40,000 training outputs and 1,068 of 5,000 validation outputs. The calibration prefix's lock-bin counts are 50 / 950 / 0 for bins 50 / 51 / 52, while the full training set has 8,575 bin-52 rows: the stored first-1,000 prefix does not cover the input distribution. This diagnoses the cause; it does not measure a broader-calibration repair (none was run). No test or holdout access, no new conversion, no tuning (`scalar_target_repair_2026-10/calibration-diagnostic/diagnosis.md`, `.json`).
