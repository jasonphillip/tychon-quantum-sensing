# Measured processor-readout results

Executed October 17, 2026. This report supersedes the proposed execution status in `QUALIFICATION.md`.
The reviewed protocol and original qualification remain unchanged.

**PASS: the preselected matched filter reached 95.8252% balanced preparation-label accuracy.**
It correctly assigned 7,850 of 8,192 held-out source-test records, exceeding the frozen 90% engineering threshold.
The affine calibration showed no improvement on these records.
This is a host result on measured data. It is not FPGA execution or certified quantum-state fidelity.

## Source and frozen comparison

The source is [Zenodo 14427490](https://zenodo.org/records/14427490), licensed CC-BY-4.0.
Source creators: Du, Botao.
The [primary paper](https://arxiv.org/html/2501.14663v1) describes QICK/hls4ml superconducting-transmon readout.
Pinned [author code](https://github.com/fastmachinelearning/ml-quantum-readout/tree/2c7efadb21c1aa2bab2e5fc12ff403cb28af5d25) establishes interleaved I/Q layout and intended preparation labels.
Each recorded trace contains 770 IQ pairs. Values use native digital units; a voltage conversion was not established.
The paper describes a 2.5-microsecond readout pulse. This study uses sample indices rather than an inferred calibrated time grid.

All development used source-train: 8,192 reference records, 4,096 calibration records, and 4,096 validation records.
Each partition contained equal counts of the two preparation labels.
All methods received the same 12,288 labelled fitting records and the same 4,096 validation records.
The pooled baselines fit both fitting partitions. The affine method fits a reference classifier and a calibration transform separately.
The final 8,192 source-test records contained 4,096 records per label.
Every row range was fixed before signal retrieval; no rows were replaced or filtered.
Exact source-signal comparison found no duplicate between selected training and final records.

The candidate windows were the full trace `[0,770)` and the paper-prior window `[100,500)`.
Each became 64 IQ pairs through overlap-weighted, equal-width integration.
The transform preserves the window mean, including fractional source-sample overlaps.
The affine model uses empirical measured reference templates. It does not reuse synthetic-project coefficients.
The matched filter uses the difference between class means. LDA uses a pooled covariance with fixed 0.2 shrinkage.
No neural model or GPU was used.

## Frozen selection and final results

Validation tied matched filtering and affine calibration at 95.4834% for `[100,500)`.
The predeclared method priority selected matched filtering. Final results did not change that choice.

| Candidate and source window | Validation balanced accuracy | Final balanced accuracy |
| --- | ---: | ---: |
| pooled_boxcar@0:770 | 94.8975% | 95.3857% |
| pooled_matched_filter@0:770 | 94.7754% | 95.3491% |
| pooled_lda_shrinkage_0.2@0:770 | 95.1416% | 95.7397% |
| affine_reference_boxcar@0:770 | 94.9219% | 95.3979% |
| pooled_boxcar@100:500 | 95.4590% | 95.8374% |
| pooled_matched_filter@100:500 | 95.4834% | 95.8252% |
| pooled_lda_shrinkage_0.2@100:500 | 95.4346% | 95.8252% |
| affine_reference_boxcar@100:500 | 95.4834% | 95.8252% |

The boxcar export candidate was separately selected on validation: `pooled_boxcar@100:500`.
Its final floating-point result was 95.8374%. A one-record difference does not establish superiority over the selected method.

Selected-method confusion counts, with preparation as rows and assignment as columns, are `[[3996,100],[242,3854]]`.
Ground-preparation assignment error was 2.4414%; excited-preparation assignment error was 5.9082%.
The separate 95% Wilson accuracy intervals are 97.0395–97.9885% and 93.3276–94.7734%.
These intervals assume independent, identically distributed shots within each preparation class.
Unverified acquisition correlations can invalidate that assumption. No acquisition-level uncertainty estimate is claimed.
The JSON also labels a pooled-accuracy interval separately; it is not a balanced-accuracy interval.

## Calibration result and unresolved scope

Against the fixed reference boxcar, full-window calibration corrected two records and regressed two.
The shorter-window calibration corrected three and regressed four: a net decrease of 0.0122 percentage points.
These paired counts show no observed calibration benefit in this final subset.
The equal-information pooled baselines remain the appropriate practical comparison.

The export lacks exact row-to-acquisition identifiers and timestamps.
Index-separated blocks are not asserted to be chronological or independent acquisitions.
**Drift-transfer eligibility remains false.** This result supports held-out source-partition preparation classification only.
Preparation errors remain possible; intended labels are not perfect true-state labels.
The study uses a bounded subset and does not reproduce or outperform the paper's full benchmark.
The prior thermal-detector experiment remains frozen at 75.8%, below its separate 80% threshold.
No failed result was replaced or retuned.

## Integer handoff

`test_frozen/candidate_integer_pack/` contains all 8,192 source-test records and their source-row identities.
Inputs contain 128 little-endian int16 values per record. Expected scores contain one little-endian int64 per record.
The new boxcar weights are `[10235, -16384]` and the bias is `-33543462`.
The input scale is 560.78 native digital units per normalized unit, with 11 input fractional bits.
The accumulated score uses 25 fractional bits and the explicit 64-bin factor in the bias.
Its full-int16 absolute score bound is 55857632550, below the signed 64-bit limit.
Python arbitrary-precision arithmetic reproduced every expected score exactly.
There were zero clipped values and one changed decision relative to floating-point boxcar inference.
The integer candidate reached 95.8496% balanced preparation accuracy.
That one changed decision is a quantization observation, not evidence of an accuracy improvement method.

These coefficients require a future FPGA image. The current image and previous consumed packs remain unchanged.
There is no compiled C, RTL, FPGA, live-sensor, radiation, or end-to-end acquisition result for this new pack.
The floating-point matched filter and LDA are not claimed to use the deployed boxcar interface.

## Execution and integrity

The source/test split, candidate selection, and acceptance rule were frozen before final access.
An independent AI code review and coordinator checks released the final set.
This was not human subject-matter review or external endorsement.
`test_consumed.json` was written before the first final payload request.

| Stage | Retrieval wall time | Fitting or evaluation/export wall time | Peak process RSS |
| --- | ---: | ---: | ---: |
| Training | 712.320 s | 0.295 s | 504,725,504 bytes |
| Final | 306.347 s | 0.234 s | 382,074,880 bytes |

RSS uses `getrusage(RUSAGE_SELF).ru_maxrss` with platform-specific units.
These are whole-stage timings, not inference latency or hardware cycle measurements.
Mac execution used Python 3.14.3 and NumPy 2.4.2, with numerical thread limits set to four.
Both stages stayed below the 8 GiB and 1,800-second limits.
The range ledger records 302,842,240 received bytes, including checked headers, and no failed retrievals.
Adding earlier data and the reserved metadata allowance accounts for 320,977,104 bytes against the 400,000,000-byte lane cap.
All 32 complete ranges retain individual SHA-256 hashes. Downloaded ranges are read-only.
These local hashes do not establish the complete upstream signal-file checksum.
The complete training-label file independently passed the source MD5 checks.

Training receipt SHA-256: `79cfec86ecc790c301fc1ca9ae9298f91da5ca44dd60562ce59b9a2161395134`.
Final metrics SHA-256: `eb9ac03f0ed929e5af40864e613fe32bcb6e4a1d6627ad4d4fb2cdf68ce518cc`.
Mac unit tests: 18 passed. Full saved-result verification passed 16,384 training rows, 16 training ranges, eight prediction candidates, and 8,192 integer records.
See `README.md` for the exact executed checking commands.
Linux portability passed on Linux generation host: 18 processor tests, 10 thermal tests, and all 8,192 saved integer records.
The existing environment used Python 3.13.11, NumPy 2.4.2, and h5py 3.14.0 on Linux aarch64.
`portability/linux_results.json` records commands, outputs, source-bundle hash, and elapsed times.
All 18 staged source/result files passed SHA-256 checks. No Linux scientific evaluation or raw-data retrieval occurred.
One orchestration wrapper had a JavaScript syntax error before SSH execution. A corrected string launcher completed once.
`portability/launcher_failure.json` preserves that non-scientific failure; it did not consume or rerun test data.
