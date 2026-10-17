# Full CUDA-Q NV dataset protocol

Prepared October 17, 2026, before development GPU execution.
This protocol extends the published four-level synthetic benchmark.
Existing public data and FPGA logic remain unchanged.

## Physical model

Basis: `|0,up>, |0,down>, |-1,up>, |-1,down>`.
Electron levels are the NV `m_s=0,-1` subspace. The nucleus is one spin-half carbon-13.
The omitted `m_s=+1` level, native nitrogen, optical dynamics, and bath dynamics are absent.
The rotating-wave and electron-secular approximations apply.
The electron operator in the coupling is `S_z=diag(0,-1)`, not Pauli Z divided by two.

Times use microseconds. Frequencies use MHz. The Hamiltonian uses radians per microsecond:

`H = 2 pi [ delta Z_e/2 + nu Z_n/2 + S_z(A_parallel Z_n/2 + A_perp X_n/2) + Omega(cos(phi) X_e + sin(phi) Y_e)/2 ]`.

The drive term is present only during the two finite pulses.
The initial density is `|0><0| tensor I_n/2`.
Each pulse lasts `1/(4 Omega)` microseconds.
Preparation phase is pi/2. Readout phase is `phase - pi/2`.
Free delays span 0 through 4 microseconds at 64 points.
Four readout phases are 0, pi/2, pi, and 3pi/2.
All parameter values are benchmark assumptions, not measured NV calibrations.
This is a matched-distribution numerical scaling study, not a robustness claim.

## Complete GPU generation

Every output density traverses three CUDA-Q Dynamics evolutions: preparation, free evolution, and readout.
No CPU-evolved state fills a GPU dataset entry.
Each segment uses normalized time `s in [0,1]` and Hamiltonian `duration * H`.
This transformation preserves the physical evolution and permits different delays within one batch.
A zero delay has a zero scaled Hamiltonian.
The maximum normalized integration step equals the registered physical step divided by the longest segment duration.
Matrices use complex128. The registered RK4 maximum physical step is 0.002 microseconds.
The GPU requires CUDA-Q Dynamics; missing CUDA-Q, missing CUDA hardware, and incompatible APIs fail explicitly.

The installed API was inspected on October 17, 2026: CUDA-Q 0.16.0.post1.
Its `evolve` signature accepts Hamiltonian sequences, initial-state sequences, and `max_batch_size`.
Version 0.16 documentation describes compatible Hamiltonian batching and limits.
A sequential-fallback warning must be retained and disclosed if CUDA-Q emits one.
The first development result determines whether the intended batching executes successfully.

## Frozen development and proposed final sets

`protocol_dev.json`: two independent detunings, 512 output probabilities, 16 detector records.
Parameter seed 1061710101; detector seed 1061710102.
First-call timing plus two warm full-generation repeats.

`protocol_final.json`: proposed 128 independent detunings, 32,768 output probabilities, 1,024 detector records.
Parameter seed 1061710201; detector seed 1061710202.
First-call timing plus three warm full-generation repeats.
The coordinator may reduce the final count using development runtime before opening the final set.
Any change requires a recorded protocol revision and new hash before final execution.
No tolerance, model, or detector tuning uses final outcomes.
Prior v1 and stress-v2 seeds are excluded by a test.
Repeated timing passes do not add independent samples.

## CPU comparator and timing

The CPU comparator batches Hermitian eigendecompositions in NumPy.
It reuses free-evolution eigenvectors across all delays.
It returns the same complete density tensors, rather than only selected observables.
All three segments are computed analytically through matrix exponentials of constant Hermitian Hamiltonians.
An independent commutator RK4 test verifies selected density matrices.
The old scalar implementation independently checks every development probability.

Execute both backends on the same Linux generation host host, with equal data, precision, and CPU thread settings.
Mac receipts validate portability and correctness only; they cannot establish GPU speedup.
Report backend initialization separately from the first evolution call and warm generation median/range.
GPU timings synchronize before completion.
State upload and final download have separate synchronized sub-timings.
Hamiltonian construction, operator encoding, and implicit Hamiltonian upload remain included in evolution timings.
Do not describe these timings as pure GPU kernel time.
GPU operator definitions persist across warm repeats; the CPU comparator still recomputes its very small matrices.
Classical detector sampling, integer matching, validation, and output writes have separate timings.
Validation runs outside the timed evolution. Neither backend uses validation results to generate its outputs.
Program elapsed includes repeats and validation, and starts at the first Python statement.
External `/usr/bin/time -v` can measure interpreter startup and complete process time on Linux.

## Detector and FPGA interface

CPU sampling uses binomial electron projection followed by conditional Poisson photon counts.
Photon rates per shot: bright 0.24, dark 0.10, background 0.02.
Shot budgets per phase/delay are 100, 500, 2,000, and 20,000.
Each configuration has two detector realizations per budget.
This represents 25,600 through 5,120,000 shots per full four-phase acquisition.
CPU sampling is explicitly separate from GPU quantum generation.

The input is 128 signed Q14 values: 64 I followed by 64 Q.
Rounding uses nearest-even, with int16 saturation and clipping counts.
The frozen 121-template ROM remains byte-identical.
Each expected output contains uint16 template index and full uint64 squared-distance score.
Ties select the lowest template index.
`verify_pack.py` compiles the unchanged C reference and compares every full-width output.
Board packs contain little-endian inputs, expected indices, expected scores, and hashes.
These are host-verified packs. New physical board execution requires separate receipts.

## Acceptance gates and limitations

Every density must meet 1e-6 trace, Hermiticity, and purity tolerances.
Eigenvalues must be at least -1e-6. Probabilities must lie within [-1e-6, 1+1e-6].
Every GPU probability and density element must match the CPU comparator within 1e-6 absolute error.
Noiseless encoded CPU/GPU features may differ by at most one Q14 LSB.
Repeated generation must agree within 1e-6.
Every exported index and full score must match the frozen C reference exactly.
Scientific acceptance does not require a GPU speedup. A slower GPU result remains a valid outcome.
The study does not establish optical realism, quantum hardware performance, radiation tolerance, or NVIDIA partnership eligibility.
Earlier low-shot calibration failures remain valid limitations of the frozen estimator.

## Resource proposal

Use one GPU process, no MPI, no new packages, and one CPU thread initially.
A maximum batch holds 512 density matrices: 131,072 raw bytes per state array.
RK4 scratch, operator storage, and CUDA context add overhead. Raw arrays are not total allocation.
The small development run is expected to fit well below 2 GiB incremental device memory; this is an estimate.
Hard registered limits: 300 seconds development, 1,800 seconds final; 8 GiB CPU peak RSS; 24 GiB observed device-free decrement.
The coordinator also owns external timeout enforcement.
Memory receipts report process peak RSS, CuPy pool allocation, and synchronized CUDA free-memory checkpoints.
CUDA free-memory changes are device-wide sampled observations, not precise process allocation peaks.
CUDA-Q can allocate outside CuPy. Unified host RAM availability is never called GPU allocation.
Checkpoint limits can miss transient peaks; this limitation must remain in the final report.

## Primary references

- [CUDA-Q 0.16 Dynamics documentation](https://nvidia.github.io/cuda-quantum/0.16.0/using/dynamics.html): batching semantics and integrators.
- [Current CUDA-Q Dynamics documentation](https://nvidia.github.io/cuda-quantum/latest/using/dynamics.html): requested API context; installed source remains authoritative.
- Original effective model provenance is retained in `SOURCE_MAP.json` and the existing published NV documentation.
