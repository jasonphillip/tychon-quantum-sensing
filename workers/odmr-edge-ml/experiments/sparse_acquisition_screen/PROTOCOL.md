# Sparse acquisition development protocol

Prepared: 2026-10-15. Status: PREREGISTERED PREPARATION.
The concrete qualification specification and adapter in QUALIFICATION.md supersede earlier placeholder qualification guidance below.
Owner: Codex sparse-acquisition lane.
Numerical registration and stopping authority: root Codex.
Data custody and publication remain with the coordinating session.

## Question and intended use

Can frequency selection reduce useful acquisition time under equal information and calibration?

The first screen compares classical policies.
It cannot establish neural superiority, measured-sensor accuracy, or novelty.
It also cannot establish NV superiority over a fluxgate or Hall sensor.

This is a fixed-axis, biased, stationary-field simulation.
It is relevant to a calibrated laboratory sensor or a fixed current-monitoring geometry.
It is not an orbital navigation experiment.
A time-varying tracking or camera-array claim needs a different protocol.

The existing known-axis result provides a classical accuracy reference.
Its consumed test data and seeds remain sealed against reuse here.
No current-file relabeling changes any earlier field-accuracy verdict.

## Prior art and stop on an adequate classical solution

Adaptive NV measurement already has measured precedent.
Dushenko et al. report an adaptive Bayesian experiment:
https://www.nist.gov/publications/sequential-bayesian-experiment-design-optically-detected-magnetic-resonance-nitrogen
Haim et al. report neural sparse-spectrum estimation:
https://flore.unifi.it/retrieve/1758f1f7-239c-4671-a618-235375ede342/Haim_2025_Mach._Learn.__Sci._Technol._6_025074.pdf

These citations motivate strong comparisons, not a new-method claim.
The linked primary sources were inspected during the preceding research lane.
The present code introduces no learned acquisition policy.
Do not add one because a weak classical implementation loses.

If a qualified classical policy meets the practical requirement, stop the learned-policy proposal.
If decision cost removes acquisition savings, stop the embedded speed claim.
A reproducible boundary showing when adaptation helps can still be useful engineering evidence.

## Frozen physical scope

The source is experiments/scalar_information_limit/forward.py from base 4bb3a035ed708652af471f70114ccb4e91677d9a.
It uses the existing spin-1 Hamiltonian and fixed-amplitude spectrum.
The fixed-amplitude factor is 0.9957299574916568.
This lane does not re-estimate that factor.

The spectrum uses the existing 100 frequencies from 2820 to 2920 MHz.
Policies choose only among those frequencies.
The simulator does not interpolate a hidden noisy spectrum.
The evaluator renders deterministic means and draws a count only after a frequency request.

All methods know the same positive field direction, 250 uT bias, and model.
The field prior spans 20 to 70 uT.
The nuisance priors span center shift 0 to 0.6 MHz and linewidth 4 to 6 MHz.
Default grids have 101 field, five center, and three linewidth values.
Their joint discrete prior is uniform.
The field grid resolution is 0.5 uT.

Fixed values are theta=0, phi=0, slope=0.02, contrast=0.015,
temperature_K=293.15, mw_scale=1, and gradient=0.196875.
Every registered case must state every Point field.
Truth can lie between grid nodes.
Do not choose only on-grid truths.

This is a correctly specified model experiment.
It does not test unknown calibration, drift, optical shot-noise excess, or varying instrument response.
Model mismatch and dynamic tracking require separate fresh development registration.
Do not silently add those effects after seeing this screen.

## Photon and timing model

For frequency i, dwell t, and rate R, the count is Poisson(R t mu_i).
Here mu_i is the inherited normalized fluorescence mean.
R is a declared normalized count-rate scale.
It is not a measured laser flux or detector calibration.

Default R is 5e8 counts per second at normalized fluorescence one.
Default dwell is 0.01 second.
The corresponding exposure is five million normalized photons per action.
The rate is a simulation parameter, not a hardware sensitivity claim.

Independent Poisson counts are assumed conditional on the stationary field.
The simulation omits laser intensity noise, detector dead time, background-count uncertainty,
frequency-dependent dwell overhead, and temporal drift during an episode.
Its conclusions must retain these limits.

