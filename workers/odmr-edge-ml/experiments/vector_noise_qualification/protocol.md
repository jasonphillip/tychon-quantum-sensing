# P0: fresh-noise and identifiability qualification

Date: 2026-10-15, America/New_York. Status: DRAFT_ROOT_REVIEW_NOT_AUTHORIZED.
This diagnostic stage cannot adopt a winner or authorize training.
The unresolved practical current-map workload does not block this qualification.

## Exact inputs and custody

Use 32 independent latent draws from regime A and 32 from regime B.
Generate exactly two independent Poisson replicas per latent row: 128 spectra total.
A has residual fields [-10,10] microtesla, D [2869.9,2870.1] MHz, FWHM [1.75,2.25] MHz,
contrast [.04,.08], baseline [.99,1.01], slope [-.005,.005].
B uses every unchanged frozen lower/upper bound.
Latent ordering is A00–A31 then B00–B31; each latent has consecutive r0/r1 rows.
Use new root-issued parameter and two independent noise seeds. Do not reuse previous campaign seeds or samples.
The root issues the certificate only after source freeze. No seed was read during preparation.
There is no held confirmation data and no observation-based selection or exclusion.

The seed certificate JSON must have purpose="vector_p0", status="ISSUED", parameter_seed as a decimal string,
noise_seeds as two distinct decimal strings, and freshness_attestation="ROOT_CONFIRMED_NOT_PREVIOUSLY_USED".
All three integers must differ and fit unsigned 128 bits.
The gate and job specification bind its exact file hash. Save only its hash in scientific output provenance.
PCG64 creates one parameter stream and one independent full-latent noise stream per replica index.
Noise is integer Poisson with mean 2000000 times fluorescence for each bin. No Gaussian replacement or label-based normalization.
All frozen orientation, oblique bias, 512-bin grid, exposure, units, line physics, bounds, and policies remain unchanged.

## Fixed methods and timing

Run once each, in this order: full LM float64/chunk1024; historical affine float32/chunk4096;
peaks float64/chunk1024; nominal calibrated float64/chunk1024.
These chunk choices came from the completed fixed-case timing qualification. They are not an accuracy ranking.
The affine shortcut previously had large errors despite full acceptance. Preserve that limitation.
Use the unchanged chunk wrapper and solver. No new refinement, stopping policy, threshold, or neural model is added.
Each timed host-to-host call includes engine/calibration setup, transfer, guard, and actual fallback.
Record generation and diagnostic time separately. One noisy pass is diagnostic cost, not a stable throughput benchmark.
No rejected case is omitted from error summaries. Save all predictions, flags, fallback masks, and errors.

## Noise, information, and error checks

Use the unchanged engine for means/Jacobians. Independently reconstruct true means through the existing laboratory-frame Hamiltonian reference and a separate Lorentzian sum.
The two mean spectra must agree within absolute 1e-11 fluorescence units before generating counts.
Manufactured tests check Poisson call arguments, integer outputs, exposure units, zero-field Lorentzian reduction,
label/group/hash identity, zero-count likelihood arithmetic, analytic diagonal information covariance, and rank-deficient covariance handling.
Do not use an unreliable small-sample distribution-fit test to declare the Poisson RNG correct.

Save true expected Fisher information and fitted-parameter expected Fisher information:
I = J^T diag(exposure/rate) J. Also save count-weighted observed Gauss-Newton information:
I_GN = J^T diag(count/rate^2) J.
I_GN is not the full observed Hessian because the residual-weighted second-derivative term is absent.
Expected-information inverse field blocks are local CRLB diagnostics under the ideal model.
The observed-GN inverse field block is a covariance proxy, not a CRLB.
Use all eight parameters, including nuisance coupling, before extracting the three-field covariance block.
Compute rank and conditioning on the scale-normalized whitened Jacobian, not unit-mixed raw columns.
The rank cutoff is max(matrix dimensions) times float64 machine epsilon times the largest singular value.
Rank-deficient cases remain present, with infinite condition and undefined (NaN) covariance; never turn a pseudoinverse into zero uncertainty.
These local quantities do not establish global identifiability or efficient estimation.
True-parameter information is labeled diagnostic truth and is never provided to estimators or acceptance guards.

Save every signed component error and vector-norm error. Report all/A/B mean, RMSE, p50/p90/p99/max,
acceptance count, fallback count, and rank-deficiency counts. No absolute field-error threshold selects a winner.
Uncertainty coverage, practical adoption, and new acceptance policies require later protocols.

## Saved-output verification

The independent verifier loads public-style saved arrays and manifests only. It does not call a forward model, RNG, or estimator.
It binds every file hash, exact 128 record IDs, 64 latent IDs, paired replicas, labels, units, ranges, and method configuration.
It independently recomputes errors, likelihood values, information rank/conditioning/covariance, and summary metrics.
Information covariance comparison tolerance is relative 1e-6/absolute 1e-8; field-error summaries use 1e-12.
Likelihood recomputation uses saved float64 diagnostic spectra. Allow absolute reduced-deviance difference .02 for historical float32 affine and 1e-6 for float64 methods.
The float32 allowance covers cross-precision spectral arithmetic; it is not an acceptance-threshold relaxation.
Acceptance flags remain checked against each method's saved finite/bounded prediction and saved reduced deviance <=2.
A failed checker or scientific contract stops qualification. Preserve outputs; do not tune or regenerate.

## Reservations and outputs

Proposed P0 ceiling: 90 CPU/GPU/wall seconds, Spark3, one numerical CPU thread, existing 16 GiB RSS plus16 GiB PyTorch allocator policy.
Fixtures: at most15 CPU/wall seconds, Spark2, 2 GiB, no GPU. Both require explicit root registration.
The independent saved-output verifier needs a separate root reservation; a suggested ceiling is15 CPU/wall seconds,2 GiB,zero GPU.
The root checks remaining eligibility capacity and all shared caps before each reservation.
No new dependencies, installs, hardware, service changes, or build actions are needed.

Outputs: data.npz, records.json, provenance.json, true_information.npz;
for each method, prediction.npz, diagnostics.npz, and summary.json; final result.json and hash manifest.json.
The manifest updates after each complete method so a timeout preserves attributable partial evidence.
Input data, predictions, and diagnostic files are written once. Never reuse the output directory.
Root independently reviews the saved verifier before drawing diagnostic conclusions.
Practical absolute accuracy, meaningful failure tolerance, and real workload amortization remain prerequisites for later adoption.
