# Stage 2 protocol: matched known-direction bias comparison

Date: 2026-10-15. Registered by root under the scoped known-axis gate in STAGE1_GATE.json.
The global independent diagnostic retains FAIL. Every known-axis comparison used here passed.
Implementation tests and development need static review; evaluation additionally needs the frozen custody lifecycle.

## Question and design
Estimate B uniform on [20,70] microtesla, always aligned positively with the single NV axis.
This is a changed task. It cannot repair or replace the old arbitrary-direction magnitude result.
Compare exactly two arms: zero bias and +250 microtesla along that axis.
The choice is based only on Stage 1: smallest tested bias, and best worst-case known-direction shape bound.
Use 100 equally spaced frequencies from 2820 through2920 MHz.
Use the unchanged Stage 1 renderer, with its single global amplitude factor0.9957299574916568.
Do not renormalize any spectrum or arm.
Use paired fields, thermal/MW nuisance states, gradient, and standard-normal noise across both arms.
Three cells: realistic_anchor (intrinsic FWHM5MHz,SNR10); wide_lines(7MHz,10); low_snr(5MHz,3).
Contrast scale.015, slope.02, post-render offset.3MHz.
Photon budget per frequency is (SNR/(.30*.015))^2.
No physical dwell time or calibrated photon-rate claim is allowed.

## Fresh nuisance generation
Use the existing cascaded OU recurrence, with a new private trajectory seed per field.
Draw a sample index uniformly from integers0..39999, then simulate only through that index.
Start T293.15K and MW1.0. Set dt1s, theta_T.001, sigma_T.05,
T_env(t)=293.15+15sin(2pi*t/5400), theta_MW10, sigma_MW.006,
MW_target=1-.0035*(T_new-293.15).
Use exact OU decays exp(-theta*dt), with independent normal streams for T and MW.
The thermal noise standard deviation is sigma*sqrt((1-decay^2)/(2theta)).
For index k, advance exactly k recurrence steps using T_env(i*dt),i=0..k-1.
Generate independent normal streams with SeedSequence(trajectory_seed).spawn(2), T first and MW second.
Apply source positive clipping T>=.001K,MW>=.000001 to returned values after recurrence, never inside it.
Draw gradient uniformly[.046875,.346875].
These same nuisance values apply to both arms and all cells for a field.
Each cell uses the same standard-normal100-vector for that field, scaled by sqrt(mean/P).
All fresh row seeds lie in[2^40,2^63); metadata-only collision audit includes earlier manifests and new partitions.
Assert every scanned old seed<2^40. Range disjointness also excludes all reserved old final row seeds.
Stage1 is deterministic and contains no generated data seeds. Include any seed metadata found in its records.
Never open consumed spectrum payloads or generate the old reserved final.
Save every new spectrum, exact mean, standard-normal vector, nuisance value, label, and seed for public reproduction.
Keep inputs.npz separate from truth.npz. Inputs contain spectra, frequencies, stated biases and row IDs only.
Truth contains labels, means, noise vectors, nuisance states and seeds.
The prediction process opens inputs only. Commit its output hash before the metric process opens truth.
Use a git-tracked JSON binding predictions.npz and the prediction receipt SHA256.
The metric command verifies these committed bytes at the supplied git revision before opening truth.

