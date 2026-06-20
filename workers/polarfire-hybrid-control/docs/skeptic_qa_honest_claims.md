# Skeptic Q&A — Honest Claims Sheet (2026-06-19)

Defensible, artifact-grounded answers to the questions a sophisticated reviewer will ask
about the PolarFire SoC hybrid PID + neural-network ODMR control demo. Assembled from the
four project repos on 2026-06-19; the most load-bearing numbers (timing closure, ML
reduction, sim→real fidelity, safety obligations, data provenance) were spot-verified
against the cited files on that date. Line numbers reference repo state on 2026-06-19.

**Source repos:** `polarfire-hybrid-control` (FPGA), `odmr-edge-ml` (ML train/eval),
`nv-sensor-sim` (NV physics/data) + `tychon-shared-data` (datasets),
`tychon-verification-workbench` (the "verification" project).

**Confidence labels:** **[CONFIRMED]** = backed by generated Libero report, live-silicon
log, RTL/config, or primary doc · **[BOUND]** = only an upper/lower bound measured ·
**[GAP]** = not measured / not present · **[OVERCLAIM-RISK]** = a current dashboard/report
claim the artifacts do **not** support as stated.

**Guiding principle:** state the narrower honest claim first. Several existing
dashboard/report numbers are overstated; the repos' own artifacts catch them, so a
reviewer will too.

---

## 1. Inference-only, control-logic-only, or full closed-loop path?

**Honest answer:** All three planes are wired and proven on live silicon — but it is **not a
real-time closed loop**; it is **host-paced with injected (not sensed) error.**

On the resident `idfix2` bitstream (Production MPFS250T, IDCODE `1F81A1CF`), verified
2026-06-19:
- **V250 NN inference runs in fabric** — `vbx_probe` → `INFERENCE COMPLETED`, `vnnx_smoke` →
  `out[0]=-2.9506`. Requires a **cold power-cycle** after programming (V250 POR; warm reset
  insufficient). `docs/two_slot_handoff_2026-06-17.md:124`, `docs/two_slot_demo_scope_2026-06-18.md:34`. **[CONFIRMED]**
- **Two-slot PID control/telemetry plane (M1 `pid_csr`)** — real decoded crossbar slave,
  `csr_version=0x00010000`, bit-exact gain readback. `docs/two_slot_demo_scope_2026-06-18.md:35`. **[CONFIRMED]**
- **Live PID actuator** (idfix2 only) — reads back `Kp·error` via M1 tap `0x60040844`
  (err 0.50→0.3999, 2.00→1.0000 clamp). `docs/two_slot_handoff_2026-06-17.md:120`. **[CONFIRMED]**
- **Watchdog → bumpless fallback** — enters `PID_ONLY_FALLBACK` with no recent V250
  `output_valid`. **[CONFIRMED]**

**What it is NOT:** the control sequence (set-gains → inject-error → pulse-start →
read-actuator) is driven step-by-step over ssh, with the **error injected into a CSR, not
sensed from a sensor**, and the V250 inference run **separately**, not per-row inside the
loop. There is no fabric-resident real-time sensor→PID→actuator loop. **[CONFIRMED]**

**[OVERCLAIM-RISK]** `libero/scripts/03_smartdesign.tcl:12-13,22-23` is a stale scaffold
claiming FIC1 wiring + a "<150 µs PID latency guarantee"; the real silicon is a 1→2 AXI
demux on SLAVE3 `0x60040000` off FIC_0 (`docs/two_slot_handoff_2026-06-17.md:139-142`).

**Defensible claim:** *"Full hybrid datapath — V250 inference, decoded control plane, live
PID actuator, and watchdog/bumpless safety — demonstrated on Production silicon, host-paced
with injected stimulus."* Not *"real-time closed-loop control."*

## 2. Real NV data — own hardware or external datasets?

**Honest answer:** **Neither — it is 100% physics simulation.** There is **zero
project-owned NV hardware data**, not even a validation set.

