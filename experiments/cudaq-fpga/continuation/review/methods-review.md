# Independent AI methods review — stage 1

Reviewed 2026-10-17T18:33:40.175278+00:00. This is an AI scientific-code review, not independent human review, external endorsement, or a TVW audit.
Only this review file was written. No scientific evaluation, GPU job, board operation, installation, paid tool, or child agent ran.

## Assessment

No final-set leakage or unqualified GPU-acceleration claim was found in the reviewed implementation.
The measured-data result **failed its frozen feasibility threshold**. That is an experimental outcome, not a reason to change the test.
NV final GPU acceptance and the final CPU/GPU comparison remain pending at this review boundary.
Final prose is not yet reviewed; the requirements below must remain in its reporting.

## Required reporting distinctions

1. **Thermal-detector domain:** `measured_readout/inputs/README.md` and the archived Zenodo metadata identify a thermal-detector experiment. Describe run 76 as measured thermal-detector voltage traces from superconducting-qubit preparation trials. Do not call it validation of the earlier synthetic dispersive-cavity acquisition model. The usable trace set has one acquisition. Run 77's integrated IQ format does not supply a second compatible trace acquisition. Drift-transfer eligibility is correctly false.
2. **Selected model versus FPGA candidate:** `evaluate.py:135` selects LDA from validation. Final LDA agreement is 758/1,000, or 75.8%, below the frozen 80% threshold. `evaluate.py:145` exports the pooled boxcar, which scores 737/1,000, or 73.7%. The integer pack is not the selected LDA implementation. Name `pooled_boxcar` explicitly beside the pack and its accuracy. Its new coefficients require a new build; no measured-data FPGA execution occurred.
3. **Calibration benefit:** the reported +0.4 percentage points is a within-acquisition point estimate. Saved predictions contain five improved and one worsened decision relative to the uncalibrated reference. This does not establish reliable benefit, drift transfer, or physical-qubit fidelity. Keep the conditional IID Wilson intervals descriptive; one acquisition cannot support acquisition-level uncertainty or generalization.
4. **NV scaling scope:** this remains the same four-level effective NV–one-carbon model. Increasing detuning configurations expands dataset throughput, not Hilbert-space size or physical model complexity. Report this as complete CUDA-Q generation for the registered small model. Do not imply a demonstrated need for multiple GPUs, larger spin-bath capability, or improved sensor accuracy.
5. **No human-review substitution:** label this artifact and any resulting packet as AI review. Human technical review and NVIDIA interest remain unestablished until actual external responses exist.

## Final-set isolation and measured-data checks

- Registered protocol, code, tests, raw-file, and metadata hashes all matched current files. The consumed-set receipt matches the saved pre-final selection hash.
- `evaluate.py:125–140` loads only reference, calibration, and validation blocks; fits parameters; selects the method; saves selection; and marks the final set consumed before loading final signal values.
- Fixed binning uses all 781 sample indices without selecting a window from final outcomes. Training scale and classifier coefficients use reference/calibration samples only.
- All methods receive the same available labelled training records. The affine/reference split is explicit. Validation tie order is deterministic.
- The tests use synthetic fixtures and inspect requested block boundaries. They do not select hyperparameters from final signals.
- Preparation labels remain intended states, not independently established true states. Repeated-shot correlation and the acquisition protocol remain limits.
- Integer scoring checks int64 bounds, clipping, and exact Python-integer arithmetic. The saved pack reports zero clipped values and zero float/integer decision disagreements. This does not prove new FPGA behavior.

## NV generation, timing, and memory review

`scaling.py:133–167` routes preparation, free evolution, and readout through CUDA-Q Dynamics for every returned GPU density. CPU evolution is used only for later validation. Classical detector sampling is explicitly CPU-side. Full-density comparisons cover every returned element, and every exported full-width score/index has a separate compiled-C verifier.

The specialized CPU comparator uses batched Hermitian eigendecompositions and reuses free-evolution eigenvectors. Development tests compare every probability with the scalar solver and selected densities with commutator RK4. These are appropriate numerical checks. They do not validate the physical NV approximations.

Before accepting the final comparison:

