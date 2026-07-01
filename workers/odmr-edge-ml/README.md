# odmr-edge-ml

Edge-optimized neural networks for real-time ODMR spectral analysis. Includes quantization-aware training pipeline, VectorBlox FPGA export chain, and a five-metric evaluation framework for magnetometry applications.

Consumes synthetic ODMR datasets from an upstream NV-diamond simulator and produces INT8-quantized model artifacts for downstream FPGA deployment.

## Features

- **Model architectures**: MLP, 1D CNN, and fully-connected neural network (FCNN) for scalar residual correction
- **Quantization-aware training (QAT)**: Fake-quantize → INT8 TFLite export → VectorBlox .vnnx compilation
- **Ops guard**: Static analysis ensures all model operations are VectorBlox V250-compatible
- **PID baseline**: Derivative zero-crossing PID proxy for comparison benchmarks
- **Five-metric evaluation**: MAE, angular error, heading sweep, Allan deviation, inference latency

## Installation

```bash
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

# Run contract tests (requires dataset in ./data/golden/)
make test-contract

# Run smoke tests (requires dataset in ./data/golden/)
make test-smoke
```

## Architecture

```
src/odmr_edge_ml/
├── baselines/         # PID proxy baseline
├── config.py          # YAML-driven configuration
├── data/              # HDF5 dataset loading + manifest validation
├── evaluation/        # PID proxy, residual dataset, feature extraction
├── models/            # MLP, CNN1D, FCNN architectures
├── training/          # Training loop, loss functions, QAT pipeline
└── validation/        # VectorBlox ops compatibility guard
```

### Data Flow

1. An upstream NV-diamond simulator produces HDF5 datasets with JSON manifests
2. `data/contracts.py` validates manifest schema (23 required fields)
3. `data/loaders.py` loads train/val/test splits from HDF5
4. Models train on spectra → scalar residual correction
5. QAT pipeline exports INT8 TFLite → VectorBlox .vnnx

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
