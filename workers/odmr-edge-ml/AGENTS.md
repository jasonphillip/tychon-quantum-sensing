> Agent instruction file as used by this repo's coding-agent session (snapshot 2026-10-09; the live file was kept outside version control).

# odmr-edge-ml

Edge-optimized neural networks for real-time ODMR spectral analysis. Consumes synthetic ODMR datasets from the upstream simulator (`nv-sensor-sim`) to train, quantize, and evaluate models for VectorBlox V250 FPGA deployment.

This file is a map. Reference detail lives under `docs/claude/` — read on demand (see the context map at the bottom).

## Scope boundary — what this repo does NOT do

**This repo does NOT compile `.vnnx` artifacts and does NOT have direct FPGA / Beelink access.** The output of this repo is a quantized TFLite model (e.g. `exports/fcnn_v2_residual_dataset_a_int8.tflite`); that's the handoff point. The `.vnnx` compile step happens in `~/projects/polarfire-hybrid-control/` via `ssh bee` against the VectorBlox SDK at `/c/Microchip/VectorBlox-SDK/` on Beelink (see `~/.claude/docs/fleet.md` § Beelink & FPGA Toolchain). If a Bundle item asks this repo to produce a `.vnnx`, the correct action is to confirm the TFLite precursor is in `exports/` and hand off — not to attempt the compile here.

## Quick start

```bash
pip install -e ".[dev]"       # install in dev mode
make test                     # all tests
```

Production architecture: **OdmrFCNN** (`models/fcnn.py`). Datasets: `./data/golden/`, `./data/production_50k/` (gitignored symlinks). Full layout, data, test targets, and dependency pins: `docs/claude/repo-layout.md`.

## VectorBlox Constraints

These constraints are enforced by `validation/ops_guard.py` — run it BEFORE training at scale:

- **No Conv1d** — use Conv2d with (1,k) kernels on reshaped input
- **No BatchNorm** — use ReLU/ReLU6 directly
- **No dynamic shapes** — all tensor dimensions must be static at export time
- **Allowed ops**: Conv2d, Linear, ReLU, ReLU6, Add, Mean, AdaptiveAvgPool2d, Reshape, Permute, Unsqueeze, Slice, GetItem
- **Quantization**: Symmetric INT8, zero_point=0 for activations, per-channel scales for weights

## Compute

Use device='cuda' for all training runs. CPU-only is acceptable for tiny models (<1000 params) but anything larger should use GPU.

## Modeling rule — scalar residual, not 3D vector

- **Scalar residual, not 3D vector**: CW-ODMR spectra at target field strengths (20-70 µT) cannot resolve B-field direction due to quantum degeneracy. All production models predict scalar ΔB residual corrections, not 3D vectors. The config default `output_dim: 3` is legacy — experiments override to `output_dim: 1`.

Deployed INT8 claim: use about 5% clamped reduction vs PID; do not call this bit-exact INT8 equivalence. Measured numbers and the harness path: `docs/claude/architecture.md` § Evaluation.

## Commit Messages
- Describe what changed technically, not how it was built
- Never reference specific development tools, assistants, or AI in commit messages
- Example good: "Fix FCNN export shape mismatch for V250 target"
- Example bad: "Refactor QAT pipeline"

## Cross-lane dispatch inbox (2026-08-19)

At session start check the inbox: `~/projects/tychon-verification-workbench/tvw/scripts/dispatch.sh list --lane odmr-edge-ml`
(equivalently `ls .dispatch/inbox/ 2>/dev/null`). If a dispatch is queued: `show <id>`, do
the work, then `ack <id> "<evidence receipt: changed paths, commits, checks run>"`.
Dispatches are file-based (sha256-verified) to defeat paste truncation; Jason may also
relay a one-liner pointing here. Strategic next-steps still go UP to TVW, never sideways.

## Context map — read on demand

| Situation | Read |
|---|---|
| Directory layout, datasets, make targets, dependency versions | `docs/claude/repo-layout.md` |
| Model architectures, training pipeline, evaluation modules + measured INT8 numbers, export chain, cross-repo data flow | `docs/claude/architecture.md` |
| Export failures, torch deprecation warnings, output_dim legacy default | `docs/claude/gotchas.md` |
