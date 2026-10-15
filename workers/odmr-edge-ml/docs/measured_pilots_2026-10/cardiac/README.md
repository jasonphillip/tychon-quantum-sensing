# Cardiac pilot: reference eligibility stopped the comparison

Prepared: 2026-10-15. Scientific status: STOP. Independent saved-output verification passed.

None of the ten development recordings passed the registered reference-eligibility gate.
The study stopped before method comparison, threshold selection or candidate selection.
P2 and P3 waveform values were not accessed.
No neural advantage, acquisition-time improvement or clinical result was demonstrated.

This is a failure of this fixed recorded-voltage evaluation route.
It does not establish that the source dataset or other cardiac methods cannot work.
The original scientific protocol, data and thresholds remain unchanged.

## What failed

The protocol required two separate noisy reference averages to agree before they could judge shorter recordings.
Every recording exceeded the maximum normalized RMS error of 0.5.
The worst-direction errors ranged from 1.210 to 2.649.
Some recordings also failed yield, amplitude, polarity, timing or width guards.
These are observed failures, not a diagnosis of their physical cause.
The outputs cannot distinguish trigger limitations, acquisition response, noise or changes between time blocks.

| Recording | Complete beats A/B | Yield A/B | Worst NRMSE | Correlation | Failed gates |
|---|---:|---:|---:|---:|---|
| P1-S01 | 207 / 217 | 0.976 / 0.986 | 1.592 | 0.006 | Error, correlation, polarity, timing, width |
| P1-S02 | 246 / 236 | 0.904 / 0.871 | 1.484 | 0.138 | Error, correlation, amplitude, polarity, timing, yield |
| P1-S03 | 249 / 252 | 0.926 / 0.923 | 1.309 | 0.222 | Error, correlation, polarity, timing |
| P1-S04 | 237 / 223 | 0.996 / 0.996 | 1.210 | 0.344 | Error, correlation, timing |
| P1-S05 | 171 / 178 | 0.586 / 0.599 | 1.634 | 0.118 | Error, correlation, amplitude, polarity, yield |
| P1-S06 | 156 / 155 | 0.513 / 0.498 | 1.302 | 0.244 | Error, correlation, amplitude, polarity, timing, width, yield |
| P1-S07 | 244 / 185 | 0.897 / 0.649 | 1.590 | 0.831 | Error, amplitude, polarity, timing, yield |
| P1-S08 | 84 / 127 | 0.609 / 0.718 | 1.586 | 0.580 | Error, correlation, amplitude, count, yield |
| P1-S09 | 163 / 163 | 0.509 / 0.500 | 2.649 | −0.658 | Error, correlation, amplitude, timing, yield |
| P1-S10 | 240 / 245 | 0.988 / 0.992 | 2.042 | −0.674 | Error, correlation, timing |

Values are rounded for display. Exact components remain in each preserved flags file under [development/](development/).
Reference A spans [180,360) seconds. Reference B spans [420,600) seconds.
Each required at least 100 complete beats and 90% trigger-to-output yield.
The gate also required correlation at least 0.8, matching peak polarity, amplitude within 20%,
peak-time agreement within 20 ms, and energy-spread width ratios between 0.8 and 1.25 in both directions.
NRMSE is the square root of `sum((estimate-reference)^2) / sum(reference^2)`; zero-power references fail.
No session was removed and no tolerance was relaxed.

## Scope and participants

The study concerns reproducibility of a centered, processed voltage waveform.
Its noisy references are not clean physiological or magnetic truth.
ECG supplies trigger timing only. Its amplitude and shape are not prediction targets.
Separate OPM recordings are not simultaneous reference measurements.
Unknown acquisition filters prevent recovered-bandwidth and physiological-latency claims.
Unresolved voltage calibration prevents absolute magnetic amplitude or sensitivity claims.
No diagnostic, clinical or sensor-superiority conclusion follows.

Neutral archive groups are P1, P2 and P3, not a verified clinical cohort.
P1-S01 through P1-S10 were development; P2-S01 and P3-S01 remain unused waveform partitions.
The qualification metadata includes their timestamps, not their waveform values.
No creator name below is associated with any participant ID.
Original participant names, archive member filenames, raw ECG traces and private mappings are excluded.

See the [frozen protocol](../../../experiments/measured_cardiac/waveform-protocol.md)
and [independent saved-output verifier](../../../experiments/measured_cardiac/verify_voltage.py).
Scientific source was frozen at `ef31f456b1d9550a655e395f40190777a285d58b` before voltage access.
The original source and protocol bytes are preserved.

