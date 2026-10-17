# Measured thermal-detector readout: first frozen test

**The measured-data test failed its preregistered 80% preparation-agreement target.**
Validation selected shrinkage LDA. It classified 758 of 1,000 untouched final records correctly: **75.8%**.
Its conditional IID Wilson 95% interval is 73.05–78.35%.
The data qualify for within-acquisition classification only. **Drift-transfer eligibility fails.**
No model or protocol was changed after the final results became available.

## Data and provenance

Source: Gunyho and colleagues, [Data for “Single-Shot Readout of a Superconducting Qubit Using a Thermal Detector”](https://zenodo.org/records/10000511).
Record DOI: `10.5281/zenodo.10000511`. The API reports CC-BY-4.0 and publication date October 13, 2023.
The associated article is [doi:10.1038/s41928-024-01147-7](https://doi.org/10.1038/s41928-024-01147-7).
The experiment uses a thermal detector, not the synthetic resonator receiver from the earlier pilot.
This test does not reproduce the article's optimized analysis or reported fidelity.

Authors' analysis code identifies run 76 as full time traces and run 77 as integrated shots.
Run 76 stores real/imaginary voltage arrays with shape `[2, 1000, 781]`.
The 781 samples span 0–49.92 microseconds at 64-nanosecond intervals.
Its acquisition GUID is `aaaaaaaa-0000-0000-0000-018210c3d8f3`.
Stored acquisition timestamps are July 18, 2022, 13:04:06–13:04:35; the stored text has no timezone.
Preparation-pulse amplitudes 0 and 1 supply labels. They do not certify the true quantum state on each shot.

Run 77 is separately acquired but supplies only integrated IQ, with shape `[2,10000]`.
It cannot supply another compatible full-trace group for this frozen comparison.
Its signal records were not evaluated.
One compatible acquisition cannot establish drift calibration across acquisitions.

Only selected archive members were downloaded, through bounded HTTP ranges.
ZIP-range transfer total: **8,934,736 bytes**, plus the small Zenodo API metadata record.
Selected members passed ZIP CRC checks and have SHA256 receipts in `retrieval.json`.
The complete 922,898,009-byte archive was not downloaded; its full-archive MD5 remains unverified.
Input members were made read-only.
The initial sandbox metadata request failed DNS resolution; a changed retry with approved network access succeeded.
No other retrieval retry or scientific rerun occurred.

## Frozen comparison

Registration occurred at `2026-10-17T18:30:04.655737+00:00`, before reading final signals.
Registration SHA256: `e168286e81e8870f79e2b17890cf31088600956ef6aa3bc5bfc3d946f6bb31cf`.
Raw run-76 SHA256: `fe151d5ba54c38ac32edc5f0a2e8e7977e2b14cdb9c9ec2680b0b3892e5b9df0`.
The registration includes protocol, implementation, test, source-metadata, and raw-input hashes.

Per preparation, stored shot indices use these half-open blocks:

| Role | Indices | Records across both preparations |
| --- | --- | ---: |
| Reference | 0:128 | 256 |
| Calibration | 128:192 | 128 |
| Validation | 192:320 | 256 |
| Unused gap | 320:500 | 360 |
| Final | 500:1000 | 1000 |

These are index-separated blocks. Per-shot chronology and cross-preparation interleaving are not established.
Every method receives the same 384 available labelled reference/calibration records.
The three pooled baselines fit all 384 records.
The affine method freezes a boxcar from 256 reference records, then fits its transform with 128 calibration records.
All methods use the same validation block. No hyperparameter sweep or final-driven window selection occurred.

All 781 samples enter 64 fixed bins, producing 64 interleaved IQ pairs.
The affine method retains the earlier least-squares formula and conditioning gates.
Empirical measured reference templates replace synthetic nominal templates.
Thus the method is transferred, while coefficients are newly fitted; original synthetic coefficients are not validated unchanged.
The fitted affine matrix passed its conditioning gate: condition number 1.503.

| Method | Validation agreement | Final agreement | Final errors |
| --- | ---: | ---: | ---: |
| Pooled boxcar/threshold | 73.83% | 73.7% | 263 |
| Pooled matched filter | 73.44% | 74.3% | 257 |
| Pooled shrinkage LDA, selected | 77.34% | 75.8% | 242 |
| Affine correction + frozen reference boxcar | 73.44% | 74.3% | 257 |
| Reference boxcar without correction, diagnostic | — | 73.9% | 261 |

LDA's final preparation-0 error was 13.6%; preparation-1 error was 34.8%.
The affine correction improved agreement by four records, or **0.4 percentage points**, relative to its uncalibrated reference.
A post-run paired diagnostic found five corrections and one regression.
The exact two-sided discordant-binomial p-value is 0.21875 under an independent-shot assumption.
This diagnostic was not a selection criterion and does not establish a reliable calibration gain.
Intervals and paired diagnostics do not imply acquisition-level independence or generalization.

## Integer handoff and checks

The exported candidate boxcar pack contains all 1,000 final records.
It uses signed int16, 64 interleaved IQ pairs, and signed int64 output scores.
Candidate weights are `[16384, -2845]`; bias is `42986618`.
No exported value clipped. No float-to-integer boxcar decision changed.
All 1,000 scores matched independent Python integer arithmetic exactly.
The full-int16 score bound is 40,369,122,426, within signed int64.

These are new measured coefficients. Deployment needs a new FPGA build.
This experiment did not program hardware, replay records on the FPGA, or validate LDA in FPGA fabric.
The LDA result has a different computation from the two-weight boxcar core.

Ten focused CPU tests passed. Saved-result verification also passed.
The measured execution took 0.0197 seconds after input integrity checks, excluding process startup and file retrieval.
Peak process RSS was 108,068,864 bytes, measured by `getrusage(RUSAGE_SELF).ru_maxrss` on macOS.
The run used Python 3.14.3, NumPy 2.4.2, and h5py 3.16.0 with four-thread limits.

## Reproduction and next gate

Portable scripts use Python, NumPy, and h5py. No CUDA-Q, vendor tools, GPU, or board is needed.
The final set is consumed. `consumed.json` prevents accidental reevaluation in this workspace.
Existing artifacts can be checked without regenerating final outcomes:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest -v test_evaluate
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python verify_saved.py
```

The original executed sequence was `evaluate.py qualify`, `evaluate.py register`, then `evaluate.py run --output results/frozen_v1`.
A deliberate independent reproduction requires a fresh copy, intact input hashes, and an unused output directory.
It reproduces an already-consumed result and does not create a new holdout.

The next useful data gate is multiple compatible measured acquisitions with preparation labels and acquisition provenance.
Use an untouched acquisition for any next calibration-transfer test.
Do not tune a timing window or method on this consumed final set.
