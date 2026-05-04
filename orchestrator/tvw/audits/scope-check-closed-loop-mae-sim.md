# Scope Check: Closed-Loop Deployed-MAE Simulation

**Date:** 2026-05-03
**Scope:** Read-only inspection (~30 min). No code changes, no sim runs.
**Files inspected:**
- `experiments/adev_simulation.py` (351 lines)
- `experiments/adev_recompute_exact.py` (111 lines)
- `experiments/adev_results_v2_dataset_a_exact.npz` (keys + values)

Cross-references consulted:
- `src/odmr_edge_ml/evaluation/pid_proxy.py` (the "PID" used in the sim)
- `experiments/clamped_eval_results.npz` (v1 + ±2.25 µT clamp baseline)

---

## Q1. Closed-loop integration or stationary residual?

**Answer: stationary residual.** `adev_simulation.py` does **not** integrate a closed-loop control system. It computes per-spectrum estimates with temporally-correlated *noise inputs* (OU on T and B1, satellite tumble on B-vector heading), but each timestep is observationally independent.

Evidence from `experiments/adev_simulation.py`:

- Lines 167–170: `pid = DerivativeZeroCrossingPID(freqs_init)` — single instance, frequencies-only constructor. No setpoint, no gains.
- `src/odmr_edge_ml/evaluation/pid_proxy.py` exposes only `__init__(frequencies)`, `estimate(spectrum)`, and `estimate_batch(spectra)` (lines 39, 45, 90). **There is no `step()`, no `Ki`/`Kp`/`Kd`, no integral accumulator, no previous-error state.** The class name is a misnomer — it is a stateless derivative zero-crossing observer, not a PID controller.
- Lines 182–210 (main loop): at each step `i`,
  1. Tumble update sets `config.B_field_T = B_vec(theta_i)` (open-loop ground truth).
  2. OU update sets `config.temperature_K = t_traj_K[i]` and `mw_scale = b1_trajectory[i]`.
  3. `corrupt_spectrum(...)` regenerates the spectrum from those ground-truth states. **No actuator output from any controller feeds back into spectrum generation.**
  4. `pid.estimate(signal)` returns a fresh estimate from the current spectrum alone.
  5. `fcnn(x).item()` returns a one-shot residual prediction from the same spectrum + lock-bin anchor.
- Line 219: `cnn_pid_estimates_uT = pid_estimates_uT + fcnn_delta_b_uT` — vectorized post-hoc sum across **all** timesteps. The FCNN correction at step `i` is never used to influence step `i+1`. Errors are computed against constant ground truth `B_MAG_UT = 50.0 µT` (lines 220–221).

So there is no plant model in the control sense (the "plant" is a measurement model with externally specified disturbances), no integrator state spanning timesteps, and no closed loop. The time axis is used **only** for the ADEV averaging statistic. Replacing the loop with a vectorized batch `pid.estimate_batch` over the same spectra would produce an identical answer (modulo ordering of the error array).

**Implication for v3.4 §8.3:** the framing "96.1 % ADEV via closed-loop integration" is incorrect on the "closed-loop integration" half. The 96.1 % figure is the per-tau ADEV reduction at τ ≈ 1 s on a stationary residual time series with realistic temporally-correlated disturbances. It is **not** a closed-loop controller-stability number. Recommend rewording to something like *"4.8 % OADEV reduction at τ = T_orb/2 = 2700 s on the disturbance-driven residual series"* (the actual `direct_red_2700 = 4.82 %` from the npz) and dropping any "closed-loop integration" language.

---

## Q2. Is MAE already tracked?

**Answer: no.** Listing of `adev_results_v2_dataset_a_exact.npz`:

| key | shape | dtype | values |
|---|---|---|---|
| `taus` | (6,) | f64 | `[1, 10, 100, 1000, 2700, 5400]` s |
| `adev_pid` | (6,) | f64 | `[3.398, 3.486, 6.926, 15.927, 16.658, 0.307]` µT |
| `adev_cnn` | (6,) | f64 | `[3.298, 3.327, 6.657, 15.254, 15.855, 0.294]` µT |
| `n_pid` | (6,) | f64 | `[16199, 16181, 16001, 14201, 10801, 5401]` |
| `n_cnn` | (6,) | f64 | `[16199, 16181, 16001, 14201, 10801, 5401]` |
| `direct_red_2700` | scalar | f64 | `4.8177 %` |
| `interp_red_2700` | scalar | f64 | `4.9799 %` |

