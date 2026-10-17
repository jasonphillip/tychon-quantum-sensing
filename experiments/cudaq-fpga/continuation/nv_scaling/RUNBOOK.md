# Registered execution commands

Source is portable between macOS and Linux. CPU generation requires NumPy and a C compiler for pack verification.
The existing isolated Linux generation host Python environment provides CUDA-Q 0.16.0.post1 and CuPy 13.6.0.
No package installation is required there.
The coordinator owns GPU execution. Run one GPU process at a time.

## Completed development checks

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ./nv_scaling/test_scaling.py
```

Eight tests passed. The registered Linux development CPU and GPU runs also passed.
Their commands match the final commands below, replacing `protocol_final.json` with `protocol_dev.json`.
Use output names `dev_cpu_linux` and `dev_gpu`, respectively.
Development has a 300-second external timeout.

## Final generation: coordinator only

Freeze `REGISTRATION.json` and verify its file hashes before execution.
Each output directory must be new. The CLI refuses to overwrite existing evidence.
Retain stdout and stderr together in `artifacts/final_gpu.log`.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 1800 python3 ./nv_scaling/run_dataset.py --protocol ./nv_scaling/protocol_final.json --backend cudaq --output ./nv_scaling/artifacts/final_gpu
```

Run the CPU comparator on the same host and environment:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 300 python3 ./nv_scaling/run_dataset.py --protocol ./nv_scaling/protocol_final.json --backend cpu --output ./nv_scaling/artifacts/final_cpu_linux
```

## Final acceptance and comparison

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ./nv_scaling/verify_pack.py --pack ./nv_scaling/artifacts/final_gpu/board_vectors --output ./nv_scaling/artifacts/final_gpu/c_reference_verification.json
```

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 ./nv_scaling/compare_runs.py --cpu ./nv_scaling/artifacts/final_cpu_linux --gpu ./nv_scaling/artifacts/final_gpu --gpu-log ./nv_scaling/artifacts/final_gpu.log --output ./nv_scaling/artifacts/final_comparison.json
```

Only after all gates pass may the coordinator use the unchanged board replay runner.
Expected final pack: 1,024 records under `artifacts/final_gpu/board_vectors`.
The manifest provides exact binary sizes, hashes, case identifiers, and the immutable ROM identity.
A board receipt must identify this manifest and compare every full-width result.
No board command or hardware operation is part of this package.

## Completed independent final acceptance

The final GPU and CPU runs completed. The unchanged C verifier passed all 1,024 records.
The independent checker verifies NPZ hashes and enforces full-array tolerances, beyond the comparison summary.
Run it in the original Linux generation host environment for exact seeded-label regeneration:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 timeout 120 python3 ./review/nv_final_acceptance.py --nv-root ./nv_scaling --output ./nv_scaling/artifacts/final_independent_acceptance_linux.json
```

This exact command passed. Its existing receipt is immutable; use a new output name for a later verification.
The earlier Mac attempt is retained as `artifacts/final_independent_acceptance.json`.
It failed exact label regeneration at a maximum difference of 1.11e-16 MHz.
The same saved CPU and GPU labels match exactly. No physics gate was relaxed.
The board handoff must identify manifest SHA-256 `0055ab3fa477e42add618d068b408cf0000fa5bea4409c8da113d35d5aeda391`.
