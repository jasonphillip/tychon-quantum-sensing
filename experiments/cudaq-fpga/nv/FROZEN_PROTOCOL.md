# Frozen protocol

Prepared 2026-10-17 before generating or evaluating this track's data.

Use the fixed `config.json`. Do not tune on evaluation outcomes. Record any failed gate unchanged.
Use 96 newly drawn detunings and four independent readouts per detuning. Split by physical configuration, 48/16/32.
Use no previous Ramsey data. Parameters, noise, and splits have separate fresh random streams.

The model contains one selected NV electron transition and one 13C spin-1/2. It retains secular anisotropic hyperfine coupling.
It includes finite rectangular preparation and readout pulses. It is a closed four-level effective model.
All numeric values are benchmark assumptions. Only detuning varies; all nuisance parameters are known exactly.
The initial electron is |0>, and the nuclear spin is maximally mixed. Each repetition resets both states independently.

Validate Hermiticity, density trace, positivity, zero coupling, finite-pulse Bloch evolution, and the ideal-pulse Ramsey limit.
Compare eigendecomposition with independently integrated density-matrix commutators at the frozen probability tolerance.
CUDA-Q checks use the same four-dimensional basis, piecewise constant pulses, and fixed RK4 substeps.
CUDA-Q must run on a GPU. Missing hardware is a gap, never a CPU substitution.

The baseline searches a fixed 121-template detuning grid, then refines within the winning adjacent interval.
Refinement uses bounded golden-section minimization. It cannot change model parameters or use true labels.
The host FPGA reference uses the same grid with signed 16-bit inputs and templates, 14 fractional bits.
Squared differences use signed 64-bit intermediates and an unsigned 64-bit accumulator. Ties select the smallest template index.
Input clipping is reported. No neural network is trained.

Report held-out detuning MAE, 95th percentile absolute error, constant-baseline error, and quantization degradation.
The exploratory utility gates are in config.json. They are synthetic benchmark goals, not product requirements.
Also report template bytes, arithmetic counts, worst-case accumulator bound, and C/Python agreement.
No FPGA timing, synthesis, power, radiation, real-sensor performance, GPU speedup, or user demand claim follows.
