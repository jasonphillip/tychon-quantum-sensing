# Measured NV-array localisation: development gate failed

Updated 2026-10-15. The registered localisation experiment stopped after development.
The combined adoption gate failed. There is no confirmed neural advantage or held-group result.

The compact model showed an exploratory tradeoff on the validation set used for model selection.
It improved on the strongest registered same-budget reference.
It did not match the full-budget reference within the required accuracy margin.
No tuning, retry, Freeze B, or held-out feature scoring followed this result.

## Result and stopping decision

| Selected method | Unique calibration positions, including validation | Validation mean error (µm) | Validation 95th-percentile error (µm) |
|---|---:|---:|---:|
| Compact MLP, width 96 | 83 | 112.383920 | 188.104792 |
| Same-budget kNN, k=3 | 83 | 134.046555 | 364.054104 |
| Full-budget kNN, k=9 | 248 | 99.477284 | 206.047056 |

All methods use the same 44 validation measurements at 34 unique positions.
The small and full calibration budgets contain 95 and 268 measurements, respectively.
Repeated coordinates count once toward the label budget and never cross partitions.

| Registered development condition | Saved value | Required | Decision |
|---|---:|---:|---|
| Candidate / same-budget mean error | 0.838395 | ≤0.90 | Pass |
| Candidate / same-budget 95th-percentile error | 0.516695 | ≤1.10 | Pass |
| Candidate / full-budget mean error | 1.129745 | ≤1.05 | **Fail** |
| Small / full unique calibration positions | 0.334677 | ≤0.50 | Pass |

These are development-selection results, not unbiased confirmation estimates.
The model used validation for checkpoint and width selection.
Each classical method used validation for configuration selection.
No confidence interval or held-group improvement is claimed.

## Complete selection record

The predeclared widths were 24, 48, and 96, with 650, 1298, and 2594 parameters.
Each used one registered seed and 200 CUDA epochs.
Saved-prediction validation mean errors were 133.744322, 133.333810, and 112.383920 µm.
The selection rule chose the lowest validation mean error, then fewer parameters.
All gates applied once to the chosen width. Failure did not permit switching candidates.

The classical comparison used 17 fixed configurations at each calibration budget, for 34 fits.
Families were centroid, ridge, distance-weighted kNN, smoothed RBF, and Gaussian-process regression.
[selection.json](development/selection.json) includes all three candidates and all 34 classical configuration records.
It also records the selected methods and per-configuration diagnostics.
All three candidate weight files and validation prediction files are included.
The selected classical predictions are included in [validation_predictions.npz](development/validation_predictions.npz).
Unselected classical prediction arrays were not saved; their individual scores are selection diagnostics.
The verifier recomputes the reported selected-method metrics and combined gate from saved predictions.

## Measured-data scope and provenance

The data come from [Hao-Cheng Weng's public archive](https://doi.org/10.5281/zenodo.19855773).
Its title is “Data/code availability for Photonic-integrated quantum sensor array for microscale magnetic localisation.”
The archive metadata gives a publication date of 2026-04-28 and a CC BY 4.0 license.
See [attribution and license](ATTRIBUTION.md) and [data-provenance.json](data-provenance.json).

The targets are published motor-stage X/Y coordinates paired with measured sensor-array fitted features.
This study uses model-loaded fit version A only.
Version A differs from version B saved by the Fig.S4 fitting notebook.
No saving notebook for version A was identified.
The published parameter/label pairing is used; raw-to-fit lineage remains unresolved.

The 24 input features contain eight triplets: resonance separation and two resonance-centre fit deviations.
The adapter converts GHz to MHz, applies logarithms, and fits scaling on training rows only.
This prospective transform does not reproduce the author's original CNN training.
No original notebook, supplied model, or object array was executed.
COMSOL simulations remain excluded.

Geometry qualification identified 49 small-training positions, 214 full-training positions, 34 validation positions, and 36 held positions.
The sealed held feature rows remain unscored.
Possible acquisition-session memberships overlap across partitions.
Unsorted original traversal and repeated coordinates prevent exact row-to-session assignment.
This design tests conditional spatial generalization within represented acquisitions.
It does not establish independent-session, independent-array, orientation, specimen, or population generalization.
Stage calibration uncertainty remains unverified.

An independently calibrated physical inverse was ineligible from the supplied inputs.
Needle moment, stage-to-sensor frame, per-sensor NV axes, and usable field calibration were missing.
The available height, tilt, and pitch did not supply those missing quantities.
This limitation does not establish that physics-based localisation cannot work.
The comparison covers only the registered classical regression methods.

## Verification and files

Independent saved-output verification passed under a separately accounted root review.
The public verifier confirmed artifact integrity and reproduced the failed scientific gate.
Root separately recomputed Euclidean mean, median, and p95, all ratios, and all four conditions.
See [independent-verification.json](independent-verification.json) for the original evidence digest and resource projection.
This verifies saved development outputs; the actual public commit still needs fresh-checkout verification.
The files below preserve the completed output bytes.
[development/artifact_manifest.json](development/artifact_manifest.json) binds each saved artifact and frozen numerical source.
[qualification/qualification.json](qualification/qualification.json) records finite positive development features and no held feature access.
[package-manifest.json](package-manifest.json) binds the complete public evidence package.

From the public repository root, with Python and NumPy available:

    python3 workers/odmr-edge-ml/experiments/measured_localisation/verify_saved.py --artifact workers/odmr-edge-ml/docs/measured_pilots_2026-10/localisation/development

From the standalone worker source root:

    python3 experiments/measured_localisation/verify_saved.py --artifact docs/measured_pilots_2026-10/localisation/development

Expected output includes artifact_integrity: pass, metric_recomputation: pass, and scientific_gate_passed: false.
Expected exit code is **2**, because the registered scientific gate failed.
Any exception or hash mismatch is a verification failure.
The verifier needs no archive, private approval, training, inference, GPU, or network access.
It checks all frozen Python source and protocol hashes exactly.
No source-hash exception or publication sanitization exception is used.

The frozen source README and provenance note describe preparation at their recorded time.
This evidence package records the completed development stage and supersedes their draft status statements.
Their original source history remains intact.

## Resources and limits

[resource-receipts.json](resource-receipts.json) separates measured resources from conservative ledger charges.
The development job measured 4.942852 CPU seconds and 4.561500 wall seconds.
Its scientific exit 2 retained the full 1800-second CPU, wall, and GPU reservations.
Peak sampled host memory was 1,394,081,792 bytes.
The approved ceilings were 8 GiB host memory and 4 GiB PyTorch allocator memory.
One CPU affinity and one numerical thread were configured; CUDA runtime helper threads may also exist.

Per-configuration timings are execution diagnostics, not matched inference benchmarks.
No FPGA, end-to-end sensing latency, energy, power, or deployment result is claimed.
The original experiment's 90–360-second integrations are separate from this software processing.
No novelty, first demonstration, clinical performance, or replacement of a calibrated sensor is claimed.