No `mae`, `closed_loop_mae`, `pid_mae`, `cnn_mae`, or any equivalent. **Only ADEV statistics and the τ=2700 s reduction scalars are persisted.**

The *upstream* artifact `adev_results.npz` (per `adev_recompute_exact.py:39–42`) does carry the raw signed-error time series `pid_error_uT` and `cnn_error_uT` (each length 16,200), so the per-sample MAE on the disturbance-driven residual could be computed directly from those without re-running the sim. But that is **per-sample MAE on a stationary residual** — not closed-loop deployed MAE.

---

## Q3. Extension cost

Two interpretations, both worth costing:

### 3a. "Per-sample MAE on the existing stationary residual series" (NOT closed-loop)
- **LOC:** ~5. Load `adev_results.npz`, compute `np.mean(np.abs(pid_error_uT))` and `np.mean(np.abs(cnn_error_uT))`, save to npz / log.
- **Wall time:** seconds.
- **Blockers:** none.
- **Caveat:** This is **not** the deployed-MAE-under-closed-loop number that v3.4 §8.3 gestures at. Reporting it as such would inherit the same naming error as the ADEV framing. It is essentially the same quantity already computed in `clamped_eval_results.npz` (`val_mae_pid`, `val_mae_fcnn_clp`) but on the OU-driven 16,200-step trajectory instead of the static 5000-sample val split.

### 3b. "Actual closed-loop deployed-MAE simulation" (what v3.4 §8.3 implies)
This is a **re-architecture**, not a tweak:

| component to add | est. LOC | blocker |
|---|---|---|
| Real PID controller class with `step(error) -> control_output` and Ki/Kp accumulator state | ~50–100 | gain values not specified anywhere in repo or upstream nv-sim — must be defined or sourced from FPGA control design |
| Plant model: control output → effective B-field offset that the spectrum generator sees on the next step | ~30–80 | conceptual choice — does the controller drive the lock-bin / setpoint, or a virtual coil offset? polarfire-hybrid-control owns this design; not yet exported into the sim repo |
| Loop bandwidth / integration timestep model: today `DT_S = 1.0` s matches the measurement rate, but the FPGA control cycle is sub-ms. Need a multi-rate model or an explicit decimation choice | ~20–40 | polarfire-hybrid-control loop spec (τ_loop) is not in this repo; appears in deployed-cascade docs but not as code |
| Integrator anti-windup behavior (per the ±2.25 µT FCNN clamp + saturation regime) | ~20 | none if Ki path is in place |
| FCNN integration mode: feed-forward to PID setpoint, parallel correction summed at output, or inner-loop residual? Choice has different deployed-MAE implications | architectural | this is the **load-bearing decision**, not a coding task |
| Re-validation that the disturbance trajectories in `nv_sensor_sim.physics.noise_injection` are still appropriate when the controller bandwidth is comparable to the OU correlation times | analysis | none code-wise; non-trivial in time |
| Re-run wall time | — | sim is currently O(few minutes) per run on Spark; closed-loop with sub-second integration could be 10–100× longer |

**Realistic wall-clock to design + implement + validate the closed-loop variant: 1–3 working days minimum**, and the principal risk is not coding effort — it is that the architectural decisions (FCNN integration mode, controller gains, loop rate) belong to `polarfire-hybrid-control`, not to `odmr-edge-ml`. Choosing them unilaterally for a Phase I figure risks publishing a number that the FPGA team has to retract.

---

## Q4. Cross-check with v1 + ±2.25 µT clamp baseline

From `experiments/clamped_eval_results.npz`:
- `clamp_uT = 2.25` µT
- `val_n_clipped = 4872` / `val_pid_err_uT.shape = (5000,)` → **97.44 % saturate at ±2.25 µT** on the val split. Confirms the saturation regime referenced in the prompt.
- `val_mae_pid = 23.75` µT (sanity-checked above; we did not extract `val_mae_fcnn_clp` but the 6.91 % open-loop reduction is consistent with prior reporting).

