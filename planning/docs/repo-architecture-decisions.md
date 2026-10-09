> Original: claude.ai project document, created 2026-04-01. Edited for publication: names of other people and business details removed.

# Tychon AI — Repository Architecture Decisions

**Document version:** 1.1  
**Date:** March 11, 2026 (updated April 1, 2026 — Repo 3 status, usage instructions)  
**Author:** Jason Phillip (decisions) + Claude analysis  
**Plan:** 90-day build plan  
**Authoritative sources:** Tychon AI Execution Playbook v4 (March 9, 2026), Platform Addendum v4 (March 9, 2026)

---

## 1. Purpose and Usage Instructions

This document is the single authoritative input for scaffolding Tychon AI code repositories. It captures every architectural decision made during the repo planning analysis, the sanitized technical requirements extracted from the v4 playbook and addendum, and explicit guidance on what to build, what to defer, and what to exclude.

**How to use this document:**

- When starting Claude Code in Plan Mode to scaffold `tychon-nv-sim`, feed this entire document as context.
- When spinning up any LLM instance to assist with repo work, provide this document first.
- When scaffolding Repo 2 (`tychon-odmr-ml`) later (~Day 20-25), the full spec is in Section 6 of this document.
- **When scaffolding Repo 3 (`tychon-polarfire-control`), use `tychon_repo3_scaffold_spec.md` as the primary input.** That document consolidates the Gemini Deep Think architecture analysis, Claude-reviewed SmartHLS PID code, and VectorBlox export pipeline into a single scaffold spec.
- This document is authoritative for *repo architecture decisions*. The v4 playbook remains authoritative for *technical requirements and execution timeline*. The v4 addendum remains authoritative for *platform reference material*.
- If a future Claude instance proposes something that contradicts this document, this document wins unless Jason explicitly overrides it.

---

## 2. Key Decisions Summary

### Repo Strategy
- **Start with ONE repo: `tychon-nv-sim`** (physics simulation + synthetic data generation).
- **Repo 2 (`tychon-odmr-ml`) is parked inside Repo 1** at `docs/future/repo2-odmr-ml-spec.md`. Build it when Repo 1 produces stable dataset manifests, likely around Day 20-25.
- **Repo 3 (`tychon-polarfire-control`) spec is now complete.** Originally deferred at the time of this document (March 11). As of March 27, a full architecture decisions document was produced by Gemini Deep Think and Claude-reviewed, then consolidated into `tychon_repo3_scaffold_spec.md` (April 1, 2026). That document is the authoritative scaffold input for Repo 3. Key decisions: SDK v2.0.x (not v3.0), bare-metal C (not Linux), MPFS250T target with MPFS460T fallback, SmartHLS PID adapted from Claude-reviewed code, CoreVectorBlox V250 preset.

### What Goes in Code Repos
- Sanitized technical context goes in `docs/phase1-context/`. This includes requirements extracted from the playbook and relevant findings from the research report.
- **NO business-sensitive material in any code repo.** See Section 7 for the explicit exclusion list.

### Development Philosophy
- **Notebooks/experiments allowed.** An `experiments/` directory is included for exploratory Jupyter work. Refactor validated experiments into package code. Notebooks are NOT the source of truth for deliverables, but they are the fastest path to first results.
- **Minimal scaffold on Day 1.** Create only the files you will actually touch in the first two weeks. Grow organically. Do not front-load 50+ empty stub files.
- **No CI pipelines until ~Day 20-30.** Run tests locally first. Set up GitHub Actions when you have actual tests worth running continuously.
- **No `.pre-commit-config.yaml` or `.editorconfig` on Day 1.** Nice-to-haves, not must-haves for a 90-day solo sprint. Use `ruff` manually if you want formatting.
- **No Claude Code skills/agents on Day 1.** Create `.claude/skills/` and `.claude/agents/` after you have working code that needs review patterns, not before.
- **Adapter pattern for all uncertain external dependencies.** SimOS, QuaCCAToo, CUDA-Q, QDsiM, and reference datasets are all wrapped behind adapter interfaces with explicit `NotImplementedError` stubs where toolchains are unavailable.
- **CPU smoke paths are mandatory.** Every pipeline must have a mode that runs without CUDA, Julia, vendor compilers, or QDsiM.

### Data Contract Drives Repo 1 Design
- Repo 1's dataset manifest schema must be designed from Day 1 with Repo 2's consumption needs in mind. The data contract (seeds, units, split definitions, config hashes, corruption parameter ranges, provenance metadata) is specified in Section 3 and duplicated in the Repo 2 spec (Section 6).

