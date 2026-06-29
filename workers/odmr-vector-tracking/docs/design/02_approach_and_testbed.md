# 02 — Approach + testbed spec

## Recommended ML approach

A **physics-informed sequential tracker with explicit data association**:

- **Backbone — KalmanNet-style recurrent filter** (arXiv:2107.10043). The NV measurement model is
  *known* (Zeeman/Hamiltonian, γ ≈ 28 kHz/µT, the 8×3 geometry); keep that physics in the
  state/measurement model and **learn only the gain and the association where the analytics break
  — the collision.** A black box would waste the known structure.
- **Association head — attention/transformer** over the per-frame peak candidates (MT3 /
  DeepDA-style soft association), trained to preserve line→axis identity through a crossing.
- **The fingerprint** that resolves "which line is which" on the far side of a crossing: each
  axis's **¹⁴N hyperfine triplet, contrast, and known Zeeman slope** (sign + magnitude of
  df/dB). Direct analogue: speaker-specific spectral signature in multi-pitch tracking through
  crossings (Liu & Wang 2017; US6453284).
- **Output:** the 4 axis-projections (Σ Bᵢ = 0) → closed-form **BLUE A-matrix** → 3D vector +
  covariance. Keep the geometry exact and analytic; let the net handle only tracking/association.
- **Deployability:** the model must stay V250-compatible (Conv2d (1,k), no BatchNorm, static
  shapes, INT8) so it can hand off to `polarfire-hybrid-control` as TFLite. Favor a *small*
  recurrent core — capacity was never the static-regime bottleneck.

## Testbed spec (what to build, and where)

**Reuse (already in `nv-sensor-sim`):** `physics/lineshape.py` per-axis resonance-frequency
computation + `nv_geometry_matrix()` (8×3 BLUE); the `multi_axis_mode` spectrum generator; the
bias config (`bias_B0_T`, `bias_direction_uvw`, Path A magnet / Path B flux-concentrator fields).

**Gap (build in `nv-sensor-sim`, since physics lives there):** there is **no time-series path**
where the field sweeps and resonances move/collide (the existing "OU trajectory" is per-spectrum
noise; `orbits/` emits B(t) columns but never renders spectra). Add a `tracking/` (or
`dynamics/`) module:
1. `field_trajectory.py` — generate **B(t)** designed to drive a clean inter-axis crossing (ramp
   magnitude/orientation); orbit-driven B(t) from `orbits/trajectory.py` wireable later.
2. `resonances.py` — compute the 8 line positions fᵢ(B(t)); **label collisions** when
   |fᵢ − fⱼ| < k·Γ.
3. `render.py` — per-timestep multi-axis ODMR spectra → (T × n_freq) series + ground-truth B(t) +
   resonance positions + collision labels (HDF5; extend the dataset contract with a time axis).

**Build in THIS repo:**
4. `tracking/classical.py` — lock-in + per-line PID with nearest-peak association (the
   Γ/2-limited baseline that **breaks at crossings**).
5. `tracking/learned.py` — the KalmanNet + association tracker above.
6. `evaluation/metrics.py` — **dynamic range** (max |B| before irrecoverable loss-of-lock),
   association accuracy through collisions, vector angular error(t), recovery time — all swept
   **vs bias magnitude** (the thesis = ML extends DR at fixed, smaller bias).

## Increment plan

- **Increment 1 (foundation, verifiable on its own):** items 1–4 + tests. Reproduce the *known
  classical failure* in our own sim — "the lock-in/PID baseline loses lock at the labeled
  crossing; dynamic range = X µT at bias Y." No ML yet. (Touches `nv-sensor-sim` for the
  generator and this repo for the baseline + metrics.)
- **Increment 2 (the thesis):** item 5 — the learned tracker; show it holds lock through the
  crossing and extends dynamic range at a fixed bias vs the Increment-1 baseline.
- **Increment 3 (deployment):** V250-compat export to TFLite → hand off to
  `polarfire-hybrid-control` for `vnnx_compile` and on-silicon evaluation alongside the PID.

## Guardrails

- Honest ceilings (ESLAC ~51 mT, GSLAC 102.4 mT) bound the claimable regime — see
  `00_problem.md`. Report dynamic range *relative to bias*, not as an absolute record.
- The learned block must be **bounded** when it reaches hardware (the `polarfire-hybrid-control`
  Simplex/clamp posture): the tracker informs association/estimation; it does not get unbounded
  actuator authority.
