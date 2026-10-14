# Frozen-model calibration repair

Completed UTC: 2026-10-14T22:24:01.777251+00:00

Original validation selected these checkpoints. This diagnostic is not fresh generalization evidence.

The fixed rule selects 1000 training rows at evenly spaced stable output ranks, including both extremes.
All three floating Keras mappings passed equivalence before export. All exports preceded validation access.

## Validation full field metrics

| Seed | Representation | MAE (uT) | RMSE (uT) | p90 absolute (uT) |
|---|---|---:|---:|---:|
| 42 | float | 10.796919 | 13.003513 | 20.799531 |
| 42 | prefix_int8 | 13.879653 | 17.678082 | 28.973109 |
| 42 | rank_int8 | 10.809719 | 12.998667 | 20.711672 |
| 20261014 | float | 10.777380 | 13.059080 | 20.958304 |
| 20261014 | prefix_int8 | 13.708878 | 17.462519 | 28.619250 |
| 20261014 | rank_int8 | 10.793678 | 13.015105 | 20.753461 |
| 20261015 | float | 10.841362 | 13.137372 | 21.257130 |
| 20261015 | prefix_int8 | 13.911061 | 17.746535 | 29.507234 |
| 20261015 | rank_int8 | 10.866374 | 13.167326 | 21.366760 |

Mean of seed metrics: {"float": {"mae_uT": 10.805220418246849, "rmse_uT": 13.066655122886045, "p90_abs_uT": 21.004988292937778}, "prefix_int8": {"mae_uT": 13.833197497996858, "rmse_uT": 17.629045286789275, "p90_abs_uT": 29.033197619559186, "mean_quantization_gap_mae_uT": 5.823748936068391, "mean_endpoint_fraction": 0.21573333333333333}, "rank_int8": {"mae_uT": 10.823257085395163, "rmse_uT": 13.060366069747628, "p90_abs_uT": 20.94396440148353, "mean_quantization_gap_mae_uT": 0.5091901524607092, "mean_endpoint_fraction": 0.0003333333333333333}}

## Quantization diagnostics

| Seed | Calibration | Output range (uT) | Quantization MAE (uT) | Endpoint rows | Float outside range |
|---|---|---|---:|---:|---:|
| 42 | prefix_int8 | -18.748072 to 32.657933 | 5.895261 | 21.200% | 21.360% |
| 42 | rank_int8 | -55.675560 to 62.635005 | 0.508633 | 0.000% | 0.000% |
| 20261014 | prefix_int8 | -19.520874 to 34.004103 | 5.785716 | 21.120% | 20.720% |
| 20261014 | rank_int8 | -57.268970 to 53.364267 | 0.568737 | 0.020% | 0.000% |
| 20261015 | prefix_int8 | -19.047503 to 31.547428 | 5.790270 | 22.400% | 21.580% |
| 20261015 | rank_int8 | -56.587936 to 62.667631 | 0.450200 | 0.080% | 0.000% |

## Limits

- Original validation selected the checkpoints; this is not fresh generalization evidence.
- The calibration rule was chosen after a prior training/validation coverage diagnosis.
- Training-output coverage does not guarantee future activation or output coverage.
- Endpoint occupancy alone does not prove clipping; float outside-range counts are separate.
- No retraining, hardware validation, original-test access, or fresh-holdout access.

## Reproduction

The output directory must not exist. This creates one new export per frozen model.

```sh
<path> <calibration-dir>/run_calibration_repair.py --out <calibration-dir>/reproduction-run
```

Protocol SHA256: f420deb9ed60b3c99640c80f9dfd973a579185b2eb583f861b3e94c4610f834b

Detailed values, array hashes, source hashes, and artifact hashes are in results.json.
training_selections.npz contains the selected rows and training float outputs. validation_predictions.npz contains every scored row.
