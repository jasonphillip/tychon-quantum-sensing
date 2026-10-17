# Source ledger

Read 2026-10-17. No source calibrates the benchmark values.

1. P. London et al., *Detecting and polarizing nuclear spins with double resonance on a single electron spin*, arXiv:1304.4709v2.
   https://arxiv.org/html/1304.4709
   The “Hartmann-Hahn dynamics with a single NV-center” section gives the electron-secular interaction `S_z A_hyp · I`.
   The paper selects the NV `m_s=0,-1` levels and a 13C nuclear spin. It explains neglected nonsecular terms through energy mismatch.
   We adopt that interaction structure, retaining longitudinal and transverse nuclear terms. We do not reproduce its experiment or parameters.
   Our finite Ramsey sequence, units, basis projection, noise assumptions, and frequency estimator are defined locally.

2. NVIDIA CUDA-Q 0.16.0, *Dynamics Simulation*.
   https://nvidia.github.io/cuda-quantum/0.16.0/using/dynamics.html
   Used the `dynamics` target, explicit density-matrix initial state, `operators.define`, `operators.instantiate`, and fixed RK4 controls.
   A single four-dimensional subsystem preserves our explicit tensor basis. No CUDA-Q qubit endian assumption enters the matrices.

3. NVIDIA CUDA-Q 0.16.0, *Python API*.
   https://nvidia.github.io/cuda-quantum/0.16.0/api/languages/python_api.html
   Used `EvolveResult.final_state` and `State.to_numpy` for sequential pulse propagation and numeric comparisons.

The source ledger describes support, not independent model validation.
Tests check algebraic/numerical correctness within the stated model. Physical adequacy requires additional models and measurements.
