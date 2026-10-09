# 02 — Approach + testbed spec

## Recommended ML approach

A **physics-informed sequential tracker with explicit data association**, designed
**deployable-first on an explicit V250/MSS execution partition** (this is the canonical design;
it supersedes the earlier "KalmanNet + attention, all on the NPU" reading, which predated mirroring
the V250 ops-guard — the guard bans `matmul`/`softmax` (attention) and `sigmoid`/`tanh` (GRU/LSTM
gates), so those cannot live on the NPU):

- **Recurrent core — KalmanNet-style.** The NV measurement model is *known* (Zeeman/Hamiltonian,
  γ ≈ 28 kHz/µT, the 8×3 geometry); keep that physics in the state/measurement model and **learn
  only the gain and the association where the analytics break — the collision.** Two variants
  share one interface: a **deployable-first ReLU-recurrent cell** (first-class; linear+relu+add)
  and a **research gated cell** (GRU-style, flagged off-NPU). Increment 2 trains both to measure
  what gating buys.
- **Association head — two variants, one interface.** A **deployable-first linear-score head**
  (linear+relu cost, hard assignment computed off-graph) is first-class; an **attention/transformer
  head** (MT3 / DeepDA-style soft association) is the research variant (softmax/matmul → flagged
  off-NPU). Both preserve line→axis identity through a crossing.
- **The fingerprint** that resolves "which line is which" on the far side of a crossing: each
  axis's **¹⁴N hyperfine triplet, contrast, and known Zeeman slope** (sign + magnitude of
  df/dB). Direct analogue: speaker-specific spectral signature in multi-pitch tracking through
  crossings (Liu & Wang 2017; US6453284).
- **Output:** the 4 axis-projections (Σ Bᵢ = 0) → closed-form **BLUE A-matrix** → 3D vector +
  covariance. Geometry stays exact/analytic (a fixed, non-learned linear map); the net only
  tracks/associates.

### Execution partition (V250 / MSS) — the resolution of the ops-guard tension

The PolarFire SoC splits work between the V250 NPU (strict INT8, op-whitelisted) and the MSS
RISC-V host (full float, no whitelist) — the same split `polarfire-hybrid-control` already uses.
Tag every block accordingly:

- **V250-targeted (ops-guarded):** *only* the per-frame feedforward **feature/peak extractor**
  (Conv2d (1,k) + ReLU + Linear, INT8). It must pass the ops-guard before training at scale.
- **host/MSS (unconstrained):** the **recurrence**, the **association/assignment**, and the
  **BLUE decode** (a fixed Linear). `softmax`/`matmul`/`sigmoid`/`tanh` are a non-issue here
  because they never reach the NPU graph.

The ops-guard test is the deployability contract: the V250 extractor (and the deployable-first
core/association) must pass; the research attention/gated variants are *expected* to be flagged
(they are host blocks). Favor a *small* recurrent core — capacity was never the bottleneck.

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
   resonance positions + collision labels (HDF5). The dataset contract with the time axis +
   collision/association labels is now formalized as **v1** in `03_data_contract.md` (the consumer
   side — validator, loader, synthetic fixtures — is built here against that spec).

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