The old Gaussian-SNR generator is not reused for noise.
A fixed per-bin SNR does not define how uncertainty scales with dwell.
A Poisson model gives an explicit exposure and variance relationship.

The first frequency request costs 0.0003 second settling.
Every frequency change costs the same settling time.
Repeating a frequency adds dwell without a new settling charge.
This is an assumed instrument model, not a measured synthesizer specification.

Every policy receives at most 24 primary actions and eight recovery actions.
Recovery uses the same fixed schedule for all policies.
Its sequence position continues from the total acquired action count.
Recovery therefore does not receive extra data or uncharged exposure.

The internal stop occurs when the 95% grid interval has half-width at most 2 uT.
This is an internal precision condition, not guaranteed 95% coverage.
All errors remain in the report, including falsely narrow intervals and failures.

## Policies and estimator permissions

Uniform is a fixed space-filling schedule over all 100 bins.
It uses bit-reversal ordering, with no observed-count dependence.
It is not an ascending-frequency sweep.
The schedule visits each bin once per 100 actions.

Coarse-to-fine uses eleven evenly spaced pilot bins.
It then cycles through estimated slopes around the two field-sensitive lines.
Its estimate comes from the same posterior used by every policy.

Nuisance Fisher uses finite differences at the posterior mean.
Its covariance includes field, center, and linewidth.
It approximates the field-variance reduction from one Poisson observation.
It divides that gain by dwell plus applicable settling time.
This is a local design approximation, not a globally optimal oracle.

Bayesian variance uses the same exact Poisson posterior update.
Its acquisition utility approximates expected posterior field variance.
It uses 16 posterior representatives and five Gaussian quadrature nodes by default.
Hypothetical counts are rounded Gaussian approximations to high-count Poisson outcomes.
This design approximation refuses expected counts below 10000.
The real acquisition oracle always draws actual Poisson counts.

The shared estimator is the marginal posterior median.
All methods may exploit the same prior, nuisance model, and fixed calibration.
None receives truth, a full noisy spectrum, unmeasured counts, or future fields.
Policies receive a calibrated model table, posterior weights, and past observations only.

Each policy uses the same case seed to initialize its acquisition RNG.
Different selected means need not produce identical noise draws.
Comparisons pair latent cases, not identical observed spectra.
Do not claim matched photon realizations across unequal actions.

## Accounting and output

Report acquisition dwell, settling, decision CPU wall time, posterior-update and estimate time,
recovery actions, exposure photons, detected photons, and complete observation traces.
Report shared model-table construction time separately.
Count model-table construction once in the numerical ledger.
Publish its cost and an explicit amortization assumption before claiming deployment latency.

Modeled total time includes dwell, settling, decision time, estimator time, policy construction, and episode posterior setup.
Simulator truth-rendering cost is excluded from modeled instrument time.
It remains included in the numerical execution ledger.
Source import time and process startup are also ledger costs, not instrument timing.

The driver is single-process CPU code.
Use one numerical worker, one BLAS thread, no GPU, and at most two GiB for this screen.
No resource request expands the existing parent campaign caps.
No training or final evaluation is authorized by this protocol.
Measured decision time applies only to the host used.
It does not establish FPGA energy or embedded latency.

Save every row before continuing.
Keep failed-precision rows in every metric.
Report MAE, p90 error, maximum error, interval coverage, narrow-but-wrong intervals,
precision failures, recovery usage, total time, and photon exposure for all four policies.
Never normalize error by only successful fits.

## Root registration required before numerical work

Root first registers a numerical preflight and its accounting allowance.
The preflight must cover the prepared unit tests and convergence checks.
The initial tests are unexecuted; syntax success is not numerical validation.

Required preflight checks:
1. Verify the inherited forward-model hash and finite positive count means.
2. Verify posterior normalization and the Poisson variance relationship.
3. Verify no extra data, future field, or hidden-count access crosses the policy interface.
4. Verify all recovery and timing costs enter the output.
5. Compare Bayesian design at 16/5 and 32/9 representatives/nodes on fixed preflight beliefs.
6. Refine field, center, and linewidth grids on those same non-evaluation beliefs.
7. Reject a baseline qualification if chosen frequencies or expected gains remain unstable.

