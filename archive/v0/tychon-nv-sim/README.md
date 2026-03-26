# Tychon NV-Sim

NV-diamond magnetometer ODMR simulator and synthetic dataset generator.

**Tychon AI Phase I SBIR** — Deliverable 1: Validated NV-Diamond Magnetometer Sensor Model + Synthetic Data Generator.

## What This Does

- Wraps [SimOS](https://www.sciencedirect.com/science/article/pii/S0010465525004205) to generate physics-based NV-diamond ODMR spectra
- Injects coupled stochastic noise (temperature, MW power) at the Hamiltonian level via Ornstein-Uhlenbeck processes
- Generates asymmetric lineshapes (B1 gradient + transverse B_perp)
- Produces versioned dataset manifests with seeds, units, splits, and provenance
- Validates synthetic spectra against published reference data

## Install

```bash
pip install -e ".[dev]"
```

## Quick Start

```bash
# Run CPU-only smoke tests
make smoke

# Run all tests
make test

# Lint
make lint
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the module layout. The authoritative design document is [docs/phase1-context/tychon_phase1_repo_architecture_decisions.md](docs/phase1-context/tychon_phase1_repo_architecture_decisions.md).

## Repo Structure

- `src/tychon_nv_sim/adapters/` — Adapter interfaces for SimOS, QuaCCAToo, CUDA-Q, QDsiM
- `src/tychon_nv_sim/physics/` — Hamiltonian construction, noise injection, lineshape generation
- `src/tychon_nv_sim/datasets/` — Dataset schema, writing, and loading
- `tests/smoke/` — CPU-only smoke tests
- `tests/unit/` — Unit tests
- `experiments/` — Exploratory Jupyter notebooks (not deliverables)
