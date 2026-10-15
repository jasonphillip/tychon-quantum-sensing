# Cardiac measured-data pilot protocol

Prepared: 2026-10-15, EDT.
Status: DRAFT_ROOT_REVIEW. Metadata incomplete. No signal access or numerical approval.
Immutable dataset: Zenodo 20703822. Scope: retrospective software processing of public recordings.

## Question and truthful claim

Can causal classical processing produce a reproducible, acquisition-band-limited MCG average with fewer recorded beats?
The primary advantage would be reduced elapsed recording time at matched reproducibility and output yield.
A reproducibility reference is noisy. It is not independent magnetic ground truth.
This protocol cannot establish diagnostic accuracy, clinical utility, or individual-beat recovery.
It does not compare NV diamonds against OPM, SQUID, Hall, or fluxgate technology.
No neural accuracy advantage is assumed.

The default candidate is one non-neural, quality-weighted completed-beat average.
The candidate is conditional on usable metadata and an identifiable quality feature.
No learned denoiser is prepared. There is no defensible clean supervised target yet.
A strong classical result can be the final result.

## Evidence and scope

Primary paper: [Human cardiac measurements with diamond magnetometers](https://pmc.ncbi.nlm.nih.gov/articles/PMC13580569/).
Machine-readable primary paper: [Europe PMC XML](https://www.ebi.ac.uk/europepmc/webservices/rest/PMC13580569/fullTextXML).
Immutable data: [Zenodo 20703822](https://zenodo.org/records/20703822), DOI 10.5281/zenodo.20703822, CC BY 4.0.

The following statements come from the paper, not from our own signal measurements.
ECG was recorded simultaneously for beat timing.
The OPM array was recorded before diamond measurements at marked chest positions.
OPM and ECG must never become paired clean MCG training targets.
Acquisition and processing differ across sites.
The Q.ANT data had acquisition filters and an 8 Hz high-pass operation described in the paper.
The other sites used different filters and recording durations.
The published averaging counts were 12,000, 300, and 2,000 for different sites.
Those counts do not establish relative intrinsic sensitivity.
The paper's adaptive BSS cardiac example is a simulation.
Measured gradiometry under applied magnetic disturbances must not be relabelled as simultaneous human cardiac ground truth.

## Eligibility before Freeze A

Claude owns the downloaded original and its custody hashes.
Do not use partial ZIP files. Do not execute downloaded notebooks or scripts.
Metadata and header inspection must identify each file's experiment and recording provenance.
The template intentionally fails until evidence fills every required field.

Require:

1. Repository checksum, byte count, local SHA256, immutable version, and license.
2. Channel count, delimiter, exact header boundary, time column, units, sample clock, and duration.
3. Exactly identified magnetic and ECG channels, with evidence beyond filenames.
4. Signed magnetic calibration, offset, uncertainty, and applicability to this recording.
5. Known acquisition filters, including removed bands and any documented delay.
6. Session identity and related-recording grouping. Unknown participants limit claims to within-recording reproduction.
7. Enough complete, disjoint time blocks after guard intervals.
8. For cancellation, a synchronized noise-reference channel with bounded cardiac leakage and explicit supporting evidence.

An ECG channel is not a noise reference.
A second magnetic channel is not automatically a cardiac-free noise reference.
Separately measured noise, OPM, or coil-response files are not synchronized targets.
Without a valid reference, skip adaptive cancellation; preserve that eligibility failure.
Without calibration or timing, stop scientific comparison and report feasibility only.
Published calibration notebooks may supply formulas or metadata after static inspection.
They must not be executed or trusted as authoritative without verifying their inputs and units.

## Splits and leakage prevention

Root freezes exact file IDs and time intervals before any waveform inspection.
Participant/session labels come from metadata, never guessed from names.
If independent participants exist, assign whole participants before signals are read.
If participants repeat across sessions, every related session stays with that participant.
With sufficient groups, use deterministic sorted group IDs: first 60% development, next 20% validation, last 20% held evaluation.
Minimum: three independent groups. Round cut points so every group is assigned once.
Do not call those groups independent people unless metadata establishes that fact.

For one participant or unresolved participant identity, allow only a within-recording claim.
Never pool unknown files as independent subjects.
Within each eligible recording, use the first 50% for development, next 25% for validation, and last 25% for held evaluation.
Discard a 60-second guard around both cut points.
Increase that guard if a filter state, template, or beat window needs more history.
Freeze those expanded intervals before processing.
The timestamp origin is the first recorded sample. The loader reads no signal values outside the allowed interval.
A recording cannot cross partitions in an unrecorded cache or preprocessing fit.

Within a validation or held block, reserve disjoint contiguous candidate and reference subblocks.
Each subblock must contain enough accepted beats for the frozen comparison.
Use 60-second guards between them, or longer if necessary.
Do not alternate odd/even beats; correlated drift would make that reference misleading.
Require at least four candidate/reference block pairs per claimed session.
If duration prevents these blocks, reduce the claim to faithful reproduction; do not shrink guards after scoring.
All beat windows are complete, nonoverlapping, and contained inside one permitted block.
Reject windows crossing a gap, reset, split boundary, or neighbouring accepted beat.
All rejected beats count toward elapsed time and output yield.
Fit thresholds, scaling, filters, calibration corrections, and any template only on development blocks.

## Frozen classical references

All methods receive identical channels, timing, calibration, and allowed past information.

- Raw calibrated data plus the fixed acquisition response.
- Causal second-order band/filter chain and site-specific notch frequencies supported by the acquisition metadata.
- Causal filtered completed-beat mean, sample-wise median, and 10% trimmed mean.
- A frozen development-template predictor as a deliberately strong null for a stationary average.
- If a valid noise reference exists: fixed-gain subtraction and 16-tap NLMS, step size 0.05.
- If future information is used for a published reproduction, label that output offline.
  Never compare its delay to a causal method or use it as an independent target.

The candidate is the same causal chain followed by bounded quality-weighted averaging.
Its one quality feature is pre-QRS out-of-band residual energy, only if acquisition metadata leaves an informative band.
Estimate quality before accepting the complete beat. Preserve the resulting decision delay.
The quality feature must not measure QRS/T amplitude or correlate weights with the desired output.
Use one frozen reciprocal-energy weighting formula, clipped to a 4:1 weight ratio.
Fit the energy floor on development only. At most three predeclared floors may be considered.
If an informative noncardiac band is unavailable, do not invent one. Stop this candidate.
Do not implement a learned policy or train against ECG-shaped targets.

The source currently supplies causal filter, subtraction, NLMS, and aggregation primitives.
It does not yet implement the complete benchmark, ECG trigger calibration, candidate quality feature, or independent verifier.
Those require the actual recording schema and a root-approved Freeze A.
This is preparation, not a runnable scientific comparison.

## Proposed acceptance, to freeze before scoring

A candidate/reference pair compares disjoint averages of the same session and acquisition response.
A reference uses 200 complete beats. Candidate budgets are 25, 50, and 100 complete beats.
Every method receives the same acquired beats and the same ECG timing.
Also report total recorded beats, rejected beats, wall-clock recording seconds, and effective sample size.
Do not hide low yield behind a small accepted-beat count.

Proposed primary criterion: at least 25% less elapsed recording time than the best classical reference.
Require this at a common registered proxy-error threshold and at least 90% output yield.
The threshold must be set from development reference-to-reference reproducibility, then frozen.
Reference-to-reference disagreement establishes the measurable proxy noise floor.
Stop if that floor cannot distinguish methods or if blocks are detectably nonstationary.

Secondary guards proposed for root review:

- No more than 5% relative worsening in normalized proxy RMS error.
- No more than 5% relative change in QRS peak-to-peak amplitude.
- No more than 10 ms shift in the registered peak timing.
- No polarity change where polarity is established by the session reference.
- No more than 10% widening of the registered QRS duration.
- No claim about P/T components outside the acquisition passband.
- Candidate must beat the frozen-template null on held block variation, not merely resemble a typical heartbeat.

These are engineering demonstrator limits, not medical tolerances.
Root must confirm whether sampling and acquisition bandwidth make each limit resolvable.
If a guard is unresolvable, stop that comparison rather than relaxing it after outputs.
Report session-level and block-level results, including every failed block.
No p-value or participant-generalization claim is justified by one session.
A method that suppresses both noise and cardiac structure fails, even if its trace looks smoother.

## Timing, costs, and saved evidence

Causal filtering uses past/current samples only. Never use filtfilt.
Beat averaging is post-beat processing; pretrigger windows add buffering and completion delay.
Report acquisition duration, filter delay, beat completion delay, CPU processing cost, and memory separately.
Do not equate faster arithmetic with fewer required measurements.
Reset state between partitions. Charge warm-up and rejected data.

Save input hashes, schema, split intervals, trigger indices, accepted/rejected flags with reasons,
calibration, filter coefficients, frozen templates, per-block predictions, reference averages, and method settings.
Save prediction timestamps and actual data-dependency intervals.
The independent saved-output verifier must recompute metrics without training, inference, or raw private dependencies.
Publish enough trace excerpts or derived arrays under the dataset license to reproduce every reported metric.
Preserve all original evidence and failure outputs.

## Limits and stopping

No numerical work starts before root freezes source, schema, splits, metric, and accounting.
Campaign limits: 16 CPU-hours, 2 GPU-hours, 4 cumulative numerical wall-hours for this lane.
Tests/qualification: 15 minutes wall total; first data qualification: at most 10 minutes.
Development: 150 minutes; first candidate run: at most 30 minutes.
Final: 30 minutes. Verification: 45 minutes.
These are ceilings, not an obligation to use the budget.
CPU jobs use at most four threads and 8 GiB.
No training is planned. Training above 1,000 parameters would require CUDA and a new frozen candidate choice.
One final held-group comparison follows a passing development gate.
No tuning, restart, or new model after a failed held gate.

Stop for insufficient metadata, inadequate block duration, invalid reference, unstable proxy,
unresolvable morphology, leakage, failed checks, or resource limits.
A reproducible classical result or bounded feasibility failure completes the lane.
No hardware, FPGA, Beelink, service changes, installs, paid compute, or purchases.
