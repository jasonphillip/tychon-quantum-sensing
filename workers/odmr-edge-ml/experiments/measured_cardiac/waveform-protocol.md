# Recorded-voltage reproducibility screen

Prepared: 2026-10-15. Status: DRAFT_ROOT_REVIEW before any voltage access.
Owner: cardiac implementation lane. Root owns approval, execution and continuation.

## Meaning and immutable evidence

This protocol evaluates reproducibility of a processed, recorded voltage waveform.
It does not estimate unfiltered cardiac magnetism, magnetic sensitivity, clinical accuracy or diagnostic performance.
ECG supplies timing only. No ECG amplitude or morphology becomes a target.
The separately recorded OPM data remain excluded.
Unknown acquisition filters prevent bandwidth-recovery or physiological-latency claims.
Different devices prevent cross-participant voltage-amplitude comparisons.
Participant labels describe archive groups, not a verified clinical cohort.

The timestamp-only qualification passed all twelve recordings, according to the root's registered run.
Its summary SHA256 is b109aaf7f2da8b147ecf8b32966f9665b8ddf14ea4888db578e8f6df214a01d6.
The original manifest, timestamp qualifier, protocols and qualification evidence retain their original bytes.
This document supplies the subsequent waveform protocol. It does not rewrite the qualification.

P1-S01 through P1-S10 constitute development. No session may be omitted.
P2-S01 is validation. P3-S01 remains held until unchanged validation passes.
Each recording belongs wholly to one partition.
No random windows, overlapping beats or participant mixing create extra test examples.
These are ten development sessions from one participant-label group and two single-recording transfer checks.
They cannot support population confidence intervals or clinical generalization.

## Exact data access

The immutable archive and original manifest must match their custody hashes.
The gate must pin every package Python source, all three protocols and the qualification summary.
An active accounting supervisor must hold the per-job lock and match the approved hash and parent PID.
The loader opens only the complete approved participant partition.
It rechecks member identity, header, timestamp hash and sample counts against the qualified outputs.
It converts voltage text only inside the three qualified sample-index ranges.
All other voltage-column bytes remain unconverted, including guards and the remainder of each recording.

The candidate block is [0,120) seconds. Reference A is [180,360); reference B is [420,600).
The original exact first and stop-exclusive sample indices control access.
The 60-second gaps remain unused. No outcome can change these intervals.
The first timestamp in each approved block defines its local clock.
Each block resets its causal filter state. Its first ten seconds count as warm-up.

## Frozen trigger and completed-beat processing

ECG processing uses a second-order Butterworth 5–25 Hz causal bandpass.
The detector squares its output and applies a trailing 50 ms arithmetic mean.
Its fixed threshold is median plus six median absolute deviations of the first ten seconds' energy.
A nonpositive threshold produces no triggers and fails the count/yield gate.
An upward crossing starts a 50 ms confirmation window.
The maximum energy within that completed window supplies the timestamp.
The decision occurs at the window end. The refractory interval is 300 ms from the chosen maximum.
No backward alignment, manual peak choice or reference-dependent correction is allowed.
This detector's timestamp is an algorithmic ECG trigger, not a clinical R-peak annotation.

Each accepted voltage window spans trigger −200 ms through +400 ms.
The window must start after warm-up and complete before its acquisition budget ends.
It must not overlap the last accepted window. Rejected triggers remain in the yield denominator.
The detector confirmation must finish before the beat window completes.
All methods use exactly the same triggers and accepted beat windows.
Candidate durations are exactly 30, 60 and 120 seconds, including warm-up and completion.
Each duration processes only its prefix. Later samples cannot change earlier outputs.

Raw voltage and a fixed causal 50 Hz plus 60 Hz Q30 notch pipeline are retained.
The common references use the notch pipeline followed by arithmetic beat averaging.
Every method scores against these same two references separately.
No method constructs its own scoring target.
Each completed beat is linearly interpolated onto 1200 fixed samples at 2000 Hz, from −200 to +399.5 ms.
Both original sample rates are lower than 2000 Hz. This interpolation adds no measured bandwidth.
Each completed beat loses its own arithmetic mean, equally for all methods.
This removes DC and limits the scientific claim to the centered, processed voltage waveform.

## Reference eligibility: stop before candidate comparison

Both reference blocks require at least 100 complete accepted beats and 90% trigger-to-output yield.
The two reference averages must satisfy all following prospective conditions.

- Worst directional normalized RMS error is at most 0.5.
- Their cosine correlation is at least 0.8. Centered beats make this equivalent to Pearson correlation here.
- Their dominant absolute peaks have the same sign.
- Each peak amplitude is between 0.8 and 1.2 times the other reference's amplitude.
- The dominant absolute peak times differ by at most 20 ms.
- Each energy-spread width is between 0.8 and 1.25 times the other width.

Normalized RMS error is sqrt(sum((estimate-reference)^2)/sum(reference^2)).
A reference with zero power is ineligible. No amplitude epsilon rescues a flat reference.
Energy-spread width is the time standard deviation weighted by squared waveform amplitude.
These limits require clear repeated structure before comparing estimators.
They are engineering tolerances for this proxy, not physiological normal ranges.
They can reject valid recordings with biological change or poor trigger placement.
All sessions in the current partition must pass. Any failure stops that phase before method comparison.
Save the rejected reference results and complete counts. Do not relax gates or choose easier sessions.

## Finite methods and normalization

There are six classical references: raw and notch processing, each with mean, median or 10% trimmed mean.
Trimming removes floor(number_of_beats/10) values from each end at each waveform sample.
The strongest passing reference at each acquisition duration determines the classical time requirement.
There is no neural model and no training.

