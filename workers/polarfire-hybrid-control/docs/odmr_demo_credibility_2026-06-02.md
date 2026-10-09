# ODMR Demo Credibility Reference (2026-06-02)

What a credible NV-center / ODMR closed-loop frequency-tracking demo must *show*, the NN's defensible value-add over PID, the synthetic-trace gap, and a correction to the V250-latency premise. Grounds the domain credibility of the hybrid-control demo. Sourced from the local corpora (`odmr-pnt-nv-docs`, `tychon-physics`, `polarfire-control-corpus`, `tychon-docs`) + web (paid APIs: exa + tavily). Companion to `docs/whole_process_strategy_audit_2026-06-02.md` Risk 3/5.

**Verification legend:** **[V]** verified from a fetched/read source · **[NC]** needs-check (typically: measure on silicon).

---

## 1. Credibility checklist — numbers/behaviors a serious demo reports

| Metric | Credible target / anchor | Source |
|---|---|---|
| Sensitivity | ~1 nT/√Hz (good ensemble); µT/√Hz honest for compact CW-ODMR; 2–5 nT/√Hz typical portable | Clevenson 1802.09713; Qnami TN1; arXiv 2508.03237 |
| Dynamic-range gain (closed vs open loop) | ~3 orders / ~20× (open-loop limited to ½-linewidth ≈ few µT; closed-loop ~mT) | 1802.09713; 2402.15748 |
| Modulation / servo bandwidth | lock-in 1–20 kHz; **sensitivity rolls off >20 kHz** (NV response ceiling — acknowledge it) | 1802.09713; 2511.11561 |
| Tracking error → field error | quantify in physical units: ~30 kHz residual ≈ ~1,000 nT (γ ≈ 28 Hz/nT) | local DLOG-009 |
| Lock acquisition + steady state | zero steady-state error (integrator); re-lock after a step | 1802.09713 |
| Control-loop rate | **two regimes**: fast servo (kHz PID lock) vs slow estimator (Hz, full-spectrum fit; photon-shot-noise-limited, 0.4–2.5 s/update) | 1808.05580; photon-limited refs |
| Stability | Allan deviation with −½ slope on the error signal | 2402.15748; 1808.05580 |

**Key honesty point [V]:** the inner frequency-lock servo is genuinely kHz-class on an FPGA, but the *spectrum→parameter* estimation is ms–seconds, gated by **photon shot noise, not compute**. Claiming a multi-kHz *full-tracking* loop on a real diamond is a number a physicist reviewer would challenge.

---

## 2. The NN's defensible value-add over PID (ODMR-specific) [V]

PID locks to a single zero-crossing; it structurally cannot do these:
- **Feedforward drift prediction (strongest claim).** An RNN/LSTM predicts the *future* resonance from history and pre-compensates readout/transport delay. Demonstrated for single-NV spin: ~3× (50%) linewidth/T₂* improvement; shorter latency → better suppression (arXiv **2201.06002**, Xu/Du). This is exactly the hybrid-PID+NN story.
- **Robust multi-parameter estimation at low SNR.** A 1D-CNN does direct inference with ~5 orders of magnitude speedup vs Monte-Carlo fitting (683 s → 2.94 ms / 5000 spectra) and avoids local-minimum/outlier failures gradient fits hit at low SNR — and the paper explicitly names **FPGA edge deployment → µs closed-loop control** as next (arXiv **2603.14728**). Closest published analog to this project's pitch.
- **Nonlinearity / lineshape compensation.** Real bulk-diamond CW-ODMR is asymmetric (Fano-like). A NN corrects systematic offset a linear PID discriminator bakes in (DLOG-009: 1.5% asymmetry ≈ 30 kHz ≈ ~1,000 nT error).

**Defensible demo claim:** *"PID holds the lock; the NN predicts drift and corrects lineshape-induced bias the PID structurally can't see."*

---

## 3. The synthetic-trace gap — and the cheapest fixes [V]

The current demo replays a **synthetic chirp**. A reviewer discounts this heavily: it proves the *datapath* (UART → V250 → controller → actuator) but nothing about the physics (no shot noise, no asymmetric lineshape, no laser/MW drift, no photon-limited latency). The project's own Phase II table flags **RPO-1 (plant ID on a physical NV-diamond) as "still blocked — Icicle is FPGA-only, not NV"** — visible to a reviewer.

The field *legitimizes* synthetic data (2603.14728 and Homrighausen Sensors 2023 both train-synthetic/validate-real) — the discount is on demos that **stop** at synthetic. Cheapest credibility boosts, in order:
1. **Replay a real recorded ODMR trace** (a CSV of an actual CW-ODMR sweep with real shot noise/asymmetry — public dataset or one borrowed sweep) instead of a chirp. Near-zero hardware cost; kills the "idealized signal" objection. The `hls/tb/stimulus/` drop-in dir already exists for this.
2. **Inject a measured drift/noise profile** (laser-intensity; thermal D-shift ≈ −74 kHz/K) over the trace; show the loop re-locks.
3. **HIL through any real RF element** (a real MW synth/SDR, even without a diamond) so the actuator path sees real analog latency.
4. Full HIL with a diamond = the real unlock, but the expensive long pole (RPO-1).

---

## 4. V250 latency — premise correction [V]

The "tens of µs" inference assumption was partly wrong. The CoreVectorBlox HB0919 handbook: **V250 = 78 GOPs, 4.2 FPS on ResNet50 @154 MHz, "network latency = 1/FPS"** → **~238 ms for a ResNet50-class net.** But:
- Our deployed model is **not** ResNet50 — it's `fcnn_v2_residual_dataset_a.vnnx`, a small residual FCNN (12.8 KB). A few FC layers on the 16×16 MXP run **orders of magnitude faster** — plausibly sub-ms to low-ms (**[NC]: measure on silicon at rung F/G**).
- Architecturally the **NN belongs in the slow outer loop** (drift estimator / lineshape corrector, Hz-class) while the **PID runs the fast inner servo** (kHz). So even 1–10 ms NN latency is loop-relevant, because NV tracking is photon-shot-noise-limited to ms–s anyway.

**Defensible statement:** *"V250 inference need only beat the ODMR integration time (ms–s), not the µs MW-servo period; the PID owns the fast loop."* **Do not quote a latency number until measured on silicon** (the ResNet50 238 ms is an upper bound for a far larger net, not this model).

---

## 5. Sources ingested

New to corpus (`odmr-pnt-nv-docs`): arXiv 2201.06002 (NN drift feedforward), 1808.05580 (NIST PID lock), MDPI 26/6/1777 (PID-on-ODMR math), MDPI 23/3/1119 (edge-ML NV magnetometer). Already present (verified): 1802.09713, 2603.14728, 2402.15748. Demo benchmark (→ `polarfire-control-corpus`): arXiv 2407.08681 (CartPole/F1TENTH FPGA neural control). Search: `/search-corpus odmr-pnt-nv-docs "<query>"`.