---

## 3. Repo 1 (`tychon-nv-sim`) — Scope and Requirements

### 3.1 Purpose

Physics-based NV-diamond ODMR simulation and synthetic dataset generation ONLY. No model training logic. No ML code. This repo owns the "truth" for synthetic spectra, corruption parameters, seeds, units, and dataset manifests. The training repo (Repo 2) treats the data contract as an input.

This repo maps to **Deliverable 1** of the v4 playbook: "Validated NV-Diamond Magnetometer Sensor Model + Synthetic Data Generator" (Task 1, Days 1-45).

### 3.2 Technical Requirements (extracted from v4 Playbook Deliverable 1)

The sensor model has three layers:

**Layer 1 — NV Physics Engine (Hamiltonian + Dynamics)**

- Use SimOS as the core. It provides: NV ground-state spin Hamiltonian (seven-level photophysics: ground triplet, excited triplet, metastable singlet), ensemble ODMR simulation with temperature dependence and strain, Lindblad master equation solvers with multiple backends, and stochastic time-dependent Hamiltonians.
- Install: `pip install simos`, backend QuTiP 5.2.3 (`pip install qutip==5.2.3`).
- SimOS has CUDA GPU acceleration via Docker images — DGX Sparks can run it directly.
- Use QuaCCAToo for cross-validation and pulse-sequence library. Pre-built NV ground-state Hamiltonian with zero-field splitting, hyperfine coupling, Zeeman interaction, and P1 center DEER sensing example (Example 07).
- Use CUDA-Q Dynamics NV+P1 demo as GPU-accelerated reference architecture (NV center with coherently coupled ¹³C and ¹⁴N nuclear spins and incoherent P1 spin bath, ran on Blackwell with 64% runtime reduction).
- Install: `pip install cudaq` (ARM64 wheels for Spark).

**Layer 2 — Sensor-Level Noise Model (Coupled Stochastic Injection)**

- Use QDsiM as noise injection and ODMR reconstruction backbone IF code is available. QDsiM provides: seven-level NV model for CW wide-field ODMR, parameterized noise catalog (photon shot noise, laser RIN, MW power noise, MW phase noise, MW frequency jitter, temperature-dependent ZFS shifts, dephasing distributions), and complete vector magnetic-field reconstruction from ODMR spectra.
- **RISK: QDsiM has no confirmed public GitHub repository as of March 2026.** Mitigation: use SimOS as guaranteed foundation and implement QDsiM's documented noise injection as wrappers around SimOS.
- **Critical v4 change — Coupled Noise Injection:** Do NOT treat noise sources as independent post-processing steps. Inject stochastic noise parameters (temperature fluctuations, MW power/phase variations) directly into the SimOS time-dependent Hamiltonian using StochasticLiouvilleParameters and stochastic_evol APIs. This ensures the Lindblad master equation captures state-mixing and cross-couplings inherently.
- Implementation: Parameterize temperature T(t) and MW amplitude B1(t) as Ornstein-Uhlenbeck stochastic processes drawn from QDsiM-defined distributions. Pass as time-dependent Hamiltonian parameters to stochastic_evol.

**Layer 3 — Noise Parameterization (Published Values)**

- Do NOT derive noise parameters from first principles. Use published, peer-reviewed values.
- P1 bath noise: Lorentzian PSD S(ω) = Δ²·2τ_c/(1 + ω²τ_c²). Δ ~ 1–7 MHz, τ_c ~ 5–50 µs. CCE study (arXiv:2503.05404) for T₂ values at 1-300 ppm P1 concentrations. Cite for measured T₂ values only; do NOT reference pulse-number scaling behavior (applies to dynamical decoupling, irrelevant to CW ODMR).
- Thermal drift: dD/dT ≈ −74.2 kHz/K (textbook). Model as Ornstein-Uhlenbeck process. SBQuantum space qualification (arXiv:2509.19179): thermal cycling -65°C to +125°C for 335+ hours, ~400 pT/√Hz sensitivity, heading errors below 5 nT.
- **Surface noise model REMOVED (v4 change):** Only relevant for shallow NV centers at depths <20 nm. Sensor uses bulk diamond ensemble. >99.99% of NV centers deeply embedded. Zero loss of physical fidelity.

**Asymmetric Lineshape Generation (v4 addition):**

Two corruption parameters added to every generated spectrum:
1. Spatial B1 gradient: Linear spatial gradient to MW drive amplitude. Magnitude drawn uniformly from 5-30% variation across diamond.
2. Transverse field injection: Random B_perp drawn uniformly from 0 to 50 µT. Enters SimOS Hamiltonian directly as off-diagonal terms.

