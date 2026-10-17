# Processor-readout qualification and bounded proposal

**This is a stronger direct readout candidate. No processor-record evaluation has occurred.**
The source-test record values remain untouched. Only four NPY headers and source-training labels were retrieved.
The earlier thermal result remains frozen and failed its 80% target.

## Established source facts

[Zenodo 14427490](https://zenodo.org/records/14427490) provides the QICK/hls4ml study data under CC-BY-4.0.
All four NPY headers were inspected through exact byte ranges.
Training signals have shape `[900000,1540]`; test signals have shape `[100000,1540]`.
Labels have corresponding one-dimensional shapes. Every array uses little-endian float64, C order, with 128-byte headers.
The complete 7.2 MB training-label file passed Zenodo's MD5 and the authors' array-MD5 check.
It contains 450,000 labels of each class, in 180 alternating 5,000-row runs.

The [primary paper](https://arxiv.org/html/2501.14663v1#S2.SS3) describes superconducting-transmon readout after intended ground/excited preparation.
A 2.5-microsecond pulse produces 770 I/Q samples. Preparation errors remain possible.
The paper describes digital acquisition and a prior 400-sample window beginning at 100; it does not supply an exact voltage conversion for the exported arrays.
These statements establish measurement context, not an independently certified state on each shot.

The [authors' processing code](https://github.com/fastmachinelearning/ml-quantum-readout/blob/2c7efadb21c1aa2bab2e5fc12ff403cb28af5d25/training/save_data.py) constructs `[shot,time,(I,Q)]` then flattens rows.
The [window slicer](https://github.com/fastmachinelearning/ml-quantum-readout/blob/2c7efadb21c1aa2bab2e5fc12ff403cb28af5d25/data/qick_data/generate_window.py) independently uses doubled sample offsets.
The [final training notebook](https://github.com/fastmachinelearning/ml-quantum-readout/blob/2c7efadb21c1aa2bab2e5fc12ff403cb28af5d25/final/train.ipynb) loads the exact 0528 files and maps 0 to ground preparation, 1 to excited preparation.
The older 1440-column description in `data/README.md` does not describe these 1540-column arrays.
Use native digital units and sample index; do not label values volts or infer a calibrated nanosecond grid.

## Acquisition limitation

Author preprocessing concatenates 100 raw HDF5 files, then splits the first 90% for training.
However, the exact export contains no row-to-file identifiers or acquisition timestamps.
Matching label runs support an ordering interpretation; they do not prove independent drift acquisitions.
**Drift-transfer eligibility remains false.** A source-test classification comparison is the proposed claim.

## Proposed next run, awaiting protocol review

`PROPOSED_PROTOCOL.json` lists every half-open row range before any signal retrieval.
The reference, calibration, and validation blocks all come from source-train.
They contain 8,192, 4,096, and 4,096 records respectively.
The source-test final ranges contain 8,192 records and remain unopened until approval and model freeze.
Index tiles are used for efficient sampling only; they are not called acquisitions.
No test-row resampling will occur if class balance differs from training labels.

Compare pooled boxcar/threshold, matched filter, shrinkage LDA, and empirical affine-reference boxcar.
All methods have equal access to 12,288 labelled fitting records and 4,096 validation records.
Use only the full 770-sample window and the 400-sample paper-prior window.
Each becomes 64 IQ pairs through mean-preserving equal-width integration.
Select the method/window on validation, freeze all parameters, then read source-test once.
The proposed engineering criterion is 90% balanced preparation accuracy, not reproduction of the paper's headline result.
Report error asymmetry, uncertainty, paired disagreements, calibration gain, clipping, and fixed-point parity.
No neural training, GPU, FPGA programming, or advantage claim is proposed.

Remaining signal ranges require 302,776,320 bytes. Selected test labels add 65,536 bytes.
Including prior thermal ranges and training labels, known data transfer totals 318,976,720 bytes.
Metadata adds less than the remaining 81 MB margin under the 400 MB lane cap.
All ranges need response-length/Content-Range validation, per-range SHA256, immutable files, and source-row mapping.
A future download must reject changed headers and preserve any failure before one changed retry.

The next step is coordinator review of the exact protocol. No final evaluation is authorized by this document.
