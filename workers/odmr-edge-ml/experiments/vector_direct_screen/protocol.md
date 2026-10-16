# Batched eight-line vector inversion: qualification protocol

Prepared: 2026-10-15.
Status: DRAFT_ROOT_REVIEW. No numerical output exists for this source.
Lane: vector. Campaign: nv-advantage-search-2026-10-15.

## Purpose and distinct contribution

Test a compact direct inverse against optimized same-device classical methods.
The proposed contribution is inspectable matched-information comparison, shifted-nuisance reliability, and full fallback cost accounting.
Generic neural ODMR acceleration is established prior art.
No novelty claim is approved.
This package prepares only physics, manufactured checks, and classical profiling.
It contains no network, trainer, population generator command, or final data.

This is an isolated biased-vector experiment.
It does not change the production scalar model rule or any previous campaign.
No measured widefield, cardiac, localisation, or consumed synthetic data enters this package.

## Frozen ideal model

Frequency units: MHz. Field units: microtesla. Dimensionless fluorescence and counts are separate.
The four crystal axes match the existing simulator and BLUE geometry.
The crystal orientation is known.
Bias is [1600,900,300] microtesla in the cubic laboratory frame.
Signal components lie in [-20,20] microtesla independently.
D lies in [2869.6,2870.4] MHz.
FWHM lies in [1,3] MHz.
Total contrast lies in [0.02,0.12].
Off-resonance baseline lies in [0.98,1.02].
Linear slope lies in [-0.01,0.01] across the scaled frequency coordinate.

The frequency grid has 512 uniform points from 2805 through 2935 MHz.
The spin Hamiltonian is D Sz^2 + gamma B dot S.
Gamma is 0.02802495164 MHz per microtesla.
Each axis contributes two transitions from its lowest eigenstate.
The model assigns equal line strengths and a common Lorentzian width.
It uses the arithmetic mean of eight Lorentzians.
Equal strengths are a declared approximation, not calculated microwave transition strengths.
No hyperfine, strain, optical pumping, microwave polarization, drive inhomogeneity, cavity, or detector electronics are represented.
This is eight-line spin-1 resonance physics, not a full NV optical simulator.

The experiment does not claim global identifiability.
The fixed local bias sector restricts symmetry-related solutions.
Population eligibility must check inverse conditioning and minimum line separation before any learning claim.

The observation law is independent Poisson counts with 2,000,000 off-resonance photons per bin times normalized fluorescence.
Exposure is identical for all methods.
This package never calls its explicit Poisson helper during preparation.
Manufactured qualification uses expected counts, which can be non-integers, and is not a noise experiment.

## Independent checks and tolerances

A SciPy reference builds the Hamiltonian in the laboratory Cartesian spin-1 representation.
It does not reuse local frames or production derivative code.
This is an independent implementation of the same ideal physics, not measured validation.
Test tetrahedral geometry, right-handed frames, zero-field D, axial splitting, finite rates, batching, invalid counts, and analytic derivatives.
Finite differences use a fixed 1e-4 fraction of each parameter scale.
Derivative tolerance is 2e-7 absolute plus 2e-4 relative.
Float64 transition agreement must be within 2e-9 MHz.
Float32 agreement must be within 0.003 MHz.
Float32 spectrum and Jacobian differences must stay within 2e-5 and 2e-4 respectively.
Float64 spectrum and Jacobian differences must stay within 1e-11 and 1e-10 respectively.

Five fixed, non-evaluation cases are declared in independent.py.
Noiseless full-solver recovery must have vector error at most 0.25 microtesla.
Maximum fluorescence reconstruction error must be at most 2e-5.
Record convergence and rejection flags even when reconstruction passes.
A failure blocks that backend or solver from timing claims.
Preserve failures. Repairs require a new pinned source and root review.

## Strong classical controls

The common implementation supports NumPy CPU and PyTorch CPU/CUDA.
Analytic Hellmann-Feynman derivatives feed batched Poisson Fisher-scoring LM.
No per-spectrum Python solver loops are used.
All reference methods may use GPU, fixed calibration, identical bounds, and identical observations.