This forces the downstream ML models to learn on realistic, asymmetric, Fano-like lineshapes rather than idealized symmetric Voigt profiles.

**Fast spectrum generation:** Lönard et al. analytical formulas (arXiv:2504.20750) for exact resonance frequencies, Voigt profile fitting. Orders of magnitude faster than numerical diagonalization. Use for bulk data generation, full Hamiltonian for validation.

**What NOT to Build:**
- Do NOT build a physics-informed neural network (PINN). No published work combines physics prior with learned model for NV-diamond ODMR. Deferred to later work.

### 3.3 Validation Protocol

1. Generate synthetic ODMR spectra across parameter sweep (P1 concentration, temperature, magnetic field orientation, B1 gradient, transverse B_perp).
2. Compare spectral features (dip positions, linewidths, contrast) against Zenodo ODMR dataset and SBQuantum published data.
3. Verify P1 bath decoherence times match CCE study at corresponding concentrations.
4. Show Allan deviation stability curves match published NV magnetometer behavior (SBQuantum: white noise to ~5 sec, then thermal drift dominance).
5. Cross-validate against Tsunaki et al. digital-twin paper (arXiv:2510.14907) stability patterns.

### 3.4 Dataset Manifest Contract (consumed by Repo 2)

Every generated dataset MUST include a manifest with:
- Generator git SHA and config hash
- Random seeds for all stochastic processes
- Train/val/test split definitions
- Units for all quantities (SI, explicit)
- Corruption parameter ranges used (P1 concentration range, temperature range, B1 gradient range, B_perp range)
- Number of spectra per split
- Spectral resolution (number of frequency points per spectrum)
- Provenance metadata (SimOS version, QuTiP version, backend used)

**Critical: Train/Test Data Separation Protocol:**
- Train on synthetic data with corruption parameters from one set of seeds and distributions.
- Test set uses DIFFERENT random seeds AND DIFFERENT noise parameter distributions (shifted means, wider variance).
- This separation must be enforced at the manifest level and documented explicitly.

### 3.5 Physics References (from Fast-Track Research Report)

These are the key external resources identified in the Fast-Track report that accelerate or de-risk Repo 1:

| Resource | Date | URL | Relevance |
|---|---|---|---|
| SimOS (ETH Zürich Degen group) | Nov 2025 | `https://www.sciencedirect.com/science/article/pii/S0010465525004205` | Core physics engine. ODMR simulation, Lindblad dynamics, stochastic framework. |
| QuaCCAToo (HZB) | 2025 | `github.com/QISS-HZB/QuaCCAToo` | Cross-validation, pre-built NV Hamiltonian, P1 DEER example. |
| CUDA-Q Dynamics NV+P1 demo | Jun 2025 | NVIDIA docs | GPU-accelerated reference. Your physics on your hardware (Blackwell). |
| cuDensityMat v26.1.0 | Jan 2026 | cuQuantum SDK | GPU Lindblad dynamics with gradient APIs for parameter fitting. aarch64 wheels available. |
| Tsunaki et al. digital twin | Oct 2025 | `https://arxiv.org/abs/2510.14907` | End-to-end pattern: ODMR prediction + stability metrics under noise. Validation blueprint. |
| QDsiM | Jan 2026 | No confirmed public repo | Parameterized noise catalog. Use documented approach as wrappers if code unavailable. |
| QuantumVillage UncutGem | Aug 2025 | `github.com/QuantumVillage/UncutGem` | Open hardware/firmware reference for ODMR sweep orchestration. |
| Lönard et al. fast ODMR | 2025 | `arXiv:2504.20750` | Analytical resonance frequencies, orders of magnitude faster than diagonalization. |
| CCE P1 bath study | Mar 2025 | `arXiv:2503.05404` | T₂ values at 1-300 ppm P1 concentrations. Use values only, not pulse scaling. |
| SBQuantum space qualification | Sep 2025 | `arXiv:2509.19179` | Thermal cycling data, ~400 pT/√Hz, heading errors <5 nT. On-orbit noise parameters. |
| Zenodo ODMR dataset | Pre-2026 | Zenodo | Empirical validation data. Also used by Repo 2 for Metric 5. |
| Non-stationary noise modeling | Accepted 2026 | `journals.aps.org/prapplied/accepted/10.1103/13mr-493z` | Framework for time-varying noise statistics (non-Markovian). Improves synthetic data realism. |
| Ensemble ODMR computation | Sep 2025 | `arXiv:2509.15427` | Drop-in forward model for ensemble ODMR lineshapes with strain and nonidealities. |