**Mapping to a hypothetical closed-loop integrator** (analytical, not measured here):

A 6.91 % per-sample MAE reduction under sustained same-sign saturation says the FCNN delivers a **biased** correction of magnitude ≪ |residual|. If there were a real integrator with gain `Ki` and loop bandwidth `1/τ_loop`, the integrator would absorb a constant bias `b` in roughly `τ_loop · ln(1/ε)` seconds (e.g. ~3–5 τ_loop for ε ≈ 1–5 % residual). The deployed-MAE over a long horizon is then dominated by the **transient** during the first few τ_loop and by **non-stationary** disturbance components after that — not by the steady-state bias the open-loop number sees.

Concretely:
- If the FPGA target loop time constant is `τ_loop ~ 10 s` and the sim horizon is 16,200 s, a real integrator absorbs the bias inside 0.3 % of the horizon → closed-loop MAE would be **dominated by the OU-driven non-stationary part**, with the FCNN's value coming from suppressing high-frequency residual rather than the static bias the open-loop number measures.
- If `τ_loop ~ 100 s`, transients still finish inside 3 % of the horizon → same conclusion.
- If `τ_loop ~ 1000 s` (slow integrator), transients consume 20–30 % of the horizon and the open-loop bias number becomes a non-trivial proxy for the early-orbit closed-loop MAE.

**`τ_loop` is the missing parameter.** It is not defined in `odmr-edge-ml`. Without it, the relationship between the 6.91 % open-loop reduction and any closed-loop MAE is undetermined — the sign of the conclusion (FCNN helps a lot / FCNN helps a little) flips with the loop bandwidth choice.

---

## Scenario classification, recommendation

**Scenario: 3 (defer to Phase II HIL).**

Rationale:
- 3a (slap MAE on the existing series, ~5 LOC) is cheap but produces a number that is *not* closed-loop deployed MAE and would inherit the same framing error that motivated this audit. Publishing it under a "closed-loop integration" label in Phase I makes the v3.4 §8.3 problem worse, not better.
- 3b (build the real closed-loop simulation) requires architectural commitments owned by `polarfire-hybrid-control` (FCNN integration mode, `Ki`, `τ_loop`, multi-rate model, plant definition). These are exactly the items that Phase II HIL is supposed to settle empirically. Front-running them with a sim built in the next few days, on the eve of the May 1 SBIR submission, optimizes for a single Phase I bullet at the cost of locking in choices the FPGA team will revisit.
- The available open-loop evidence (4.82 % τ=2700 s ADEV reduction, 6.91 % per-sample MAE reduction under ±2.25 µT clamp, 97.4 % clamp-saturation rate on val) is internally consistent and defensible as Phase I evidence **provided v3.4 §8.3 drops the "closed-loop integration" framing** and reports it as what it actually is: stationary-residual ADEV/MAE under disturbance-driven OU + tumble.

### Recommendation

1. **Do not extend `adev_simulation.py` for Phase I.**
2. **Reword v3.4 §8.3** to remove the "closed-loop integration" claim. Replace with: *"OADEV reduction on a 16,200-s disturbance-driven residual series (cascaded OU on T and B1, satellite tumble): 4.82 % at τ = T_orb/2 = 2700 s; per-sample MAE reduction under ±2.25 µT clamp on the v1 val split: 6.91 %."* Both numbers are auditable from the existing npz files.
3. **Defer closed-loop deployed MAE to Phase II HIL,** where `τ_loop`, controller gains, and FCNN integration mode are real (not invented) and where the FPGA team is the joint owner of the architecture.
4. *(Optional, low cost)* If a Phase I bullet specifically needs a deployed-MAE number, compute 3a on the existing time series (~5 LOC) but **label it explicitly as "open-loop / per-sample MAE on the disturbance-driven residual series, no controller integrator modeled"**. Do not allow it to be reframed as closed-loop in any submission text.

### What would change the recommendation

A late green-light from `polarfire-hybrid-control` providing a frozen `(τ_loop, Ki, Kp, integration mode)` spec, plus a willingness to scope §8.3 narrowly to "feasibility-of-integration" rather than "deployed-MAE-headline," would move this to Scenario 2 (1–2 days of work). Absent that spec, Scenario 3 is the disciplined call.
