# Deliverable 1 — Technical Requirements

*Extracted from Section 3 of the architecture decisions document.*

## Purpose

Physics-based NV-diamond ODMR simulation and synthetic dataset generation ONLY. No model training logic. No ML code. This repo owns the "truth" for synthetic spectra, corruption parameters, seeds, units, and dataset manifests.

Maps to **Deliverable 1** of the v4 playbook: "Validated NV-Diamond Magnetometer Sensor Model + Synthetic Data Generator" (Task 1, Days 1-45).

## Three-Layer Sensor Model

### Layer 1 — NV Physics Engine (Hamiltonian + Dynamics)
- SimOS as core: 7-level photophysics (GS triplet, ES triplet, SS singlet), ensemble ODMR with temperature dependence and strain, Lindblad master equation solvers, stochastic time-dependent Hamiltonians
- QuaCCAToo for cross-validation: pre-built NV ground-state Hamiltonian with ZFS, hyperfine, Zeeman, P1 DEER sensing
- CUDA-Q Dynamics for GPU acceleration: NV+P1 demo as reference (64% runtime reduction on Blackwell)

### Layer 2 — Sensor-Level Noise Model (Coupled Stochastic Injection)
- **Critical v4 change:** Noise injected AT THE HAMILTONIAN LEVEL, not as post-processing
- T(t) and B1(t) parameterized as Ornstein-Uhlenbeck processes
- Passed to SimOS `stochastic_evol` via `StochasticLiouvilleParameters`
- Lindblad master equation captures state-mixing and cross-couplings inherently

### Layer 3 — Noise Parameterization (Published Values)
- P1 bath: Lorentzian PSD, Δ ~ 1-7 MHz, τ_c ~ 5-50 µs (arXiv:2503.05404)
- Thermal drift: dD/dT ≈ -74.2 kHz/K (textbook)
- SBQuantum: thermal cycling -65°C to +125°C, ~400 pT/√Hz, heading errors <5 nT (arXiv:2509.19179)
- Surface noise model REMOVED (v4): irrelevant for bulk diamond ensemble

### Asymmetric Lineshape Generation (v4 addition)
- Spatial B1 gradient: 5-30% variation across diamond
- Transverse field injection: B_perp 0 to 50 µT as off-diagonal Zeeman terms
- Forces ML to learn on realistic, asymmetric, Fano-like lineshapes

## What NOT to Build
- Physics-informed neural network (PINN) — no published precedent for NV-diamond ODMR
- Surface noise model — irrelevant for bulk ensemble
- Any ML training code — belongs in Repo 2

## Validation Protocol
1. Generate spectra across parameter sweep (P1, temperature, B-field, B1 gradient, B_perp)
2. Compare against Zenodo ODMR dataset and SBQuantum published data
3. Verify P1 bath decoherence times match CCE study
4. Show Allan deviation stability curves match published behavior
5. Cross-validate against Tsunaki et al. digital-twin paper (arXiv:2510.14907)
