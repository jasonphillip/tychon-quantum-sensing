# NV full CUDA-Q dataset results

Updated October 17, 2026, after final host acceptance and the separately recorded FPGA replay.

CUDA-Q Dynamics generated every quantum density in the registered final dataset.
The dataset contains 128 independent detunings and 32,768 quantum probabilities.
CPU photon sampling produced 1,024 FPGA input records across four shot budgets and two detector realizations.
Four complete quantum generations supplied one first-call and three warm timings.
Those repetitions do not increase the independent dataset size.

## Numerical and interface acceptance

The unchanged independent checker passed in the original Linux generation host environment.
It verified the pre-final registration, all source/protocol hashes, and both backends' NPZ hashes before loading arrays.
Every density and probability passed the registered absolute 1e-6 comparison tolerance.
Maximum probability difference: 2.151061218036432e-09.
Maximum density-element difference: 2.253899752277844e-09.
Every density passed trace, Hermiticity, positivity, and purity checks.
Maximum noiseless CPU/GPU Q14 difference: 1 LSB.

The unchanged C reference matched all 1,024 template indices and full 64-bit scores.
The independent checker also reconstructed every input from saved detector counts and recomputed every integer score.
Maximum exported score: 9,182,441,195.
Clipped detector features: 56; clipping remains recorded, not removed.
The frozen FPGA ROM and ABI are unchanged.
These acceptance receipts establish saved-data and host-reference results.
The [subsequent board run](../board/REPORT.md) matched all 1,024 records and full scores.
Its separate receipts also record 15 control checks and a successful V250 regression.
Historical host receipts retain their original `board_executed=false` value.

## Same-host runtime and memory

| Measurement | Specialized CPU | CUDA-Q GPU |
|---|---:|---:|
| Warm full-generation median, seconds | 0.012491890 | 106.637202 |
| Warm minimum, seconds | 0.012132030 | 106.630337 |
| Warm maximum, seconds | 0.013169511 | 106.799856 |
| First call plus backend initialization, seconds | 0.015382488 | 107.963614 |
| Process peak RSS, bytes | 91,693,056 | 2,598,612,992 |

The specialized CPU was approximately 8537 times faster for this four-level model.
These timings compare the configured CUDA-Q RK4 implementation with a specialized exact CPU solver.
They do not establish the best achievable GPU runtime or CUDA-Q performance on larger models.
This is complete GPU generation with numerical agreement, not a GPU performance win.
The GPU process took 428.217 seconds including repeats, validation, sampling, and writing.
GPU evolution timings include operator preparation and implicit Hamiltonian transfers.
Initial-state upload and final-state download remain separate sub-timings in the receipt.
Sampled maximum CUDA device-free decrement: 1,414,672,384 bytes.
Sampled maximum CuPy pool usage: 0 bytes.
Device-free changes are device-wide checkpoints, not precise process allocation peaks.
CUDA-Q can allocate outside CuPy. Unified host RAM availability is not GPU allocation.

No sequential-fallback warning appears in the retained log.
This establishes batched API use, not independent proof of simultaneous GPU batching.

## Portability correction and preserved failure

The first independent check on Mac failed exact seeded-label regeneration.
The saved CPU and GPU detuning arrays agree exactly.
On Mac, 39 of 128 regenerated labels differed by at most 1.1102230246251565e-16 MHz.
Both environments used NumPy 2.4.2.
The unchanged checker passed on Linux generation host, where both datasets were generated.
This establishes a cross-environment rounding difference; its lower-level cause was not isolated.
No registered physics tolerance, source file, seed, or dataset byte changed.
The Mac failure remains in `artifacts/final_independent_acceptance.json`.
Exact random-label regeneration therefore requires the original environment for this evidence set.

## Frozen evidence

- Registration SHA-256: `096a1f08ca40840502119a4e276a6e45fcafc9f509c1c724744915f12db447c8`.
- Final protocol SHA-256: `c42c84ab70cd67007fdf7d7f05e86b019a07a94355d1b84e4cae6900037e2662`.
- Independent acceptance: `artifacts/final_independent_acceptance_linux.json`.
- Independent acceptance SHA-256: `d987a54c3bfd1c57edddd3e0ffbc09b4403acb661f3a9904667357d6ff30b31d`.
- C verification: `artifacts/final_gpu/c_reference_verification.json`.
- Comparison: `artifacts/final_comparison.json`.
- Board pack: `artifacts/final_gpu/board_vectors`, 1,024 records.
- Board manifest SHA-256: `0055ab3fa477e42add618d068b408cf0000fa5bea4409c8da113d35d5aeda391`.

Source hashes and every board-file hash appear in the independent acceptance receipt.
`PROTOCOL.md` retains the model assumptions and acceptance gates.
The prior NV low-shot calibration failures remain limitations of the unchanged estimator.
No optical sensing, radiation, physical quantum hardware, or NVIDIA partnership claim follows from this benchmark.
