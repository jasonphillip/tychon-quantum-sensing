# Additive classical optimization and fresh-population protocol

Date: 2026-10-15 (America/New_York).
Status: DRAFT_ROOT_REVIEW_NOT_AUTHORIZED. No numerical stage is authorized by this file.

## Scope and known limits

The concrete computational task is offline reconstruction of spatial vector-field maps from many independent eight-line ODMR spectra.
A later use could be current-distribution imaging with known sensor orientation and calibrated bias.
We have no measured instrument workload, required map feature size, current amplitude, or allowable field error for that use.
Therefore practical absolute accuracy, failure, and service-time requirements remain UNRESOLVED.
No practical adoption claim may pass while these requirements remain unresolved.
A prospectively frozen accuracy/throughput Pareto comparison may still report useful simulation evidence.

This is an ideal spin-1, equal-strength Lorentzian simulation with known axes and bias.
It is not measured widefield imaging or a complete NV optical model.
Generic neural spectral inversion and neural acceleration already have prior art.
The proposed contribution is an inspectable accuracy/cost comparison with strong same-device classical shortcuts, observable rejection, and honest total costs.
Neither novelty nor useful neural advantage is established.

Root's independent post-hoc saved-profile check found affine mean error about 6.031 microtesla and maximum 15.311 microtesla on five repeated cases.
These fixtures had 100% observed acceptance and no fallback.
Peaks reached about 2.989 microtesla maximum; nominal calibration reached about 19.261 microtesla maximum.
Full LM float64 reached approximately 6.2e-11 microtesla maximum on those cases.
These are manufactured diagnostics, not new population gates. Original evidence stays unchanged.

The frozen Poisson scaling is internally consistent on source inspection:
counts equal exposure times fluorescence; the deviance is twice the log-likelihood ratio; residual degrees of freedom are 512−8.
The present goodness-of-fit guard does not bound parameter error. No scaling bug was identified by this source inspection.
This is not an empirical noise-law or calibration validation.

## Stage C0: exact chunk-only qualification

Frozen dependency: vector_direct_screen at f5032fa3461aba2d2395bd1313c25fd9a8f98220.
Its 10 source/config/protocol files and previous receipts must remain byte-identical.
The additive adapter imports Engine, initialize, observed_check, and full_fallback unchanged.
Its private policy body differs only in the outer loop's chunk expression.
It never mutates CFG. A structural AST fixture checks this exact restriction.
Changing chunk size also changes which rows share the original all-converged stopping check.
That existing solver behavior is retained, and output agreement must be qualified rather than assumed.

First run the 10 prepared manufactured contract tests under a separate root-approved CPU fixtures reservation.
Proposed fixture ceiling:15 CPU seconds,15 wall seconds,2 GiB,one numerical CPU thread,zero GPU.
These tests check source identity, dispatch, row order, mixed fallback masks across boundaries, input validation, and additive source guards.
No test has run during preparation.

Then freeze the 15 conditions in matrix.json before any GPU execution:
- Batch 4096 only; Spark 3 only; sequential jobs, one numerical CPU thread.
- Methods/precision: affine float32, affine float64, peaks float64, calibrated float64, full LM float64.
- Exactly three chunks per condition:256,1024,4096. No fourth alternative.
- Each job:20 CPU,20 wall,20 GPU seconds maximum;16 GiB process RSS plus 16 GiB PyTorch allocator policy.
- Total GPU timing reservations:300 CPU,300 wall,300 GPU seconds. No reserve reset or retry.

The earlier float32 iterative cap outcomes remain preserved. This finite matrix uses the qualified float64 iterative comparator.
It does not claim float32 iterative methods can never work.
Before release, root must verify the complete remaining eligibility reservation fits the shared ledger.
A CPU/wall cap is a censored timing, not completed throughput. Preserve partial files and exact receipts.
Stop the matrix on any scientific mismatch, source drift, accounting uncertainty, or malformed output.
The runtime's allocator/RSS restrictions and CUDA-context limitations remain in force.

Every job first compares the additive and frozen policies on the same five manufactured expected-count cases.
Accepted and fallback flags must match exactly.
Maximum absolute normalized-parameter and reduced-deviance differences must be at most 1e-8 for float64 or 1e-3 for float32.
Parameter normalization uses the frozen CFG scales. These are roundoff-only implementation checks, not practical accuracy thresholds.
Any miss requires a new source decision; never loosen the tolerance after outputs.