- All training/eval spectra come from a SimOS/QuTiP spin-Hamiltonian + Lorentzian +
  Ornstein-Uhlenbeck simulator (`nv-sensor-sim`). Dataset manifests record
  `backend=qutip`, `simos_version=0.2.3`, `noise_mode=stochastic`
  (`tychon-shared-data/production_50k_v2_aic/manifest.json`). **[CONFIRMED]**
- The deployed model `fcnn_v2_residual_dataset_a` was trained on
  `production_50k_v2_aic` (40k/5k/5k, AIC-shifted regen of `production_50k`). **[CONFIRMED]**
- The **only** real-world data is a **public external** set (Sengottuvel et al. 2022,
  Zenodo 7233869), used solely for a fidelity check, never training. **[CONFIRMED]**
- **The one sim→real fidelity check FAILED:** PCA principal-angle `min cos = 0.009` vs a
  `≥0.80` threshold → **FAIL**, logged as *"regime mismatch, not physics failure… block
  external citation"* — the simulator's 20–70 µT longitudinal regime and the Zenodo
  micro-diamond spectra barely overlap (66/200 points).
  `tychon-sbir/docs/06_research_inputs/pca_fidelity_zenodo_2026-05-17.md:11-13,15,28`. **[CONFIRMED]**

**Defensible claim:** *"Trained and evaluated entirely on a physics-based NV simulator;
no owned-hardware data; sim-to-real fidelity is unvalidated because the only accessible
real dataset is in a different measurement regime."* Lead with this — do not let a reviewer
discover it.

## 3. Offline evaluation or live/hardware-in-the-loop?

**Honest answer:** **ML = entirely offline** on held-out *simulated* test splits (5k spectra,
disjoint seeds); zero HIL. **FPGA = benchtop live-silicon**, "HIL-ish" only in that real
silicon executes — but with injected error and a host-side NN surrogate per row, not an
integrated sensor-in-the-loop. The ML repos place true HIL at "Phase II, TRL 6"
(`tychon-odmr-ml/docs/final_report_outline.md:279,326`). **[CONFIRMED]**

**Defensible claim:** *"Offline ML evaluation + a benchtop live-silicon control-plane
demonstration; not integrated real-time HIL."*

## 4. Field-estimation errors vs baseline fitting

**First correction:** the baseline is a **derivative-zero-crossing PID lock**, **not
Lorentzian spectral fitting** (`odmr-edge-ml/evaluation/pid_proxy.py`). You benchmarked
NN+PID-residual vs PID-only, not vs a fitting baseline. **[CONFIRMED]**

Numbers (`odmr-edge-ml/experiments/phase_c_comparison_table.csv`, **[CONFIRMED]**):
- **Deployed `fcnn_v2_residual_dataset_a` (INT8): ~5% MAE reduction vs PID** — 4.97%
  AIC-test, 5.01% val, 3.74% heading-sweep, 4.82% Allan-dev @τ=2700 s. PID baselines
  23.54 / 23.75 / 13.33 µT. **This is the defensible deployed number.**
- **"8.71% vs PID" = the abandoned `cascade_v1`, whose own gate FAILED** (70% of INT8
  outputs saturate the boundary). `exports/cascade_v1/cascade_eval_report.json`
  (`cascade_reduction_pct_vs_pid=8.7085`); `docs/phase2/cascade_saturation_finding.md:36,105`. **[OVERCLAIM-RISK]**
- **"54%"** = the *float, unclamped* FCNN-v1 measured per-sample (54.27% val); **"84.2%
  Allan"** = FCNN-v1 interpolated (96.13% direct). Different models / different metrics. **[OVERCLAIM-RISK]**
- **"bit-exact INT8"** means int8-runner *reproducibility* for the cascade, **not
  INT8≈float**; the deployed INT8 output is clamped to ±~2.9 µT. **[OVERCLAIM-RISK]**

**Defensible claim:** *"~5% MAE and Allan-deviation reduction vs a PID lock baseline, on
held-out simulated data, offline."*

