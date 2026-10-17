# Processor-readout release review

Reviewed October 17, 2026. This is an independent AI code and methods review.
It is not human review, external endorsement, or a TVW claim adjudication.

## Decision

No release-blocking code defect was found in the reviewed version.
Code approval is conditional on the completed training receipts and the release checks below.
Training was still retrieving data during review. No completed frozen-training receipt was available.
This review did not release or evaluate the final source-test set.
It did not access GPUs, FPGA hardware, or remote hosts.

## Reviewed version and execution

The lane is `measured_readout/processor_readout/` under this continuation workspace.

| File | SHA-256 |
| --- | --- |
| `processor_io.py` | `6575e07940ffee4cc51766c8b3b691a7a9b36d9f3f8179b7bdb4a041b25c44cf` |
| `processor_eval.py` | `445d6f5b8d631e35e8acdd4423d269406102b43c71a7aa4ec5abd342793dab16` |
| `test_processor.py` | `25e09889d6aec2b6f6c227ef0765d675cecf4b80deb0016b67f4f970ee2cb13b` |
| `PROPOSED_PROTOCOL.json` | `bffb0be2cf21e6d34c95afdbed6adb2e70e4a20f9db1a442f52f30a398d7ea44` |
| `train_registration.json` | `99d983d8f5e1def1e604d73e0e82d1b923aea28d44fd1a2af380be3ddc263a6f` |

All seven files listed in the training registration matched their hashes during review.

The independent test command was:

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 -m unittest discover -s ./measured_readout/processor_readout -p test_processor.py -v
```

Result: **18 tests passed in 0.030 seconds**.
These tests use synthetic fixtures, mocked HTTP responses, and temporary directories.
They do not download final data or execute scientific evaluation.

At 18:42:15 UTC, the range ledger recorded 12,615,808 received bytes and one completed range.
It contained no source-test range and no failure entry.
`test_consumed.json`, `train_frozen/receipt.json`, and `train_frozen/selection.json` were absent.
These are review-time observations, not a claim about later execution.

## Reviewed safeguards

**Source-test seal.** `processor_io.py:44` binds approval to the exact frozen-training receipt hash.
It checks registered source files and every frozen training artifact.
Both range retrieval and header verification apply this gate to source-test files.
Tests reject missing approval, altered code, altered models, mismatched receipts, and false approval.

**Single final evaluation.** `processor_eval.py:131` checks approval before opening the final set.
It rejects an existing consumed marker or output directory.
It writes the consumed marker before the first final label or signal request.
Failures must preserve that marker and partial output. They must not trigger unregistered resampling or retuning.

**Training freeze.** `processor_eval.py:81` uses only the registered source-train partitions.
Reference, calibration, and validation rows are disjoint.
All eight method/window candidates and deterministic tie-breaking are specified before final evaluation.
Training freezes the selected model and a separately named boxcar export candidate.
The final routine scores frozen models without refitting them.

**Byte alignment and download scope.** `processor_io.py:34` checks the NPY header, dimensions, dtype, order, and file length.
Byte offsets use the 128-byte header and the full 1,540-value float64 row width.
Ranges require HTTP 206 and an exact `Content-Range`.
The code checks its cumulative byte cap before requesting data.
Cached data require matching length, ledger entry, and SHA-256.
Tests reject ignored ranges, truncated data, duplicate rows, invalid bounds, and altered cached bytes.
Signal ranges reshape into 770 interleaved IQ samples per row.
Independent overlap-integration tests support the mean-preserving 64-bin transform.

**Accuracy and intervals.** `processor_eval.py:46` separates balanced accuracy from pooled accuracy.
It reports class counts, confusion counts, and per-class Wilson intervals.
The pooled Wilson interval is explicitly not a balanced-accuracy interval.
Intervals retain their conditional IID assumption.
The source supports preparation-label classification. It does not certify the quantum system's true state.
Unavailable acquisition identities prevent independent-acquisition or drift-transfer claims.
The 90% threshold is a preregistered engineering criterion, not a physics fidelity guarantee.

**Integer arithmetic.** `processor_eval.py:114` exports the frozen boxcar candidate, which may differ from the selected classifier.
The scale derives from training data only. Quantization uses signed 16-bit inputs and explicit clipping counts.
The bias includes the 64-bin factor required when replacing a mean with an integer sum.
Before scoring, the code checks the bound `64 * 32768 * sum(abs(weights)) + abs(bias) < 2**63`.
An independent Python-integer loop checks every full-width score.
The pack records clipping, floating-point decision disagreements, weights, bias, scale, and source row IDs.
This establishes host arithmetic parity. It does not establish compiled C, RTL, or FPGA parity for these coefficients.

## Conditions before the coordinator releases source-test data

1. Recheck the registration SHA above and all registered source, protocol, header, and label hashes.
2. Require a completed training receipt with 8,192 reference, 4,096 calibration, and 4,096 validation rows.
3. Check actual class counts, finite inputs, valid scales, exact registered row ranges, and every cached training-range hash.
4. Require all eight candidate results and deterministic selection. Keep the boxcar export candidate separately identified.
5. Verify the frozen models, selection, source-row record, and range-manifest hashes against the training receipt.
6. Corroborate `source_test_values_read: 0` with the actual ledger. Require no consumed marker or source-test signal/label retrieval.
7. Bind the release file to that exact receipt SHA. Identify the reviewer honestly as AI/coordinator review.
8. Preserve the frozen final ranges and acceptance rule. Do not select another model after seeing final candidate results.

## Conditions before reporting final results

Require exactly 8,192 registered source-test rows and at least 1,024 rows per preparation label.
Require the saved source-row IDs, range hashes, predictions, confusion counts, and duplicate check.
Exact training/test signal duplicates cause failure. Do not silently remove or replace them.
Report the preregistered selected classifier's threshold outcome even when another candidate scores better.
Name the exported boxcar candidate and report its own metrics and clipping separately.
Retain per-class intervals, conditional IID language, and acquisition limits.
Treat calibration differences as observed paired changes unless a prespecified uncertainty analysis supports a stronger claim.

Range hashes verify downloaded bytes and later local integrity.
They do not establish a complete upstream signal-file checksum because only selected byte ranges are downloaded.
The pinned source URL, header checks, and range receipts must remain available for provenance.

New measured-readout coefficients remain host-only under the current hardware contract.
No final-data, accuracy, or hardware result is approved by this code review alone.

## Deferred evidence

The completed training receipt and frozen artifacts were unavailable during this review.
Final evaluation receipts and numerical outcomes therefore remain unreviewed.
The coordinator may apply the checks above when those artifacts arrive.
