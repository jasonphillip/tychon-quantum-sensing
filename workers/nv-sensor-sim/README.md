# NV Sensor Sim

NV-diamond ODMR simulator for synthetic data generation: labelled spectra with configurable imperfections and noise, and reproducible datasets with full provenance. Part of [Tychon quantum sensing](../../README.md); the [synthetic-data walkthrough](../../docs/synthetic-data.md) explains the data for readers who start here.

## Where this fits

| | |
|---|---|
| Purpose | Simulate continuous-wave ODMR spectra of an NV-diamond sensor and write labelled datasets for the ML workers |
| Takes in | YAML configs in [`configs/`](configs/): field, imperfection, noise and split settings. Public measured spectra in `data/experimental/` are used for comparison only |
| Produces | One folder per dataset with `dataset.h5` and `manifest.json` (gitignored; regenerate them with the scripts) |
| Status | Supplies synthetic data for the scalar models and vector tracker. Separate [measured-data pilots](../odmr-edge-ml/docs/measured_pilots_2026-10.md) use public acquisitions. Against four public datasets, default simulated lines are 2 to 11 times narrower than measured ([results](docs/external_validation_results.md)); the per-spectrum width fit is in-sample only ([fit](docs/simulator_fit_results.md)). The deployed scalar dataset has a [committed recipe and manifest](../../docs/synthetic-data.md#the-deployed-scalar-models-data), reproduced byte for byte |
| Used by | [`odmr-edge-ml`](../odmr-edge-ml/README.md) (static datasets) and [`odmr-vector-tracking`](../odmr-vector-tracking/README.md) (time series) |

## What This Does

- Wraps [SimOS](https://www.sciencedirect.com/science/article/pii/S0010465525004205) to compute NV line positions from the spin Hamiltonian, then draws each line as a Lorentzian (not an optical-pumping or Lindblad model)
- Samples temperature and microwave amplitude from coupled Ornstein-Uhlenbeck processes and feeds them into that calculation (`noise_mode: stochastic`)
- Generates asymmetric lineshapes (B1 gradient + transverse B_perp)
- Produces versioned dataset manifests with seeds, units, splits, and provenance
- Compares simulated spectra with public measured ODMR data ([results](docs/external_validation_results.md))

## Install

Python 3.11 or later. Run the commands in this README from `workers/nv-sensor-sim`:

```bash
cd workers/nv-sensor-sim
pip install -e ".[dev]"
```

The `gpu` extra installs CUDA-Q, but the CUDA-Q backend is a stub (see Adapter Pattern below), so it adds no GPU path today.

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

### Generate synthetic spectra

A tiny dataset (2 / 1 / 1 spectra, about a second on a CPU):

```bash
python -m nv_sensor_sim.pipelines.batch_generate --config configs/quickstart_tiny.yaml --output-dir /tmp/nv-sim-tiny
```

It writes `dataset.h5` and `manifest.json`. Use `configs/batch_stochastic.yaml` for the full 1,000 / 200 / 200 set. Both flags are required together, and unknown config keys are rejected. The vector and time-series lineages use `scripts/generate_vector_dataset.py` and `scripts/generate_sequence_dataset.py` ([dataset contract](docs/dataset-contract.md#released-lineages)).

One spectrum:

```python
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter
from nv_sensor_sim.config import SimulationConfig

config = SimulationConfig(n_freq_points=2000, include_nitrogen=False, use_optics=False)
adapter = SimOSAdapter(config)
frequencies, signal = adapter.generate_odmr_spectrum()  # Hz, normalized PL
```

`return_line_centers=True` adds the line positions as a third array.

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
experiments/         # Exploratory Jupyter notebooks
scripts/             # Dataset generation, benchmarking, data extraction, notebook generation
docs/                # Architecture docs, dataset contract, external validation results
logs/                # Generation records of released lineages
```
