# Final NV dataset and FPGA evidence review

Reviewed October 17, 2026. This is an independent AI review of saved artifacts and source code.
It is not human review, external endorsement, or TVW claim adjudication.
No network, hardware, GPU generation, retraining, or scientific rerun occurred during this review.

## Decision

**The saved evidence supports the bounded synthetic CUDA-Q-to-FPGA result. No reporting blocker was found.**
Every saved FPGA index and full-width distance score matched an independently recomputed Python-integer result.
The final simulation passed its frozen numerical comparison gates.
The specialized CPU was approximately 8,537 times faster for this four-level model.
These results support numerical integration and exact hardware replay. They do not support GPU acceleration or measured sensor accuracy.

The current `nv_scaling/REPORT.md` and `board/REPORT.md` retain the important scope limits.
Keep the failure history, CPU advantage, clipping counts, timing definitions, and memory qualifications in any public summary.

## Independent local verification

An inline Python verifier completed successfully with NumPy 2.4.2 and one BLAS thread.
It loaded saved arrays without pickle and did not call the model's evolution functions.
The integer matcher used Python integers and independent squared-distance loops over all 121 templates.
It did not import or call the existing matcher or acceptance helper.

| Check | Independently verified result |
| --- | --- |
| Registered source and input hashes | All 11 match |
| Final protocol hash | Matches registration and both backend receipts |
| CPU/GPU receipt hashes | Match independent acceptance |
| Saved NPZ hashes | All four match receipts and acceptance |
| Dataset dimensions | 128 detunings × 4 phases × 64 delays; each density is 4 × 4 |
| Complete probability comparison | 32,768 values; maximum difference `2.151061218036432e-09` |
| Complete density comparison | 524,288 complex elements; maximum difference `2.2538997522778442e-09` |
| Frozen comparison tolerance | Both differences remain below `1e-6` |
| Physical checks | Trace, Hermiticity, minimum eigenvalue, and purity pass frozen tolerances |
| Detector input reconstruction | All 1,024 input records match saved counts and registered conversion |
| Clipped input features | 56; all retained and recorded |
| Template matching | All 1,024 lowest-index minima and full integer scores match |
| Scores larger than unsigned 32-bit range | 255 |
| Maximum score | 9,182,441,195 |
| FPGA CSV | All 1,024 records, indices, scores, status values, and completion deltas match |
| Completion counter | Consecutive increments from 85,833 to 86,857 |
| Fabric cycles | 23,479 for every replay call |
| Control checks | All 15 passed; timeout restored |

The GPU pack, CPU pack, and staged board pack contain identical binary input and reference files.
The staged board manifest is byte-identical to the accepted GPU manifest.
The frozen ROM hash matches the pack and registered source.
The saved C-verification receipt also reports exact indices and uint64 scores for all 1,024 records.
Its receipt hash matches independent acceptance. This review did not recompile or rerun C.

All four board-command receipts report exit zero. Their captured stderr files are empty.
The replay receipt records fabric MMIO at `0x60040000`, identity `0x51465047`, and ABI `0x00010000`.
The wrapper source hash and its fixed acceptance-helper hash match the executed receipt.
The wrapper checks the expected boot identity before every command.
That identity matches the preceding cold-boot record: `0a33ca92-8c42-4db5-8815-00f93df307d3`.
The continuation wrapper contains no programming or power-control operation.

The V250 log hash matches local verification.
The log records `error_val=0` and `RESULT: INFERENCE COMPLETED`.
This supports successful inference completion. It does not add a separate V250 output-accuracy measurement.

## CUDA-Q coverage and scientific scope

Source review confirms that preparation, free evolution, and readout use CUDA-Q Dynamics for every GPU dataset entry.
The GPU path downloads final density matrices only after those three segments.
CPU reference evolution runs afterward for validation and does not populate GPU output.
Detector projection and photon sampling run on the CPU and are identified separately.

This remains a four-level effective model: two NV electron levels coupled to one spin-half carbon-13 nucleus.
The continuation scales the number of detunings, not the Hilbert-space dimension.
It omits the third electron level, native nitrogen, optical dynamics, and bath dynamics.
All physical parameters are benchmark assumptions.
There are 128 sampled configurations and 1,024 detector records. Four timing generations do not multiply that independent sample count.
Existing estimator limitations remain unresolved. Exact replay does not establish estimation accuracy, optical realism, or radiation tolerance.

## Runtime and memory claims

