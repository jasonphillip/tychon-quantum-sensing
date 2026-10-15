# Measured widefield pilot

Prepared 2026-10-15. Source preparation only; no signal values, tests, training, or evaluation have run.
Read [PROTOCOL.md](PROTOCOL.md) and [protocol.json](protocol.json) before preparing an approval.
The coordinator must freeze this draft and supply custody plus accounting bindings.

This package predicts a held measured fluorescence spectrum from another scan.
It does not predict independently labelled magnetic field.
NumPy/SciPy support CPU processing across the Sparks and Mac.
All three registered residual widths train only with CUDA on an allocated Spark.
There is no FPGA access or export claim.

Run from the standalone worker root, or the public checkout's `workers/odmr-edge-ml` directory.
Set `PYTHON` to the host's absolute Python path.
Set `SOURCE` to the absolute worker root containing `experiments/`.
The accounting job must use that source root as its working directory.
Set absolute paths for `DATA`, `CUSTODY`, `APPROVAL`, and `OUT` in the coordinator's job specification.
Every numerical command runs through the coordinator's registered accounting adapter.
Direct shell invocation of a numerical command is not authorized.

Header-only inspection:

```bash
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" inspect --fits "$DATA/f0.fits" "$DATA/f8.fits" "$DATA/f24.fits"
```

Staged numerical argument examples, for later registered jobs:

```bash
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" extract-inputs --split train --approval "$APPROVAL" --data-root "$DATA" --custody "$CUSTODY" --out "$OUT/train-inputs"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" extract-targets --split train --approval "$APPROVAL" --data-root "$DATA" --custody "$CUSTODY" --inputs "$OUT/train-inputs" --out "$OUT/train-targets"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" fit-classical --approval "$APPROVAL" --inputs "$OUT/train-inputs" --targets "$OUT/train-targets" --out "$OUT/classical-model"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" predict --split development --approval "$APPROVAL" --inputs "$OUT/development-inputs" --model "$OUT/classical-model" --methods raw,training_mean,savgol_5,savgol_11,savgol_21,ridge_0.001,ridge_0.01,ridge_0.1,pca_wiener_4,pca_wiener_8,pca_wiener_16,robust_lorentzian --out "$OUT/classical-development"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" score --split development --approval "$APPROVAL" --model "$OUT/classical-model" --targets "$OUT/development-targets" --prediction-bundles "$OUT/classical-development" --out "$OUT/classical-development-score"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" train-candidate --approval "$APPROVAL" --inputs "$OUT/train-inputs" --targets "$OUT/train-targets" --out "$OUT/candidate-16-model"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" predict --split development --approval "$APPROVAL" --inputs "$OUT/development-inputs" --weights "$OUT/candidate-16-model" --methods candidate_16 --out "$OUT/candidate-16-development"
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" score --split development --approval "$APPROVAL" --model "$OUT/classical-model" --targets "$OUT/development-targets" --prediction-bundles "$OUT/classical-development" "$OUT/candidate-16-development" "$OUT/candidate-32-development" "$OUT/candidate-64-development" --out "$OUT/candidate-development-score"
```

Repeat candidate train/predict jobs once for widths 32 and 64, using distinct outputs and width-bound approvals.
Every candidate trains for 100 epochs; save all three development predictions before candidate selection.
Development input/reference extraction uses the same two commands with `--split development` and distinct output directories.
Final extraction requires Freeze B. Final reference extraction also requires `--predictions` and a root-bound prediction manifest.
The final prediction list contains the frozen classical reference, the selected `candidate_16`, `candidate_32`, or `candidate_64`, and `training_mean`, without duplicates.
Approvals may grant only the next bounded phase; the examples do not authorize the whole sequence.

Custody adapter contract:

```json
{"status":"verified","record_id":"7233869","files":{"f0.fits":{"sha256":"FULL_SHA256","bytes":2621445120,"header_sha256":"HEADER_SHA256","axis_order_confirmed":true}}}
```

Include all three filenames. The current-to-file map comes from the official repository table.
The checked adapter is [custody-manifest.json](custody-manifest.json).
It binds original receipt hashes, URLs, MD5, SHA256, byte counts, current-table provenance, and individual header cards.
All files record 20 ms exposure; f8 total measurement time is 191.882476 seconds.

Approval contract:

```json
{"status":"approved","study":"measured-widefield-2026-10-15","phases":["extract-inputs:train"],"source_files":{"experiments/measured_widefield/protocol.json":"SHA256"},"data_manifest_sha256":"SHA256","artifacts":{}}
```

Include every package and test `.py` file in `source_files`, not only the example protocol entry.
Set `protocol_sha256` to the frozen full JSON hash and `allowed_run_ids` to the exact reserved job IDs.
Set `accounting_authority` to the coordinator's exact registered authority identifier.
The accounting supervisor must supply the active context and hold the per-job lock.
Root must change protocol status to `FROZEN` and regenerate source pins before approving jobs.
The compiled implementation contract permits that status change only; other JSON changes require source review.
`artifacts` maps each consumed absolute `manifest.json` path to its SHA256.
Prediction approvals specify the exact `methods` list.
Training approval supplies `candidate_width`, `training_seed`, and `baseline_execution_valid:true`.
Scoring requires `--model` for the frozen training-only shape mask.
Scoring approval supplies `bootstrap_seed`; final scoring also requires `reference_method` and `candidate_method`.
Classical accuracy is a diagnostic, not a veto on the three fixed neural tests.
Final reference approval supplies `prediction_manifest_sha256` after root commits the predictions.
Never include secrets or unused held-data seeds in public reports.

Manufactured tests, not yet run:

```bash
"$PYTHON" "$SOURCE/experiments/measured_widefield/run.py" tests --approval "$APPROVAL"
```

The first registered test job must validate FITS scaling, header truncation, disjoint groups,
repeat-access restrictions, analytic derivatives, metric invariants, and NumPy/Torch candidate parity.
Authored tests cover header metadata, spatial guards, repeat 0-only selection, analytic derivatives,
metric corruption, shape flattening, the finite classical grid, protocol mismatch, supervisor spoofing, and Torch/NumPy parity.
None have run.
The parity fixture performs inference only; actual candidate training remains CUDA-only.
