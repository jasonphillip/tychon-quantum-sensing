# Development Guide

Edge-optimized neural networks for real-time ODMR spectral analysis. Consumes synthetic ODMR datasets from an upstream NV-diamond simulator to train, quantize, and evaluate models for VectorBlox V250 FPGA deployment.

## Layout

- `src/odmr_edge_ml/` — package source (src layout)
- `tests/unit/` — self-contained unit tests (no external data needed)
- `tests/contract/` — contract tests against golden dataset
- `tests/smoke/` — end-to-end CPU-only smoke tests
- `experiments/` — standalone experiment scripts (training, evaluation, figures)
- `scripts/` — utility scripts (first training pass, FCNN export fix)
- `configs/` — YAML configuration files

## Data

Golden dataset: `./data/golden/` (dataset.h5 + manifest.json).
Production dataset: `./data/production_50k/` (50K spectra for full experiments).

Both are gitignored and expected to be symlinks to a shared data directory. The golden dataset is generated with master_seed=12345: 100 train / 20 val / 20 test, 100-point spectra.

## Commands

```bash
pip install -e ".[dev]"       # install in dev mode
make test                     # all tests
make test-unit                # unit tests only
make test-contract            # contract tests (need golden dataset)
make test-smoke               # smoke tests (need golden dataset)
```

## Dependencies

Runtime: torch>=2.2, numpy>=1.26, h5py>=3.10, pyyaml>=6.0
Dev: pytest>=8.0
Python: >=3.11

## Architecture

### Models

Three architectures, all VectorBlox V250 compatible:

- **OdmrMLP** (`models/mlp.py`) — Fully connected, ReLU6 activations. ~8.6K params.
- **OdmrCNN1D** (`models/cnn1d.py`) — 1D CNN using (1,k) Conv2d kernels (no Conv1d — banned by VectorBlox).
- **OdmrFCNN** (`models/fcnn.py`) — Fully convolutional, no Linear layers. Final Conv2d collapses spatial dim to output. ~3.3K params. Production architecture.

All models reshape input to (batch, C, 1, length) for Conv2d ops. Multi-channel input supported (e.g., 2-channel: spectrum + PID anchor).

### Training Pipeline

1. `data/contracts.py` validates manifest schema (23 required fields, type checks, seed disjointness, range validation)
2. `data/loaders.py` loads train/val/test splits from HDF5, optional per-spectrum normalization
3. `training/loop.py` runs training with Kaiming He init, cosine LR schedule, Huber + angular loss
4. `training/qat.py` wraps model in FX-graph QAT (symmetric INT8, per-channel weights, per-tensor activations)
5. `validation/ops_guard.py` verifies all ops in the exported graph are in the VectorBlox whitelist

### Evaluation

- `evaluation/pid_proxy.py` — Derivative zero-crossing PID baseline for comparison
- `evaluation/residual_dataset.py` — Generates 2-channel residual training data: ΔB = |B_true| - B_PID
- `evaluation/feature_extraction.py` — Physics-informed spectral feature extraction

### Export Chain

PyTorch → QAT (FX graph mode) → ONNX → TFLite INT8 → .vnnx (via `vnnx_compile -c V250`)

The `vnnx_compile` step requires VectorBlox SDK v2.0.3.

## VectorBlox Constraints

Enforced by `validation/ops_guard.py` — run it before training at scale:

- **No Conv1d** — use Conv2d with (1,k) kernels on reshaped input
- **No BatchNorm** — use ReLU/ReLU6 directly
- **No dynamic shapes** — all tensor dimensions must be static at export time
- **Allowed ops**: Conv2d, Linear, ReLU, ReLU6, Add, Mean, AdaptiveAvgPool2d, Reshape, Permute, Unsqueeze, Slice, GetItem
- **Quantization**: Symmetric INT8, zero_point=0 for activations, per-channel scales for weights

## Compute

Use `device='cuda'` for all training runs. CPU-only is acceptable for tiny models (<1000 params); anything larger should use GPU.

## Cross-Repo Data Flow

The downstream FPGA control repo consumes .vnnx models from this repo's export pipeline. Exported artifacts go to `./exports/` and must be compiled with `vnnx_compile -c V250` using SDK v2.0.3.

## Known Gotchas

- **FCNN TFLite export**: The FCNN uses `batch_shape` in its forward pass which can introduce dynamic shape ops. `scripts/fix_fcnn_export.py` patches this for V250 compatibility.
- **torch.ao.quantization deprecation**: FX QAT raises DeprecationWarning on torch>=2.10. Suppress with `warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")`. Functionally correct on torch 2.11.
- **Scalar residual, not 3D vector**: CW-ODMR spectra at target field strengths (20-70 µT) cannot resolve B-field direction due to quantum degeneracy. Production models predict scalar ΔB residual corrections, not 3D vectors. The config default `output_dim: 3` is legacy — experiments override to `output_dim: 1`.