Classical policies are calibrated affine inverse, local observed peak inverse, calibrated nominal shortcut, and full LM control.
The affine inverse uses the nominal model Jacobian and likelihood weights.
The peak inverse uses fixed prior windows and the same Hamiltonian Jacobian.
It receives no true line assignments, fields, or noise draws.
Every shortcut can skip fitting when the common observed-data check passes.
Rejected shortcuts use the same batched physical fallback.
The fallback starts from the affine inverse at widths 1,2,3 MHz and retains the best qualifying likelihood.
The full LM control is diagnostic; it is not automatically the primary speed reference.
The fastest accuracy-qualified classical policy is the primary reference.

Common acceptance uses finite predictions, frozen parameter bounds, and Poisson reduced deviance at most 2.
Simulator labels never choose acceptance or fallback.
Solver convergence is reported separately.
Residual acceptance alone does not prove field accuracy.
A later error and catastrophic-failure gate is mandatory.

## Profile plan

Freeze batches 64 and 4096. Chunk size is 256.
Report NumPy float64 CPU, Torch float64 CPU, and qualified Torch float32/float64 CUDA separately.
The root can omit an unqualified configuration, with its reason preserved.
CUDA is reserved for Spark3 in this campaign.
No service eviction is permitted.
The runtime pins one process, source hashes, and memory limits.
CPU concurrency is controlled by the supervisor.

Report three repeats after one disclosed warm-up.
Resident timing includes initialization, residual checks, fallback, and synchronization.
Host-to-host timing additionally includes input transfer, calibration construction, and output transfer.
Disclose fixed-calibration construction and initial transfer separately.
Report resident and end-to-end throughput.
Extrapolate total time for one million spectra and label that figure as extrapolated.
This stage repeats five manufactured cases. It cannot establish population accuracy or representative fallback rate.

4096 spectra per second is illustrative.
It is not an adoption gate or measured instrument requirement.
Root judges whether absolute savings justify training after the profile.
Do not stop solely because this illustrative threshold is met.

## Later decisions, not execution authorization

Before development, freeze fresh seeds, parameter groups, calibration shifts, failures, and final allocation.
Use different calibration/noise regimes for training, development, and confirmation.
No old test data or seeds may select this candidate.
A fixed physics check must first establish conditioning throughout the chosen regime.

At most one direct model family is proposed: a static 512-128-64-8 ReLU multilayer perceptron.
No training code or run is authorized here.
A later freeze must set one seed, finite training size, epochs, checkpoint rule, and normalization.
Models above 1000 parameters must train on CUDA.
All direct predictions use the exact same observed acceptance and classical fallback.
All methods receive identical information and hardware access.
Do not add arbitrary nuisances to slow the classical solver.

Proposed comparative gate: at least 2x throughput over the fastest qualified same-device classical policy.
Require the upper uncertainty bound on vector-error ratio below 1.05.
Absolute catastrophic-error and non-ratio rules remain BLOCKING prerequisites for population generation.
They are not silently inferred from this preparation.
Shifted nuisance groups and total fallback costs must pass.
Training, calibration, rejected outputs, and all failures remain visible.
A classical winner is valid and does not support neural superiority.

## Stages and budget

1. Root review, source pinning, and manufactured CPU checks: first bounded job.
2. Qualified CUDA fidelity and solver checks: next bounded jobs on Spark3.
3. Classical shortcut and solver profiles: finite root-selected configurations.
4. Root evaluates absolute savings and model adequacy before any training proposal.
5. Development, confirmation, saved-output verification, and publication require later freezes.

Lane ceiling: 8 CPU-hours, 2 GPU-hours, 4 numerical wall-hours.
Keep at least 15 percent for independent verification.
No initial qualification job may exceed 15 minutes wall time.
Suggested first fixtures reservation: 120 CPU seconds, 120 wall seconds, 2 GiB, one CPU thread.
CPU memory ceiling is 8 GiB.
GPU source contract is one PyTorch process, no descendants or loader workers, 16 GiB allocator plus 16 GiB host RSS.
The supervisor enforces host availability and competing-process rules.
Driver/context memory limits remain those stated in the root plan.

The earlier 2–4 working-day estimate is a possible full demonstrator duration.
These stages start immediately after their individual approvals.
No scientific result or fixed finish time is promised.
