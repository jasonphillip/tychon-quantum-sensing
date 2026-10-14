# Supplementary scalar constant baselines

Measured: 2026-10-14. Exploratory analysis after Task 6.

A constant prediction from training labels beats the deployed residual FCNN on production total-magnitude MAE.
This exposes a larger limitation than the comparison against PID alone.
The independent benchmark MLP does beat its corresponding constant baseline.

| Cohort | Training mean | Training median | Neural model | Two-line fit | PID |
|---|---:|---:|---:|---:|---:|
| Benchmark test, 200 spectra | 12.262343 | 12.277713 | 10.530261 | 21.452206 | 25.931017 |
| Production test, 5,000 spectra | 12.333963 | 12.337598 | 22.381699 | 22.864476 | 23.535723 |

All entries are MAE in µT. The neural columns use different models on their compatible grids.
The benchmark neural model is the retrained MLP. The production model is the deployed INT8 residual FCNN.

Both constant rules were fixed before this supplementary scoring.
Their values use only training labels: 1,000 benchmark rows or 40,000 production rows.
No test-based choice, parameter tuning, or additional neural training occurred.
Training mean predictions are 45.421948 µT for benchmark and 45.064080 µT for production.
Both mean and median results are retained.

For any estimator constrained to B_PID + δ with |δ| ≤ 2.25 µT, each row has this error lower bound:

    minimum absolute error = max(|B_PID - B_true| - 2.25 µT, 0)

Averaging that bound gives **21.334551 µT** on production.
Thus, no residual predictor under the current clamp can beat the **12.333963 µT** constant-mean MAE on this split.
That conclusion follows from the output constraint, independent of model capacity.
This oracle uses truth to compute a bound. It is not a deployable estimator.

These results do not evaluate tracking, responses to field changes, or performance outside the sampled field distribution.
A constant estimate ignores the spectrum and cannot follow changing fields.
It is a basic aggregate accuracy check, not a proposed replacement controller.

The existing claim of incremental improvement over PID remains supported.
A stronger claim of useful total-field magnitude estimation needs a stronger baseline and target justification.
The scalar fit's orientation limitation and the neural residual clamp both matter.
No vector validation or final comparison data was read.

Provenance and all constant metrics are in `constant-baselines.json`.
The fixed analysis script is retained at the main session's handoff location.
The raw prediction artifacts also passed an independent check of all 36 Task 6 metrics and fallback accounting.

Suggested public qualification:

> On the synthetic production split, the residual FCNN improves MAE over PID, but does not beat a training-mean constant predictor. Its ±2.25 µT output constraint prevents it from closing that aggregate total-field accuracy gap on this split.
