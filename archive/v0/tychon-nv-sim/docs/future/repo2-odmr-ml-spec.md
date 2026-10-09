# Repo 2 Specification — `tychon-odmr-ml`

*Extracted from Section 6 of the architecture decisions document.*

**Status:** DO NOT BUILD until Repo 1 produces stable dataset manifests. Target: ~Day 20-25.

## Purpose

Model training, INT8 quantization-aware training, export, and evaluation ONLY. Consumes dataset manifests from `tychon-nv-sim`. Produces model artifact bundles for `tychon-polarfire-control`. Does not own the simulator.

Maps to **Deliverable 2**: "Trained and INT8-Quantized Neural Network" (Task 2, Days 30-75).

## The Core Reframe

The neural network is NOT a noise filter. It is a nonlinear Hamiltonian inverter solving three problems a PID cannot:

1. **Heading Error Correction:** At 50 µT transverse field, second-order perturbation creates ~37 nT systematic bias. CNN maps ODMR features + temperature to true 3D field vector. Target: >85% reduction (report >50% KPP).

2. **Asymmetric Lineshape Inversion:** Symmetric Voigt fit on skewed profile creates ~500-1,500 nT systematic bias. INT8 CNN maps shape features to correct field vector. Deterministic O(1) in <0.1 ms vs classical 10-50 ms.

3. **MIMO Degeneracy Tracking:** Four NV orientations create up to 8 ODMR resonances. At symmetry orientations, PID channels cross-talk. CNN processes full spectrum as MIMO estimator.

## Dual Architecture Strategy

**Architecture A (MLP, primary):** 2-3 hidden layers, 128-256 neurons. Input: ~100-point ODMR sweep. Output: B-field vector. FULLY_CONNECTED + RELU only. <0.1 ms on PolarFire.

**Architecture B (1D-CNN, secondary):** 2-4 conv layers, depthwise-separable, residual connections, global average pooling. Target <1,000 params post-pruning.

## VectorBlox SDK 3.0 Constraints

- Allowed ops: CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, RELU/RELU6, ADD, MEAN
- No separate CONV_1D — implement as CONV_2D with (1×k) kernels
- Export chain: PyTorch → ONNX → TFLite INT8 → `vnnx_compile` → `.vnnx`
- Target board: PolarFire SoC Video Kit (not RT PolarFire)

## Training Pipeline

1. Generate training data (Repo 1 with coupled noise + asymmetric corruption)
2. Train BOTH architectures in PyTorch on DGX Spark
3. INT8 QAT via TorchAO: `export` → `prepare_qat_pt2e` → train → `convert_pt2e`
4. Export: PyTorch → ONNX → TFLite INT8 → VNNX binary
5. Validate with VectorBlox bit-accurate simulator
6. Select architecture that compiles AND generalizes best

## Five-Metric Evaluation Stack

| # | Metric | What It Measures | KPP |
|---|---|---|---|
| 1 | Spherical Heading Error Profile | Peak-to-peak vector error across 360° rotation in 50 µT field | >50% heading error reduction |
| 2 | Asymmetric Inversion Bias | Absolute vector bias on skewed spectra vs ground truth | <5 nT bias |
| 3 | Frequency-Partitioned PSD | Noise in sub-0.1 Hz drift band AND >1 Hz white noise band | >10× suppression (drift) |
| 4 | Allan Deviation (ADEV) | Stability across timescales; flattened drift at τ >5 sec | Complements PSD |
| 5 | MagNav.jl Positioning RMSE | Navigation error using SGL 2020 flight data | System-level |

## Data Contract

See [../dataset-contract.md](../dataset-contract.md) for the full manifest specification that this repo consumes.

## File Tree

```
tychon-odmr-ml/
  src/tychon_odmr_ml/
    data/          — contracts, loaders, transforms
    models/        — mlp, cnn1d, vectorblox_compat, pruning
    training/      — loop, losses, checkpoints, seeds
    quantization/  — torchao_qat, calibration
    export/        — onnx, tflite, vnnx, artifact_bundle
    evaluation/    — heading_error, asymmetry_bias, psd, adev, magnav_bridge
    baselines/     — pid_proxy
    validation/    — ops_guard, golden_vectors
  tests/
    smoke/         — CPU-only tiny train+eval
    unit/          — shapes, contracts, ops guard
    integration/   — full pipeline, export bundle
    contract/      — Repo 1 manifest compatibility
```