## 5. Latency

**Honest answer:** **Not measured end-to-end — this is a real gap.** **[GAP]**
- Fabric PID is an II=1 pipeline by construction (`hls/src/nv_pid.cpp:22`), derivative
  filter 7 cycles. **[CONFIRMED design-intent]**
- **"<150 µs" is a design target, never a measured number** (`README.md:80`,
  `03_smartdesign.tcl:23`). **[OVERCLAIM-RISK as a measurement]**
- V250 inference: only an **upper bound** (<~5 ms poll granularity; true latency
  uninstrumented — `docs/rung_f_v250_on_silicon_results_2026-06-16.md:47-48`). **[BOUND]**
- Host-loop period: unrecorded. **[GAP]**

**Defensible claim:** *"II=1 pipelined datapath by construction; no measured closed-loop
latency yet — instrumenting it is open work."*

## 6. Target clock closed at

SDC asks **200 MHz** (`constraints/timing_200mhz.sdc`). Actual shipped two-slot closure
(`libero/reports/2026-06-17-two-slot/two_slot_timing_r10_s29.rpt`, FCVG484, Production,
post-layout) **[CONFIRMED]**:
- **PID / MSS-FIC fabric = 125 MHz, +0.977 ns slack** (`PF_CCC_C0/OUT0`, l.23-26).
- **V250 core = 200 MHz, +0.950 ns slack** (`Vectorblox…PF_CCC_C1/OUT1`, l.65-69);
  100 MHz domain +1.225 ns (l.59-62).

**[OVERCLAIM-RISK]** The headline "+0.950 ns at 200 MHz" is the **V250's** domain — **the
PID controller itself runs at 125 MHz.** The `idfix2` "+0.789 ns" is **prose-only**
(`docs/two_slot_handoff_2026-06-17.md:113-115`); no idfix2 timing `.rpt` is committed.

**Good news:** the **75/150 MHz Icicle de-rate concern is falsified** — the V250 closed at
full 100/200 MHz with positive slack. Side effect of the 125 MHz fabric: the 200k-cycle
watchdog = **1.6 ms, not 1 ms** (and the demo build ships a **500 ms host-paced** watchdog;
see Q8).

**Defensible claim:** *"PID control fabric closed at 125 MHz (+0.977 ns); CoreVectorBlox
V250 core closed at 200 MHz (+0.950 ns) on Production silicon."*

## 7. Resource utilization

- **Two-slot design: 109 DSP / 54,491 LUT** — but this is a **synthesis-survival GATE
  note**, not a committed full P&R util table (`libero/reports/2026-06-17-two-slot/README.md:18`,
  `docs/two_slot_register_map_2026-06-17.md:91`). No LSRAM/register/% breakdown exists for
  the shipped bitstream. **[CONFIRMED as a GATE note; full table is a GAP]**
- **Base design (committed P&R, with % of MPFS250T):** 4LUT 62,837/254,196 = **24.7%**,
  DFF **25.2%**, uSRAM 18.5%, LSRAM 11.8%, Math/DSP 164/784 = **20.9%**
  (`libero/reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt`). **[CONFIRMED, older base]**
- **[OVERCLAIM-RISK]** committed util reports carry an internal **FCVG1152-vs-FCVG484**
  package-label inconsistency (same die totals, so percentages hold, but a reviewer will
  notice).

**Defensible claim:** *"~25% 4LUT / ~21% DSP of the MPFS250T for the base design; the
two-slot add shows 109 DSP / 54.5k LUT at synthesis. A committed post-layout util table for
the shipped bitstream is open work."*

## 8. Safety bounds — formally enforced vs practical guards

**Honest answer:** clamp/slew/watchdog are **practical guards (implemented, on silicon)**;
**formal absolute stability is NOT proven.**

