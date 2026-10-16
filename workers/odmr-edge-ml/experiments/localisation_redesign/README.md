# Localisation redesign: prospective calibration-efficiency test

Status: source preparation only. No result exists for this experiment.
The frozen protocol requires root approval before numerical execution.

The closed 83-position experiment failed its full-budget comparison.
This experiment uses 90 coverage-selected training positions and 34 existing validation positions.
Its 124-position budget is half the 248-position full reference budget.
The original 36 held positions and spatial exclusion gaps remain unchanged.
Only measured features at those held positions remain unseen; their coordinate geometry is already known.
Development outcomes were consumed by the earlier study and are used for development here.

## Hypothesis and control

A 24→96→2 network minimizes smoothed Euclidean position error in micrometres.
A matched control minimizes the earlier standardized-coordinate squared error.
They share architecture, seed, initialization, rows, optimizer, epochs and checkpoint metric.
The control is diagnostic. It cannot replace a failed candidate.
An improved candidate does not establish that the loss caused improvement unless it also improves on the control.
The primary gate tests calibration efficiency; the control comparison does not create another adoption claim.

## Strong references

Both calibration budgets receive the same 38 registered configurations.
These comprise mean1, ridge6, weighted kNN12, weighted RBF9, isotropic GP6 and fitted ARD GP4.
Distance representations include splitting-only, quality weight0.25 and quality weight1.
Ridge and ARD use splitting-only or all features.
ARD uses squared-exponential or Matérn3/2 kernels, with independent kernels for each coordinate.
Each output uses two deterministic starts and at most60 L-BFGS-B iterations per start.
Training likelihood selects an optimizer start. Validation mean error selects a reference configuration.
Finite solutions at the iteration limit remain eligible, with optimizer status disclosed.
Any configuration failure is recorded and makes the comparison incomplete.
Transformations and kernel optimization use training data only.
All predictions, invalid flags, selected states and optimizer records are saved.
No Python-loop timing or hardware performance claim is part of this trial.

## Gates and stopping

Candidate mean error must be at most0.90 of the best same-budget reference.
Its p95 error must be at most1.10 of that reference.
Its mean error must be at most1.05 of the strongest full-budget reference.
The calibration-position ratio must be at most0.50, with complete prediction coverage.
Final whole-cell bootstrap upper bounds must be below1.0 for the same-budget ratio and at most1.05 for the full-budget ratio.
There must be at least30 held positions and6 spatial cells.
A failed development gate closes this formulation without held-feature access.
A failed final gate ends this claim without tuning or another test.
The saved small/full classical ratio also identifies a possible classical calibration tradeoff.
It does not authorize switching candidates or opening the held set after a failed neural gate.

## Custody and prior art

Source data: [Zenodo19855773](https://doi.org/10.5281/zenodo.19855773), CC-BY4.0, Hao-Cheng Weng and contributors.
The [published paper](https://doi.org/10.1038/s41467-026-73701-0) already demonstrates learned localisation.
This experiment cannot claim first learned localisation or compare headline errors across incompatible splits.
It uses the declared version-A fitted-feature/stage-coordinate pairs.
Version-A raw-to-fit lineage remains unresolved; versionB is not substituted.
Coordinate repeats stay grouped. Possible session overlap remains disclosed.
The scope is conditional spatial generalization within represented acquisitions.
It is not independent-session, independent-sensor, or arbitrary-target generalization.
A calibrated physical inverse is unavailable because moment, axes, coordinate-frame mapping and field calibration are missing.
No claim against all physical methods follows.

## Stages and portable commands

Use Python with NumPy, SciPy and PyTorch installed.
CUDA is required for both 2594-parameter training runs.
Every entry point accepts explicit paths and uses no subprocesses.
Set one BLAS/OpenMP thread through the accounting supervisor.
Root supplies an immutable approval, source pins and one paired-training seed plus a bootstrap seed.

Run `run.py partition` with `--approval`, `--bundle`, `--parent-partition`, and `--output`.
This phase reads position metadata only.
Run `run.py qualify` with `--approval`, `--bundle`, `--partition`, and `--output`.
It checks only full-training and validation rows and exports the development-only bundle.
Copy only that subset to the GPU host. Do not transfer the original fitted arrays.
Run `run.py develop` with the same path options plus `--qualification` and `--development-bundle`.
The original bundle JSON is needed for its hash, but original fitted arrays are absent from the GPU host.
After a separate FreezeB, `run.py evaluate` also requires `--development` pointing at the saved development directory.
It uses frozen saved classical states and network weights without refitting.

A public saved-only check is `python3 experiments/localisation_redesign/verify_saved.py --artifact PATH`.
Use an absolute script and artifact path in operational commands.
It verifies all source and artifact hashes, all38 configuration scores per budget, selected winners and headline metrics.
Expected exit2 means a preserved scientific failure; an artifact mismatch raises an error.
The private shared handoff supplies absolute operational commands and inactive job templates.
No stage is authorized by this README.
