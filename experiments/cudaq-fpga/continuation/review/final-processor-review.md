# Final processor-readout evidence review

Reviewed October 17, 2026. This is independent AI code and saved-result review.
It is not human review, external endorsement, or TVW claim adjudication.
The reviewer waited for final evaluation completion before opening final artifacts.
No model was fitted, selected, changed, or evaluated through the experiment entry point during this review.
No network retrieval, GPU, hardware, service, or installation operation occurred.

## Decision

**The saved results pass the registered 90% engineering threshold. No reporting blocker was found.**
The frozen selected classifier achieved 95.8251953125% balanced preparation accuracy: 7,850 correct assignments from 8,192 records.
The selected classifier remains `pooled_matched_filter@100:500`.
Another candidate's slightly higher final score does not change that selection.

The exported integer pack uses the separately frozen `pooled_boxcar@100:500` candidate.
It achieved 95.849609375%, with 7,852 correct assignments.
Every saved integer score matched an independent Python-integer calculation.
This is host-only evidence for new coefficients. It is not FPGA execution evidence.

## Release and provenance checks

The training receipt hash matches the release, consumed marker, final metrics, and copied training receipt:
`79cfec86ecc790c301fc1ca9ae9298f91da5ca44dd60562ce59b9a2161395134`.

All seven registered source/input hashes and four frozen artifact hashes remain unchanged.
All 16 frozen training-range hashes match.
The coordinator's saved training gate records 16,384 verified source-train rows and the exact registered partitions.
This review checked its bound receipt and frozen row-hash artifact.

The saved chronology is consistent:

1. Training froze at 18:53:09 UTC.
2. The coordinator released final access at 18:54:02 UTC.
3. The consumed marker was written at 18:54:18 UTC.

The release labels the reviewers as AI, not human reviewers.
The copied release is byte-identical to the coordinator's release.
The pre-final selection uses the registered validation rule, including deterministic tie-breaking.
This review independently recomputed that selection from the frozen candidate metrics.

## Independent saved-data verification

The final verifier completed successfully with local NumPy and one BLAS thread.
It did not import the experiment's metrics or integer-scoring functions.

| Check | Result |
| --- | --- |
| Final records | Exactly 8,192 registered source-test row IDs, without duplicates or replacements |
| Preparation labels | 4,096 ground preparation; 4,096 excited preparation |
| Downloaded final ranges | Eight signal ranges and eight label ranges |
| Range validation | All byte offsets, lengths, SHA-256 values, and ledger entries match |
| Extra final ranges | None |
| Training/final exact signal duplicates | Zero against the frozen 16,384 training-row hashes |
| Predictions | All eight candidate columns retain the frozen candidate order |
| Statistical verification | All eight confusion matrices, accuracies, class errors, and Wilson intervals recompute |
| Integer inputs | All 8,192 records match an independent binning and quantization reconstruction |
| Integer scores | All 8,192 signed 64-bit scores match independent Python-integer sums |
| Integer labels and source IDs | Match downloaded labels, predictions, and registered row IDs |
| Clipping | Zero |
| Retrieval ledger failures | Zero; no retained partial file |

The independent binning check used a quarter-sample grid over the 400-sample window.
Each of its 64 bins averages 25 quarter-samples.
This independently reproduces the registered overlap-weighted integration and every exported int16 input.

The recorded range ledger contains 302,842,240 received bytes for this processor retrieval.
Earlier source-label and thermal retrieval costs remain separate budget components.
Range hashes establish downloaded-byte integrity. They do not establish checksums for unrequested portions of the upstream signal files.

## Results that may be reported

| Frozen model or export | Correct / total | Balanced preparation accuracy |
| --- | ---: | ---: |
| Selected matched filter, window 100:500 | 7,850 / 8,192 | 95.8251953125% |
| Boxcar float candidate, window 100:500 | 7,851 / 8,192 | 95.83740234375% |
| Boxcar integer export, window 100:500 | 7,852 / 8,192 | 95.849609375% |

The selected classifier's confusion matrix is `[[3996, 100], [242, 3854]]`.
Rows represent preparation labels; columns represent assigned labels.
Balanced and pooled accuracy coincide here because both preparation classes contain 4,096 records.

Per-preparation Wilson intervals match the saved results:

- Ground preparation assignment accuracy: 97.0395% to 97.9885%.
- Excited preparation assignment accuracy: 93.3276% to 94.7734%.

These intervals assume conditionally IID shots.
The saved pooled interval is not a balanced-accuracy interval.
The acquisition identities remain unverified, so neither interval establishes performance across independent acquisitions.

One integer decision differs from the floating boxcar decision, at source-test row 40,905.
That change increases the observed correct count by one.
It does not establish integer superiority, and the integer export is not the selected matched-filter model.

The exported weights are `[10235, -16384]`, with bias `-33543462`.
The maximum absolute score bound over all int16 inputs is 55,857,632,550, below the signed 64-bit limit.
The native input scale remains 560.78 units per normalized unit.

The affine calibration has no observed improvement over its frozen reference.
Its full-window accuracy difference is zero; its 100:500 difference is −0.01220703125 percentage points.
The receipt reports two corrected/two regressed records and three corrected/four regressed records, respectively.
This review verified those totals' consistency with the aggregate differences.
Reference-model per-row predictions are absent from the saved CSV, so this review did not independently recompute those paired memberships.
Do not claim a calibration benefit or drift correction from these outcomes.

## Required scope limits

The result concerns source-test preparation labels from recorded QICK processor readout.
Preparation labels are not perfect certificates of the quantum system's true state.
The experiment does not establish NV sensing accuracy or validate the separate thermal-detector model.
The source's native digital units have no established volts conversion here.
Index tiles are not proven independent acquisitions.
No superiority or equivalence claim against the source paper follows from this selected subset.
The earlier thermal-study failure remains unchanged.
These new coefficients require a separate FPGA build and acceptance run before any hardware claim.

## Review diagnostics and fingerprints

The first reviewer interval check used rounded `z=1.96` and failed its strict equality check.
The frozen implementation uses `z=1.959963984540054`.
After correcting that reviewer assumption, one changed-approach verification passed all requested checks.
No experiment tolerance, source file, model, prediction, or data byte changed.
An earlier schema-inspection command also assumed a list instead of the model dictionary; corrected inspection resolved it.

| Artifact under `measured_readout/processor_readout/` | SHA-256 |
| --- | --- |
| `test_frozen/metrics.json` | `eb9ac03f0ed929e5af40864e613fe32bcb6e4a1d6627ad4d4fb2cdf68ce518cc` |
| `test_frozen/predictions.csv` | `c5c8a4f58b4c12578272895c7d0568dad299609cb3b22f5ae662030de721d90e` |
| `test_frozen/candidate_integer_pack/manifest.json` | `945efa478d6ecd455886e65e2f51fd077c6e371d67b4c1b0b44489e7907f3ce7` |
| `test_consumed.json` | `4450ba7dbfbf6c08e5b3bfa873e41c14a2c623b553c35e32a612da60e467ac07` |
| `range_ledger.json` | `404073b75c4a1bf90133d8a8d37e6c005f7568230b7879d7d9d8e293b6b60558` |
