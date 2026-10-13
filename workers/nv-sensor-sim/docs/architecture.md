# Architecture

NV Sensor Sim follows an adapter-based architecture with three layers matching the physics sensor model.

## Module Layout

```
SimOS Adapter ──→ Physics Modules ──→ Dataset Writer ──→ Manifest
     │                  │
     │            ┌─────┴─────┐
     │            │           │
     ▼            ▼           ▼
  NVSystem   hamiltonian   noise_injection   lineshape
             (Layer 1)     (Layer 2)         (asymmetry)
                                │
                          parameters.py
                          (Layer 3: published values)
```

## Layers

### Layer 1 — NV Physics Engine
`adapters/simos_adapter.py` + `physics/hamiltonian.py`

SimOS NVSystem provides the 7-level photophysics model (GS triplet + ES triplet + SS singlet). The Hamiltonian module adds temperature-dependent ZFS correction and transverse field injection.

### Layer 2 — Coupled Noise Injection
`physics/noise_injection.py`

Ornstein-Uhlenbeck stochastic processes for T(t) and B1(t) injected at the Hamiltonian level via SimOS StochasticLiouvilleParameters — parameter perturbation upstream of the spectrum computation, not output post-processing. NOTE: the production spectrum path computes spectra by Hamiltonian eigenvalue diagonalization + phenomenological Lorentzian lineshape (see `simos_adapter.generate_odmr_spectrum`); it does not solve the Lindblad master equation, so state-mixing enters only through the perturbed Hamiltonian eigenstructure.

Note added 2026-10-13: batch generation does not call this injector. In `noise_mode: stochastic` it samples (T, B1) pairs from OU trajectories (`sample_ou_trajectory_pair`) and passes them to the eigenvalue path. That path builds a spin-only `NVSystem(optics=False)`, so the Layer 1 photophysics model is not used for dataset spectra. Walkthrough: [`docs/synthetic-data.md`](../../../docs/synthetic-data.md) at the monorepo root.

### Layer 3 — Published Parameters
`physics/parameters.py`

All noise parameters from peer-reviewed literature (CCE study for P1 bath, textbook dD/dT, SBQuantum space qualification data). No first-principles derivation.

### Asymmetric Lineshape Generation
`physics/lineshape.py`

Two corruption channels: spatial B1 gradient (5-30%) and transverse B_perp (0-50 µT). Forces downstream ML to learn on realistic Fano-like lineshapes.

### Dataset Contract
`datasets/schema.py` + `datasets/writer.py`

Versioned manifest with seeds, units, splits, provenance. Consumed by downstream ML training pipelines.

## Adapter Strategy

| Backend | Status | File |
|---------|--------|------|
| SimOS | Primary (implemented) | `adapters/simos_adapter.py` |
| QuaCCAToo | Stub (planned) | `adapters/quaccatoo_adapter.py` |
| CUDA-Q | Stub (planned) | `adapters/cudaq_adapter.py` |
| QDsiM | Stub (no public repo) | `adapters/qdsim_adapter.py` |