## Sizes and custody
One development batch of32 fields; one sealed evaluation batch of256 fields.
Each field has3 cells and2 arms:192 development spectra,1536 evaluation spectra.
No additional candidate family or validation-selection stage.
Development verifies implementation, runtime, and numerical behavior. It is not a tuning sweep.
One documented implementation-defect repair is allowed before freeze, using the same development data.
No new development batch or threshold change.
A development numerical failure or projected compute overrun stops the experiment before evaluation.
Claude holds one32-byte evaluation secret, commits its SHA256 after registration, and never syncs the secret.
Development entropy is the integer SHA256 of UTF8 'tychon/scalar-information-limit/2026-10-15/dev'.
Entropy is int.from_bytes(secret,'big') for evaluation; development uses int(sha256(label).hexdigest(),16).
SeedSequence(entropy).spawn(3) gives field/gradient, trajectory/index, noise, in that order.
Each child drives default_rng(child), drawing n distinct integers with rng.integers(2**40,2**63,dtype=int64).
Reject any previously drawn or audited seed, advancing the same stream until each list has n values.
For each field_seed, default_rng(field_seed) draws B=uniform(20,70),then gradient=uniform(.046875,.346875).
For each nuisance_seed, SeedSequence(seed).spawn(2) gives an index RNG and a trajectory RNG.
Index comes from default_rng(child0).integers(0,40000).
The trajectory entropy is the high-range integer from default_rng(child1).integers(2**40,2**63).
Reject derived trajectory seeds on collision; store them explicitly.
Each noise_seed generates default_rng(noise_seed).standard_normal(100), reused across arms and cells.
Seed ordering, collisions and every derived seed must be saved and auditable.
After development, freeze the protocol, generator, estimator, metric code, seed audit, and commitment hashes.
Claude verifies the freeze independently, then runs the frozen generator under the shared lock.
Claude owns the secret and the sealed output until issuing access. Root does not inspect either beforehand.
Custody is procedural separation on one user-owned host, not security from its owner.
The new custody.py helper creates, freezes, authorizes access, then reveals and retires this one secret.
The registration JSON must contain stage:'stage2',approved:true,and the exact protocol_sha256.
The freeze binds a relative-path code manifest; generation and access revalidate every bound hash.
The generator consumes entropy through a custody callable that revalidates the freeze and secret commitment.
It creates one exclusive generation.used marker before returning entropy in memory; it never prints entropy.
Generate evaluation once into a new read-only output directory.
After generation, the exclusive access receipt binds its completed sealed manifest, freeze and code hashes.
The lifecycle is freeze -> generation -> access -> predictions -> git commitment -> metrics -> reveal/retire.
Both prediction and metric receipts bind freeze_sha256, access_sha256 and input manifest hashes.
Commit the secret commitment hash in git before generation. The secret file stays outside Shared.
A binding or exposure failure stops this study with a recorded failure; no automatic replacement secret.
Evaluate once, then reveal and retire the secret. No replacement test or post-result tuning.
Do not reserve or create a future neural test.

## One practical estimator
Use a bounded, nuisance-estimating weighted least-squares fit.
Fit field B[20,70], raw common resonance center[2865,2878]MHz,
intrinsic width[.5,12]MHz, contrast scale[.001,.06], baseline[.9,1.1], slope[-.08,.08].
The fitted mean uses two dipoles of squared strength.5 each, with known splitting2*gamma*(B+bias).
Nominal component amplitude=.03*(saturation/(1+saturation))/(.1/1.1).
Multiply the combined dip by global_factor*(fitted_contrast/.015), matching the renderer's normalization.
Use the Stage 1 nominal ten-component microwave mixture, MW1,gradient.196875.
Evaluate the fixed.3MHz interpolation offset identically to the renderer.
The estimator receives only observed spectrum, frequencies, and stated bias calibration.
It does not receive row truth, temperature, MW, gradient, seed, or exact mean.
Center and width absorb much of thermal/MW variation; the exact latent mixture remains unknown.
Use weights1/sqrt(clip(observed,.8,1.2)); explicitly call this weighted least squares, not exact likelihood.
Six fixed starts: B25/45/65 crossed with center2871.50827 and an observed-data center estimate.
Estimate that center from nonnegative dips after fitting a line to the outer15 bins on each side.
Subtract the known.3MHz interpolation shift from the dip-weighted observed centroid.
Clip this raw-center start to[2868,2875]; use2871.50827 if total positive dip is zero.
Other starts: width5,contrast.015,baseline1,slope.02.
Use scipy least_squares,method trf,linear loss,max_nfev120,ftol=xtol=gtol=1e-8,
x_scale=[45,1,5,.015,1,.02]. Use numerical derivative scheme '3-point'.
Choose the successful finite start with minimum weighted squared residual.
If all starts fail, record raw failure and use45 as the operational estimate.
Save each start's termination reason, evaluations, objective, fit parameters, elapsed time, and boundary flags.
Boundary flags use scipy OptimizeResult.active_mask!=0, without another numerical threshold.
Boundary hits are reported; they are not silently removed or automatically counted as failures.
A nonfinite observation gives a recorded failure and fallback.
The prior constant45 is the baseline. No old neural model is scored.