---

## 4. Repo 1 — Recommended Minimal Scaffold

### 4.1 Initial File Tree (Day 1 target: ~20 files, not 50+)

```
tychon-nv-sim/
  README.md
  CLAUDE.md
  pyproject.toml
  .gitignore
  Makefile

  docs/
    phase1-context/
      requirements.md          ← extracted from Section 3 of this document
      physics-references.md    ← extracted from Section 3.5 of this document
    future/
      repo2-odmr-ml-spec.md    ← extracted from Section 6 of this document
    architecture.md
    dataset-contract.md        ← extracted from Section 3.4 of this document

  experiments/
    README.md                  ← "Exploratory notebooks. Refactor to src/ when validated."

  src/tychon_nv_sim/
    __init__.py
    config.py

    adapters/
      __init__.py
      simos_adapter.py
      quaccatoo_adapter.py     ← stub with NotImplementedError
      cudaq_adapter.py         ← stub with NotImplementedError
      qdsim_adapter.py         ← stub with NotImplementedError

    physics/
      __init__.py
      hamiltonian.py
      noise_injection.py       ← coupled OU processes for T(t) and B1(t)
      lineshape.py             ← asymmetric lineshape generation
      parameters.py            ← published noise parameter catalog

    datasets/
      __init__.py
      schema.py                ← manifest schema definition
      writer.py                ← writes spectra + manifest to disk
      loaders.py               ← reads manifest + spectra

  tests/
    smoke/
      test_smoke_generate.py   ← CPU-only, no CUDA/QDsiM required
    unit/
      test_manifest_schema.py
      test_noise_parameters.py
```

### 4.2 What to Create First (ordered)

1. `pyproject.toml` — package metadata, dependencies (simos, qutip, numpy, pyyaml)
2. `src/tychon_nv_sim/__init__.py` + `config.py` — basic package structure
3. `src/tychon_nv_sim/adapters/simos_adapter.py` — first real code, wraps SimOS ODMR generation
4. `experiments/01_simos_hello_world.ipynb` — run SimOS, generate one spectrum, plot it, understand the data
5. `src/tychon_nv_sim/physics/parameters.py` — published noise parameter catalog (P1 bath, thermal drift)
6. `src/tychon_nv_sim/physics/noise_injection.py` — OU processes for coupled noise
7. `src/tychon_nv_sim/datasets/schema.py` — manifest schema
8. `src/tychon_nv_sim/datasets/writer.py` — write spectra + manifest
9. `tests/smoke/test_smoke_generate.py` — CPU-only smoke test
10. `docs/` files — populate from this document

### 4.3 What to Defer (create later when needed)

- `src/tychon_nv_sim/adapters/quaccatoo_adapter.py` — real implementation (keep stub for now)
- `src/tychon_nv_sim/adapters/cudaq_adapter.py` — real implementation (keep stub)
- `src/tychon_nv_sim/physics/fast_analytic.py` — Lönard et al. fast spectrum generation (add when bulk data generation needed, ~Day 15-20)
- `src/tychon_nv_sim/validation/` — validation metrics, plots, ADEV (add ~Day 20-30)
- `src/tychon_nv_sim/pipelines/` — batch generation scripts (add when single-spectrum generation works)
- `.github/workflows/ci.yml` — add ~Day 20-30
- `.pre-commit-config.yaml` — add when you want it
- `.claude/skills/`, `.claude/agents/` — add when you have working code that needs review patterns
- `configs/` directory with YAML sweep configs — add when you're running parameter sweeps

### 4.4 Adapter Boundaries

Every external dependency that is uncertain, unavailable, or platform-specific gets an adapter:

| Dependency | Status | Adapter Strategy |
|---|---|---|
| SimOS | Available (`pip install simos`) | Full implementation in `simos_adapter.py`. This is the primary path. |
| QuaCCAToo | Available (GitHub) | Stub initially. Implement for cross-validation ~Day 15-20. |
| CUDA-Q Dynamics | Available (`pip install cudaq`, ARM64) | Stub initially. Implement for GPU-accelerated validation ~Day 10-15. |
| QDsiM | **No confirmed public repo** (Risk 5 in playbook) | Stub with NotImplementedError. If code becomes available, implement. If not, QDsiM's documented noise parameters are used via `parameters.py` and injected through SimOS. |
| cuDensityMat | Available (aarch64 wheels) | Stub initially. Optional GPU backend for Lindblad dynamics. |
| Zenodo ODMR dataset | Available | Reference data adapter for validation comparisons. Stub until validation phase. |

