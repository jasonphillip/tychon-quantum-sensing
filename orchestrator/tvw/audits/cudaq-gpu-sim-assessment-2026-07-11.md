# CUDA-Q / GPU spin-simulation assessment — for the nv-sensor-sim data-generation stack

**Date:** 2026-07-11. **Trigger:** Jason asked whether CUDA-Q (or another new NVIDIA product)
would help the data simulations, and whether it works on our systems. **Method:** two parallel
TVW research agents (platform compatibility; regime fit + alternatives), with an **empirical
benchmark run on this DGX Spark** during the session. Docs + refs ETL'd into
`~/.corpus/gpu-quantum-sim`. **Status:** decision support; activating any of this in
nv-sensor-sim is a worker-lane dispatch after Jason picks.

## Headline answers

1. **CUDA-Q works on our hardware TODAY — empirically proven, not just docs-verified.** The
   agent pip-installed `cuda-quantum-cu13` (0.15.0, 2026-07-02) + `cupy-cuda13x` on ws2
   (GB10, aarch64, sm_121, driver 580.159.03, Py3.13) and ran batched 3-level Lindblad
   evolution: **batch 128 × 201 steps = 1.39 s; batch 1024 = 4.51 s** (sub-linear — batching
   amortizes). Benchmark script preserved: `cudaq-batched-dynamics-benchmark-2026-07-11.py`.
   NOTE: cudaq 0.15.0 is now installed in ws2's base conda env (session side-effect, benign).
2. **nv-sensor-sim already anticipated this.** `adapters/cudaq_adapter.py` is a stub
   (NotImplementedError) whose docstring cites the NVIDIA NV+P1 demo ("64% runtime reduction
   on Blackwell"). The primary backend is SimOS (CPU; arXiv:2501.05922). So the question was
   never "incorporate CUDA-Q?" but "activate the planned adapter — and is CUDA-Q even the
   right engine?"
3. **For the workload we actually have, the literature-and-docs verdict is nuanced:**
   - **Today's analytic generator** (closed-form eigenvalues + Lorentzians, huge batch × tiny
     Hilbert dim): a quantum-dynamics library adds ergonomics, not speed. If/when generation
     speed binds, the right move is batched linear algebra (JAX `vmap`+`eigvalsh` or PyTorch
     batched `eigh`) or drop-in `cuPyNumeric` — one fused GPU kernel over 10⁶ samples.
   - **The future fidelity generator** (Lindblad T1/T2, spin-bath, pulsed Rabi/Ramsey — the
     sim-to-real direction, O13-adjacent): two credible engines:
     **(a) dynamiqs** (v0.3.6, JAX): batching is its core design, **fully differentiable**
     (fit simulator params — linewidths, strain, T1/T2 — to real hardware data by gradient
     descent; the Craig 2024 / NVRNet 2026 sim-to-real calibration pattern), runs on aarch64
     via JAX's official ARM CUDA wheels. Risk: pre-1.0 API churn; NOT yet tested on GB10.
     **(b) CUDA-Q Dynamics** (cuDensityMat): batched many-small-systems is first-class
     (batch over states AND Hamiltonians; 0.12.0+), **empirically working on our GB10 now**,
     multi-GPU via MPI; but **no autodiff** — forfeits differentiable calibration.
   - Recommended posture: **prototype the fidelity generator on dynamiqs** (differentiability
     is the strategic capability), keep the **CUDA-Q adapter as the verified fallback/
     throughput engine** (it is now de-risked on-target), and validate BOTH against QuTiP v5
     CPU `mesolve` as the correctness oracle (qutip's own GPU path is pre-alpha — not a
     candidate). PennyLane lightning.gpu, QuantumOptics.jl, Warp: wrong abstraction/language/
     domain — rejected.
4. **AWS:** CUDA-Q/cuQuantum run on ordinary g6/L4 instances (Ada explicitly supported,
   plain pip wheels) — so fidelity-generation at scale can ride the same gpu-fanout harness
   and credits. Not empirically tested on L4 this session.
5. **Novelty note:** no published work claims GPU-batched million-sample ODMR dataset
   generation (nearest: QDsiM digital twin arXiv:2601.11649, no GPU/ML-data story; NVRNet
   arXiv:2603.14144 sim-to-real for Ramsey). If the fidelity generator lands, that corner is
   open — feeds the Q5 novelty ledger (O7).

## Gotchas booked (from the empirical run + docs)

- **Use the cu13 wheel on the Spark** (`cuda-quantum-cu13`): Blackwell is supported under
  CUDA 13.x only; the cu12 wheel has documented "Known Blackwell Issues." Python ≥3.11.
- Batching Hamiltonians requires `collapse_operators` as list-of-lists (one per Hamiltonian)
  or `evolve` raises ValueError.
- Torch-based integrators need nightly torch on Blackwell — use the built-in Runge-Kutta.
- Open GitHub reports of cuStateVec OOM under GB10 unified memory affect the *circuit* path,
  not the dynamics path (none observed here).
- CUDA-Q is absent from the DGX Spark porting-guide table (cuQuantum/Warp/cuPyNumeric are
  listed "Yes") — our empirical run is the evidence it works; pin versions.
- Millions of instances need chunked batches; MGMN multi-GPU requires power-of-2 MPI ranks
  and batch divisible by rank count.

## Corpus/ETL record

New topic `~/.corpus/gpu-quantum-sim`: NVIDIA primary docs (CUDA-Q dynamics/install/examples,
release notes, cuQuantum getting-started, cuDensityMat API, DGX Spark porting guide),
dynamiqs repo + batching docs, qutip-jax status, JAX aarch64 install docs, and 5 arXiv refs
(2501.05922 SimOS; 2601.11649 QDsiM; 2403.04678 Craig differentiable master-equation;
2603.14144 NVRNet sim-to-real; 2603.14728 DL-ODMR analysis). Processed with Qwen3-Embedding-4B
(Spark2). Versions as of today: CUDA-Q 0.15.0; cuQuantum Python 26.6.0 (cuDensityMat 0.6.0);
dynamiqs 0.3.6; Warp 1.15.0; cuPyNumeric 26.6.0.

## What activation would look like (when Jason green-lights, via nv-sensor-sim dispatch)

1. Benchmark today's SimOS CPU generator (baseline throughput on a v3-shaped workload).
2. Implement `CudaQAdapter.generate_odmr_spectrum` against the batched `evolve` API (the
   preserved benchmark script is the seed) + a dynamiqs spike of the same physics; validate
   both against SimOS/QuTiP to spectral tolerance.
3. Decide engine on measured throughput + the differentiability requirement; wire into
   `pipelines/sequence_generate.py` behind the existing adapter interface.
4. Only then: next-gen dataset design (spin-bath, pulsed protocols) as its own increment with
   the usual pre-hoc discipline.
