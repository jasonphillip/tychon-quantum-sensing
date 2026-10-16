# One archived acquisition: unchanged-model transfer

This package prepares a separate acquisition-transfer test.
The original spatial confirmation remains FAIL.
Its consumed positions and unused buffer cells are not part of this evaluation.

All 25 August 4 raw sweeps are included.
The frozen small/full index-34 ARD GP checkpoints remain unchanged.
No position model is fitted, refitted, selected or replaced.
The previously qualified extractor performs spectral fitting only.
No neural model runs.

## Scope and practical criterion

This is one archived acquisition with mixed interpolation and slight extrapolation.
One position equals a previous training coordinate.
Five positions have y=1184 µm, below the original y minimum of 1200 µm.
Source timestamps support a separate day; they are not instrument logs.
Version-A lineage and stage calibration uncertainty remain unresolved.
Eight training pairs passed numerical extractor compatibility.
That limited check does not prove complete raw lineage.

The prospective engineering benchmark uses the 127 µm sensor pitch:
mean error and its conditional 95% upper bound must be at most 63.5 µm;
the p95 error must be at most 127 µm.
This is a pitch-scale localisation criterion.
It is not a published clinical or needle-navigation tolerance.

Original relative thresholds remain:
small/full mean and conditional upper ratio ≤1.05, and p95 ratio ≤1.10.
Both models must cover every case.
Calibration counts stay 124 versus 248 unique labelled positions, including validation.
The models previously used 140 versus 268 measurement rows.

## All-case reporting and uncertainty

The geometry freezes five y-stripes, with all five x positions in each stripe.
Whole stripes are resampled, never individual points.
Report every case and every stripe; never select a winning subgroup.
The required percentile is 95%.
The 98.333% bound is a sensitivity diagnostic only.
Neither gives a population-level or multiple-search discovery guarantee.
One acquisition cannot estimate between-day variability.

A pass can support a bounded archived-transfer/calibration demonstration.
It cannot establish general sensing quality or an advantage across days.
It does not change the previous spatial failure.
The comparison is classical against classical.

## Data safety and execution

Source: Hao-Cheng Weng and contributors, Zenodo 19855773, CC BY 4.0:
https://doi.org/10.5281/zenodo.19855773.
Geometry contains only custody metadata and filename stage coordinates.
The exact 25 members, checksums, labels and stripe identities are pinned.
The code imports the qualified extractor without changing it.
All raw-fit failures remain flagged and count as infinite error.
Invalid cases receive no position prediction and fail adoption.
No case is imputed, silently dropped or replaced.

Only a root-approved reservation may run evaluate.
A fresh 32-byte bootstrap seed and timestamped commitment are sealed before signal access.
The released bytes must match the commitment. NumPy SeedSequence uses their big-endian integer.
An exclusive consumption record is created before the first raw decode.
A scientific failure returns 2 and never permits a retry.
The limit is 600 CPU seconds, 600 wall seconds, 4 GiB and one thread.
No GPU, children, hardware, downloads or installations are needed.

The saved-only verifier reads published outputs and recomputes the same gates.
It does not invoke the raw extractor or GP prediction.
Use explicit absolute paths; root supplies approved accounting specs.
The test entrypoint calls pytest.main in-process for manufactured fixtures only.

This package is preparation only until root freezes the protocol and releases execution.
