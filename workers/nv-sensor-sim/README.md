# NV Sensor Sim

Physics-based NV-diamond ODMR simulator for synthetic data generation. Supports ensemble simulation with configurable noise models, GPU acceleration via SimOS, and reproducible dataset generation with full provenance tracking.

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

For GPU acceleration (CUDA-Q backend):

```bash
pip install -e ".[gpu]"
```

For the orbit-in-the-loop benchmark (SGP4 + IGRF-14):

```bash
make install-orbit
```

Pre-stage manylinux2014_aarch64 wheels for an air-gapped DGX Spark target:

```bash
# On a connected box:
make orbit-wheels
# Sync wheels/orbit/ to the Spark, then on the Spark:
pip install --no-index --find-links wheels/orbit sgp4 ppigrf
```

The benchmark itself is configured in `configs/orbit_benchmark_v1.yaml` (TLEs
baked inline; see the file header for ADEV statistical-power notes).

## Quick Start

```bash
# Run CPU-only smoke tests
make smoke

# Run all tests
make test

# Lint
make lint
```

### Generate a dataset

```python
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig

config = SimulationConfig()
adapter = SimOSAdapter(config)
spectrum = adapter.generate_spectrum()
```

### Batch generation from config

```bash
python -m nv_sensor_sim.pipelines.batch_generate --config configs/batch_stochastic.yaml --output-dir output/
```

## Architecture

See [docs/architecture.md](docs/architecture.md) for the full module layout.

```
SimOS Adapter --> Physics Modules --> Dataset Writer --> Manifest
     |                  |
     |            +-----+-----+
     |            |           |
     v            v           v
  NVSystem   hamiltonian   noise_injection   lineshape
             (Layer 1)     (Layer 2)         (asymmetry)
                                |
                          parameters.py
                          (Layer 3: published values)
```

### Adapter Pattern

| Backend | Status | File |
|---------|--------|------|
| SimOS | Primary (implemented) | `adapters/simos_adapter.py` |
| QuaCCAToo | Stub (planned) | `adapters/quaccatoo_adapter.py` |
| CUDA-Q | Stub (planned) | `adapters/cudaq_adapter.py` |
| QDsiM | Stub (planned) | `adapters/qdsim_adapter.py` |

## Repo Structure

```
src/nv_sensor_sim/
  adapters/          # Backend interfaces (SimOS, QuaCCAToo, CUDA-Q, QDsiM)
  physics/           # Hamiltonian, noise injection, lineshape, published parameters
  datasets/          # Schema, writer, loader for HDF5 + JSON manifest bundles
  pipelines/         # Batch generation pipeline
  validation/        # Reference comparison against experimental data
  config.py          # Typed configuration dataclasses
tests/
  smoke/             # CPU-only smoke tests
  unit/              # Unit tests
  integration/       # Integration tests
configs/             # YAML configs for batch generation and sweeps
data/experimental/   # Zenodo ODMR reference data (25 CSV spectra)
docs/external_validation_results.md   # Simulator vs public ODMR datasets: overlap, shape, contrast, linewidth (table)
experiments/         # Exploratory Jupyter notebooks
scripts/             # Benchmarking, data extraction, notebook generation
docs/                # Architecture docs, dataset contract
```