---

## 5. Repo 1 — What NOT to Build Yet

This section exists to prevent a future Claude instance from over-scaffolding. The following items were explicitly discussed and deferred:

- **GitHub Actions CI (`ci.yml`)** — Run tests locally. Add CI ~Day 20-30.
- **`.pre-commit-config.yaml`** — Not needed for 90-day solo sprint. Use `ruff` manually.
- **`.editorconfig`** — Nice-to-have, not must-have.
- **Claude Code skills (`.claude/skills/`)** — Create after working code exists.
- **Claude Code agents (`.claude/agents/`)** — Create after working code exists.
- **Regression test suites** — Add when you have baseline results to regress against.
- **Sweep config YAML files** — Add when you're actually running sweeps.
- **`docs/adr/` (Architecture Decision Records)** — This master decision document serves the same purpose for now. Add ADRs if the repo grows complex enough to warrant them.
- **Elaborate validation module** — The playbook's validation protocol (Section 3.3) is for ~Day 20-30. Don't build the validation framework before you have spectra to validate.
- **Any ML training code** — That belongs in Repo 2, period.
- **Any FPGA or hardware code** — That belongs in Repo 3, which is deferred entirely.

---

## 6. Repo 2 Parking Lot — `tychon-odmr-ml` Full Spec

**Status:** DO NOT BUILD until Repo 1 produces stable dataset manifests. Target: ~Day 20-25.  
**Location in Repo 1:** `docs/future/repo2-odmr-ml-spec.md` (copy this entire section).

### 6.1 Purpose

Model training, INT8 quantization-aware training, export, and evaluation ONLY. This repo consumes dataset manifests produced by `tychon-nv-sim` and produces model artifact bundles for the future `tychon-polarfire-control` repo. It does not own the simulator.

This repo maps to **Deliverable 2** of the v4 playbook: "Trained and INT8-Quantized Neural Network" (Task 2, Days 30-75).

### 6.2 Technical Requirements (extracted from v4 Playbook Deliverable 2)

**The Core Reframe:** The neural network is NOT a noise filter. It is a nonlinear Hamiltonian inverter solving three specific problems that a linear SISO PID controller cannot handle:

1. **Heading Error Correction:** At worst-case transverse field (50 µT), second-order perturbation creates ~37 nT systematic geometric bias. PID tracks the shifted resonance perfectly but cannot detect the bias. CNN maps ODMR features + temperature to true 3D field vector. Expected: heading errors from 30-40 nT to sub-5 nT (>85% reduction; report >50% KPP).

2. **Asymmetric Lineshape Inversion:** Symmetric Voigt fit on skewed profile creates ~500-1,500 nT systematic bias. INT8 CNN maps higher-order shape features directly to correct field vector. Deterministic O(1) forward pass in <0.1 ms. Classical Levenberg-Marquardt achieves comparable accuracy but requires 10-50 ms, violating <1 ms latency budget. The AI is a latency-enabling capability.

3. **MIMO Degeneracy Tracking:** Four NV crystallographic orientations create up to 8 ODMR resonances. At symmetry orientations, frequencies converge and independent SISO PID channels cross-talk and lose lock. CNN processes full spectrum as MIMO estimator.

**Dual Architecture Strategy (MLP + CNN):**

Architecture A (MLP, primary): 2-3 hidden layers, 128-256 neurons. Input: ~100-point ODMR frequency sweep. Output: magnetic field vector estimate. Composed entirely of FULLY_CONNECTED + RELU. Expected inference: <0.1 ms on PolarFire.

Architecture B (1D-CNN, secondary): 2-4 conv layers with depthwise-separable convolutions, residual connections, global average pooling. Target <1,000 parameters post-pruning. Reference: Feb 2026 MDPI Electronics paper (3,121 → 358 params with INT8 QAT).

**VectorBlox v3.0 Compilation Rules:**
- No separate CONV_1D operator. Implement 1D convolutions as CONV_2D with kernel shape (1×k) on input tensors reshaped to (1×N×channels).
- Allowed ops: CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, RELU/RELU6, ADD (residuals), MEAN (global avg pooling).
- Validate frozen TFLite graph against ops list BEFORE training at scale.
- **VectorBlox SDK 3.0 targets PolarFire SoC Video Kit only, NOT RT PolarFire.** This plan uses simulator + resource utilization reports. Full on-board execution deferred to later work.

