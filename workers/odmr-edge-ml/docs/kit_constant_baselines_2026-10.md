# Constant baselines on the exact 512-row kit cohort

Date: 2026-10-14. These are exploratory checks with two fixed training-only rules.
Neither constant was selected or tuned using test labels.

**Both training constants have lower errors than the deployed FCNN and PID on the same 512 rows.**
This result concerns the selected kit cohort, not the complete 5,000-row test split.

| Predictor | MAE, µT | RMSE, µT | p90 absolute error, µT | Worst absolute error, µT |
| --- | ---: | ---: | ---: | ---: |
| Training mean: 45.064080129 µT | **12.559596326** | **14.613327928** | 22.930835601 | 25.051483358 |
| Training median: 44.904043610 µT | 12.561772465 | 14.613470320 | **22.902958402** | **25.015370957** |
| Deployed FCNN INT8 final field | 14.474248644 | 17.456952560 | 29.055859952 | 49.583338877 |
| PID proxy | 15.208567604 | 18.357447634 | 30.516876803 | 51.833338877 |

The constants were independently reproduced from all 40,000 training field vectors.
The kit manifest specifies test rows 0–511, in order. Its two index lists match exactly.
Every selected saved truth, PID, and residual label matches the original PID dataset row.
Every truth magnitude also matches the original HDF5 field vector.
Independent preprocessing reproduces the previously verified 512-row input payload hash.
The saved hardware output bytes and manifest retain their previous verified hashes.

FCNN final predictions were reconstructed as `B_PID + clip(dequantized_output, -2.25, +2.25)`.
Recomputed FCNN MAE is exactly **14.474248643587522 µT**.
Recomputed PID MAE is **15.208567604032694 µT**, matching the previous verification.
No hardware, model inference, training, or repository changes occurred. Computation used 0.041 CPU seconds.

The constants predict the complete field magnitude. The deployed network supplies a bounded correction to PID.
Thus, this exposes a limitation of the complete deployed estimator on this cohort.
It does not isolate whether the network, the PID input, or the correction constraint causes that limitation.
Saved deployment parity remains valid; parity alone does not establish useful predictive accuracy.

The same 512 rows give a **13.044395457 µT** clairvoyant lower bound for any PID correction limited to ±2.25 µT.
It equals `mean(max(abs(B_PID - B_true) - 2.25, 0))`; it is not an implemented estimator.
Both training constants beat even that bounded-correction oracle on this cohort.
Therefore, merely improving the residual model within the fixed clamp cannot match these constant baselines in MAE here.

## Provenance

- Dataset: `<data-root>/production_50k_v2_aic`.
- Saved kit evaluation: `.scratch/kit-run-2026-10-14`.
- Dataset HDF5 SHA256: `92dd4a53f66920676a076232644860501216f5b59503557900ad02dd7d90ef4b`.
- Selected labels NPZ SHA256: `544194b51d1e1875935f079f8ec280e10fe5e715a192b2cd1d903b6bb062d765`.
- Selected truth float64 payload SHA256: `65e4ed88d7e07b713e94f2ca4f022a14bcb9ab510b9f417d32d6328824444405`.
- Selection manifest SHA256: `1c67f097b6a85e4732ee1a4df4b45862189c5a133a12bf3b49b2c991eac9a52e`.
- Training magnitude float64 payload SHA256: `62b224874937c4eb1439d80e4bc97644fdcc672cf37ff67c2b02c45c5560511e`.
- Quantized input NHWC payload SHA256: `51e97e715e7845fa32fe59f45e340f6d3d608568a22b32adbee19e117ba37f33`.
- Kit raw output SHA256: `080474358d3a1efeacc89cc946821e7e8446db266f84fa433cdbc0598748ec90`.

[Machine-readable metrics, checks, and exact selection](kit-constant-baselines.json).
Prior evidence: `outputs/kit-artifact-verification/{REPORT.md,results.json,dataset-results.json}`.
