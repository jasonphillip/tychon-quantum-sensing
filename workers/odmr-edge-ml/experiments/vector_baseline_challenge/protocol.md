# Finite classical precision and zero-step neural challenge

Dated: 2026-10-15. Status: FROZEN_BASELINE_CHALLENGE.

This additive protocol preserves P1 commit c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e and every earlier experiment.
P1 is closed development. Its cases do not select these new routes.
P1 omitted two-step and mixed-precision refinement. No empirical rejection of those options was recorded.
Its approximately 2.23-fold speed margin motivates this stronger comparator check.
Generic neural acceleration is prior art. This test makes no novelty claim.

## Fixed routes

| Route | Initializer | Physical attempts | Final guard and fallback |
|---|---|---|---|
| lm | Frozen full multistart LM | Original policy | float64 |
| affine3 | Frozen affine | Three float64 | float64 |
| tied12 | Frozen tied-line comparator | Original policy | float64 |
| neural1 | Frozen P1 weights, float32 | One float64 | float64 |
| affine2_f64 | Frozen affine | Two float64 | float64 |
| affine2_f32 | Frozen affine, float32 | Two float32 | float64 |
| affine3_f32 | Frozen affine, float32 | Three float32 | float64 |
| neural0 | Frozen P1 weights, float32 | Zero | float64 |

The final four rows are new candidates. No further alternatives are permitted.
No training, new architecture, weight selection, threshold relaxation, or calibration fitting is permitted.
Mixed routes use the unchanged LM algebra at their declared precision.
Their eight resulting parameters cross into float64 before the common observed-data guard.
The cast cannot clamp or otherwise repair the parameters.
The original float64 guard uses physical bounds and Poisson reduced deviance at most two.
Every rejected proposal receives the original float64 three-start full-LM fallback.
This guard is a residual check. It does not establish field accuracy.
The fresh labels evaluate field error separately and never control a route.
Float32 internal LM acceptance uses the frozen stable Poisson deviance implementation.
Final acceptance never uses float32 Poisson subtraction.
Neural model and input normalization stay float32; outputs and all final physics use float64.

## Fresh data and custody

After source freeze, root issues two distinct unsigned128-bit seeds for parameters and Poisson noise.
The custody certificate purpose is vector_baseline_challenge; it must attest no previous use.
Exactly4096 full-B independent latents receive one independent Poisson observation each.
All eight parameters are uniform within the unchanged configuration bounds.
Bias, orientation,512frequency bins,2,000,000photons per bin, units, and eight-line forward model remain unchanged.
Generation checks32 prospectively evenly spaced rows against the independent Hamiltonian/Lorentzian means.
No cases are excluded. No P0/P1 counts, labels, or predictions are read.
Only the exact frozen model-final.pt, scaling.npz, and setup.json may enter from P1.
The approval and supervisor pin their hashes. Original setup cost is used only for amortization.
The model remains fixed even when every new candidate fails.
Counts occupy one int64 block of4096×512,16MiB uncompressed. Every saved file stays below64MiB.

## Timing and fixed decision

Use Spark3 CUDA, one numerical CPU thread, one process, and no descendants.
One batch4096 and chunk1024 apply to every route.
Each route has equal persistent Engine and affine-calibration permission.
Mixed routes may retain their required float32 Engine; neural routes may retain loaded weights and scaling.
Setup costs are recorded separately for each route. No route rebuilds its cache inside service timing.
The fixed route order is the table order. Each route has one warmup, then three measured repetitions.
Each repetition includes host counts, transfers, casts, initializer, refinement, guard, full fallback, and output transfer.
Service outputs are the same four arrays: parameters, accepted, reduced_deviance, and fallback.
Native diagnostic exports and fitted-rate checks occur outside the service timer for every route.
All diagnostic computation remains charged to the numerical job.
Report absolute seconds per4096 and per million spectra, fallback counts, and retained failures.
All three repetitions must reproduce flags and parameters within1e-5absolute tolerance at the identical chunking.
This is a deterministic-repeat check, not an extra accuracy allowance.

A classical route is adequate when mean and p95 Euclidean field error each stay within1.05×fullLM.
Its rejection count cannot exceed fullLM's rejection count.
Choose the smallest median host time among adequate classical routes; exact ties use the declared classical order.
For each neural route, mean and p95 error must stay within1.05×the best adequate classical values separately.
Its rejection count cannot exceed the smallest adequate classical rejection count.
It must also provide at least2× speed over the fastest adequate classical route at batch4096.
Report both neural decisions. A failed neural0 is retained and cannot replace neural1 silently.
A finite positive setup break-even is required. Conservatively count original P1 generation/training/setup plus current neural setup.
Fresh challenge generation is an evaluation cost, reported separately and charged to the campaign.
No neural or classical practical adoption follows from this challenge.
External workload, absolute accuracy, failure requirements, and fresh confirmation remain unresolved requirements.

## Execution and stopping

Manufactured fixtures precede a root-approved status-only freeze.
Root then binds fresh custody, exact source, frozen inputs, and immutable approval/spec files.
Proposed fixtures:30CPU/wall seconds,8GiB,oneCPUthread,development stage.
Proposed challenge:1800CPU seconds,600GPU/wall seconds,16GiBRSS plus16GiBPyTorch allocator,oneCPUthread.
Proposed saved verification:360CPU seconds,120wall seconds,8GiB,oneCPUthread,verification stage.
Root must check remaining campaign caps before reservation. The requested verification reserve exceeds15percent of challenge wall time.
Stop on source drift, invalid noise/units, nonfinite outputs, accounting uncertainty, or resource termination.
Preserve partial artifacts and exact receipts. Do not retry, tune, train, or increase limits autonomously.
Saved verification reads published arrays and manifest bytes only. It never loads a model or calls the forward model.
Its physical acceptance reconstruction uses float64 fitted rates, counts, bounds, and independent Poisson arithmetic.
The source pins bind those fitted rates to the approved producer; the verifier does not re-run inference.
Prepared fixtures do not establish CUDA performance or population accuracy.