**Training Pipeline:**
1. Generate training data using SimOS with coupled noise injection and asymmetric lineshape corruption (from Repo 1).
2. Train BOTH architectures in PyTorch on DGX Spark.
3. INT8 QAT via TorchAO: `torch.export.export()` → `prepare_qat_pt2e()` → training → `convert_pt2e()`. XNNPACKQuantizer for symmetric INT8.
4. Export: PyTorch → ONNX → TFLite INT8 → VNNX binary (`vnnx_compile`).
5. Validate with VectorBlox bit-accurate simulator.
6. Select the architecture that compiles cleanly AND generalizes best.

**PID Baseline:**
- SmartHLS C++ for PID implementation. SmartHLS motor controller achieves ~2 µs deterministic latency at 200 MHz. PID is ~3 multiplies, 2-3 adds, 1 accumulation: 50-250 ns. Every published NV frequency-locking system uses PID or PI control.
- Note: The actual PID implementation belongs in Repo 3. Repo 2 implements a `pid_proxy.py` that replicates PID behavior in Python for evaluation comparison purposes only.

**Five-Metric Evaluation Stack:**

| # | Metric | What It Measures | Plan KPP |
|---|---|---|---|
| 1 | Spherical Heading Error Profile | Peak-to-peak vector error across 360° 2D rotation in 50 µT field | >50% heading error reduction |
| 2 | Asymmetric Inversion Bias | Absolute vector bias on skewed ODMR spectra vs ground truth | >99% accuracy (reframed as <5 nT bias) |
| 3 | Frequency-Partitioned PSD | Noise comparison: sub-0.1 Hz drift band AND >1 Hz white noise band separately | >10× suppression (drift band only) |
| 4 | Allan Deviation (ADEV) | Stability across timescales; show flattened drift at τ >5 sec | Complements PSD |
| 5 | MagNav.jl Positioning RMSE | Navigation error using SGL 2020 flight data with Zenodo-derived noise | System-level (cf. Q-CTRL 11×) |

**Train/Test Separation (critical):**
- Metrics 1-4: Held-out synthetic test set with DIFFERENT random seeds AND DIFFERENT noise parameter distributions (shifted means, wider variance).
- Metric 5: Empirical Zenodo ODMR dataset characteristics injected into real SGL 2020 flight data.
- Document the train/test split explicitly.

### 6.3 VectorBlox SDK 3.0 Constraints (from Fast-Track Report)

- SDK 3.0 released Feb 10, 2026. End-to-end flow: quantize → compile → simulate → run on board.
- Supported board: PolarFire SoC Video Kit ONLY (not RT PolarFire, not Icicle Kit).
- For this plan: Use VectorBlox bit-accurate simulator for inference validation. Resource utilization reports from Libero for FPGA sizing.
- The SDK's supported-ops list is the hard constraint. Read it end-to-end before designing architectures.
- 1D convolutions must be implemented as 2D with (1×k) kernels.
- Export chain: PyTorch → ONNX → TFLite INT8 → `vnnx_compile` → `.vnnx` binary.

### 6.4 Data Contract (what Repo 2 expects from Repo 1)

Repo 2 consumes dataset manifests produced by `tychon-nv-sim`. The manifest must include:
- Generator git SHA and config hash
- Random seeds for all stochastic processes
- Train/val/test split definitions with explicit index lists
- Units for all quantities (SI)
- Corruption parameter ranges (P1 concentration, temperature, B1 gradient magnitude, B_perp range)
- Number of spectra per split
- Spectral resolution (frequency points per spectrum, frequency range)
- Provenance metadata (SimOS version, QuTiP version, backend)
- File format: HDF5 or numpy `.npz` with manifest as JSON sidecar

Repo 2's `data/contracts.py` validates incoming manifests against this schema and raises clear errors on mismatch.

### 6.5 Corrected File Tree

This tree incorporates the ChatGPT plan's structure with our corrections (minimal scaffold philosophy applies — not all files need to exist on Day 1 of Repo 2):

