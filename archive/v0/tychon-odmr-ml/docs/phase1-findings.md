# Phase 1 Finding: CW-ODMR Spectra Cannot Resolve B-Field Direction

## Summary

Diagnostic experiments on the 50K production dataset proved that 3D B-field vector prediction from CW-ODMR spectra is impossible at the target field strengths (20-70 µT). This is a fundamental quantum degeneracy, not a training failure.

## Evidence

### Experiment: Architecture Comparison (2026-04-01)

Trained both MLP (8,643 params) and FCNN (3,299 params) on 40K spectra for 100 epochs with QAT. Both converged to **57.3° angular error** — exactly the mean angular distance from the pole of a uniform hemispherical distribution. This is the mathematical constant for a model outputting a single constant direction.

### Diagnostic 1: Sign Ambiguity

Compared spectra for B-field vectors and their negatives (-B):
- Correlation between B and -B spectra: **0.888**
- Correlation between random pairs: **0.884**
- **Opposite B-field pairs are statistically indistinguishable from random pairs.**

The directional Zeeman splitting (~1.4 MHz at 50 µT) is unresolvable within the ~2 MHz linewidth and corruption noise (P1 concentration, temperature, B1 gradient, MW power drift).

### Diagnostic 2: Magnitude-Only

MLP trained to predict scalar |B| achieved 10.94 µT MAE vs 12.52 µT naive baseline (13% improvement). The model extracts some physics, but direction is unrecoverable.

### Diagnostic 3: Unit Vectors

Training with pure cosine loss on unit-vector labels:
- With sign folding (hemisphere): 57.33° — stuck at hemisphere pole
- Without sign folding (full sphere): 90.14° — predicting near-zero vector

## Physics Explanation

The NV center Hamiltonian is H = D·Sz² + γ_NV·(B·S). Under B → -B, the Zeeman term flips sign, producing slightly different spectra. However, at 20-70 µT (splitting 1.1-3.9 MHz), this difference is swamped by:

1. **Linewidth**: ~2 MHz broadening from P1 bath and temperature
2. **B1 gradient**: 5-30% MW inhomogeneity
3. **MW drift**: ±5% temporal power variation (cascaded OU noise)

Published NV magnetometer groups (SBQuantum, Lockheed Martin, Walsworth Lab) never extract 3D vectors from raw zero-bias CW-ODMR spectra. They use **permanent DC bias fields** (2-5 mT) to break degeneracy and separate the 8 NV hyperfine transitions.

## Reformulation: Scalar Residual Correction

### New Task

CNN as a PID error de-embedder: corrects the scalar line-pulling error of a derivative zero-crossing PID frequency lock.

- **Input**: 2-channel [spectrum, PID anchor Gaussian]
- **Output**: ΔB = |B_true| - B_PID (scalar, µT)
- **Loss**: Huber on scalar residual
- **PID baseline MAE**: ~15 µT on production dataset

### Why This Works

The CNN detects asymmetric lineshape distortion from the full 100-point context. The PID tracks a local derivative zero-crossing and is blind to global lineshape structure. Overlapping NV hyperfine transitions pull the PID's lock point away from the true resonance frequency as a function of:

1. P1 concentration (determines linewidth/overlap)
2. Temperature (shifts ZFS parameter D)
3. B1 gradient (creates inhomogeneous broadening)
4. MW power drift (modulates contrast)

These are exactly the corruption parameters in the production dataset. The CNN learns the correction as a function of the full spectral context.

### INT8 Resolution Advantage

Predicting ±35 µT residual (instead of absolute 0-100 µT) with INT8 gives:
- Residual: 70 µT range / 256 levels = **0.27 µT/bit** resolution
- Absolute: 100 µT range / 256 levels = 0.39 µT/bit resolution
- **1.4× better quantization resolution**

## Impact on Phase 1 Deliverables

- **Deliverable 2** (trained INT8 NN): Reframed as scalar residual corrector, not 3D vector estimator
- **Heading Error KPP** (>50% reduction): Achievable if CNN residual MAE < 7.5 µT (half of PID's 15 µT)
- **Asymmetric Inversion Bias KPP** (<5 nT): Requires subsequent bias field experiments in Phase 2
- **Architecture**: Both MLP and FCNN remain V250-compatible; only the task changes
