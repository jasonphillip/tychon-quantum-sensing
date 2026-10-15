# Measured widefield repeat prediction

Prepared: 2026-10-15. Status: prospective draft. Numerical execution is not authorized by this document.
The root coordinator must approve Freeze A, data custody, source hashes, seeds, and accounting first.

## Question and evidence

Can one measured scan predict another scan better than strong classical spectrum processing?
The primary target is normalized fluorescence, not magnetic field.
This campaign is separate from the closed synthetic experiments.

Use the three public files f0, f8, and f24 from [Zenodo 7233869](https://zenodo.org/records/7233869).
Their recorded current settings are 0, +600, and -600 mA.
The download owner must verify the CC BY 4.0 license, repository checksums, local SHA256, and complete byte counts.
Never derive pixel-field labels from these setpoints.
Current and acquisition time are confounded because the files were acquired in a fixed order.

The inspected f0 primary header defines five repeats, 200 frequencies, and 1024 by 1280 pixels.
Storage is signed big-endian int16 with BSCALE1 and BZERO32768.
The frequency grid is 2700 +1.5*i MHz for i=0..199;3000 MHz is the exclusive endpoint.
The header records 20 ms exposure and 190.4458242 s measurement time for f0.
Camera gain, read noise, per-frame timestamps, and scan independence are not established.
Use neither a Poisson likelihood nor an absolute sensitivity claim.

The [source paper](https://www.nature.com/articles/s41598-022-22610-5) describes spatial drift and multiresonance fitting.
We therefore test fixed registration offsets and retain fit-quality flags.
Repeat ordinal follows the FITS outer axis and NSCANS agreement.
It does not prove chronological order, independent noise, or an independent acquisition.

## Fixed partitions and access order

Use only the central 512×512 crop: rows 256..767 and columns 384..895, zero-based.
Divide it into 64 blocks of 64×64 pixels.
Use block columns 0–3 for training, 4–5 for development, and 6–7 for final evaluation.
All three files share the same spatial groups.
All repeats of a position stay in its assigned group.

Discard an 8-pixel border within each block before patch selection.
Within its 48×48 interior, rank 4×4 patches by mean repeat 0 brightness.
Ties use increasing y, then x.
Choose eight patches with at least 8 pixels between patch origins in Chebyshev distance.
Selection reads repeat 0 only and operates independently within the current block.
Selection is adaptive preprocessing from the observation, not from the held reference.
The resulting sizes are 768 training, 384 development, and 384 final patch spectra.

Training inputs use repeat 0; training references average separately normalized repeats 1 and 2.
Development inputs use repeat 0; references use repeat 3.
Final inputs use repeat 0; references use repeat 4.
Normalize every observed/reference spectrum by its own median of its first 10 and last 10 bins.
This removes overall gain from the target definition and does not establish off-resonance background truth.
Undefined normalization stops the stage; it never removes a difficult row after scoring.
Storage-extrema flags remain in saved artifacts and do not exclude rows.

Final block values remain unopened before Freeze B.
At Freeze B, freeze all preprocessing, model weights, the classical reference, source hashes, and evaluation command.
Generate final predictions first and commit their manifest before final reference extraction.
The final-reference approval must bind that prediction manifest hash.
Retain all consumed splits and all original results; no final-driven tuning is permitted.

## Fixed classical methods

All predictors receive the same normalized 200-bin repeat 0 spectrum.
They may use training groups only for calibration.

1. Raw input identity predictor.
2. Savitzky–Golay smoothing, window 11, polynomial order 3, default interpolation edges.
3. Full linear ridge prediction from training input to averaged training reference.
   The ridge penalty is 0.01 times mean diagonal input cross-product, with floor 1e-8.
4. Rank 8 PCA/Wiener prediction from training references.
   Estimate component noise from the repeat 1-minus-repeat 2 difference on training groups only.
5. Robust multiresonance fit with a linear background and shared FWHM.
   Compare 0, 1, 2, 4, 8 lines by fixed input-only BIC heuristic.
   Nonlinear counts use width starts 8 and 16 MHz, analytic Jacobians, soft-L1 loss, and 80 evaluations per start.
   Width bounds are 1.5–60 MHz; centers stay inside the measured band; contrast bounds are 0–0.3.
   Initial centers use input-only peak prominence and deterministic low-value fill.
   A rank/bound/contrast flag identifies fits that do not support reliable line interpretation.
   Background-only fits predict spectra but do not establish ODMR line reliability.

These are optimized NumPy/SciPy implementations with analytic fit derivatives.
No method receives an inferred field label or privileged reference repeat at inference.
Select the classical reference by smallest development MSE; break exact ties alphabetically.
Freeze it before candidate scoring and final access.
Candidate training requires a classical development improvement of at least 2% over raw input and at most 1% numerical failures.
If this qualification fails, stop the neural route and report the measured-data limitation.

## One learned candidate

Use one residual MLP:200→16→200, ReLU, 6616 parameters.
Zero-initialize the final layer so the initial prediction equals the observed input.
Train exactly 20 epochs with Adam, learning rate 0.001, batch 64, and one custodian-audited seed.
Use normalized-spectrum MSE on training groups only.
No architecture search, early stopping, extra seed, or held-reference adaptation is permitted.
Training requires CUDA. There is no CPU fallback.
Deployment uses the equivalent NumPy matrix operations and needs no Torch runtime.
Float32 training versus NumPy deployment parity needs a manufactured check before the first candidate comparison.
No FPGA compatibility or quantization claim is made.

The classical development predictions are reused when evaluating this candidate.
Do not rerun classical inference merely to add the candidate.
At final evaluation, run the frozen candidate and classical reference on the same observation bundle.

## Metrics and advancement gate

Primary loss is normalized-spectrum MSE, first averaged within each spatial block and then equally across blocks.
The zero-offset reference is primary.
Report patch-level RMSE90th percentile, numerical failure fraction, fit reliability, and file/current subgroups.
Report all fixed shifts: zero, ±1 and±2 pixels along each axis separately, with no diagonals.
Never pick the best registration shift after scoring.

The candidate advances only if every condition passes:

- Primary MSE is at least 5% below the frozen strongest classical reference.
- The upper 95% paired block-bootstrap bound on the MSE ratio is below 1.
- The patch-RMSE90th percentile is no more than 2% worse.
- Numerical failures are at most 1% and at most 0.5 percentage points above the reference.
- Each registration shift and each file/current subgroup has MSE no more than 2% worse.

Use 10000 bootstrap draws, resampling whole spatial blocks jointly across files and patches.
The custodian supplies and registers the seed before any draw.
These intervals are conditional spatial resampling estimates from one field of view.
They are not calibrated population uncertainty or independent-acquisition evidence.
The four repeated scans and pixels are not treated as independent experimental subjects.
The sole primary advantage is measured repeat reconstruction quality.
No processing-speed, sensing-bandwidth, field-accuracy, or acquisition-time advantage follows from this gate.

## Runtime, failure handling, and limits

Numerical commands require the accounting approval hash and run ID in their environment.
The approval lists exact allowed phases, all source hashes, protocol hash, custody hash, and artifact manifests.
Root owns the separate campaign accounting implementation and allocations.
This package does not create another supervisor or ledger.

Lane maxima:16 CPU-hours, 2 GPU-hours, and 4 cumulative numerical wall-hours.
Eligibility/tests:15 minutes; development:150 minutes; final:30 minutes; verification:45 minutes.
First qualification is capped at 10 minutes; first candidate run at 30 minutes.
CPU memory is at most 8 GiB; GPU allowance is at most 32 GiB.
Use one numerical process; root may allocate up to four numerical-library threads.
Central receipts cover all I/O, extraction, calibration, fitting, and model training.
Saved batch 1 prediction times include fallback but exclude FITS reading and patch extraction.
Publish both scopes; do not substitute prediction time for complete processing cost.

Non-finite model output falls back to the observed input and remains flagged in the primary metric.
Optimization failure has a deterministic fallback; fit non-identifiability remains explicit.
Stop for incomplete downloads, provenance failures, partition mismatch, undefined normalization, missing groups, failed gates, or a cap.
Fix an identified implementation bug once with a changed approach, retaining the failed run.
Do not change thresholds or candidate choices after a failed scientific gate.
No hardware, Beelink, paid compute, downloaded-code execution, or production-checkout edits are allowed.

## Reproducibility acceptance

Publish source, the exact source/data manifests, partitions, patch coordinates, observed/reference spectra,
all predictions, failure flags, recorded timings, bootstrap indices, and decisions.
A fresh public checkout must recompute the reported metrics from saved arrays without model inference.
An independent verifier and final-public-checkout command are required before publication.
They are not yet implemented or executed in this preparation commit.
If every method fails, a reproducible limitation report is a valid result.
