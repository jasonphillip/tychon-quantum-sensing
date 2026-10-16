# Fresh-acquisition widefield reconstruction: eligibility preparation

Status: source preparation. No new measured signal, manufactured test, numerical evaluation, or training has run.
The protocol is **DRAFT_ROOT_REVIEW**. Runtime entrypoints reject this status.
Root must freeze the protocol, source, custody, seeds, stage approval and numerical reservation before execution.

This implements the first eligibility stage only. A failed eligibility decision stops this formulation before training.
A pass permits a separate prospective development review; it does not authorize training automatically.
Old source, datasets, evaluation groups, reports and failures remain unchanged.

## Task and labels

The proposed task reconstructs reproducible spatial-spectral structure from one measured scan.
It uses repeated fluorescence spectra as references. It has no independently calibrated pixel magnetic-field labels.
Successful reconstruction would not establish sensing speed, instrument bandwidth, neural novelty or hardware performance.

The [source paper](https://www.nature.com/articles/s41598-022-22610-5) describes sparse fluorescent diamond spots and random crystal orientations.
It reports spots around4–5 pixels, frame/repeat positional drift around1–2 pixels, and mean linewidth16 MHz.
Nearby crystals need not have the same spectrum. Unrestricted image smoothing is therefore not a sound assumption.

All repeats of an acquisition stay together:

| Role | Files |
|---|---|
| Eligibility, training only | f1, f4 |
| Inner fit | f1, f4, f6, f10 |
| Inner stopping holdout | f12, f14 |
| Development | f2, f5, f13, f16 |
| Sealed confirmation | f7, f11, f17, f19, f20, f21 |

Only f1/f4 are accessed by this implementation. It has no other signal-phase entrypoint.
The f0/f8/f24 campaign is excluded. The six remaining acquisitions stay reserved.
Prior short range reads of f1/f12 must be recorded separately from signal decoding; neither is called byte-pristine.

## Fixed fluorescence-only geometry

Use the central512×512crop, starting at native pixel(y256,x384).
This preserves a documented central-field geometry; it does not establish field-wide representativeness.
Average repeat 0's first 10 and last 10 frequency frames to form the observation template.
No reference repeat is read for spot detection.

Smooth that image with Gaussian sigma 0.8 pixel.
Subtract its31×31median background.
Threshold at the residual median plus 6 times its robust noise scale, defined as 1.4826×MAD.
Use8-connected components of3–49 pixels and bounding width/height at most 7 pixels.
These limits target isolated4–5 pixel emitters while allowing threshold and drift broadening.
They are engineering choices, not measured optimal thresholds.

Use the positive residual-weighted centroid, rounded to the nearest pixel.
Require8 pixels of crop boundary clearance and every component pixel within 3 pixels of the centroid.
Dilate the component once with a3×3footprint inside a fixed9×9ROI.
Reject both components when their centroids lie within 12 pixels in Chebyshev distance.
This prevents mixing nearby, differently oriented crystals; it never chooses the brighter one.
Sort accepted IDs by y then x. Keep every accepted spot, including later failed measurements.
Store all geometric rejection reasons. Never select by reference agreement, resonance quality or outcome.

Require32–512 accepted spots per file, across at least 8 of the16 fixed128×128 spatial regions.
The lower limit supports a bounded spatial uncertainty calculation.
The upper limit bounds processing and public artifacts.
Failure means this particular ROI formulation is ineligible. It does not establish absent optical or magnetic signal.
If this input-only gate fails, do not decode reference repeats for that file.

## Registration and normalization

Registration operates on **each frequency frame**, including every repeat 0 frame.
It uses normalized, mean-centered fluorescence correlation over the selected9×9ROI pixels.
The template and coordinates always come from repeat 0 endpoints.
Search integer translations±3 pixels. Refine an interior peak with a separable three-point quadratic fit.
Clamp each subpixel refinement to±0.5 pixel, then sample with bilinear interpolation.
Require the total accepted translation to remain within±2 pixels and correlation at least0.90.
Report integer best/second margins below0.002 as ambiguous; ambiguity alone does not fail a frame.

The method handles a common translation. It does not handle local motion, rotation or arbitrary nonrigid drift.
For a failed frame, use zero shift and retain values plus its flag.
Require no more than 1% failed frames and no more than 1% clipped spot-frequency samples.
These are acquisition-quality conditions; failed spots never disappear from the result.

Reference frame registration produces targets only.
No reference-derived translation, footprint, brightness scale or correction enters observed inputs.
Use one normalization scalar for the whole acquisition: the median observed endpoint-template intensity over the fixed crop.
Save the scalar and apply it to all repeats. No per-spot/reference normalization can manufacture shared spatial contrast.
A shared scalar and ROI geometry still condition the comparison; they do not establish independent noise.

Store opposing±1 pixel reference perturbations for both spatial axes.
These quantify residual registration sensitivity without selecting a shift from spectral agreement.

## Repeat consistency and exact gate

For each selected spot, average repeats 1/2 intoA and repeats 3/4 intoB.
These are disjoint averages. Ordinal indices do not prove temporal independence or stationarity.
No per-frame timestamps are supplied by the checked schema.
Current, time, illumination and positioning remain potentially confounded.

Apply a fixed normalized Gaussian with sigma 3 MHz and radius 9 MHz to each spectrum.
Use only valid convolution bins, then subtract the average of the smoothed spectrum at±15 MHz.
At1.5 MHzspacing,168 bins remain.
This suppresses bin-scale noise while testing broad structure near the paper's16 MHzmean linewidth.
It is not a complete resonance detector or a test of every recoverable spatial feature.

Center the resulting feature vectors over all selected spots in the acquisition.
DefineS as mean cross-repeat covariance andN as half the mean squared centeredA−Bdifference.
Reliability isR=S/(S+N), only when the denominator is positive.
With equal independent noise, N estimates each two-repeat mean's noise variance.
That interpretation is an assumption; the saved covariance and disagreement remain valid descriptive statistics without it.

Resample whole occupied128×128 spatial regions,2000 times, with replacement.
Weight by their spot counts and recenter feature vectors in every resample.
Root supplies the fresh seed before signal access; save the actual resampling indices.
The uncertainty is conditional within one field of view, not independent acquisition replication.

**Both files must pass all conditions:**

- Positive lower 2.5%bootstrap quantile ofS.
- Point reliability at least0.50.
- Lower2.5%bootstrap quantile of reliability at least0.25.
- The stated ROI count, coverage, clipping and registration limits.
- Each opposing±1 pixel registration perturbation retains positive lower covariance and point reliability at least0.25.

The0.50point threshold asks for repeat-consistent variation at least as large as repeat disagreement.
The0.25lower threshold prevents a weak uncertainty bound from being described as robust recoverable structure.
A zero/undefined signal denominator fails. A registration or geometry failure is reported separately from contrast failure.

## Later development, still closed

After eligibility, root will review one direct decoder and matched strong classical implementations.
The decoder must represent the training mean, with no mandatory input identity skip.
Use one fixed capacity/seed and an inner-training checkpoint rule; no architecture search after development.
Compare mean/location templates, robust low-rank/Wiener, edge-preserving and spatial physical methods.
All receive the same observations, spot geometry, calibration and context.
Spatial regularization must respect individual crystal footprints.

The prospective target remains10%lower contrast-reconstruction error versus the strongest reference.
Require uncertainty excluding no gain, tail ratio at most1.02, full coverage and physical-shape/amplitude safeguards.
Exact later implementations and metrics require root review before their stages. This eligibility commit does not silently freeze incomplete decoder code.

## Runnable commands after root release

Set absolute paths explicitly. `SOURCE` is the standalone worker root or public checkout's `workers/odmr-edge-ml`.
`PYTHON` is the exact interpreter string registered by the supervisor.
`OUT` must be new and outside the checkout. No command below is authorized merely by appearing here.

```sh
"$PYTHON" "$SOURCE/experiments/widefield_redesign/run.py" fixtures --approval "$APPROVAL" --out "$OUT"
"$PYTHON" "$SOURCE/experiments/widefield_redesign/run.py" qualify --approval "$APPROVAL" --data "$DATA" --custody "$CUSTODY" --out "$OUT"
"$PYTHON" "$SOURCE/experiments/widefield_redesign/verify_saved.py" --bundle "$BUNDLE" --manifest-sha256 "$PINNED_MANIFEST_SHA256" --out "$OUT"
```

The first two commands must run directly inside the numerical supervisor.
Fixtures use `pytest.main` in the same process. No subprocess orchestration is used.
Saved verification uses NumPy plus the standard library, saved spectra/statistics/indices and a separately pinned public manifest.
It does not load FITS, run inference, use private approval files, or import Torch/SciPy.
It returns 0 when integrity passes, including a correctly reproduced scientific-negative result.
Qualification returns2 for a scientific eligibility failure; the coordinator must preserve that expected negative result.

Required packages for qualification and fixtures: NumPy, SciPy, pytest.
Required source dependency: unchanged `experiments/measured_widefield/io.py` for the header reader and memory map.
No package installation, GPU or service change is requested.

Custody JSON must have status`verified`, this study ID, and per-file SHA256, header SHA256, size, current,
`prior_decoding_status`, audit limitations, and an explicit `prior_byte_exposure` record.
Accepted statuses describe no recorded decoding or recorded header-only access; neither proves no unrecorded access.
Known signal decoding is rejected. The derived certificate binds the original custody and header-record hashes.
Its path and both raw FITS hashes must be bound in approval inputs.
Root approval pins every Python source here, protocol JSON and the unchanged reader.
A valid active supervisor parent, approval/spec/run identities and held flock are required.
Environment strings alone cannot grant access.

Initial lane limits:4 CPU-hours,1 GPU-hour,2 cumulative numerical wall-hours.
Eligibility reserves at most900 CPU/wall seconds,8 GiB and at most4threads; no GPU.
Reserve at least 15% of the lane for independent saved-output verification.
Actual throughput is unmeasured. Stop on budget, source drift, custody failure or unexpected implementation error.
