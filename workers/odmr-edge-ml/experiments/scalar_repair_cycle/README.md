# Bounded scalar repair experiment

This experiment changes no trained weights, exported models, or deployed hardware.
Read [PROTOCOL.md](PROTOCOL.md) for fixed estimators, gates, and limits.
Run from an existing scientific environment containing NumPy, SciPy, PyTorch, TensorFlow and pytest.
Every path below is an explicit argument. Replace placeholder roots with absolute paths.

## Commands

The receipt wrapper enforces one numerical thread, a CPU deadline and an 8 GiB address-space ceiling.
It appends CPU time, wall time, memory and exit status to a JSONL ledger.

```sh
/path/to/python /path/to/repo/experiments/scalar_repair_cycle/job_receipt.py \
  --ledger /path/to/work/compute_ledger.jsonl --seconds 900 -- \
  /path/to/python -m pytest -q /path/to/repo/tests/test_scalar_repair_cycle.py
```

Runtime profiling reads spectra, frequencies and metadata only. It does not read field labels.
The recorded first-revision profile explicitly carries the discarded OU-distribution limitation.

```sh
/path/to/python /path/to/repo/experiments/scalar_repair_cycle/profile_runtime.py \
  --data /path/to/data/dev --model-manifest /path/to/original/FROZEN_CHOICES.json \
  --out /path/to/work/profile
```

Run all numerical commands through the receipt wrapper.
For development scoring, use the accepted manifest hash and a new output directory:

```sh
/path/to/python /path/to/repo/experiments/scalar_repair_cycle/run_development.py \
  --mode dev --data /path/to/data/dev --data-manifest-sha256 SHA256 \
  --model-manifest /path/to/original/FROZEN_CHOICES.json --out /path/to/work/results-dev
```

The historical runner filename is retained. It also supports gated validation and final modes.
Validation and final reject partial-row limits and require the isolated-timing declaration.
They check both source and model hashes before payload access and after scoring.

Create Freeze 1 only after source review and acceptance of the corrected development recipe:

```sh
/path/to/python /path/to/repo/experiments/scalar_repair_cycle/gates.py --stage 1 \
  --model-manifest /path/to/original/FROZEN_CHOICES.json \
  --development-manifest /path/to/data/dev/manifest.json \
  --evaluation-root /path/to/work/evaluation --out /path/to/work/freeze1.json
```

The custodian then produces a hash-bound release, gate document and access receipt.
The validation command uses --mode val and --out /path/to/work/evaluation/results-val.
It must also provide --freeze, --freeze-sha256, --release, --release-sha256,
--gate-document, --access-receipt, and --timing-isolated.
The release JSON contract appears in PROTOCOL.md.

Freeze 2 requires the pinned Freeze 1 and completed passing validation summary:

```sh
/path/to/python /path/to/repo/experiments/scalar_repair_cycle/gates.py --stage 2 \
  --model-manifest /path/to/original/FROZEN_CHOICES.json \
  --prior /path/to/work/freeze1.json --prior-sha256 SHA256 \
  --validation /path/to/work/evaluation/results-val/SUMMARY.json \
  --out /path/to/work/freeze2.json
```

Final uses --mode final, the Freeze 2 receipt, a new custodian release, and
/path/to/work/evaluation/results-final. Its access receipt must be the data root's
exclusive-access-receipt.json. No prior final spectra are required by these commands.

## Evidence and limitations

Outputs retain predictions, raw estimates, fallback/validity masks, field/group identifiers,
fit diagnostics, model endpoint counts, paired intervals, selection and timing.
Review may recompute metrics from saved predictions without reopening reserved spectra.
Conditional likelihood intervals are not calibrated measurement intervals.
The single-axis magnitude estimates depend on the declared prior.
A failed gate or ambiguous result is a valid experiment outcome.