- Use the same NVIDIA host, protocol hash, detunings, precision target, and thread settings for CPU and CUDA-Q receipts. Mac timing establishes portability only.
- Report initialization, first call, warm median/range, detector generation, validation, and output writes separately. Quantum timing includes operator construction, transfers, and synchronized downloads. Process elapsed includes repeated runs and validation; it is not an uncontaminated generation-speed ratio.
- Describe the algorithm comparison: specialized analytic CPU propagation versus general CUDA-Q RK4. Matching the frozen numerical tolerance permits a useful implementation comparison; it does not isolate GPU hardware advantage.
- Preserve any sequential-batching warning. A successful API call alone does not establish concurrent execution or acceleration.
- Validate actual output shapes/counts and all numerical gates from execution receipts before stating full CUDA-Q coverage. `gpu_generated_fraction=1` is an implementation declaration, not independent runtime attestation.
- Preserve the sampled-memory qualifier. CUDA free-memory decrements are device-wide; CuPy does not track every CUDA-Q allocation. Checkpoints can miss transient peaks. Do not call these values exact process allocation peaks.
- Use an external wall timeout. `run_dataset.py:63` checks elapsed time only after a full generation pass. The coordinator reports GNU timeout 300 seconds for development and at most 1,800 seconds for final execution. That resolves the operational concern if the launch receipt confirms it.
- Freeze any development-cost-driven final count change before final execution, recording the new protocol hash. Warm repeats and detector realizations do not increase independent physical configurations. Preserve final failures and do not retune on them.

## Remaining evidence dependencies

The full final GPU receipt, matched-host CPU receipt, complete C pack parity receipt, final classification report, and external-review packet were not available for completed review here. Recheck those artifacts against the distinctions above. Any compatible NV replay must retain its separate board receipt; it cannot establish measured thermal-readout FPGA execution.

## Reviewed snapshot hashes

| File | SHA256 |
| --- | --- |
| `nv_scaling/protocol_dev.json` | `40e784eba9d89640e856e67783a2c1d06b1aa4d31539e51a1f76319ebe2044ea` |
| `nv_scaling/protocol_final.json` | `c42c84ab70cd67007fdf7d7f05e86b019a07a94355d1b84e4cae6900037e2662` |
| `nv_scaling/PROTOCOL.md` | `379c1e42446ddac59ae674419b8d0a95087100cf9abddd4c7697444d85e2d5c0` |
| `nv_scaling/scaling.py` | `f23c0a92609c9572113f8e9a831657993b81cd765ec7ff9ad0ccacc38beae17d` |
| `nv_scaling/run_dataset.py` | `dc8c580a42f6dee2dd620378206fcab1a1dc45146c76fd463c8f03396b9cfecd` |
| `nv_scaling/verify_pack.py` | `75b878897b172ef1a57713a6604d9988cc956953cd682b2edefd522cf493b0df` |
| `nv_scaling/test_scaling.py` | `283e5507e1f00b95010928bde98e95aa884aa1af1f5b78c5be0e770e8f2c9b24` |
| `measured_readout/protocol.json` | `646c9a333ae36abc22af37cbc27c136df9195b874abaf637d893294c74d55622` |
| `measured_readout/PROTOCOL.md` | `4808a1abf66c00d9a4fe8d0484b213b12b37029acef7998c11900ae646c459a5` |
| `measured_readout/evaluate.py` | `fab8f44b3415a176eb89f7c335540c1ae9942ff858d9585521654e3426e576a7` |
| `measured_readout/test_evaluate.py` | `b8f60a5febfa2d869a370c7004369d1f7ed84825222fd05735925f5e036f7e81` |
| `measured_readout/registration.json` | `e168286e81e8870f79e2b17890cf31088600956ef6aa3bc5bfc3d946f6bb31cf` |
| `measured_readout/consumed.json` | `0e516c85703c2d2338af09a388e887c2c8a793d30b2a858c46d4d840f1056724` |
| `measured_readout/results/frozen_v1/selection_before_final.json` | `848d7db376222a5a43c7364b306b53bdec33bffc528272145ffa71389fc20f2a` |
| `measured_readout/results/frozen_v1/metrics.json` | `f98f7da43607cedd725013a8bc1cc4c2a7eb48b63ba97bacb10978534eb50757` |

Primary dataset provenance was read from the archived Zenodo 10000511 metadata: DOI `10.5281/zenodo.10000511`, title naming a thermal detector, license `CC-BY-4.0`. No external source search was needed for this bounded source-and-receipt review.
