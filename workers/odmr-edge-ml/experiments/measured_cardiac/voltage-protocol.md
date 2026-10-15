# Voltage-domain cardiac qualification and prospective study

Prepared: 2026-10-15, EDT.
Status: DRAFT_ROOT_REVIEW. No timestamp qualification or waveform evaluation has run.

This revision supersedes magnetic-calibration requirements for the voltage-only route in protocol.md.
It does not repair the conflicting calibration evidence.
The recorded voltage waveform is the object of study.
It is not the unfiltered physiological magnetic waveform.

## Three distinct routes

| Route | Requirement | Permitted result | Current state |
|---|---|---|---|
| A: recorded-voltage reproducibility | Verified archive, channel roles, exported timestamps, stable sampling, grouped split | Within-session reproducibility versus recording duration, in volts or dimensionless error | Timestamp qualification prepared |
| B: reference-noise cancellation | Route A plus a simultaneous noise reference with bounded cardiac leakage | Observed-voltage noise suppression with preservation checks | Ineligible: ECG is not that reference |
| C: absolute magnetic evaluation | Applicable calibration, units, uncertainty, acquisition response, and physical reference | Calibrated field or sensitivity statements | Ineligible: calibration applicability/units and filters unresolved |

Route A does not require a V-to-T conversion.
It cannot support pT/nT amplitude, T/sqrt(Hz) sensitivity, absolute physiological morphology, clinical accuracy, or sensor superiority.
No cross-device or cross-participant voltage-amplitude comparison is permitted.
Unknown filters mean no claim of recovered bandwidth or unfiltered physiological shape.
ECG supplies timing only. Separately recorded OPM data remain excluded.
The paper's simulated BSS example is not a measured paired target.

## Immutable metadata

Use manifest.voltage.json.
It selects all12 raw ECG-plus-NV recordings through SHA256 hashes of ZIP member names.
Names remain private. Public identities are P1, P2, P3 and their neutral session IDs.
The archive SHA256 is b3d79874553f3d8a9434a5daba1002765c810b134f98697b1f0cb58f09232e1f.
Custody verified the immutable version20703822 and its CC BY4.0 license.

P1 has ten recordings, ordered by header date/time, on three dates.
P2 and P3 each have one recording.
These are participant-label groups from custody, not a verified clinical cohort.
P3's filename date differs from its header date. Preserve both facts; use the header for ordering.
Do not infer site identity from filenames or map unknown acquisition settings across devices.

## Timestamp-only qualification

Run qualify_timestamps.py only through a root-approved qualification reservation.
The private approval must state access_mode=timestamps_only.
It pins the complete source, both protocols, manifest, approval authority, and permitted recording IDs.
A timestamp-only token cannot authorize the signal-value loader.

The program reads the compressed member bytes and decodes only each row's time prefix.
It does not decode, convert, print, save, or fit the waveform value column.
It saves incremental per-recording JSON so a timeout preserves completed evidence.

Prospective conditions, fixed before numerical outputs:

1. The exact archive and member CRC/size/name-hash match custody.
2. Seven comment header lines precede semicolon-separated time/value rows.
3. Exactly two channel blocks exist, with a single time restart.
4. ECG and NV blocks have equal row counts and exactly identical exported timestamp arrays.
5. Each block is strictly increasing. Duplicate, missing, reordered, or nonfinite times fail.
6. Every interval differs by at most2% from the whole-block mean interval.
7. Ten contiguous timestamp chunks differ by at most0.1% in mean interval.
8. Each recording covers at least600seconds.
9. No block exceeds4million rows, and no text line exceeds512bytes.
10. All12 recordings must qualify. No silent removal of a failing recording is allowed.

The reported timeline can qualify sample-index pairing.
It does not prove the absence of analog, digital, or channel-specific group delay.
Therefore, even a PASS does not authorize physiological ECG-to-MCG latency claims.
A mismatch stops the route. Do not estimate a waveform-dependent alignment correction.
A malformed timestamp never gets interpolated.

The exact data windows are defined before values:
candidate [0,120) seconds; reference A [180,360); reference B [420,600).
The60-second gaps prevent direct overlap.
Timestamp qualification translates these bounds into exact sample indices.
The first recorded timestamp defines time zero.
These windows are prospective resources, not a claim that180seconds gives a clean reference.

## Partitions and future access