```
tychon-odmr-ml/
  README.md
  CLAUDE.md
  pyproject.toml
  .gitignore
  Makefile

  docs/
    phase1-context/
      requirements.md          ← Deliverable 2 requirements from playbook
      vectorblox-constraints.md ← SDK 3.0 ops list and compilation rules
      data-contract.md         ← what this repo expects from tychon-nv-sim
    architecture.md
    vectorblox-op-policy.md    ← formal policy on which ops are allowed
    evaluation-protocol.md     ← five-metric stack methodology
    train-test-separation.md   ← explicit separation policy

  experiments/
    README.md                  ← exploratory notebooks for model prototyping

  configs/
    model/
      mlp.yaml
      cnn.yaml
    train/
      baseline.yaml
      qat.yaml
    export/
      tflite.yaml
      vnnx.yaml
    eval/
      heading.yaml
      adev.yaml

  src/tychon_odmr_ml/
    __init__.py
    cli.py
    config.py

    data/
      contracts.py             ← validates incoming manifests from Repo 1
      loaders.py               ← reads Repo 1 datasets
      transforms.py            ← input normalization, augmentation
      normalization.py

    models/
      mlp.py                   ← Architecture A
      cnn1d.py                 ← Architecture B (1D conv via 2D reshape)
      vectorblox_compat.py     ← ops whitelist check before training
      pruning.py               ← post-training pruning

    training/
      loop.py
      losses.py
      checkpoints.py
      seeds.py

    quantization/
      torchao_qat.py           ← TorchAO INT8 QAT pipeline
      calibration.py

    export/
      onnx_export.py
      tflite_export.py
      vnnx_export.py           ← wraps vnnx_compile, stub if unavailable
      artifact_bundle.py       ← packages model + metadata for Repo 3

    evaluation/
      heading_error.py         ← Metric 1: spherical heading error profile
      asymmetry_bias.py        ← Metric 2: asymmetric inversion bias
      psd.py                   ← Metric 3: frequency-partitioned PSD
      adev.py                  ← Metric 4: Allan deviation
      magnav_bridge.py         ← Metric 5: MagNav.jl bridge (stub if no Julia)
      report_builder.py        ← generates evaluation report

    baselines/
      pid_proxy.py             ← Python PID proxy for evaluation comparison

    validation/
      ops_guard.py             ← checks model against VectorBlox ops whitelist
      golden_vectors.py        ← reference I/O pairs for FPGA integration testing

  tests/
    smoke/
      test_tiny_train_eval.py  ← CPU-only, tiny synthetic fixture, no vendor tools
    unit/
      test_data_contracts.py
      test_mlp_shapes.py
      test_cnn_shapes.py
      test_ops_guard.py
    integration/
      test_train_pipeline.py
      test_export_bundle.py
    contract/
      test_repo1_manifest_compat.py  ← validates against Repo 1 manifest schema

  artifacts/
    model_cards/
    bundles/                   ← exported model bundles (git-ignored, not tracked)
    reports/
```

### 6.6 Changes from Original ChatGPT Plan

| Item | ChatGPT Proposed | Our Decision | Rationale |
|---|---|---|---|
| CI on Day 1 | `.github/workflows/ci.yml` in scaffold | Defer to ~Day 20-30 | Solo sprint, run tests locally first |
| `.pre-commit-config.yaml` | Include in scaffold | Defer | Nice-to-have, not must-have |
| Claude skills/agents | 2 skills + 1 agent on Day 1 | Defer | Create after working code exists |
| `docs/adr/` directory | Multiple ADR files | Defer | Master decision doc serves this purpose |
| regression tests | `tests/regression/` | Defer | Need baseline results first |
| `.editorconfig` | Include in scaffold | Defer | Minimal overhead benefit |
| Notebooks | Excluded ("package code as source of truth") | Added `experiments/` directory | Fastest path to first results from Jupyter background |
| Scaffold size | ~50+ files | Start with ~20, grow organically | Wall of empty files slows Week 1 |

---

## Appendix A: Original ChatGPT Repo Plan — Annotated

The following is the original ChatGPT-generated repo split plan with annotations marking what we kept (✓), modified (△), and rejected (✗).

### Overall Architecture

**✓ Three-repo split** (`tychon-nv-sim`, `tychon-odmr-ml`, `tychon-polarfire-control`). The deliverable mapping is correct. However, we're executing sequentially: Repo 1 first, Repo 2 ~Day 20-25, Repo 3 deferred.

**✓ Common baseline** (README, CLAUDE.md, pyproject.toml, Makefile, src/, tests/, docs/). Correct structure.

**✗ All three repos scaffolded simultaneously.** Rejected. Build one at a time. Repo 2 spec parked in Repo 1.

### Common Baseline Items

