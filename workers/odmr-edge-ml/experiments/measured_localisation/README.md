# Measured NV-array localisation preparation

Status: draft implementation. No measured numerical run has occurred in this lane.
The protocol requires root approval, custody validation, and representative tests before use.

## Question and limits

Can one compact model use fewer calibration labels without losing useful position accuracy?
The target is the motor-stage position of a magnetic needle above a fixed sensor array.
The source is [Zenodo 19855773](https://doi.org/10.5281/zenodo.19855773), accompanying
[Weng et al.](https://www.nature.com/articles/s41467-026-73701-0).
Measured needle data and COMSOL microrobot simulations must remain separate.

The primary gate requires at least 50% fewer total calibration labels than the full-pool classical reference.
Mean error may exceed that reference by at most 5%, including the registered uncertainty limit.
The model must also improve mean error by at least 10% over the strongest same-budget classical reference.
Its 95th-percentile error may exceed that reference by at most 10%.
Validation labels count toward both calibration budgets.
All thresholds are proposals until root freezes the protocol after metadata qualification.

No claim concerns arbitrary source orientations, new sensors, clinical use, or a first demonstration.
No FPGA run, power measurement, live measurement, or deployment is part of this lane.
The original experiment's 90–360-second integrations must remain distinct from processing latency.

## Custody boundary

Claude owns original downloads and their hashes. This package does not download or execute source archives.
It expects a reviewed extraction of existing per-sample fitted features, not new spectrum fitting.
The 24 features are eight channel-major triplets: splitting, first resonance fit deviation, second resonance fit deviation.
All three quantities must be in MHz before this package applies a natural logarithm.
Targets are motor-stage X/Y positions in micrometres.
The extractor must prove row alignment and per-sample feature construction from the original analysis source.
It must document any original global calibration and all previously viewed values.

`bundle.example.json` describes the required custody contract.
Its position bounds and hashes are placeholders, not valid defaults.
Use relative paths inside the custody bundle. The runtime accepts the bundle's absolute path.
Sample IDs must be unique. Record acquisition groups when available; otherwise state their absence.
No difficulty-based filtering or automatic removal of nonpositive features is allowed.

The header inspector reads hashes, NPY headers, IDs, and supplied index arrays only.
The partition stage reads positions after approval; it does not read feature values.
The qualification stage checks finite positive development features under a separate ten-minute run limit.
Development reads only training/validation feature rows.
Evaluation reads test feature rows only after Freeze B binds the passed development output.

## Comparators and training

The references are centroid, ridge, distance-weighted kNN, smoothed inverse-multiquadric RBF, and Gaussian-process regression.
Finite configuration grids are in `protocol.json`; each runs at the small and full calibration budgets.
SciPy supplies vectorized nearest-neighbour, interpolation, distance, and factorization operations.
There is no deliberately slow per-element classical implementation or timing-based primary claim.

The candidate is one 650-parameter 24→24→2 ReLU network.
It uses one seed, 200 epochs, fixed optimizer settings, and validation checkpoint selection.
It falls below the repository's 1000-parameter CUDA requirement; CPU training is permitted.
Any larger replacement would require a new pre-scoring freeze and CUDA.
Input and position scaling use each training subset only.

A calibrated physical inverse needs sensor geometry in the label frame, fixed target geometry, and independent field calibration.
Zeeman splitting is not automatically calibrated field magnitude for random NV ensembles.
If custody establishes a usable calibrated physical inverse, execution stops until that comparator is added and frozen.
Otherwise custody must record the metadata-based exclusion reason before development.
Do not omit an available physical comparator because it performs well.

## Partition and stopping rules

The proposed operating-area grid is 12×12, using custody-declared bounds.
Nine fixed interior cells are the test groups. A one-cell gap excludes neighbouring training/validation samples.
Validation uses complete spatial cells and a separate one-cell exclusion gap.
Repeated coordinates remain together; selection uses a registered hash salt.
The small total label budget is 25% of the eligible calibration pool, including validation.
Minimum sample/group counts and actual label reduction are checked before feature scoring.
If the partition fails, stop. Root may revise geometry rules only before viewing signal outcomes, with a new documented freeze.

Spatial bootstrap intervals describe these spatial blocks within available acquisitions.
They do not establish independent-session, independent-sensor, or population generalization.
The originally published split is reproduction evidence, never a new sealed test.
`reproduce` scores supplied saved predictions if custody can establish their ordering and units.
It does not execute downloaded networks or retrain the published architecture.

The development gate must pass before one held-group evaluation.
Failure ends this registered candidate cycle. There is no rescue tuning on the test output.
Nonfinite values, missing baselines, ambiguous calibration, or uncertain row provenance stop the lane.

## Commands

Use Python 3.11+ with existing NumPy, SciPy, and PyTorch environments.
No package installation is part of this preparation.
All numerical commands must run inside root's approved accounting supervisor.
Root must change the protocol status to `FROZEN`, commit it, and pin its complete source hashes before numerical work.
The supervisor supplies the approval hash, unique reservation ID, active context, and one-thread environment.

```sh
python /absolute/source/experiments/measured_localisation/run.py inspect --bundle /absolute/custody/bundle.json
python /absolute/source/experiments/measured_localisation/run.py partition --approval /absolute/approval.json --bundle /absolute/custody/bundle.json --output /absolute/new-partition-output
python /absolute/source/experiments/measured_localisation/run.py qualify --approval /absolute/qualification-approval.json --bundle /absolute/custody/bundle.json --partition /absolute/partition-output/partition.json --output /absolute/new-qualification-output
python /absolute/source/experiments/measured_localisation/run.py reproduce --approval /absolute/reproduction-approval.json --bundle /absolute/custody/bundle.json --output /absolute/new-reproduction-output
python /absolute/source/experiments/measured_localisation/run.py develop --approval /absolute/development-approval.json --bundle /absolute/custody/bundle.json --partition /absolute/partition-output/partition.json --qualification /absolute/qualification-output/qualification.json --output /absolute/new-development-output
python /absolute/source/experiments/measured_localisation/run.py evaluate --approval /absolute/final-approval.json --bundle /absolute/custody/bundle.json --partition /absolute/partition-output/partition.json --selection /absolute/development-output/selection.json --candidate /absolute/development-output/candidate.npz --output /absolute/new-final-output
python /absolute/source/experiments/measured_localisation/verify_saved.py --artifact /absolute/development-or-final-output
```

Every output directory must be new. Commands never overwrite prior evidence.
Exit 2 denotes a registered scientific or qualification failure, not an infrastructure crash.
Exceptions denote missing evidence, implementation failures, or broken contracts.
The public verifier needs published predictions, labels, flags, protocol, manifests, and matching source.
It needs no private approval, training, inference, original 5.5 GB archive, or network access.
During this campaign, root still accounts for verification work before launching it.

## Required validation before the first run

Run the prepared tests only after root approves the numerical fixture stage.
Check partition leakage, label-budget counts, perfect-reference handling, failure flags, and saved-output recomputation.
Then run the metadata/feature qualification stage under the ten-minute first-run limit.
The per-lane cap is 16 CPU-hours, 2 GPU-hours, and 4 cumulative numerical wall-hours.
The accounting supervisor enforces these caps. This package does not create or reset a ledger.
