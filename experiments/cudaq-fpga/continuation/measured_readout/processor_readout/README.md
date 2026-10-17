# Measured processor-readout comparison

This study compares frozen classical classifiers on recorded superconducting-transmon readout.
The labels describe intended state preparation. They do not certify each shot's true state.
Acquisition identifiers are unavailable, so this study cannot establish drift transfer.
The earlier thermal-detector failure remains unchanged in the parent directory.

The source is [Zenodo 14427490](https://zenodo.org/records/14427490), licensed CC-BY-4.0.
`QUALIFICATION.md` records the paper, pinned author code, array layout, and source limitations.
`PROPOSED_PROTOCOL.json` fixes every row range, candidate, selection rule, and acceptance threshold.
Its original proposed-status wording remains preserved. The coordinator approved that exact protocol before execution.

## Check the saved work

The following commands use the isolated Mac environment. They need no network or hardware.

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 python3 -m unittest discover -s ./measured_readout/processor_readout -p test_processor.py -v

PYTHONDONTWRITEBYTECODE=1 python3 ./measured_readout/processor_readout/verify_saved_processor.py --pack-only
```

The verifier needs completed frozen outputs. During training, use its `--train-only` option after the training receipt exists.
For a compact copied result bundle, use `--pack-only`. That mode uses Python's standard library only.
It checks saved integer arithmetic, file hashes, source-row labels, and prediction confusion counts.
It does not fit classifiers or rerun scientific evaluation.

The unit tests require NumPy. The evaluation code supports macOS and Linux and limits numerical threads to four.
Linux execution must use an existing isolated interpreter or a new local environment.
No global installation is required.

## Registered execution

The `register`, `train`, and `test` subcommands each refuse existing output or consumed state.
Do not delete receipts to make an existing experiment run again.
`train_registration.json` freezes source, protocol, headers, and source-training labels before signal retrieval.
`train_frozen/receipt.json` binds the resulting parameters, selection, source rows, and range hashes.

The `test` command requires an independent release file bound to that training receipt.
`REVIEW_GATE.md` specifies its schema. This lane cannot approve its own release.
The final command records consumption before its first source-test request.
All retrieved ranges require exact HTTP range responses, byte lengths, source offsets, and SHA-256 receipts.
Partial failures remain preserved. A complete upstream signal-file checksum is unavailable from selected ranges.

## Integer handoff

`test_frozen/candidate_integer_pack/` contains new boxcar coefficients and recorded input vectors after final evaluation.
Each record contains 64 interleaved IQ pairs: 128 little-endian signed 16-bit values.
The reference output is a little-endian signed 64-bit score.
The manifest records two integer weights, bias, normalization, source-row mapping, clipping, and decision differences.

The exported boxcar candidate may differ from the selected floating-point classifier.
These coefficients require a future FPGA image. Current evidence covers host arithmetic only.
The previous deployed image and its coefficients remain unchanged.

## Verified Linux checks

The following exact commands passed in the existing Linux generation host environment. They download no raw data.

```sh
PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 python3 -m unittest discover -s ./measured_readout/processor_readout -p test_processor.py -v

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 python3 -m unittest discover -s ./measured_readout -p test_evaluate.py -v

PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 python3 ./measured_readout/processor_readout/verify_saved_processor.py --pack-only

```

The receipt is `portability/linux_results.json`. All three commands returned zero.

Public-copy note: raw processor ranges are excluded. Use `--pack-only` for offline saved verification.