Timing uses one separately disclosed warm-up, then three resident and host-to-host repetitions.
The resident engine caches the same nominal calibration for every method and chunk.
Each host-to-host call creates a fresh engine and calibration for every method and chunk.
Both paths include the same likelihood check and all actual fallback work.
Process startup, file serialization, and photon acquisition are reported separately, outside these measurements.
Save all timing arrays, exact predictions/counts/parameters, accepted/fallback flags, and reduced deviance.
The original solver does not expose per-row convergence through this policy interface; do not invent that field.
Noisy-population usefulness cannot be inferred from this repeated-case timing study.

## Stage P0: prospective population freeze and custody

This section is a draft for later source implementation and root approval. The current package cannot generate a population.
Root/custodian issues new independent parameter/noise seed commitments for qualification, development-design, development-validation, and confirmation.
No old scalar, vector, hybrid, sparse, or measured-data seed or sample may be used.
The confirmation seed remains sealed. Do not generate its data before the development gate.
Save the generator/version/source hashes, split manifests, latent IDs, noise-replicate IDs, units, parameter labels, and exposure.
Group all noise replicates of one latent spectrum together. No latent ID crosses a split.
Hash exact parameter rows to check cross-split duplicates before releasing data.
Seed contents stay private until their data split is consumed and the publication policy permits release.

All observations use independent Poisson counts with expectation 2000000×the unchanged fluorescence model in each of 512 bins.
Do not use Gaussian-SNR substitution, normalize using hidden labels, or rescale exposure without a new source/noise qualification.
Keep bias[1600,900,300]microtesla, known axes, frequency 2805–2935 MHz, equal line strengths, and all frozen parameter bounds.
Counts do not contain temporal/spatial correlations; no claim about such robustness follows.

Define fresh independent uniform latent draws within these prospective regimes:
A, core: each residual field[-10,10]microtesla; D[2869.9,2870.1]MHz; width[1.75,2.25]MHz; contrast[.04,.08]; baseline[.99,1.01]; slope[-.005,.005].
B, full registered range: use every frozen lower/upper bound independently.
C, weak/broad shift: full bounds except width[2.5,3]MHz and contrast[.02,.04].
D, strong/narrow shift: full bounds except width[1,1.5]MHz and contrast[.10,.12].
C and D signal values remain absent from development. Their distributions are declared now.
Do not remove inconvenient draws or sessions after observing method errors.

Proposed finite populations, subject to a later immutable source/seed freeze:
- Qualification:32 latent rows from A and 32 from B, two independent noise replicates each:128 spectra.
- Development-design:256 latent rows from A and 256 from B, four replicas each:2048 spectra.
- Development-validation:256 different latent rows from A and 256 from B, four replicas each:2048 spectra.
- One confirmation:128 new latent rows from each of A/B/C/D, four replicas each:2048 spectra.
The total is 6272 spectra, excluding any later separately authorized model training set.
No candidate may select settings from development-validation after it is consumed.
Use exactly one selection from development-design, then one validation and one confirmation.

Qualification validates source/noise correctness and saved-output reconstruction. It does not select a winner.
A full-rank whitened spectral Jacobian is necessary for local identifiability, but does not prove global identifiability.
Report its singular values, scaled condition number, and local covariance from the known likelihood.
The numerical rank cutoff is max(matrix dimensions)×machine epsilon×largest singular value.
Report all rank-deficient draws separately and in aggregate. Do not silently exclude them.
Also report error against line separation, linewidth, contrast, and nuisance regime.
Truth-based conditioning may be used only for labeled benchmark diagnosis. An acceptance policy may use observations and supplied calibration only.
A local Cramer-Rao covariance is an approximation, not proof that an estimator attains the bound.

## Stage P1: strengthen the classical reference before a learned candidate

Keep the historical affine, peaks, nominal, and three-start full LM policies available with explicit provenance.
Select each method's chunk from C0 completed timings only, at the same precision; confirm output fidelity before using it.
Compare optimized CPU and GPU implementations on their appropriate devices. Never compare only serial CPU fitting to a GPU network.
All methods get the same observations, axes, bias, nominal calibration, parameter bounds, exposure, and caching permissions.
All methods may skip refinement only through the same prospectively qualified observable acceptance policy.
A neural warm start, if authorized later, gets exactly those same refinement/fallback permissions.

