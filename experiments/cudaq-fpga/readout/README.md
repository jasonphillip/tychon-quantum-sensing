# Conditional-cavity readout

A synthetic dispersive-resonator benchmark with a frozen two-weight integer readout core.
CPU analytic data generation, an independent CPU density solver, and optional CUDA-Q Dynamics serve separate roles.
No physical qubit, receiver, or quantum sensor supplied these data.

## Recorded results

- The frozen selection rule chose boxcar over matched filtering and shrinkage LDA after tied validation scores.
- The initial held-out test scored 640/640; initial drift stress scored 627/640 with that unchanged boxcar.
- The later stress pack contains 10,240 records: raw and host-calibrated views of 5,120 final synthetic shots.
- All exported scores match the portable integer reference. Correct arithmetic does not imply correct state classification.
- CUDA-Q 0.16.0.post1 and CuPy 13.6.0 on NVIDIA GB10 validated **four representative density evolutions**.
  Maximum amplitude error was 3.438e-7. CUDA-Q did not generate every receiver record.

See [initial metrics](artifacts/cpu_v2/metrics.json), [GPU metrics](artifacts/gpu_v2_retry/metrics.json),
and [stress results and limitations](stress_v2/README.md).
These are frozen, consumed evaluation sets. Do not tune algorithms against their final results.
This package does not claim GPU speed advantage, physical quantum validation, or radiation qualification.

## Verify the published package

From this directory, use Python with NumPy 2.x, a C compiler, and a C++11 compiler.
Dependencies are listed in [requirements.txt](requirements.txt); install them in your own isolated environment.
The commands below run focused tests and verify existing frozen records. They do not regenerate the scientific benchmark.

```sh
export OPENBLAS_NUM_THREADS=4 OMP_NUM_THREADS=4 VECLIB_MAXIMUM_THREADS=4 PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s . -p test_readout.py -v
python3 -m unittest discover -s stress_v2 -p test_stress.py -v
python3 verify_frozen.py
```

The verifier checks published hashes, replay shapes, and all 10,240 exact C++ scores.
It builds the executable in a fresh temporary directory and removes it afterward.

## Optional experiment reproduction

Use new output paths. The runners refuse an existing output directory.
The following examples are reproduction instructions, not experiments rerun during publication curation.

```sh
python3 readout_pilot.py cpu --config config_v2.json --output runs/cpu-new
python3 stress_v2/run_stress.py --output stress_v2/runs/stress-new
python3 readout_pilot.py gpu --config config_v2.json --output runs/gpu-new
```

The GPU command requires a compatible CUDA-Q Dynamics/CuPy installation and NVIDIA hardware. It has no CPU fallback.
The frozen `artifacts/cpu_v2/fixed_test_vectors.npz` can also support `export_hls.py` in a fresh copied artifact directory.
Generated vendor HDL, tool environments, executables, and licensed Microchip project files are excluded.

## Model and integer interface

For fixed qubit label `z = ±1`, `H/ħ = (Δ + zχ)a†a + ε(a+a†)` and `L = sqrt(κ)a`.
Times use microseconds; Hamiltonian coefficients use rad/µs and photon loss uses inverse microseconds.
An independent Fock-basis Lindblad RK4 solver checks analytic coherent amplitudes, trace, eigenvalues, truncation, and step convergence.
Receiver samples add classical correlated noise. They are not measurement-conditioned quantum trajectories.

The core consumes 64 interleaved I/Q pairs as signed int16 with eleven fractional bits.
It returns a signed int64 score with 25 fractional bits; score ≥0 predicts initial excitation.
Two fixed weights are −16,384 and 2,811; bias is 214,072,292.
Each quadrature sum fits int32. The frozen full-input score bound is 40,468,904,932; int64 preserves headroom.
The [replay manifest](stress_v2/artifacts/frozen_v2/board_replay/manifest.json) defines byte order, shapes, coefficients, and hashes.

## Preserved corrections

The original twelve-level truncation failed before dataset evaluation. Its [failure receipt](artifacts/cpu/failure.json)
and [physics diagnostics](artifacts/cpu/physics.json) remain included.
Sixteen levels, checked against twenty, passed without relaxing tolerances or changing seeds.
The first GPU call failed before evolution because of an operator namespace mismatch.
Its [failure receipt](artifacts/gpu_v2/failure.json) remains separate from the successful retry.
The historical CPU source snapshot identifies the pre-API-correction execution; current code uses `operators.define` and `operators.instantiate`.

[SOURCE_MAP.json](SOURCE_MAP.json) maps original relative paths and hashes to public files.
Only recorded private command paths were normalized; frozen numerical bytes and inference cores remain unchanged.
Full calibration/evaluation float arrays are omitted. The final integer replay pack, labels, per-record metadata, metrics, and calibration fits are included.

Model context: [Blais et al., Circuit quantum electrodynamics](https://arxiv.org/pdf/2005.12667).
API context: [NVIDIA CUDA-Q Dynamics examples](https://nvidia.github.io/cuda-quantum/latest/using/examples/dynamics_examples.html).
The recorded execution receipts, rather than these references, support the reported results.