| Item | Verdict | Notes |
|---|---|---|
| `README.md` | ✓ | Essential |
| `CLAUDE.md` | ✓ | Essential for Claude Code |
| `.claude/settings.json` | △ | Create minimal version. Don't over-configure. |
| `.claude/skills/` | ✗ Defer | Create after working code exists |
| `.claude/agents/` | ✗ Defer | Create after working code exists |
| `.editorconfig` | ✗ Defer | Not needed for solo sprint |
| `.gitignore` | ✓ | Essential |
| `.pre-commit-config.yaml` | ✗ Defer | Use ruff manually |
| `pyproject.toml` | ✓ | Essential |
| `Makefile` or `justfile` | ✓ | Use Makefile |
| `configs/` | △ | Create directory but don't populate with YAML files until needed |
| `scripts/` | △ | Create directory, populate incrementally |
| `src/<package>/` | ✓ | Essential |
| `tests/unit`, `tests/integration`, `tests/smoke` | △ | Create `tests/smoke/` and `tests/unit/` only. Add integration later. |
| `docs/architecture.md` | ✓ | Useful from Day 1 |
| `docs/traceability.md` | △ | Replaced by `docs/phase1-context/requirements.md` which traces to playbook |
| `.github/workflows/ci.yml` | ✗ Defer | Run tests locally until ~Day 20-30 |
| `artifacts/README.md` | △ | Create `artifacts/` directory with .gitkeep. Don't over-structure. |

### Repo 1 (`tychon-nv-sim`) Scaffold

| Item | Verdict | Notes |
|---|---|---|
| Adapter pattern (SimOS, QuaCCAToo, CUDA-Q, QDsiM) | ✓ | Exactly right. Critical for uncertain dependencies. |
| CPU smoke path | ✓ | Mandatory. |
| Dataset manifest schema with seeds, units, provenance | ✓ | Core requirement. Drives Repo 2 design. |
| Parameter catalog in docs | ✓ | Useful but can be lightweight initially. |
| Traceability doc | △ | Replaced by `docs/phase1-context/requirements.md` |
| Sample fixture dataset | ✓ | Tiny checked-in fixture for smoke tests. |
| Deep file tree (~50+ files) | ✗ | Too many files. Start with ~20, grow organically. |
| Separate `validation/` module with metrics, plots, adev | △ | Defer until ~Day 20-30 when there are spectra to validate. |
| Separate `pipelines/` module | △ | Defer. Start with scripts or notebook-driven generation. |
| Multiple config YAML files (sweeps, noise params) | △ | Defer. Create when running sweeps. |

### Repo 2 (`tychon-odmr-ml`) Scaffold

| Item | Verdict | Notes |
|---|---|---|
| VectorBlox compatibility guard (`ops_guard.py`) | ✓ | Critical. Check ops BEFORE training at scale. |
| Model artifact bundle with hashes, model card | ✓ | Essential for downstream FPGA integration. |
| Held-out distribution policy | ✓ | Mandatory per playbook train/test separation protocol. |
| Five-metric evaluation modules | ✓ | All five required. |
| `vectorblox-op-policy.md` | ✓ | Prevents tribal knowledge about export constraints. |
| Contract tests against Repo 1 manifests | ✓ | Right pattern for cross-repo validation. |
| `experiments/` directory | △ Added | Not in ChatGPT plan. Added for notebook-based model prototyping. |

### Repo 3 (`tychon-polarfire-control`) Scaffold

| Item | Verdict | Notes |
|---|---|---|
| Entire repo | ✗ Defer | Not building until ~Day 45+. No spec written. |

### Claude Code CLI Recommendations

| Item | Verdict | Notes |
|---|---|---|
| Plan Mode first, then Normal Mode | ✓ | Correct workflow per Anthropic docs. |
| `/init` for starter CLAUDE.md | ✓ | Good starting point. |
| Project scope for shared settings | ✓ | Correct. |
| Hooks for formatting and smoke checks | △ | Good idea but defer until working code exists. |
| `pyright-lsp` plugin | ✓ | Genuinely useful. Install it. |
| `github` plugin | △ | Install if using GitHub actively. |
| `commit-commands` plugin | △ | Install when making commits regularly. |
| `pr-review-toolkit` | ✗ Defer | Solo developer, no PRs to review yet. |
| `plugin-dev` | ✗ Defer | Only if packaging Tychon-specific plugins. |

### ChatGPT Plan Mode Prompts

| Item | Verdict | Notes |
|---|---|---|
| Repo 1 Plan Mode prompt | △ | Reasonable but too verbose. Simplify when using. |
| Repo 2 Plan Mode prompt | △ | Reasonable but too verbose. Simplify when using. |

---

*End of document. This file should be saved as `tychon_phase1_repo_architecture_decisions.md` and provided as context to any Claude instance working on Tychon repositories.*