For steps 5-6, predeclare acceptable gain differences, action differences, and maximum preflight cost.
No convergence evidence exists yet.
Do not choose tolerances after inspecting policy performance.
If the bounded preflight cannot qualify the Bayesian baseline, stop and report that limitation.
Do not benchmark a weak approximation and call its loss an adaptive-policy victory.

After preflight passes, root supplies at most eight fresh development cases.
Those cases must span the field and nuisance ranges and include off-grid truth.
Eight cases can expose an implementation or cost failure.
They cannot establish a one-percent failure rate or population superiority.

Root freezes the source hashes, protocol, acquisition parameters, case manifest, and seed audit.
The seed audit must cover every consumed scalar, vector, and information-limit campaign.
The new noise seeds must be unique integers in the audited 64-bit development namespace.
The unit-test seed namespace is separate and cannot supply evaluation cases.

The registered gate needs:
- status ROOT_APPROVED_DEVELOPMENT_SCREEN
- allow_training false and allow_final_evaluation false
- preflight_passed true, with evidence recorded in the parent registration
- source_files mapping the five required source/protocol files to SHA256 values
- maximum_cases between one and eight
- cases_sha256, seed_audit_path, and seed_audit_sha256
- acquisition mapping the exact Acquisition fields to registered values

The seed-audit file needs status pass, cases_sha256, all_consumed_campaigns_checked true,
excluded_seeds, and approved_noise_seeds.
No such approval or case file is included in this preparation.

Root's remote supervisor must hold its per-job lock and a central Spark2 reservation.
It must update every applicable shared ledger and enforce the tighter remaining cap.
The child expects TYCHON_ACTIVE_NUMERICAL_CONTEXT to name a temporary JSON receipt.
That receipt needs status running, parent_pid, gate_sha256, and shared_lock_path, central_reservation_id, central_spec_sha256, and accounting_authority.
The central authority is spark2-reservation-journal-v1.
The parent PID must identify the process that launches the driver.
The driver checks that the supervisor holds the per-job lock and binds the reservation environment.
These checks prevent accidental unregistered use; they are not a security boundary.

Do not invent a second independent numerical ledger for this lane.
Use the new remote supervisor adapter; preserve every legacy wrapper and ledger.
The parent must enforce CPU, wall, memory, thread, and worker limits.
A receipt alone does not enforce these resource limits.

## Falsifier and stopping rules

A candidate acquisition benefit requires at least 25% lower median modeled total time
than the best qualified classical alternative at comparable error and failure behavior.
The future sealed gate must define adequate sample size and statistical uncertainty.
The eight-case development screen can only nominate or reject that hypothesis.

For this initial screen, reject further work if:
- Any data custody or accounting check fails.
- Any policy receives undeclared information.
- Bayesian/grid convergence cannot pass within its registered preflight allowance.
- Adaptive decision time cancels its acquisition saving.
- A simple fixed or coarse-to-fine policy meets the practical requirement.
- Apparent savings require discarding failures or excluding recovery.
- No distinct, falsifiable learned-policy hypothesis remains.

A numerical failure does not authorize automatic tuning and rerunning.
Root decides any repair within the registered budget and records the consumed cases.
Preserve all original outputs.
Do not run a final test, select new seeds, or restart an experimental cycle here.

## Commands after registration only

The following commands are templates, not authorization.
Use the root accounting wrapper around the exact Python command.
Set OMP_NUM_THREADS=1, OPENBLAS_NUM_THREADS=1, and MKL_NUM_THREADS=1 before Python starts.

Numerical tests:
python -m unittest discover -s tests -p test_sparse_acquisition_screen.py

Development screen:
python experiments/sparse_acquisition_screen/run_screen.py --gate ROOT_GATE.json --cases FRESH_CASES.json --out NEW_OUTPUT_DIRECTORY

Run from this isolated worktree.
Use absolute paths when constructing the real invocation.

Expected time is unmeasured.
Preparation estimate: one to five minutes for focused unit tests and small-model checks;
five to twenty minutes for eight cases across four policies, depending on Bayesian design cost.
A careful convergence preflight may need more.
Register a hard allowance before execution; stop rather than exceed it.
Code preparation and review fit within one working day.
A new defensible measured-data or sealed superiority result is not promised within that time.