P1-S01 through P1-S10: development.
P2-S01: validation.
P3-S01: one held-session evaluation.
Every recording belongs wholly to one participant partition.
Do not randomize windows, beats, files, or adjacent samples across partitions.
The candidate/reference windows are disjoint comparison subblocks inside that same partition.
They are not train/test mixing.

Only timestamps from all recordings are permitted by the present proposed qualification.
Waveform approval requires a new private gate with exact record IDs and sample/time intervals.
P3 waveform values remain inaccessible until Freeze B.
A participant split does not remove the device/filter confound.
Report the single held-session result without population generalization.

## Method alternatives to freeze after timestamp qualification

The first waveform stage must test whether the proxy is usable.
It must not begin by training a denoiser.

Use identical input voltage, permitted time history, ECG triggers, and candidate durations for every method.
Candidate duration budgets are30,60,and120seconds.
All record acquisition, rejected beats, trigger fitting, warm-up, and output completion time count.

Strong references:

- Identity voltage processing with completed-beat mean removal and arithmetic averaging.
- The same method with a causal Q30 notch at50and60Hz.
- Sample-wise median and10% trimmed mean over complete beats.
- A frozen development-template null, with any amplitude fit using candidate-block data only.
- A constant-output null.
- No adaptive cancellation unless route B independently becomes eligible.

One prospective non-neural candidate:
the same shared causal preprocessing with quality-weighted completed-beat averaging.
Use the variance of the preceding100ms NV-voltage window as the quality statistic.
Use a reciprocal-variance weight, bounded to a4:1 ratio, with a development-only floor.
At most three floor settings may be registered before development.
The statistic can contain real physiology. It is a quality heuristic, not an identified noise measurement.
All methods must receive the same permitted information.
If the candidate merely erases variation or matches a generic template, it fails.

ECG is used to locate triggers, never as an amplitude, shape, or denoising target.
Do not score success by correlation with ECG shape.
Use complete nonoverlapping beat windows. Reject windows crossing gaps or subblock bounds.
A future causal trigger/window implementation must freeze its completion delay and thresholds before scoring.
The published offline FFT filters can be reproduced separately, but cannot establish causal latency.

## Proxy and stopping gate

References A and B are disjoint noisy averages from the same recorded channel.
Their disagreement tests whether the observed waveform is reproducible enough for this study.
Neither reference is a clean magnetic target.
A physiologically changing signal can fail this proxy, even when correctly measured.
Such failure is a limitation of the evaluation, not evidence of bad physiology or a bad sensor.

Before method comparison, require sufficient complete beats in both reference blocks.
Freeze the minimum after timestamp qualification and before voltage access.
The proposed minimum is100beats per reference block.
If either block falls short, stop rather than shorten guards or extend into unapproved intervals.

Proposed practical advantage:
at least25% less elapsed acquisition time than the best classical baseline at a common recorded-voltage proxy threshold.
Require at least90% output yield.
The threshold must be set from P1 reference-to-reference variability, then frozen before P2/P3 scoring.
Preserve amplitude/polarity/timing/width of the recorded reference within declared tolerances.
These are recorded-waveform preservation tests, not physiological accuracy.
No useful advantage is accepted if a constant or frozen-template null explains the apparent improvement.
If reference disagreement is too large to distinguish methods, report feasibility failure.

This revision does not implement the full waveform evaluator or its independent verifier.
Those remain blocked until timestamp qualification passes and root freezes a defensible proxy.
No learned clean-target claim is currently available.
A negative feasibility result is a valid completion.

## Qualification limits and command

Proposed first qualification: one CPU core,1GiB memory,600CPU seconds,600wall seconds, no GPU.
Expected runtime is1–5minutes for about1GB of selected text, but this estimate is unmeasured.
Stop at the cap. Preserve partial JSON and receipts.
Do not repeat a failed qualification with relaxed tolerances.

Use configured absolute paths and the root's approved accounting wrapper:

```sh
cd "$SOURCE"
"$PYTHON" -m experiments.measured_cardiac.qualify_timestamps --archive "$DATA" --manifest "$SOURCE/experiments/measured_cardiac/manifest.voltage.json" --approval "$APPROVAL" --approval-sha256 "$APPROVAL_SHA256" --out "$OUTPUT"
```

The command is prepared, not executed.
Root must fill the private approval from timestamp-qualification.template.json.
Both approval templates intentionally remain unable to authorize execution.