## Metrics and fixed gate
All rows remain in every operational metric. Report raw fit coverage separately.
Per arm/cell: MAE,RMSE,median and90th/95th absolute error,max error, failure fraction, boundary fraction,
median/p95 per-spectrum fit latency including starts and preprocessing, plus total time.
Use5000 paired field bootstrap resamples, shared across comparisons/cells.
Bootstrap seed is the high-range integer from SHA256('tychon/scalar-information-limit/2026-10-15/bootstrap'),
mapped as 2**40+int(sha256_hex,16)%(2**63-2**40). Publish all indices.
For realistic_anchor, require ALL:
1. 95% percentile interval upper bound for mean absolute error difference(biased minus zero)<-.5microtesla.
2. Same upper bound against constant45<-.5microtesla.
3. Biased operational MAE<=2microtesla,90th absolute error<=5microtesla.
4. Fit failure fraction<=.01.
The secondary cells cannot rescue failure. No threshold change or retest.
A pass is a conditional simulated measurement-design improvement, not neural superiority or reliable real sensing.

## Secondary diagnostics without new fitting
Report error and failures in four fixed temperature ranges:[-infinity,288.15),[288.15,293.15),
[293.15,298.15),[298.15,infinity), in kelvin.
Explain the ideal known-axis cancellation of common thermal center in the two-line splitting.
Report the naive single-line temperature error scale using the saved T values and the stated gamma.
For assumed bias-calibration offsets delta=-5,-1,0,1,5microtesla, subtract delta from successful saved biased
fit estimates without clipping; failed rows retain fallback45. Report all-row MAE and tails.
This is postprocessing sensitivity, not another acquisition or a rerun of a constrained fit.
It is an approximation at fit boundaries. Report boundary and fallback fractions alongside it.
The offsets are explicit engineering assumptions, not magnet specifications.

## Limits and stop rules
Portable CPU Python on Spark2, exactly one numerical worker. No GPU, training, paid service, hardware, or vector work.
Stage2 total<=2700CPU seconds and1500 cumulative numerical wall seconds.
Reserve at least120CPU and120wall seconds for saved-output publication checks.
Report CPU model, OS, Python/NumPy/SciPy versions and worker count with timing.
Shared-machine latency is descriptive and makes no portable hardware claim.
Whole new study<=5400CPU/3600wall; all-old-plus-new<=14400CPU/7200wall.
Use one shared numerical lock, all three existing ledgers plus any new stage ledger, <=4workers and8GiB.
Choose the tighter remaining cap. Independent review and publication numerics count too.
Freeze before evaluation. A failed binding, numerical failure, or cap ends the campaign with saved evidence.
No replacement secret after a consumed evaluation. Never hide a failed case.
Publish predictions, labels, flags, means/spectra, manifests, bootstrap indices, source, and offline metric checker.
Claude remains sole public pusher. Root verifies the actual public commit and workflows.

## Publication contract
Publish Stage1 and Stage2 together, including any stopped stage and original failed numerical receipts.
Do not change the old scalar bundle or decision record.
Every source hash in the freeze must exist publicly at its frozen bytes, or an explicit exception must be recorded.
Private machine paths use opaque public identifiers with a sanitization map.
The public saved-output checker requires an expected bundle-manifest SHA256.
It recomputes metrics and acceptance from published predictions, flags, labels and bootstrap indices, without inference.
Optional data regeneration is separate from metric recomputation.
