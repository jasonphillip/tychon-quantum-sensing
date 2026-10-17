# CUDA-Q generation, FPGA replay, and measured readout

Results collected October 17, 2026. This is the public continuation of the [three FPGA demonstrations](../README.md).

| Experiment | Result | Boundary |
| --- | --- | --- |
| Complete CUDA-Q dataset | 32,768 probabilities; maximum CPU difference 2.1511e-9 | 128 synthetic effective NV configurations |
| FPGA replay | 1,024 exact indices and full 64-bit scores; zero mismatches | Saved synthetic inputs, existing PolarFire image |
| Warm generation | CPU 0.01249 s; CUDA-Q 106.637 s | Specialized exact CPU solver versus configured RK4 GPU implementation |
| Thermal-detector data | 75.8% preparation accuracy; failed the 80% target | 1,000 held-out records from one acquisition; host only |
| QICK processor-readout data | 95.8252% balanced preparation accuracy; passed the 90% target | 8,192 fixed source-test rows; host only |

CUDA-Q produced every quantum evolution in the new GPU dataset. CPU code sampled the synthetic detector counts.
The FPGA then reproduced all 1,024 encoded results. Fifteen control checks and the existing V250 inference check passed.
No live sensor or quantum processor was connected.

The CPU was approximately 8,537 times faster for this small model and these implementations.
This does not rank the best possible GPU implementations or demonstrate GPU acceleration.
The measured processor model classified 7,850 of 8,192 preparation labels correctly.
The integer boxcar candidate reached 95.8496%, with zero clipping and one decision changed by quantization.
That small difference does not establish superiority. Preparation labels do not certify the true physical state.
Neither new measured-data classifier ran on the FPGA.

## Verify the saved evidence offline

Run these commands from this directory with Python 3.11+.
The aggregate verifier uses NumPy 2.4.2. The three individual saved-file verifiers use the standard library.
No command below downloads data, fits a model, reruns a quantum experiment, or accesses hardware.

```sh
python3 verify_saved_evidence.py
python3 demo/show_evidence.py --root . --manifest demo/evidence_manifest.json
python3 measured_readout/verify_saved.py
python3 measured_readout/processor_readout/verify_saved_processor.py --pack-only
python3 -m unittest discover -s . -p test_public_verification.py -v
```

The aggregate check verifies publication hashes, all saved NV density/probability tolerances, every NV integer result,
and every saved board index/full score. It also runs the thermal, processor, and 27-file demonstration checks.
It compares saved CPU/GPU labels exactly without regenerating platform-sensitive random labels.
The original Mac seed-rounding failure and the successful original Linux check are both preserved.

Optional fixture tests require NumPy 2.4.2 and h5py 3.14.0:

```sh
python3 -m unittest discover -s demo -p test_show_evidence.py -v
python3 -m unittest discover -s nv_scaling -p test_scaling.py -v
python3 -m unittest discover -s measured_readout -p test_evaluate.py -v
python3 -m unittest discover -s measured_readout/processor_readout -p test_processor.py -v
```

## Evidence and limits

- [NV methods, runtime, memory, and retained portability failure](nv_scaling/REPORT.md)
- [FPGA replay](board/REPORT.md)
- [Thermal detector, including the failed gate](measured_readout/REPORT.md)
- [Processor readout and frozen selection](measured_readout/processor_readout/REPORT.md)
- [AI review of NV and board results](review/final-nv-board-review.md)
- [AI review of measured processor results](review/final-processor-review.md)
- [Publication transformations and exclusions](PROVENANCE.md)

Original low-shot NV limitations remain unresolved. The earlier 98.4375% floating/fixed agreement failed its 99% target.
The prior 249.5 kHz outlier remains evidence against a broad robustness claim.
No acquisition-transfer, radiation-tolerance, power-efficiency, quantum-advantage, or NVIDIA endorsement claim is established.
AI reviews are labeled as AI reviews. No independent human review or external endorsement is recorded.

Authored code uses [Apache-2.0](LICENSE). Measured data and derived records retain [CC-BY-4.0 attribution](NOTICE).
The licensed thermal trace is included for its offline hash check.
Large processor raw signal ranges and unlicensed upstream code copies are excluded; source URLs and hashes remain.