Do not treat three-start 40-iteration full LM as the only accurate classical competitor.
Prospectively implement one affine warm-start refinement family with exactly 1,3,or 6 Gauss-Newton/Fisher steps.
Use the same full eight-line likelihood, bounds, derivatives, damping rules, and terminal full-LM fallback.
This family is not implemented or timed by the current chunk package.
Its observable stationarity/curvature test must be frozen and manufactured-tested before population access.
The test must inspect the estimated field correction and parameter uncertainty, not deviance alone.
The precise stopping formula and numerical tolerances are UNRESOLVED pending that source review.
Do not choose them by inspecting final labels or by weakening the registered field-error requirement.

For acceptance calibration, use grouped development-design outputs only.
Estimate how observed correction/curvature/uncertainty relate to field error. Preserve rejected outputs and count fallback time.
Freeze one policy before validation. If its coverage or field-error claim fails validation, stop that claim without threshold tuning.
Approximate uncertainty must be checked for coverage; a covariance formula alone is insufficient.

A strongest-baseline claim also needs a practical line-fit-plus-vector-inversion comparator.
It must estimate line locations/association from the same noisy spectra; oracle line centers are not a fair comparator.
Separate the cost/error of spectral line fitting from the analytic line-to-field map.
If an optimized GPU line-fitting implementation is applicable, include it or state the missing comparator explicitly.
The current code fits the full eight-line Hamiltonian directly. It has not implemented or defeated that prior-art pipeline.
Root's paper/Gpufit applicability review is a dependency. No additional package download is authorized here.

## Outcomes, selection, and stopping

Report vector-norm field MAE/RMSE/p 50/p 90/p 99/max, component bias, rejection rate, fallback rate, and total wall/CPU/GPU cost.
Save per-case predictions, labels, accepted/rejected/fallback flags, condition diagnostics, method config, and timing records.
Report all cases, plus accepted-only summaries with coverage. Never improve accuracy by hiding rejection.
Predeclare error exceedance curves at[.1,.25,.5,1,2,5,10]microtesla; these are reporting thresholds, not application requirements.
Use latent-group bootstrap intervals. No noise replicate crosses a bootstrap group or a development split.
A saved-output verifier must independently bind labels to the split manifest and recompute all reported metrics without inference.
The root must freeze bootstrap seeds and replicate count before that calculation.

A simulation Pareto result needs matched accuracy and failure coverage on independent groups.
Select the strongest adequate classical method from development-design using the later frozen accuracy/coverage requirements.
If those practical requirements remain unresolved, select no adopter; publish the Pareto curve and the unresolved requirement.
Avoid a post-hoc single weighted score that conceals an accuracy/speed tradeoff.
Final confirmation compares at most the frozen chosen classical method and one already-frozen candidate, plus required reference checks.
If no candidate has a useful predicted advantage, do not train one.
No current neural architecture, training set, hyperparameter search, or training reservation is authorized.

The practical adoption gate must record the measured workload size/frequency and maximum acceptable absolute field error/failure rate.
For current-distribution imaging, derive that requirement from the smallest relevant field/current feature and downstream reconstruction error.
Those external quantities are absent; do not invent convenient thresholds to produce a pass.
The previous 0.25 microtesla manufactured solver tolerance is implementation fidelity, not an instrument requirement.

Include amortization: calibration+training+retraining time divided by the measured per-spectrum time saved at matched accuracy/coverage.
Also report the absolute seconds saved per map and per million spectra. A 2 xspeedup alone is insufficient.
The inaccurate affine 45 ms profile is not an adequate reference merely because its residual guard accepted every case.
Use the fastest independently qualified classical solution after finite refinement and chunk checks.
Include setup, transfer, preprocessing, stationarity/uncertainty tests, rejection, and every fallback call.
Acquisition latency/energy and FPGA performance remain outside this software-only result.

## Proposed later reservations and stop rules

These are draft ceilings, not active reservations:
P0 qualification at most 90 GPU/wall seconds after checking remaining eligibility capacity;
P1 development at most 900 GPU/wall seconds;
one confirmation at most 300 GPU/wall seconds;
saved-output verification at most 180 CPU/wall seconds.
All remain inside the authoritative vector lane 8 CPU-hour/2 GPU-hour/4 wall-hour shared caps.
Use one CPU thread, existing GPU/RSS bounds, one Torch process, no children, no installs, and no hardware.
A timeout preserves partial evidence. Never silently retry, enlarge caps, regenerate data, or reopen a consumed split.
Root owns all approvals, seed custody, selection, and final completion decisions.
