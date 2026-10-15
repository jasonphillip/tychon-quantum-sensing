# Measured NV-array localisation preparation

Status: draft implementation. No measured numerical run has occurred in this lane.
The protocol requires root approval, custody validation, and representative tests before use.

## Question and limits

Can one compact model use fewer calibration labels without losing useful position accuracy?
The target is the published motor-stage coordinate paired with a fitted feature row.
Use only model-loaded version A. Its raw-to-fit lineage is unresolved because it differs from the saved Fig.S4 fits.
Any result concerns these published fitted-feature/stage-coordinate pairs. It does not validate the raw acquisition pipeline.
The source is [Zenodo 19855773](https://doi.org/10.5281/zenodo.19855773), accompanying
[Weng et al.](https://www.nature.com/articles/s41467-026-73701-0).
Measured needle data and COMSOL microrobot simulations must remain separate.

The primary gate requires at least 50% fewer unique calibration positions than the full-pool classical reference.
Mean error may exceed that reference by at most 5%, including the registered uncertainty limit.
The model must also improve mean error by at least 10% over the strongest same-budget classical reference.
Its 95th-percentile error may exceed that reference by at most 10%.
Validation labels count toward both calibration budgets.
Repeated measurements at one coordinate count as one labelled position. Measurement-row counts remain separate.
All thresholds are proposals until root freezes the protocol after metadata qualification.

No claim concerns arbitrary source orientations, new sensors, clinical use, or a first demonstration.
No FPGA run, power measurement, live measurement, or deployment is part of this lane.
The original experiment's 90–360-second integrations must remain distinct from processing latency.

## Custody boundary

Claude owns original downloads and their hashes. This package does not download or execute source archives.
`custody_request.json` specifies exact members and safe byte copies. No original notebooks or models execute.
The loader accepts native fitted parameter arrays. It constructs features only for explicitly requested rows.
The 24 features are eight channel-major triplets: splitting, first resonance fit deviation, second resonance fit deviation.
The source fits use GHz. The native adapter multiplies each triplet by 1000 before applying the natural logarithm.
The saved sensor ordering is already correct. The loader does not reorder sensors again.
Targets are motor-stage X/Y positions in micrometres.
The extractor must preserve the published version-A parameter/label pairing and disclose the unresolved raw-to-fit lineage.
It must document any original global calibration and all previously viewed values.

`bundle.example.json` describes the required custody contract.
Its position bounds and hashes are placeholders, not valid defaults.
Use relative paths inside the custody bundle. The runtime accepts the bundle's absolute path.
Sample IDs are neutral row IDs. No model receives IDs, coordinates, filenames, paths, or session identifiers as inputs.
The original extractor uses unsorted `os.walk`. Archive order cannot recover row-to-session identity for repeated coordinates.
Custody supplies a raw-position catalog. The partition reports all possible sessions for each coordinate.
These memberships are conservative, not exact row-session assignments. Session-overlap counts must carry this qualifier.
No difficulty-based filtering or automatic removal of nonpositive features is allowed.

The header inspector reads hashes, NPY headers, IDs, and supplied index arrays only.
The partition stage has a separate positions-only approval while the scientific protocol remains draft.
It does not open feature files or require `features.npy`. It reads safe saved X/Y labels and the raw-position catalog.
`geometry-approval.example.json` denies signal access and model execution. Root must pin the complete reviewed source.
The qualification stage checks finite positive development features under a separate ten-minute run limit.
Development reads only training/validation feature rows.
Evaluation reads test feature rows only after Freeze B binds the passed development output.

## Comparators and training

The references are centroid, ridge, distance-weighted kNN, smoothed inverse-multiquadric RBF, and Gaussian-process regression.
Finite configuration grids are in `protocol.json`; each runs at the small and full calibration budgets.
SciPy supplies vectorized nearest-neighbour, interpolation, distance, and factorization operations.
There is no deliberately slow per-element classical implementation or timing-based primary claim.

The candidate family has three predeclared widths: 24, 48, and 96 hidden units.
The parameter counts are 650, 1298, and 2594. Each uses one seed and 200 epochs on CUDA.
Checkpoint selection uses validation error. Configuration selection uses the lowest validation mean error, then fewer parameters.
All development gates apply once to that winner. A failed winner cannot be replaced by another configuration.
Each configuration saves its weights, predictions, validation score, and diagnostic resource receipt.
The central job receipt remains authoritative for CPU, GPU, wall time, and memory accounting.
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
The small total label budget is 25% of eligible unique positions, including validation.
Minimum sample/group counts and actual label reduction are checked before feature scoring.
If the partition fails, stop. Root may revise geometry rules only before viewing signal outcomes, with a new documented freeze.

The draft permits spatial generalization within represented sessions. Root must accept this limit before geometry approval.
Possible session overlaps are explicit. A connected-session holdout requires a different, prospectively reviewed partition.
Spatial bootstrap intervals describe these spatial blocks within available acquisitions.
They do not establish independent-session, independent-sensor, or population generalization.
The originally published split is reproduction evidence, never a new sealed test.
`reproduce` scores paired `estimated_position.npy` and `pos_test.npy`, as loaded together by the original figure source.
Those row IDs identify the published prediction table, not unique indices into the 819-row calibration bundle.
The Fig.S5 split contains coordinate arrays. Repeated coordinates prevent automatic conversion into unique row indices.
Custody proved Fig.S5 test labels and Fig.3d/e `pos_test.npy` byte-identical.
Their relationship to the separate-day Fig.3b/c sweeps remains unproved.
It does not execute downloaded networks or retrain the published architecture.

The development gate must pass before one held-group evaluation.
Failure ends this registered candidate cycle. There is no rescue tuning on the test output.
Nonfinite values, missing baselines, ambiguous calibration, or uncertain row provenance stop the lane.

## Commands

Use Python 3.11+ with existing NumPy, SciPy, and PyTorch environments.
No package installation is part of this preparation.
All numerical commands must run inside root's approved accounting supervisor.
Root must approve and account for geometry-only work first. It may run while the scientific protocol remains draft.
Root must then freeze the actual partition and protocol before feature qualification, training, or evaluation.
The supervisor supplies the approval hash, unique reservation ID, active context, and one-thread environment.

```sh
python /absolute/source/experiments/measured_localisation/run.py inspect --bundle /absolute/custody/bundle.json
python /absolute/source/experiments/measured_localisation/run.py partition --approval /absolute/geometry-approval.json --bundle /absolute/custody/bundle.json --output /absolute/new-partition-output
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
