# odmr-edge-ml

Edge-optimized neural networks for real-time ODMR spectral analysis. Includes quantization-aware training pipeline, VectorBlox FPGA export chain, and a five-metric evaluation framework for magnetometry applications.

Consumes synthetic ODMR datasets from [`nv-sensor-sim`](../nv-sensor-sim/README.md) and produces INT8-quantized model artifacts for [`polarfire-hybrid-control`](../polarfire-hybrid-control/README.md). Part of [Tychon quantum sensing](../../README.md).

## Where this fits

| | |
|---|---|
| Purpose | Train, evaluate, quantize and export small networks that estimate the magnetic field from an ODMR spectrum |
| Takes in | Datasets from `nv-sensor-sim` (`dataset.h5` + `manifest.json`), checked against the dataset contract. None is committed; see the [synthetic-data walkthrough](../../docs/synthetic-data.md) |
| Produces | Trained models, evaluation results in `docs/` and `experiments/`, and INT8 TFLite exports. The FPGA worker compiles the TFLite file to a VectorBlox `.vnnx` |
| Status | The deployed scalar model, `fcnn_v2_residual_dataset_a` (2,905 parameters, INT8), cut mean field error by 4.90 % against the PID proxy on its synthetic test split (22.38 against 23.54 µT). Its training set, `production_50k_v2_aic`, is not in this repository (`data/production_50k_v2_aic` is a link to a folder outside it). The vector models are evaluated on simulated spectra only |
| Try it | `make bench` at the repository root trains a small scalar model on CPU in one command ([bench](../../bench/README.md)) |

## Features

- **Model architectures**: MLP, 1D CNN, and fully-connected neural network (FCNN) for scalar residual correction
- **Quantization-aware training (QAT)**: Fake-quantize → INT8 TFLite export, with an operator check for the VectorBlox compiler (the `.vnnx` compile runs in `polarfire-hybrid-control`)
- **Ops guard**: Static analysis ensures all model operations are VectorBlox V250-compatible
- **PID baseline**: Derivative zero-crossing PID proxy for comparison benchmarks
- **Five-metric evaluation**: MAE, angular error, heading sweep, Allan deviation, inference latency

## Installation

Run the commands in this README from `workers/odmr-edge-ml`:

```bash
cd workers/odmr-edge-ml
pip install -e ".[dev]"
```

### Dependencies

- Python >= 3.11
- PyTorch >= 2.2
- NumPy >= 1.26
- h5py >= 3.10
- PyYAML >= 6.0
- pytest >= 8.0 (dev)

## Quick Start

```bash
# Run all tests
make test

# Run unit tests only
make test-unit

# Run contract tests (requires a dataset in ./data/golden/, not included in this repository)
make test-contract

# Run smoke tests (requires a dataset in ./data/golden/, not included in this repository)
make test-smoke
```

## Architecture

```
src/odmr_edge_ml/
├── baselines/         # PID proxy baseline
├── cascade/           # Two-stage (coarse, fine) INT8 cascade
├── config.py          # YAML-driven configuration
├── data/              # HDF5 dataset loading + manifest validation
├── evaluation/        # PID proxy, residual dataset, feature extraction
├── export/            # PyTorch → ONNX export with VectorBlox compatibility checks
├── models/            # MLP, CNN1D, FCNN architectures
├── sampling/          # Bias-aware importance samplers for cascade training
├── training/          # Training loop, loss functions, QAT pipeline
├── validation/        # VectorBlox ops compatibility guard
└── vector/            # Vector readout: per-resonance anchors, windowing, BLUE projection
```

### Data Flow

1. An upstream NV-diamond simulator produces HDF5 datasets with JSON manifests
2. `data/contracts.py` validates manifest schema (23 required fields)
3. `data/loaders.py` loads train/val/test splits from HDF5
4. Models train on spectra → scalar residual correction
5. QAT pipeline exports INT8 TFLite; `polarfire-hybrid-control` compiles it to VectorBlox .vnnx

## Experiments

The `experiments/` directory contains standalone scripts for:

- `fcnn_v2_int8_float_equivalence.py` — deployed `fcnn_v2_residual_dataset_a` float-vs-INT8
  equivalence/accuracy harness on `production_50k_v2_aic`; 2026-06-21 test split result:
  INT8-vs-float MAE `0.0346 uT`, RMSE `0.0452 uT`, max abs `0.7033 uT`, saturation fraction
  `0.0012`, deployed INT8 clamped reduction vs PID `4.90%`
- `architecture_comparison.py` — MLP vs FCNN head-to-head evaluation
- `scalar_residual_comparison.py` — Scalar residual correction pipeline
- `heading_sweep.py` — 360-degree heading error characterization
- `adev_simulation.py` — Allan deviation stability over simulated LEO orbits
- `feature_mlp.py` — Physics-informed feature extraction comparison
- `diagnose_angular_error.py` — Angular error diagnostic analysis
