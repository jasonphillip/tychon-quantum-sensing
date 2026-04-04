# Design Decisions

Architectural choices and their rationale for the odmr-edge-ml system.
This document is intended as a citable reference for technical reports.

---

## 1. Memoryless Single-Frame Architecture for Drift Correction

### The question

> "If the FCNN is stateless with no recurrent memory, how does a single-frame
> network correct long-term temporal drift out to 2,700 seconds?"

### Answer

The FCNN operates as a memoryless spectral-to-residual corrector by design.
Temporal drift tracking is handled entirely by the upstream PID lock loop,
which maintains state across successive ODMR acquisitions. The CNN's role is
narrower: given a single CW-ODMR spectrum and the PID's current lock-point
estimate, it predicts the instantaneous systematic bias that the PID cannot
resolve -- primarily spectral asymmetries from Fano interference,
temperature-dependent linewidth distortion, and off-axis field components.

Because these biases are functions of the current spectral shape (not its
history), a single-frame correction is sufficient. The PID closes the
temporal loop; the CNN sharpens the spatial/spectral correction at each
timestep.

### System-level architecture

```
                 Temporal tracking          Instantaneous correction
                 ================          ========================

  ODMR spectrum ──> PID lock loop ──> B_PID ──> FCNN ──> delta_B
       |            (stateful,              (stateless,
       |             maintains               single-frame,
       |             lock-point)             spectral bias only)
       |                                         |
       v                                         v
  Next acquisition <──── B_corrected = B_PID + delta_B
```

### Why recurrent layers are unnecessary

1. **Separation of concerns**: The PID controller tracks the temporal
   evolution of the magnetic field (drift, orbital modulation, thermal
   transients). The neural network corrects the *spatial/spectral* bias
   that the PID's derivative zero-crossing algorithm cannot capture.

2. **Physics grounding**: The systematic biases corrected by the FCNN --
   Fano asymmetry from B1 gradients, linewidth broadening from temperature,
   spectral distortion from off-axis fields -- are all deterministic
   functions of the *current* spectrum. They do not depend on previous
   spectra.

3. **Hardware constraints**: The VectorBlox V250 FPGA target does not
   support stateful operators (LSTM, GRU, attention). All operations must
   be static and expressible as Conv2d, ReLU, Add, and Mean. Even if
   recurrent layers were beneficial, they could not be deployed.

4. **2-channel input provides spatial context**: The FCNN's optional
   second input channel is a Gaussian anchor centered at the PID lock-point
   bin. This gives the network "where the PID thinks the dip is" without
   requiring temporal history -- it is spatial attention within a single
   snapshot, not a memory mechanism.

### What the training data looks like

Each training sample is an independent snapshot: a 100-point CW-ODMR
spectrum paired with a scalar residual label (delta_B = |B_true| - B_PID).
There are no trajectory IDs, timestamps, or sequence positions in the
dataset. The upstream simulator generates spectra with random corruption
parameters (temperature, P1 concentration, B1 gradient, off-axis field)
drawn independently per sample.

This design is intentional: the network must generalize across the full
corruption parameter space at each instant, not memorize temporal patterns
from a specific trajectory.

---

## 2. Scalar Residual vs. 3D Vector Output

CW-ODMR spectra at the target field strengths (20-70 uT) cannot resolve
B-field direction due to quantum degeneracy: +B and -B produce identical
spectra. All production models therefore predict a scalar residual
correction (delta_B = |B_true| - B_PID), not a 3D vector.

The config default `output_dim: 3` is legacy from early development.
Production experiments override to `output_dim: 1`.

---

## 3. No Conv1d -- Conv2d with (1,k) Kernels

The VectorBlox V250 TFLite runtime does not support the CONV_1D operator.
All 1D convolutions are implemented as Conv2d with (1, k) kernels on input
reshaped to (batch, channels, 1, length). This is validated by ops_guard
before training and before export.

---

## 4. Fully Convolutional Head (No Linear Layers in FCNN)

The production FCNN architecture uses no Linear layers. The final Conv2d
has a kernel width matching the remaining spatial dimension, collapsing it
to (batch, output_dim, 1, 1). This avoids the Flatten op that some TFLite
runtimes handle inconsistently and ensures the entire model is expressible
as a pure convolutional graph.
