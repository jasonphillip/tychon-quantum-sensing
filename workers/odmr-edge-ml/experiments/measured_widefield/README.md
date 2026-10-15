# Measured widefield pilot

Prepared 2026-10-15. Source preparation only; no signal values, tests, training, or evaluation have run.
Read [PROTOCOL.md](PROTOCOL.md) and [protocol.json](protocol.json) before preparing an approval.
The coordinator must freeze this draft and supply custody plus accounting bindings.

This package predicts a held measured fluorescence spectrum from another scan.
It does not predict independently labelled magnetic field.
NumPy/SciPy support CPU processing across the Sparks and Mac.
The 6616-parameter candidate trains only with CUDA on an allocated Spark.
There is no FPGA access or export claim.

Run from the standalone worker root, or the public checkout's `workers/odmr-edge-ml` directory.
Use the host's absolute Python path. Examples below use Spark Python.
Set absolute paths for `DATA`, `CUSTODY`, `APPROVAL`, and `OUT` in the coordinator's job specification.
Every numerical command runs through the coordinator's registered accounting adapter.
Direct shell invocation of a numerical command is not authorized.

Header-only inspection:

```bash
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline inspect --fits "$DATA/f0.fits" "$DATA/f8.fits" "$DATA/f24.fits"
```

Staged numerical argument examples, for later registered jobs:

```bash
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline extract-inputs --split train --approval "$APPROVAL" --data-root "$DATA" --custody "$CUSTODY" --out "$OUT/train-inputs"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline extract-targets --split train --approval "$APPROVAL" --data-root "$DATA" --custody "$CUSTODY" --inputs "$OUT/train-inputs" --out "$OUT/train-targets"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline fit-classical --approval "$APPROVAL" --inputs "$OUT/train-inputs" --targets "$OUT/train-targets" --out "$OUT/classical-model"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline predict --split development --approval "$APPROVAL" --inputs "$OUT/development-inputs" --model "$OUT/classical-model" --methods raw,savgol,ridge,pca_wiener,robust_lorentzian --out "$OUT/classical-development"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline score --split development --approval "$APPROVAL" --targets "$OUT/development-targets" --prediction-bundles "$OUT/classical-development" --out "$OUT/classical-development-score"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline train-candidate --approval "$APPROVAL" --inputs "$OUT/train-inputs" --targets "$OUT/train-targets" --out "$OUT/candidate-model"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline predict --split development --approval "$APPROVAL" --inputs "$OUT/development-inputs" --weights "$OUT/candidate-model" --methods candidate --out "$OUT/candidate-development"
~/miniconda3/bin/python3 -m experiments.measured_widefield.pipeline score --split development --approval "$APPROVAL" --targets "$OUT/development-targets" --prediction-bundles "$OUT/classical-development" "$OUT/candidate-development" --out "$OUT/candidate-development-score"
```

Development input/reference extraction uses the same two commands with `--split development` and distinct output directories.
Final extraction requires Freeze B. Final reference extraction also requires `--predictions` and a root-bound prediction manifest.
The final prediction method list contains the frozen classical reference plus `candidate`.
Approvals may grant only the next bounded phase; the examples do not authorize the whole sequence.

Custody adapter contract:

```json
{"status":"verified","record_id":"7233869","files":{"f0.fits":{"sha256":"FULL_SHA256","bytes":2621445120,"header_sha256":"HEADER_SHA256","axis_order_confirmed":true}}}
```

Include all three filenames. The current-to-file map comes from the official repository table.
The custodian must bind this derived adapter to its original download manifest.
The adapter format awaits reconciliation with the final custody handoff; do not fabricate verification fields.

Approval contract:

```json
{"status":"approved","study":"measured-widefield-2026-10-15","phases":["extract-inputs:train"],"source_files":{"experiments/measured_widefield/protocol.json":"SHA256"},"data_manifest_sha256":"SHA256","artifacts":{}}
```

Include every package `.py` file in `source_files`, not only the example protocol entry.
`artifacts` maps each consumed absolute `manifest.json` path to its SHA256.
Prediction approvals specify the exact `methods` list.
Training approval supplies `training_seed` and `classical_development_gate_pass:true`.
Scoring approval supplies `bootstrap_seed`; final scoring also requires `reference_method`.
Final reference approval supplies `prediction_manifest_sha256` after root commits the predictions.
Never include secrets or unused held-data seeds in public reports.

Manufactured tests, not yet run:

```bash
~/miniconda3/bin/python3 -m unittest discover -s experiments/measured_widefield/tests -p 'test_*.py'
```

The first registered test job must validate FITS scaling, header truncation, disjoint groups,
repeat-access restrictions, analytic derivatives, metric invariants, and NumPy/Torch candidate parity.
Authored tests cover header metadata, spatial guards, repeat 0-only selection, analytic derivatives,
metric corruption, and manufactured Torch/NumPy deployment parity. None have run.
The parity fixture performs inference only; actual candidate training remains CUDA-only.
