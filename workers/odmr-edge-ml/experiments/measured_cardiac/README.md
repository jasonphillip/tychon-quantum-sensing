# Measured cardiac-data preparation

Prepared: 2026-10-15, EDT. Status: blocked pending complete custody metadata and root Freeze A.

This package prepares a bounded analysis of public NV-diamond cardiac recordings.
It does not contain a measured result, a trained model, or a diagnostic tool.
The dataset download belongs to the coordinator. Do not duplicate it.

[Protocol](protocol.md) records the target, baselines, proposed limits, and failure rules.
[Manifest template](manifest.template.json) deliberately fails eligibility until provenance is filled.
[Approval template](approval.template.json) cannot authorize data access.
ECG provides timing. Separately recorded OPM data cannot serve as clean MCG truth.

## Dependencies

Metadata commands: Python 3.11+ standard library.
Future classical primitives/tests: NumPy >=1.26 and SciPy >=1.11.
No PyTorch, CUDA, MNE, notebook execution, or installation is required for preparation.
The text loader supports comma, semicolon, tab, and whitespace-delimited recordings.
It does not read FIF or Mathematica notebooks as signal targets.
Run from the source root with the full module path to avoid import collisions.

## Prepared commands

Set these variables to your existing absolute paths.
The data file must be the custody-verified immutable archive.
Use a new output path because eligibility refuses to overwrite evidence.

```sh
export PYTHON=/absolute/path/to/python
export SOURCE=/absolute/path/to/source-checkout
export DATA=/absolute/path/to/2026-6-15-dataset-mcg.zip
export OUTPUT=/absolute/path/to/new-eligibility-output.json
cd "$SOURCE"
"$PYTHON" -m experiments.measured_cardiac.cli inventory --archive "$DATA"
"$PYTHON" -m experiments.measured_cardiac.cli eligibility --manifest "$SOURCE/experiments/measured_cardiac/manifest.template.json" --out "$OUTPUT"
```

The inventory rejects incomplete archives. It reads central-directory metadata, not scientific samples.
Eligibility exits 2 for a documented blocker. It writes a new result and refuses an overwrite.
The equivalent private eligibility command returned the expected exit 2 against the template.
It reported no signal values read and no eligible capability.
The inventory command remains prepared until custody completes.
Syntax inspection passed. Numerical tests have not run.

After root authorizes the accounting stage, use the configured absolute paths for the prepared tests:

```sh
cd "$SOURCE"
"$PYTHON" -m unittest discover -s "$SOURCE/experiments/measured_cardiac/tests" -p 'test_*.py' -v
```

The test process must run through the shared accounting supervisor. Do not launch it directly before approval.
Source changes and scientific comparisons remain separate from integration and publication.

## Limits of this preparation

The loader requires verified metadata, a pinned approval, approved time intervals, and an active supervisor context.
This is procedural custody enforcement, not security against the host owner.
Reading an archive still touches compressed bytes; the loader does not decode signal values outside permitted intervals.
No candidate performance, speed, power, uncertainty calibration, clinical utility, or novelty is established.
