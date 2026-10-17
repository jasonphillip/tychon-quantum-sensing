# Coupled-spin NV estimator

This synthetic benchmark connects an effective NV–13C spin model to a compact integer template matcher.
It includes finite microwave pulses, photon-count noise, calibration mismatch, and a shot-budget sweep.
No diamond, optical apparatus, or live quantum sensor was used.

The CPU generated the datasets. CUDA-Q Dynamics checked **eight representative evolution cases** on an NVIDIA GPU.
That check does not establish full-dataset GPU generation or GPU speed advantage.
The [parent experiment](../README.md) records the separate FPGA deployment and replay evidence.

## Model and interface

The basis is `|0,↑>, |0,↓>, |-1,↑>, |-1,↓>`.
The model keeps two electron levels and one nuclear spin-1/2 under rotating-wave and electron-secular assumptions.
The physical projected electron operator is `Sz = diag(0,-1)`, not electron Pauli-Z divided by two.

```text
H/(2π) = δ σz/2 + ν τz/2 + Sz (Aparallel τz/2 + Aperp τx/2)
         + Ω (cos(φ) σx + sin(φ) σy)/2
```

Time is in microseconds; δ, ν, A, and Ω are in MHz. H is in radians per microsecond.
The electron starts in `|0>` and the nucleus is maximally mixed.
Rectangular π/2 pulses last 1/6 microsecond at nominal Ω=1.5 MHz.
The numerical couplings and readout rates are benchmark assumptions, not measured device parameters.
The stress model adds free-evolution phase damping. Pulse dephasing, optical dynamics, and a larger spin bath are absent.
See [sources](SOURCES.md), [initial protocol](FROZEN_PROTOCOL.md), and [stress protocol](STRESS_PROTOCOL_V2.md).

The frozen core accepts 128 signed Q14 values: 64 I samples followed by 64 Q samples.
It searches 121 fixed templates and returns a uint16 index plus the full uint64 squared-distance score.
The ROM contains 30,976 numerical bytes. The detuning grid spans −750 to +750 kHz in 12.5 kHz steps.
The worst possible score is 549,739,036,800; a 32-bit accumulator is insufficient.
The score is not a calibrated confidence probability. See the [arithmetic contract](FPGA_CONTRACT.md).

## Results and preserved failures

The matched pilot's continuous CPU fit reached 252 Hz mean absolute error on 128 held-out readouts.
That result assumes known calibration. It does not describe performance under unknown mismatch.
The stress sweep used 96 new configurations, including 64 final configurations and 2,048 final readouts.
The same final configurations appear across budgets and scenarios; those observations are paired.

| Repetitions per phase/delay | Matched fixed-grid MAE | Combined-mismatch fixed-grid MAE | Combined-mismatch profiled CPU MAE |
| ---: | ---: | ---: | ---: |
| 100 | 4.40 kHz | 10.23 kHz | 7.27 kHz |
| 500 | 3.62 kHz | 6.61 kHz | 4.78 kHz |
| 2,000 | 3.31 kHz | 6.24 kHz | 4.30 kHz |
| 20,000 | 3.29 kHz | 6.11 kHz | 4.18 kHz |

**The frozen 99% floating/fixed agreement gate failed:** optical drift at 100 repetitions produced **98.4375%**, or 126/128 agreement.
Both disagreements contained three saturated input values. Forty readouts in that cell contained saturation.
The 100-repetition combined-mismatch cell also contained a **249.5 kHz worst error**.
These failures remain in the [metrics](artifacts/stress_frozen_v2/metrics.json) and replay package.
They were not removed by rescaling inputs, replacing the core, or changing the acceptance threshold.

The profiled CPU estimator is a comparison method, not the FPGA implementation. It does not improve every setting.
At 2,000 repetitions, combined-mismatch fixed-grid MAE has a configuration-cluster interval of 5.30–7.25 kHz.
Increasing the budget tenfold barely improves that cell, indicating model/grid limits in this experiment.
Each input requires 256 times the per-phase/delay repetition count; acquisition cost is separate from inference latency.
Illustrative acquisition times of 0.162–32.427 seconds are modeled, not measured sensor or board timings.

The retained [CUDA-Q receipt](artifacts/cudaq_check_v1.json) records eight passing cases using CUDA-Q 0.16.0.post1.
Maximum probability disagreement was `1.1035e-10`; maximum density-element disagreement was `1.0365e-10`.
The stress sweep adds no GPU execution claim.

## Verify the frozen package

Use Python 3.11 or later with NumPy; the CPU validation environment used NumPy 2.4.2.
`requirements.txt` specifies the supported NumPy major range. Install it in your own environment if needed.
Set `NV_PYTHON` to that environment's Python executable, or let it use `python3`.
Run these commands from this `nv` directory:

```sh
NV_ROOT="$(pwd)"
NV_PYTHON="${NV_PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=1
"$NV_PYTHON" -m unittest discover -s "$NV_ROOT" -p 'test_*.py' -v
"$NV_PYTHON" "$NV_ROOT/verify_board_vectors_v2.py" --directory "$NV_ROOT/artifacts/stress_frozen_v2/board_vectors"
NV_TEST_BIN="$(mktemp "${TMPDIR:-/tmp}/nv-c-test.XXXXXX")"
cc -O2 -std=c99 -Wall -Wextra -Werror "$NV_ROOT/nv_match.c" "$NV_ROOT/artifacts/hls_reference_v1/nv_testbench.c" -o "$NV_TEST_BIN"
"$NV_TEST_BIN"
rm -f "$NV_TEST_BIN"
```

Expected results: 14 Python tests, all 2,061 replay indices and full scores verified, and eight exact compiled-C test vectors.
These commands do not access FPGA hardware or generate a new scientific dataset.
The 2,061 replay vectors comprise all 2,048 final stress inputs and 13 interface boundaries.
Their [manifest](artifacts/stress_frozen_v2/board_vectors/manifest.json) preserves case IDs, saturation flags, hashes, and byte counts.

## Optional reproduction

These commands regenerate the original consumed datasets into new directories; they are not fresh model-selection evidence.

```sh
"$NV_PYTHON" "$NV_ROOT/run_pilot.py" --output "$NV_ROOT/outputs/pilot-new"
"$NV_PYTHON" "$NV_ROOT/run_stress_v2.py" --output "$NV_ROOT/outputs/stress-new"
```

For the optional eight-case GPU check, use a compatible CUDA-Q 0.16.0.post1 environment with an NVIDIA GPU.
The historical receipt records the precise Python, NumPy, CuPy, and GPU versions.
Set `NV_CUDAQ_PYTHON` to that environment's executable before running:

```sh
"${NV_CUDAQ_PYTHON:?Set the CUDA-Q environment Python path}" "$NV_ROOT/check_cudaq.py" --output "$NV_ROOT/outputs/cudaq-check-new.json"
```

The script refuses CPU substitution and an existing output file.
`hls/` contains authored wrapper/configuration files; no generated Microchip HDL or IP is included.
Historical command metadata was made portable. [SOURCE_MAP.json](SOURCE_MAP.json) maps every altered file to its original hash.
Frozen numerical binaries retain their original bytes. Large raw v2 arrays are omitted; aggregate metrics and every replay vector remain available.
