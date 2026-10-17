# Frozen v2 mismatch and measurement-budget protocol

Prepared 2026-10-17 before generating v2 data or evaluating its final split.
Keep all v1 data, generated ROM, inference code, and HLS interfaces unchanged.
The v1 final split remains consumed. This experiment uses new independent random streams.

## Questions and data

Measure how fixed-template frequency estimation changes under lower repetition counts and unobserved calibration drift.
Use 96 new detunings with 32 development and 64 final configurations, two readout realizations each.
Each configuration shares one group assignment across every budget and scenario. Final data cannot select methods or thresholds.
No fitting or model selection uses development data in this bounded run; it is preserved for future diagnostics.

Four budgets: 100, 500, 2,000, and 20,000 repetitions at each of four phases and 64 delays.
Total repetitions per input are 25,600; 128,000; 512,000; and 5,120,000.
These are candidate measurement budgets, not measured sensor operating modes.
Use the same fresh physical configurations across budgets, with independently seeded detection noise.
Paired observations do not increase the number of independent physical configurations.

Scenarios are matched, optical drift, control drift, and combined mismatch.
Optical drift changes collection gain, bright/dark contrast, background, and collection gain between phase acquisitions.
Control drift changes microwave amplitude by up to 10% and readout phase by up to six degrees.
Pulse durations stay fixed at their nominal 1/6 microsecond. Amplitude errors therefore remain actual pulse-area errors.
Combined mismatch adds up to 10% hyperfine changes, 2% nuclear-frequency changes, and free-evolution dephasing over 6–15 microseconds.
All ranges are assumptions, not fitted experimental variability.

The dephasing map multiplies electron off-diagonal blocks by exp(-t/T).
It is the exact channel for electron sigma-z Markovian dephasing during free evolution, which commutes with the free Hamiltonian.
During finite pulses, dephasing is absent by assumption. No optical-cycle simulation or sensor validation is implied.
Check this map against independent Lindblad RK4 integration before final evaluation.

## Frozen estimators and reported evidence

1. Existing integer v1 ROM and unchanged quadrature-major ABI.
2. Existing nominal floating-point template grid, then continuous detuning-only refinement.
3. Classical nominal-model fit with a profiled shared positive gain and separate quadrature offsets.
   Gain is bounded to [0.1,2]. Offsets and gain come only from the observed features, never nuisance truth.
   Grid search and bounded refinement are fixed before final evaluation.
4. Development-mean constant comparator. This comparator is labeled as such.

Each feature uses the known repetition count and nominal bright/dark contrast of 0.14 photons.
Quantization stays signed 16-bit with 14 fractional bits and explicit saturation reporting.
Do not silently correct features with true gain, true contrast, true coupling, or true pulse errors.
Report nominal/mismatched error distributions, bootstrap intervals clustered by physical configuration, clipping, and floating/integer disagreement.
Report every frozen utility gate even if it fails. A utility failure is not an integer hardware-correctness failure.

Use exact Python integer and compiled C comparisons on every final input and deterministic stress vectors.
Export all final vectors plus interface boundaries for board replay.
Export `inputs_i16.bin`, `expected_indices_u16.bin`, and `expected_scores_u64.bin` with little-endian encoding.
The manifest records dimensions, source hashes, vector IDs, clipping flags, and exact array hashes.
Hardware input order and the original ROM remain unchanged.

## Timing interpretation and sources

NIST's accepted manuscript for McMichael et al., *Sequential Bayesian experiment design for adaptive Ramsey sequence measurements*,
dated 13 September 2021, section III.A, describes approximately 3 microseconds of laser illumination and 1 microsecond of relaxation.
Source: https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=932411 (DOI 10.1063/5.0055630).
We use that four-microsecond optical/relaxation illustration plus this benchmark's two finite pulses and its actual delay schedule.
This gives 0.1621, 0.8107, 3.2427, and 32.4267 modeled seconds per input.
Actual initialization, extra readouts, drift, transport, and apparatus deadtime may change these values.
This timing model prevents an inference-latency result from being confused with sensor update rate.
