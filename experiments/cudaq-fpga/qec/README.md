# Small surface-code decoder and noisy-history comparison

This experiment connects an explicit `[[9,1,3]]` rotated surface code to a compact FPGA lookup core.
The core maps one eight-bit syndrome to an 18-bit Pauli-frame correction.
Its 256-entry table uses maximum-likelihood stabilizer-coset decoding, frozen at data-error probability `p=0.03`.
This is an established decoding method, not a novel decoder.

The FPGA receives **one compressed syndrome**, not a sequence of noisy measurements.
The host performs last-record or majority compression before replay.
Exact FPGA agreement validates the interface and lookup implementation. It does not establish successful physical quantum correction.
See the [parent experiment](../README.md) for integrated FPGA results.

## Frozen results

The [single-round configuration](config.json) assumes independent depolarizing data errors and perfect syndrome measurement.
Exhaustive checks cover all 262,144 Pauli errors, all 256 syndrome values, and all 27 single-qubit Pauli errors.
At `p=3%`, exact logical failure is 1.110994% for the fixed table and 1.301599% for separate X/Z minimum-weight decoding.
These results concern this small noise model. They establish neither a threshold nor a general advantage over optimized decoders.

The [repeated-round protocol](noisy_rounds/PROTOCOL.md) adds independent measurement-bit flips and accumulated data errors.
The frozen study contains 240,000 trials across twelve cells, with 3, 5, or 9 noisy rounds.
The table below shows nine rounds with `p=q=1%`, using the same 20,000 trials.

| Method | Available information | Recovery failures |
| --- | --- | ---: |
| Last noisy syndrome → table | Noisy history only | 3,003 / 20,000 (15.015%) |
| Majority syndrome → table | Noisy history only | 6,421 / 20,000 (32.105%) |
| Final-perfect syndrome → table | Perfect terminal syndrome | 1,591 / 20,000 (7.955%) |
| Space-time PyMatching | Noisy history and perfect terminal syndrome | 738 / 20,000 (3.690%) |

**The majority baseline failed when data errors changed the true syndrome over time.**
Its 6,421 failures include 5,975 residual syndrome violations and 446 logical residuals within the code space.
Reporting only logical residuals would conceal most failures.
Measurement-only noise is different: majority helps there, but zero observed failures does not establish a zero failure rate.

The fair offline comparison is final-perfect table versus PyMatching. Both receive perfect terminal information.
The online compressors lack that information, so their difference cannot be attributed solely to the decoder.
PyMatching uses separate X/Z space-time graphs and ignores Y-error correlations between sectors.
This is phenomenological noise, without faulty extraction gates, leakage, or crosstalk.

- [Complete noisy-round metrics and Wilson intervals](noisy_rounds/artifacts/frozen_v1/metrics.json)
- [Measurement-only analytic diagnostic](noisy_rounds/artifacts/frozen_v1/measurement_only_analytic_check.json)
- [Original Mac CPU metrics](artifacts/mac_retry/metrics.json) and [Linux CPU metrics](artifacts/linux_validation/metrics.json)

## Verify the published package

Run these commands from this directory. The first three require Python 3.10+ and a C++11 compiler only.
They check saved evidence and deterministic invariants without regenerating the scientific trial streams.

```sh
python3 -m unittest discover -s . -p test_qec.py -v
python3 verify_frozen.py
python3 noisy_rounds/verify_board_vectors.py --directory noisy_rounds/artifacts/frozen_v1/board_vectors
```

The compiler can be selected through `CXX`, for example `CXX=g++ python3 verify_frozen.py`.
The verifier compiles into a temporary directory and compares all 768 outputs across the three C++ decoders.
It also checks all 4,864 saved replay corrections against compiled C++ output.

Optional noisy-history tests need the recorded reference dependencies. The original environment used Python 3.11.
Create a separate environment; do not install these packages globally.

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -r noisy_rounds/requirements-lock.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python noisy_rounds/test_noisy.py
```

Five test groups include 162 independent Stim trajectory checks in both logical bases.
They also preserve a counterexample where majority misses a late data error.
The lockfile records the original environment; dependency installation was not repeated during publication.

To regenerate the original studies, use new output directories:

```sh
python3 run_benchmark.py --output artifacts/new_cpu_run
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv/bin/python noisy_rounds/run_noisy.py --output noisy_rounds/artifacts/new_run
```

These commands rerun consumed seeds. They reproduce prior experiments and do not create fresh evaluation sets.
The CPU benchmark rewrites `qec_tables.h` deterministically from the frozen configuration.
Publication verification did not rerun either study.

## CUDA-Q role and preserved failure

CUDA-Q independently checks ideal encoded-state circuits and injected Pauli errors.
The classical Pauli sampler generates the main study. This experiment demonstrates no GPU speedup.
The saved CUDA-Q run used `cuda-quantum-cu13 0.16.0.post1` on an NVIDIA GPU.

The [FP32 run](artifacts/cudaq_nvidia_fp32_failed.json) failed the frozen `1e-5` absolute tolerance: maximum error `6.031990051269531e-5`.
The [explicit FP64 retry](artifacts/cudaq_nvidia_fp64.json) passed all 60 syndrome and eight logical-basis checks.
Its maximum error was `1.7053025658242404e-13`, with the same tolerance.
Use an existing compatible CUDA-Q environment on an NVIDIA host:

```sh
python3 cudaq_spotcheck.py --target nvidia --precision fp64 --output artifacts/new_cudaq_fp64.json
```

The script rejects a requested GPU target without an available GPU. Publication verification did not repeat GPU execution.
For larger Clifford circuits, a stabilizer simulator such as Stim is an appropriate baseline.

## FPGA replay contract and package contents

`qec_decode(uint8_t syndrome)` uses no allocation or data-dependent loop.
Input bits 0–3 encode Z-check syndromes; bits 4–7 encode X-check syndromes.
Output bits 0–8 encode X-frame changes; bits 9–17 encode Z-frame changes; upper bits are zero.
The source table contains 4,608 meaningful bits, stored as 1,024 bytes of `uint32_t` values.
These source-level counts are not synthesis resource measurements.

The [replay manifest](noisy_rounds/artifacts/frozen_v1/board_vectors/manifest.json) preserves case histories and failure labels.
It covers 128 fixed-index trials per cell for three input modes, plus all 256 syndrome words.
`inputs_u8.bin` and `expected_corrections_u32.bin` retain their original bytes and SHA256 hashes.
The manifest's original host-only wording describes vector generation, before subsequent integrated board replay.

Authored SmartHLS inputs are in `hls/`; no generated Microchip HDL or IP is included.
Its 10 ns configuration describes the standalone HLS stage, not the integrated system clock.
Original summary receipts remain unchanged, including their stage-specific hardware fields.
[SOURCE_MAP.json](SOURCE_MAP.json) records original and published hashes and every text adaptation.
Raw Monte Carlo NPZ streams, private command logs, environments, and executables are omitted.
Their historical hashes remain in the frozen metrics; they are not claims that omitted files are bundled here.

Quantum correction does not harden the FPGA against radiation.
This package establishes no physical-qubit correction, full temporal FPGA decoder, threshold, radiation qualification, or GPU acceleration advantage.
[Micro Blossom](https://github.com/yuewuo/micro-blossom) is established FPGA-decoder prior art and was not benchmarked here.
The PyMatching construction follows its [noisy-syndrome documentation](https://pymatching.readthedocs.io/en/stable/toric-code-example.html#noisy-syndromes).