The sole candidate family uses the fixed notch pipeline and completed-beat quality weighting.
Its quality value is voltage variance in the 100 ms immediately preceding the trigger.
That interval can contain physiology. It is not a proven independent noise measurement.
The normalization scale is the median variance of disjoint 100 ms windows within that recording's first ten seconds.
This identical input-only normalization applies prospectively to P1, P2 and P3.
No reference block, later duration, performance score or held-participant fit changes the scale.
A nonpositive scale makes the candidate ineligible.

The only three floor multipliers are 0.1, 0.25 and 0.5.
For variance q, scale s and multiplier f, weight = clip(1/(q/s+f), 1/(4f), 1/f).
The maximum weight ratio is four. No beats disappear through weighting.
P1 selects one multiplier. P2 and P3 reuse it unchanged.

Design correction before voltage access: a P1-only absolute voltage-variance scale was considered and rejected.
Different uncalibrated devices need not share voltage gain.
The fixed per-recording warm-up normalization prevents arbitrary gain differences from controlling the weights.
This is prospective input normalization, not held-group parameter tuning.

## Common acceptance threshold and null guards

The common error threshold is clip(1.5 × median(P1 reference-pair errors), 0.15, 0.5).
It freezes after the complete P1 reference gate passes.
Each estimate must satisfy that threshold against both references independently.
Each comparison also requires the same peak-sign, amplitude, 20 ms timing and width guards defined above.
Each candidate duration requires at least ten complete beats and at least 90% yield.

The constant null is the zero waveform after the identical DC-removal convention.
The template null uses a bank of unit-RMS P1 reference-pair averages.
Development excludes the current P1 session from its bank.
Validation and held evaluation use the complete frozen P1 bank.
For each template, fit only a signed scalar amplitude against the current candidate-block notch mean.
Select the template with smallest residual to that candidate-block mean, never against the scoring references.
This permits a strong simple-template explanation without leaking reference values.

The candidate must beat both null errors by at least 10%.
Neither null may pass the full common acceptance threshold and preservation guards at that duration.
A generic-template or flat-output explanation therefore prevents an advantage claim.

## Development selection and continuation

At each duration, compare the candidate with the earliest passing method among all six classical references.
The candidate must require at most 75% of that method's acquisition time.
With the fixed 30/60/120-second grid, observed successful reductions are at least 50%.
Do not interpolate a claimed 25% saving between these budgets.
If no classical reference passes by 120 seconds, mark the ratio undefined; do not infer an unlimited advantage.
Method computation time is reported separately from acquisition time.
The 600-second evaluation record includes the two later reference blocks and unused gaps.
Those later blocks are evaluation evidence, never online candidate input.

Select the floor with the most P1 sessions meeting the complete advantage gate.
Ties choose the smaller numerical floor. No further settings may be tried.
At least nine of ten P1 sessions must pass that gate, and all ten reference pairs must be eligible.
Freeze threshold, multiplier, template bank, code and commands only after independent saved-output verification.
P2 must then pass the same gates unchanged. Only then may root authorize P3 once.
A P3 pass describes that one held recording. It does not establish clinical or population performance.
Every gate failure ends the route with a bounded negative or feasibility result.

## Outputs and independent verification

Save neutral-ID completed beats, quality values, trigger/decision/completion times, accepted counts and prediction arrays.
Save both noisy reference arrays, all metric components, nulls and finite selection scores.
Save byte-identical metadata inputs, source/protocol hashes and qualification indices.
No participant names, filenames from the archive or raw ECG traces are needed in the evidence package.
Partial results remain after interruption. Never overwrite an output directory.

verify_voltage.py uses independent arithmetic and does not import estimator or metric implementation code.
It checks hashes, full participant coverage, time-window containment, prefix consistency, aggregates, weights,
template nulls, individual proxy metrics, gates and final selection from saved artifacts.
It does not reconstruct ECG triggering or causal filtering from these saved completed beats.
Those transformations require source review, manufactured tests and immutable input provenance.
This limitation must remain explicit in publication.

Verifier exit zero means a reproduced scientific PASS.
Exit two means a successfully reproduced scientific STOP.
An exception means checker or artifact failure, not a scientific verdict.

## Commands and limits

Use the root's reviewed accounting wrapper for every numerical launch.
Use configured absolute paths. No hardware, GPU, paid compute or service change is required.

```sh
cd "$SOURCE"
"$PYTHON" -m unittest discover -s "$SOURCE/experiments/measured_cardiac/tests" -v
"$PYTHON" -m experiments.measured_cardiac.evaluate_voltage --phase development --archive "$DATA" --manifest "$SOURCE/experiments/measured_cardiac/manifest.voltage.json" --qualification "$QUALIFICATION" --approval "$APPROVAL" --approval-sha256 "$APPROVAL_SHA256" --out "$OUTPUT"
"$PYTHON" -m experiments.measured_cardiac.verify_voltage --input "$OUTPUT" --out "$VERDICT"
```

Validation adds --phase validation and --frozen "$FROZEN" instead of --phase development.
Final adds --phase final, --frozen "$FROZEN" and --validation "$VALIDATION_SUMMARY".
Each phase needs a different root-approved gate and a new output directory.
The templates cannot authorize themselves.

Suggested first development job: one core, 2 GiB, 1800 CPU seconds and 1800 wall seconds.
Suggested validation/final jobs: one core, 2 GiB, 600 CPU seconds and 600 wall seconds each.
Suggested verification: one core, 2 GiB, 600 CPU seconds and 600 wall seconds per phase.
These remain subject to the shared lane, stage and campaign ledgers.
Expected extraction and processing is a few minutes, but no waveform runtime has been measured.
Stop on a cap, preserve evidence and request root review. Do not automatically restart or change a gate.
