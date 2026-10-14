# Scalar fit versus neural estimators

Measured: 2026-10-14. Scope: synthetic scalar tests only.

The benchmark MLP has lower MAE than this two-Lorentzian estimator on its 200-spectrum test set.
The deployed INT8 FCNN also has lower MAE on the separate 5,000-spectrum production test split.
These are descriptive results for fixed recipes, not a state-of-the-art verdict.

## Estimator and physical limit

`fit_field_magnitude(spectrum, freqs_hz)` returns splitting / (2γ), in µT, and the raw-signal RMS fit residual.
The fit uses two Lorentzian dips, a common width, and an affine baseline.
It initializes from the two deepest local minima.
A single detected minimum triggers a symmetric initialization around that minimum.
The bounded solver allows 200 evaluations. Configuration was fixed before scoring either complete cohort.

The scalar split formula measures an axial projection at low field.
It does not generally recover total field magnitude for arbitrary field orientation.
An independent spin-1 eigenvalue test gives approximately 25 µT for a 50 µT field at 60°.
The benchmark uses spherical field directions and total-magnitude labels.
Its simulator also includes multiple NV orientations and varying nuisance parameters.
Therefore, the original “50 noise-free bench spectra, MAE <1 µT” acceptance criterion is not physically justified.

The replacement unit test measures 50 explicitly valid two-Lorentzian spectra.
It passes MAE <1 µT. A separate noisy fixture measured MAE 0.037090 µT.
These fixtures validate implementation behavior; they do not establish benchmark accuracy.

Task 6 specifies γ = 2.8035e10 Hz/T for this fit.
The unchanged published PID uses 2.8024e10 Hz/T.
No rationale for this specification difference was located.

## Benchmark test: 200 spectra

Frequency grid: 100 points, 2.866–2.874 GHz.
Generator recipe: seed 12345; 1,000 training, 200 validation, and 200 test spectra.
The simulator's `deterministic` mode does not mean an ideal noise-free two-line signal.
The benchmark MLP uses hidden layers [64, 64], seed 20261009, Adam at 0.01, and 1,000 full-batch epochs.
It uses the final epoch, without checkpoint selection using test results.
Training took 2.806 seconds on one CPU core.

| Estimator | N | MAE (µT) | RMSE (µT) | p90 error (µT) | Worst (µT) | Median (µs) | p90 (µs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Two-Lorentzian fit + PID fallback | 200 | 21.452 | 26.166 | 43.356 | 63.201 | 4028.851 | 24948.642 |
| Published PID proxy | 200 | 25.931 | 30.927 | 48.997 | 64.842 | 16.768 | 31.683 |
| Benchmark MLP | 200 | 10.530 | 12.729 | 21.247 | 31.341 | 244.707 | 254.363 |
| Deployed INT8 FCNN | N/A | — | — | — | — | — | — |

The fit failed on 13/200 spectra (6.5%).
Those rows use the unchanged PID proxy. The table includes their errors and fallback latency.
The deployed FCNN expects a different frequency grid and is not evaluated on this cohort.

The MLP reproduces the published benchmark MAE of 10.530261 µT within 0.000001 µT.
This reproduction uses per-row inference and higher-precision scoring.

## Production test: 5,000 spectra

Frequency grid: 100 points, 2.82–2.92 GHz.
The existing production test split was evaluated without retraining the deployed FCNN.
The script verifies test-content MD5 before scoring.

| Estimator | N | MAE (µT) | RMSE (µT) | p90 error (µT) | Worst (µT) | Median (µs) | p90 (µs) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Two-Lorentzian fit + PID fallback | 5000 | 22.864 | 27.667 | 45.823 | 69.802 | 2705.274 | 3765.413 |
| Published PID proxy | 5000 | 23.536 | 28.897 | 48.489 | 70.035 | 16.241 | 19.376 |
| Benchmark MLP | N/A | — | — | — | — | — | — |
| Deployed INT8 FCNN | 5000 | 22.382 | 27.658 | 46.817 | 68.091 | 54.033 | 76.611 |

The fit failed on 121/5,000 spectra (2.42%).
Those rows use the PID fallback and remain in every metric.
The FCNN output is B_PID + clip(ΔB, ±2.25 µT).
Fresh PID predictions and anchor bins matched the saved production inputs.
The benchmark MLP expects a different frequency grid and is not evaluated on this cohort.

## Timing and acceptance

All latency samples use one thread on CPU 2, an ARM Cortex-A725 core, with a 2.808 GHz maximum frequency.
Other independent development jobs ran on separate cores. Shared resources were not isolated.
One prediction warms up each path before measurement.
Fit latency includes input validation, initialization, fitting, and any fallback.
MLP latency includes normalization and inference.
FCNN latency includes PID, preprocessing, quantization, invocation, dequantization, and clamp.

The fit meets a 5 ms median requirement on both cohorts.
It does not meet 5 ms at p90 on the benchmark: 24.949 ms.
The original “latency <5 ms” requirement did not name a percentile, so it cannot receive an unconditional pass.

## Scope and provenance

No spectra were dropped after failed fitting.
Failure indices, metrics, and artifact hashes are in the companion JSON.
These scalar test splits are separate from the sealed vector comparison.
No vector validation or final comparison data was read.

- Scalar repository base: `3d1a4f6c32cd1f52cf10be80116f752256962499`.
- Benchmark source: `92bacb92ea4b9a102223fb4dcba3a4b07bf9ccb4`.
- Simulator source: `9df6dd161719b369e90c0e284cbef0bae39a0612`, clean at evaluation.
- Benchmark normalized-data SHA-256: `4c204a8d4afb437e101a738825a4b9742185ce560f85fe04d354f78be41ae270`.
- Production test-content MD5: `b350320066a4c6a4553f05cd1f469704`.
- TFLite SHA-256: `e3b55da96ee633a58109007d4244304e2ad4a22853b10335fa41879e815b5371`.
- Runtime: Python 3.13.11, NumPy 2.4.2, SciPy 1.17.1, PyTorch 2.11.0.
- TFLite runs in a separate existing TensorFlow environment; interpreter threading is set to one.
- Full scalar repository suite: 212 passed, 16 skipped, 32 existing deprecation warnings, 5.16 seconds.
- New scalar tests: 9 passed. The initial test run failed because the implementation was absent.

## Reproduce

Set these variables to absolute local paths: `SCALAR_REPO`, `NV_SIM_REPO`, `PRODUCTION_DATA`, `RESULT_WORK`, `PYTHON_BIN`, and `TF_PYTHON`.
The TensorFlow environment must also contain the scalar package's runtime dependencies.
The script contains no host-specific paths. The evaluation ran on Linux; macOS execution remains unverified.
The recorded CPU affinity requires Linux; omit `--cpu 2` on macOS.

```sh
env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$SCALAR_REPO/src:$NV_SIM_REPO/src" \
  "$PYTHON_BIN" "$SCALAR_REPO/experiments/scalar_fit_baseline.py" \
  --dataset "$PRODUCTION_DATA" --work-dir "$RESULT_WORK" \
  --out "$SCALAR_REPO/docs/scalar_fit_vs_network_2026-10.json" \
  --tf-python "$TF_PYTHON" --cpu 2
```

Use a fresh work directory or the same verified benchmark recipe cache.
To check runtime before scoring, add `--pilot 25`.
The recorded command completed successfully on the development host.