| Timing | Specialized CPU | CUDA-Q GPU |
| --- | ---: | ---: |
| Warm full-generation median | 0.012491889996 s | 106.637202173 s |
| Warm range | 0.012132030–0.013169511 s | 106.630336640–106.799855870 s |
| First call plus backend initialization | 0.015382488 s | 107.963613603 s |
| Process peak RSS | 91,693,056 bytes | 2,598,612,992 bytes |

The launch receipt runs both backends consecutively in the same environment with one CPU thread.
Both use the same protocol and return full density tensors.
The CPU uses specialized Hermitian eigendecomposition; CUDA-Q uses general RK4 dynamics.
This compares these implementations at verified accuracy. It is not a general CPU-versus-GPU performance ranking.
GPU timings synchronize and include state transfer, Hamiltonian construction, operator encoding, and evolution overhead.
Warm GPU runs retain operator definitions. The CPU recomputes its small matrices.
The three warm samples provide an observed range, not a runtime confidence interval.

The GPU process elapsed time was 428.217 seconds; the external launch wall time was 428.818 seconds.
The receipt records four complete generations: one first call and three warm repeats.
Only the first output tensor is saved. Repeat equality is recorded by the registered execution code and receipt.
Component sums in `final_comparison.json` are explicitly sums, not separately measured end-to-end elapsed times.

The observed CUDA device-free decrement was 1,414,672,384 bytes.
The zero CuPy pool value does not mean zero GPU memory use.
Device-wide sampled checkpoints cannot establish exclusive process allocation or exclude transient peaks.
The retained log lacks a sequential-fallback warning. That does not prove simultaneous GPU execution.

Independent CSV aggregation reproduces host median 209 microseconds, p99 215 microseconds, and maximum 290 microseconds.
These include register setup, input writes, polling, and result reads. They exclude CSV output and physical acquisition.
The 187.832-microsecond fabric conversion uses the configured 125 MHz clock.
It is a nominal conversion of 23,479 cycles, not an independent frequency measurement.
The prior integration records document an 8 ns FIC0 period; this review did not rerun timing analysis.

## Preserved portability failure

`final_independent_acceptance.json` retains the first Mac failure: exact seeded labels did not reproduce.
This review reproduced the difference using local NumPy 2.4.2.
Exactly 39 of 128 regenerated detunings differ from the saved labels.
The largest difference is `1.1102230246251565e-16` MHz.
Saved CPU and GPU detuning arrays match exactly.
The unchanged checker passed in the original Linux generation host environment, according to its retained acceptance receipt.
Registered source and dataset hashes remain unchanged.
The evidence establishes a cross-environment numerical difference. Its lower-level cause remains unisolated.
Do not claim bit-exact seeded reproduction across the fleet for this evidence set.

## Evidence fingerprints

Paths below are relative to the continuation workspace.

| Artifact | SHA-256 |
| --- | --- |
| `nv_scaling/REGISTRATION.json` | `096a1f08ca40840502119a4e276a6e45fcafc9f509c1c724744915f12db447c8` |
| `nv_scaling/artifacts/final_independent_acceptance.json` | `43624d2c3342460da0fcaa21471e4b8a4da73dce321b536716ef2d96c27deb99` |
| `nv_scaling/artifacts/final_independent_acceptance_linux.json` | `d987a54c3bfd1c57edddd3e0ffbc09b4403acb661f3a9904667357d6ff30b31d` |
| `nv_scaling/artifacts/final_comparison.json` | `8e7971bb6391d4dc623ac50124e4ebd69bec4b6583ffda90513ef9735f1c34e4` |
| `nv_launch_receipt.json` | `cc0195bb3307c882cd9b051eabfb6bc7d005a55570e2cb0fdf29aefe15b37681` |
| `board/execution/acceptance.json` | `84ac47f166e88e8243d677e0983f2d091f5411d52a87b265389b91a1594a4d0f` |
| `board/execution/nv-replay.csv` | `ed6c6f237103866e494f9e05d143b75f52c07162011bf799faad333da3dea1c7` |
| `board/local_verification.json` | `cd170c64d0d4bb88339b1e5f3ab3ffe914db4ad63e597a0d191800f06d0a5ca1` |
| GPU and staged board manifest | `0055ab3fa477e42add618d068b408cf0000fa5bea4409c8da113d35d5aeda391` |

The review clears the saved synthetic-generation and exact-replay claims within these limits.
It does not establish live board state, physical sensor validation, radiation qualification, commercial demand, or NVIDIA endorsement.