- **Practical guards (on silicon):** sector clamp ±4.5%, slew limiter (0.001/cycle),
  watchdog → bumpless transfer. **[CONFIRMED implemented]** — but the **demonstrated**
  bitstream ships a **500 ms host-paced watchdog**, not the 1 ms safety bound (the 1 ms /
  125k-cycle build is unbuilt). `libero/reports/2026-06-17-two-slot/README.md:17`. **[OVERCLAIM-RISK on "1 ms"]**
- **Formal Lur'e/Circle-Criterion absolute stability is the *framework*, NOT proven.** The
  README itself: these mechanisms *"do not constitute a proof that the AI cannot destabilize
  the loop"* (`README.md:130`). It rests on **six Residual Proof Obligations, ALL OPEN**
  (`docs/safety_architecture.md:58-70`): plant-model ID, ZOH phase margin, transport-delay
  bound, derivative-filter SI, ReLU/NN sector verification, workload-driven SmartPower. **[CONFIRMED]**
- **[OVERCLAIM-RISK]** "Verified by the verification workbench" is unsupportable:
  `tychon-verification-workbench` is an **LLM document-audit** that retrieved the report's
  own prose and rated it "supported" — no formal proof, no model-checking, and its own
  critic-independence gate failed (10/10 supported, 0 disagreements). It does **not** verify
  the safety bound, HLS→RTL equivalence, or INT8 equivalence.

**Defensible claim:** *"The clamp, slew limiter, and watchdog/bumpless transfer bound the
AI's output magnitude and rate — a practical guard demonstrated on silicon. Closed-loop
stability is sector-bounded by design within Phase I assumptions, not formally proven; six
proof obligations remain open."*

## 9. Tested under flight-like conditions?

**Honest answer:** **No.** Benchtop Icicle Kit over LAN only — no thermal, vibration,
radiation, or flight testing anywhere. **[CONFIRMED]**
- "Space-qualification" framing lives only in the simulator's noise parameters (narrative,
  not validation); the orbit-in-the-loop benchmark is itself synthetic (SGP4 + IGRF).
- The STA "0–100 °C" in the timing report is a multi-corner *analysis* envelope, not a
  thermal-chamber test (`two_slot_timing_r10_s29.rpt:12`).

**Defensible claim:** *"Benchtop validation only; no environmental, vibration, radiation, or
flight testing — Phase II work."*

---

## Summary — solid vs what a skeptic sinks

**Solid / defensible:**
- Real Production silicon; CoreVectorBlox V250 NN inference completing in fabric (`out=-2.9506`).
- Clean decoded two-slot control plane + live PID actuator tracking `Kp·error` with a
  saturating sector clamp, on silicon.
- Working watchdog → bumpless fallback on silicon.
- Timing closed with positive slack (PID 125 MHz +0.977 ns; V250 200 MHz +0.950 ns).
- ~5% offline MAE/Allan-deviation reduction vs a PID baseline (simulated data).
- Honestly documented inverse-crime handling in the dataset contract.

**What a skeptic sinks (claim these honestly, first):**
1. 100% simulated data; sim→real fidelity check **failed**; no owned-hardware data. (Q2)
2. Not a real-time loop — host-paced, error injected via CSR, inference run separately. (Q1/Q3)
3. No measured end-to-end latency. (Q5)
4. Formal stability unproven — six open RPOs; "verification" is an LLM doc-audit. (Q8)
5. Flashy ML numbers (8.71% / 54% / 84% / "bit-exact INT8") belong to other or abandoned
   models / different metrics — the **deployed** model is **~5%**. (Q4)
6. Zero environmental / flight testing. (Q9)

## Claims to fix on the dashboard / report
- "8.71% vs PID" → use **~5%** for the deployed model (8.71% is the failed cascade).
- "bit-exact INT8" → "INT8 deployment; bit-exact runner reproducibility" (not INT8≈float).
- "200 MHz" → "PID 125 MHz / V250 200 MHz".
- "1 ms watchdog" → "500 ms host-paced (demo); 1 ms safety build pending".
- "closed-loop" → "host-paced datapath with injected error".
- Any "real NV data" / "sim-to-real validated" / "verified safety" wording → remove or qualify.