## Attribution and license

Omar, Muhib; Zhang, shaowen (2026). *Human Cardiac Measurements with Diamond Magnetometers* [Data set]. Zenodo.
[Immutable version DOI](https://doi.org/10.5281/zenodo.20703822).
License: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/).
Creator spelling and capitalization follow the custodian's saved Zenodo metadata.
These names credit dataset authors only.
The [published study](https://pmc.ncbi.nlm.nih.gov/articles/PMC13580569/) supplies the scientific context.

Original archive SHA256: `b3d79874553f3d8a9434a5daba1002765c810b134f98697b1f0cb58f09232e1f`.
Original archive size: 1,783,355,725 bytes. The original archive remains in private custody.
The published derived arrays contain approved intervals processed with causal filters, completed-beat interpolation and centering.
They are licensed derivative evidence, not untouched raw measurements.
The original derived artifact bytes remain unchanged by packaging.

## Evidence and verification

The [artifact manifest](artifact-manifest.json) identifies all 24 original development artifacts and their storage form.
It records metadata, exact source pins, neutral completed beats, trigger decisions, quality values, flags and the stopped run summary.
There are no method predictions, selected thresholds, chosen candidates or held-waveform results because the gate stopped first.

The [independent root verdict](verification/root-verification-result.json) reproduced scientific STOP and all ten reference-pair errors.
The public verifier separately recomputes aggregates and all gate components from saved arrays.
The verdict's orchestration-manifest hash is provenance only; public recomputation does not need that private manifest.

The checker validates exact participant coverage, block durations, template identities where applicable, hashes and temporal containment.
It does not reconstruct ECG triggering or causal filtering from saved completed beats.
Those transformations rely on source review, manufactured tests and immutable input provenance.
No raw archive, private approval, model inference or training is needed for the saved-output check.

## Fresh public checkout: exact reconstruction and verification

The public repository places this worker under `workers/odmr-edge-ml/`.
Set `REPO` to an absolute fresh-checkout path.
Choose a new absolute `EVIDENCE` directory and new absolute `VERDICT` filename outside that checkout.
The parent directory of `EVIDENCE` must already exist.
Use Python with NumPy; the broader experimental package also uses SciPy.

```sh
WORKER="$REPO/workers/odmr-edge-ml"
PACKAGE="$WORKER/docs/measured_pilots_2026-10/cardiac"
python3 "$PACKAGE/reassemble_package.py" --package "$PACKAGE" --expected-manifest-sha256 "040b5648dcaa69898707aec1f926144de237255957baf2d744618d154eb66794" --out "$EVIDENCE"
cd "$WORKER"
python3 -m experiments.measured_cardiac.verify_voltage --input "$EVIDENCE" --out "$VERDICT"
```

Expected reconstruction: `status: PASS`, 24 restored artifacts, and summary SHA256
`9ce02d515dc17b5d7640eacc8e77d6ae44e8522928e322bc31345ab4b82c638c`.
Expected verification: a verdict with `verified: true`, `scientific_status: STOP`, `reference_passes: 0`, and exit code 2.
A traceback or missing verdict is a failure. Exit code 2 alone does not prove successful reproduction.

Six immutable NPZ files exceed the overlay's 10 MiB blob limit.
They are stored as ordered byte parts no larger than 6 MiB.
Each part manifest preserves the original NPZ byte count/hash and every ordered part's count/hash.
The [stdlib reassembly utility](reassemble_archive.py) is copied unchanged from the widefield package at
`ad1ba6c5ede5cd4588dce5f9c926cd0bedf823fb`.
The [package helper](reassemble_package.py) restores all artifacts outside the checkout and checks their original hashes.
The four smaller NPZ files and all JSON artifacts are copied without transformation.
No NPZ is decoded, recompressed, requantized or numerically modified during packaging.
Original private evidence remains intact.

## Resource accounting

The [resource records](verification/resource-receipt-projections.json) are labelled privacy projections with original receipt hashes.
They omit commands, environment, private paths and host identifiers. Raw receipts remain private.
Development used 100.42024 CPU seconds and 89.01607 wall seconds.
The supervisor recorded the nonzero scientific-stop exit as failed and conservatively charged 1800 CPU and wall seconds.
Independent root verification used and charged 1.547851 CPU seconds and 1.393742 wall seconds.
No GPU or hardware work occurred in these jobs.
Actual use and conservative ledger charges must not be conflated.

Publication completion still requires reconstruction and verification from the actual public checkout, plus public-file and CI checks.
