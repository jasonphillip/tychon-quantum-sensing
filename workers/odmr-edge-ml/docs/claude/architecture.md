# odmr-edge-ml — architecture, pipeline, evaluation, export chain

Companion to `CLAUDE.md` (the map). Moved here verbatim from `CLAUDE.md` on 2026-09-04.

## Architecture

### Models

Three architectures, all VectorBlox V250 compatible:

- **OdmrMLP** (`models/mlp.py`) — Fully connected, ReLU6 activations. ~8.6K params.
- **OdmrCNN1D** (`models/cnn1d.py`) — 1D CNN using (1,k) Conv2d kernels (no Conv1d — banned by VectorBlox).
- **OdmrFCNN** (`models/fcnn.py`) — Fully convolutional, NO Linear layers anywhere. Final Conv2d collapses spatial dim to output. ~3.3K params. This is the production architecture.

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
- `experiments/fcnn_v2_int8_float_equivalence.py` — 2026-06-21 deployed
  `fcnn_v2_residual_dataset_a` float-vs-INT8 harness on `production_50k_v2_aic`; current result
  is INT8-vs-float MAE `0.0346 uT`, RMSE `0.0452 uT`, max abs `0.7033 uT`, saturation
  fraction `0.0012`, and deployed INT8 clamped reduction vs PID `4.90%`. Use about 5% as the
  deployed dashboard/report claim; do not call this bit-exact INT8 equivalence.

### Export Chain

PyTorch → QAT (FX graph mode) → ONNX → TFLite INT8 → .vnnx (via `vnnx_compile -c V250`)

The `vnnx_compile` step requires VectorBlox SDK v2.0.3.

## Cross-Repo Data Flow

The downstream FPGA control repo (`polarfire-hybrid-control`) consumes .vnnx models from this repo's export pipeline. Exported artifacts go to `./exports/` and must be compiled with `vnnx_compile -c V250` using SDK v2.0.3.

> Scope reminder (kept in `CLAUDE.md` § Scope boundary): this repo stops at the TFLite INT8 artifact; the `.vnnx` compile runs in `polarfire-hybrid-control` via `ssh bee`.
