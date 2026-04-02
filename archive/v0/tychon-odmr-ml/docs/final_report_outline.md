# Tychon AI — Phase I Final Technical Report Outline

**Proposal:** FX255-PCS02-0044 (AFWERX SBIR Phase I; not selected 2026-05-12, never a contract)
**Page Budget:** 25 pages
**Template Source:** Gemini Deep Think narrative (Claude-reviewed, 2026-03-27)
**Primary Model:** FCNN v1 — 2,905 parameters, scalar residual correction

---

## Section 1: Executive Summary & BLUF (1 page)

**Bottom Line Up Front:**

[PLACEHOLDER — 1 paragraph: NV-diamond magnetometers enable GPS-denied PNT but nonlinear drift
makes classical PID insufficient for LEO mission durations. Tychon's bounded hybrid architecture
couples a deterministic PID controller with an INT8-quantized FCNN that reduces measurement
instability by [CITE: 84.2%] at the operationally relevant half-orbit timescale.]

**Phase I KPP Scorecard:**

| # | Metric | Target | Achieved | Status |
|---|--------|--------|----------|--------|
| 1 | Spherical Heading Error Reduction | >50% | [CITE: 31.3% MAE, 54.3% val MAE] | [PLACEHOLDER — discuss dual metrics] |
| 2 | Asymmetric Inversion Bias | <5 nT | [PLACEHOLDER — requires DC bias experiments, Phase 2] | Deferred |
| 3 | Frequency-Partitioned PSD | >10× drift suppression | [PLACEHOLDER — TO BE COMPUTED] | [TBD] |
| 4 | Allan Deviation (τ = T_orb/2) | >50% improvement | [CITE: 84.2% at τ=2700s] | PASS |
| 5 | MagNav.jl Positioning RMSE | Demonstrate improvement | [PLACEHOLDER — plausibility validation] | Phase 2 |

**Safety paragraph:** [PLACEHOLDER — 2-3 sentences on bounded hybrid Simplex RTA. The CNN's control
authority is hardware-limited to ±5% via sector saturation clamps. Even under complete AI failure,
the spacecraft cannot destabilize.]

---

## Section 2: Operational Context — Quantum Navigation in Cislunar Space (1 page)

[PLACEHOLDER — Why NV-diamond magnetometers for GPS-denied PNT. Classical PID tracks a local
derivative zero-crossing and is blind to global lineshape structure. Long-duration LEO missions
expose PID to cascaded drift from temperature, MW power, and heading-dependent degeneracy.]

**> FIGURE 1:** High-level ConOps diagram — satellite, NV-diamond magnetometer, control loop
- Status: **TO BE CREATED**
- Content: Satellite in LEO orbit → ODMR spectrum acquisition → PID frequency lock → CNN residual correction → navigation solution
- Placement: Center of section, half-page

---

## Section 3: Safety Architecture — Bounded Hybrid Simplex RTA (3 pages)

> **Narrative note:** This section MUST come BEFORE any ML discussion. "Build the cage before you
> introduce the beast." By the time the reviewer reaches Section 5, they already know the AI
> cannot crash the satellite.

### 3.1 Architecture Overview

[PLACEHOLDER — Bounded hybrid Simplex Run-Time Assurance (RTA). PID provides deterministic
stabilization (SmartHLS C++, II=1 pipeline). CNN operates purely as a bounded feedforward
compensator for adaptive bias cancellation — NOT in the direct feedback path.]

**> FIGURE 2:** Simplex RTA block diagram (annotated)
- Status: **TO BE CREATED**
- Content: PID inner loop, CNN feedforward path, sector saturation clamp (±5%), slew-rate limiter, watchdog timer, bumpless transfer path
- Must show: control authority bounds, watchdog trigger, and bumpless transfer I_new = I_old + u_AI_old
- Placement: Full-width, top of subsection

### 3.2 Formal Safety Guarantee

[PLACEHOLDER — 1 paragraph: Lur'e/Circle Criterion framing. The linear plant and PID satisfy
strict positive realness. The AI acts as a memoryless nonlinearity restricted to sector [0, K].
Absolute Stability guaranteed via Circle Criterion.]

**Precedents:** NASA IFCS F-15 (1-2 sentences), Air Force Auto-GCAS (1-2 sentences).

### 3.3 Hardware Safety Implementation

**Clamp Authority Analysis:**

| Parameter | Value | Justification |
|-----------|-------|---------------|
| Sector saturation | ±5% of actuator range | [PLACEHOLDER] |
| Slew-rate limit | [PLACEHOLDER — du_AI/dt max] | Prevents transient injection |
| Watchdog timeout | 1.0 ms (200,000 cycles at 200 MHz) | VectorBlox AXI bus deadline |
| Bumpless transfer | I_new = I_old + u_AI_old | Zero discontinuity at handoff |
| Bumpless transfer delta | [CITE: 0.0762939 V exact match] | Ki × error natural step, verified in SmartHLS testbench |

---

## Section 4: Deliverable 1 — Validated Synthetic Data Pipeline (3 pages)

### 4.1 SimOS Architecture

[PLACEHOLDER — Coupled noise model with cascaded Ornstein-Uhlenbeck processes for temperature
drift, MW power variation, B1 gradient inhomogeneity. Asymmetric lineshape corruption via Fano
distortion. 100-point CW-ODMR spectra spanning 2820-2920 MHz.]

### 4.2 Production Dataset

[PLACEHOLDER — 50K spectra (40K train / 5K val / 5K test) with master_seed reproducibility.
Field range 20-70 µT. Corruption parameters sampled from physically justified distributions.]

**> FIGURE 3:** Synthetic spectrum overlay — clean vs corrupted
- Status: **TO BE CREATED**
- Content: 3-4 overlaid spectra showing progressive corruption (temperature shift, B1 broadening, MW power variation, Fano distortion)
- Placement: Half-page

**Corruption Parameter Ranges:**

| Parameter | Range | Physical Justification |
|-----------|-------|----------------------|
| P1 concentration | [PLACEHOLDER] | Determines linewidth/overlap |
| Temperature | [PLACEHOLDER] | Shifts ZFS parameter D |
| B1 gradient | 5-30% | MW inhomogeneity |
| MW power drift | ±5% | Cascaded OU temporal variation |
| Fano distortion | [PLACEHOLDER] | Asymmetric lineshape |

### 4.3 Train/Test Separation Protocol

[PLACEHOLDER — Table format: split sizes, seed ranges, parameter distribution shifts between
train and test. Critical for reviewer trust — document that test set was never seen during
training or hyperparameter selection.]

---

## Section 5: Deliverable 2 — Cognitive Control & Edge Quantization (4 pages)

### 5.1 The Physics Finding: CW-ODMR Degeneracy at Earth Field

> **Narrative note:** Frame the pivot as a strength: "Phase I feasibility studies are supposed to
> identify what works. The discovery of fundamental quantum degeneracy — confirmed by published
> literature — is itself a key Phase I result."

[PLACEHOLDER — 3D B-field vector prediction from CW-ODMR spectra is impossible at 20-70 µT.
Diagnostic evidence: both MLP (8,643 params) and FCNN (3,299 params) converged to exactly
[CITE: 57.3° angular error] — the mathematical constant for a model outputting a single constant
direction. Sign ambiguity: B and -B spectra correlation = 0.888 vs random pairs 0.884.
Published precedent: SBQuantum, Lockheed Martin, Walsworth Lab use DC bias fields (2-5 mT) to
break degeneracy.]

### 5.2 Scalar Residual Reformulation

[PLACEHOLDER — CNN as PID error de-embedder: ΔB = |B_true| - B_PID. Input: 2-channel
[spectrum, PID anchor Gaussian]. Output: scalar correction (±35 µT range). INT8 quantization
resolution advantage: [CITE: 0.27 µT/bit] (residual) vs 0.39 µT/bit (absolute) = 1.4× better.]

### 5.3 Architecture Evolution

| Stage | Architecture | Params | Task | Key Result |
|-------|-------------|--------|------|------------|
| 1 | MLP + FCNN | 8,643 / 3,299 | 3D B-vector | [CITE: 57.3°] angular error — degeneracy proof |
| 2 | MLP scalar | 8,643 | Scalar \|B\| | 10.94 µT MAE (13% over baseline) — physics extractable |
| 3 | FCNN v1 scalar residual | [CITE: 2,905] | ΔB correction | [CITE: 54.3% val MAE reduction] — deployed model |
| 4 | Feature MLP exploration | 241-737 | ΔB w/ physics features | Strong feature correlations, but raw-spectrum FCNN generalizes better on heading sweep |

### 5.4 INT8 Quantization Pipeline

[PLACEHOLDER — PyTorch QAT (symmetric, per-tensor activations, per-channel Conv2D weights)
→ ONNX export → TFLite INT8 conversion → vnnx_compile -c V250.]

**Quantization Impact Matrix:**

| Metric | FP32 | INT8 | Delta |
|--------|------|------|-------|
| Validation MAE (µT) | [PLACEHOLDER] | [PLACEHOLDER] | [PLACEHOLDER] |
| Model size | [PLACEHOLDER] | [CITE: 7.4 KB TFLite] | [PLACEHOLDER] |
| Weight fidelity | — | [CITE: max \|PT - TF\| = 1.91e-05] | — |

---

## Section 6: Deliverable 3 — FPGA Implementation & SWaP-C Analysis (3 pages)

### 6.1 SmartHLS PID Controller

[PLACEHOLDER — Deterministic PID in SmartHLS C++ targeting PolarFire SoC.]

| Parameter | Value |
|-----------|-------|
| Pipeline | [CITE: II=1, 6-stage, 100 MHz] |
| Fixed-point | freq_t: Q34.30 (64-bit), gain_t/out_t: Q16.16 (32-bit) |
| Frequency precision | 0.93 mHz |
| Bumpless transfer | PASS — [CITE: delta = 0.0762939 V exact match] |

### 6.2 VectorBlox V250 CNN Accelerator

[PLACEHOLDER — INT8 inference on CoreVectorBlox V250 soft-vector processor.]

| Parameter | Value |
|-----------|-------|
| Model | FCNN v1 scalar residual |
| Parameters | [CITE: 2,905] |
| Binary size | [CITE: 12.5 KB .vnnx] |
| TFLite ops | CONV_2D only (no SHAPE/STRIDED_SLICE/PACK) |
| Input shape | (1, 1, 100, 2) NHWC — pre-shaped, no dynamic reshape |
| Output shape | (1, 1, 1, 1) — scalar ΔB correction |
| Weight fidelity | [CITE: max error = 1.91e-05] |

### 6.3 Resource Utilization

**Source:** Libero SoC 2025.2 synthesis + P&R on MPFS250T Icicle Kit (FCVG484, STD speed grade).
Design includes full Icicle Kit reference (MSS, PCIe, DMA, SRAM) + CoreVectorBlox V1000 + SmartHLS PID.
Reports at: `/mnt/nas/projects/tychon-artifacts/libero_reports/`

| Resource | Used | Available (MPFS250T) | Utilization |
|----------|------|---------------------|-------------|
| 4LUT | [CITE: 62,837] | 254,196 | [CITE: 24.72%] |
| DFF | [CITE: 64,079] | 254,196 | [CITE: 25.21%] |
| uSRAM | [CITE: 434] | 2,352 | [CITE: 18.45%] |
| LSRAM | [CITE: 96] | 812 | [CITE: 11.82%] |
| Math/DSP | [CITE: 164] | 784 | [CITE: 20.92%] |
| PLL | 2 | 8 | 25.00% |
| User I/O | 65 | 144 | 45.14% |

> **Note:** VectorBlox configured as V1000 (PRESET:1) in this synthesis. V250 would use fewer
> resources. The full Icicle Kit design (MSS, PCIe, DMA, peripherals) is included — production
> firmware would strip unused peripherals, further reducing utilization.

### 6.4 Timing & Power

**SmartTime Timing Analysis (post-layout, multi-corner):**

| Clock Domain | Frequency | Worst Slack | Status |
|-------------|-----------|-------------|--------|
| VectorBlox main (PF_CCC_C1 OUT0) | [CITE: 100 MHz] | [CITE: +1.522 ns] | PASS |
| VectorBlox 2x (PF_CCC_C1 OUT1) | [CITE: 200 MHz] | [CITE: +1.040 ns] | PASS |
| FIC_0 / FIC_1 (PF_CCC_C0 OUT0/1) | 125 MHz | +2.065 ns | PASS |
| FIC_3 (PF_CCC_C0 OUT3) | 50 MHz | [CITE: +0.165 ns] | PASS |

- **P&R:** Passed on first seed (1 of 20 iterations)
- **All clock domains:** Positive slack = no timing violations
- **Worst path:** FIC_3 APB readback (MSS ↔ fabric, not PID or VBX critical path)
- **Conditions:** slow_lv_ht corner (worst case: 100°C, 1.0185V)

**SmartPower:**
- Status: **NOT YET RUN** — listed as remaining step in Beelink session log
- [PLACEHOLDER — run SmartPower on Beelink to get static + dynamic power estimates]

**> FIGURE 4:** Execution timeline (Gantt-style)
- Status: **TO BE CREATED**
- Content: PID cycles (deterministic, <150 µs) interleaved with CNN async updates (<1 ms). Show watchdog window.
- Placement: Half-page

---

## Section 7: System Validation & 5-Metric Evaluation (8 pages)

> **Narrative note:** This is the most important section. Each metric ~1.5 pages (figure +
> discussion + interpretation). The Allan Deviation plot is THE MONEY SHOT — the single most
> compelling figure in the report.

### 7.1 Metric 1: Spherical Heading Error Profile (1.5 pages)

**> FIGURE 5:** Heading error sweep — HERO FIGURE
- File: `experiments/heading_sweep_figure.pdf`
- Status: **EXISTS**
- Content: Dual-panel — bottom: ODMR spectrogram (freq vs angle heatmap), top: heading error (PID red spikes, FCNN+PID blue). Degeneracy angles aligned vertically.
- Placement: Full-width, top of subsection

**Key results:**
- Rotation plane: (1,-1,0) crystallographic plane, 1,440 angles at 0.25° steps
- Field magnitude: 50 µT with cascaded OU noise
- PID-only MAE: [CITE: 13.33 µT]
- FCNN+PID MAE: [CITE: 9.16 µT]
- MAE reduction: [CITE: 31.3%]
- Validation MAE reduction: [CITE: 54.3% (23.75 → 10.85 µT)]

[PLACEHOLDER — Discussion of degeneracy angles (0°, 54.7°, 90°, 125.3°, 180°) where PID
catastrophically fails. CNN eliminates dead-zones by recognizing morphological envelope of
merged dips. The ±4.5% sector clamp provides ±2.25 µT authority — sufficient to steer
the FLL out of line-pulling traps.]

### 7.2 Metric 2: Asymmetric Inversion Bias (1.5 pages)

**> FIGURE 6:** Bias histogram across B1 gradient range
- Status: **TO BE CREATED** (or deferred to Phase 2)
- Content: Histogram of signed bias (B_predicted - B_true) across B1 gradient conditions
- Target: <5 nT systematic bias

[PLACEHOLDER — This metric requires DC bias field experiments to fully evaluate. Present
available characterization from synthetic data. Note: full validation requires Phase 2
hardware-in-the-loop testing with known reference fields.]

### 7.3 Metric 3: Frequency-Partitioned PSD (1.5 pages)

**> FIGURE 7:** Log-log PSD plot
- Status: **TO BE CREATED** (or deferred to Phase 2)
- Content: PSD with drift band (<0.1 Hz) and white noise band (>1 Hz) highlighted
- Target: >10× suppression in drift band

[PLACEHOLDER — Frequency-domain decomposition of sensor error. Show PID drift accumulation
in low-frequency band and CNN's selective suppression of correlated noise sources.]

### 7.4 Metric 4: Allan Deviation — THE MONEY SHOT (1.5 pages)

**> FIGURE 8:** Allan deviation stability comparison — THE MONEY SHOT
- File: `experiments/adev_figure.pdf`
- Status: **EXISTS**
- Content: Log-log ADEV plot, PID drifts upward at τ > 5s, FCNN+PID flattens
- Placement: Full-width, prominently placed

**Allan Deviation Results (3 LEO orbits, 16,200s):**

| τ (s) | PID OADEV (µT) | FCNN+PID OADEV (µT) | Improvement |
|-------|---------------|---------------------|-------------|
| 1 | [CITE: 3.40] | [CITE: 2.56] | 24.6% |
| 10 | [CITE: 3.46] | [CITE: 2.17] | 37.2% |
| 100 | [CITE: 6.85] | [CITE: 3.58] | 47.7% |
| 1000 | [CITE: 15.84] | [CITE: 8.07] | 49.1% |
| **2700** | [CITE: **14.85**] | [CITE: **2.35**] | [CITE: **84.2%**] |

> **Headline:** At the operationally relevant half-orbit timescale (τ = 2700s = T_orb/2),
> the FCNN+PID hybrid reduces measurement instability by 84%.

[PLACEHOLDER — Discussion: PID hits 1/f corner at τ ≈ 1.5-3s and enters random walk.
FCNN compensates cascaded OU drift that PID cannot track. "Software-defined shielding" —
AI noise compensation replaces physical shielding mass, directly relevant to SWaP-C.
Connect to operational significance: "Flattening ADEV at τ > 5s allows a USSF satellite
to maintain positioning capability for the full orbital period without GPS."]

### 7.5 Metric 5: MagNav.jl Positioning RMSE (2 pages)

> **Framing note:** This is the weakest metric. Frame as "system-level plausibility validation"
> — NOT "proof of navigation performance." A reviewer who knows MagNav.jl will probe whether
> the noise model is realistic.

[PLACEHOLDER — "This metric validates that the sensor-level improvements demonstrated in
Metrics 1-4 translate to meaningful navigation error reduction when integrated into a
representative flight framework. Full validation requires Phase II hardware-in-the-loop
testing." Inject synthetic noise characteristics into SGL 2020 flight data framework.
Report positioning RMSE improvement as plausibility check.]

**> FIGURE 9:** MagNav.jl RMSE visualization
- Status: **Phase 2 plausibility validation**
- Content: RMSE comparison with/without CNN correction in MagNav.jl framework

---

## Section 8: Limitations & Future Work (0.5 pages)

> **Narrative note:** This builds reviewer trust faster than any other section. Be honest.

| Limitation | Mitigation (Phase 2) |
|------------|---------------------|
| **Scalar-only prediction** — 3D heading requires DC bias fields to break quantum degeneracy (literature-backed: SBQuantum, Lockheed, Walsworth) | Permanent DC bias field design (2-5 mT) in Phase 2 hardware |
| **Synthetic-to-real gap** — trained on SimOS, not hardware data | Phase 2 HITL validation with NV-diamond hardware |
| **Silver license** — synthesis on commercial PolarFire (MPFS250T), not RT PolarFire | Gold license procurement + RT PolarFire Dev Kit in Phase 2 |
| **Dataset scale** — 100-sample golden set for contract tests; 50K production for training | Production dataset validates gradient plumbing; Phase 2 expands to hardware-calibrated data |

---

## Section 9: Phase II Transition & Licensing Strategy (1.5 pages)

### 9.1 Silver → Gold License Transition

[PLACEHOLDER — Use Gemini language nearly verbatim:]

> "Because the commercial PolarFire and the space-grade RT PolarFire share an architecturally
> identical underlying logic fabric, routing matrix, and VectorBlox IP core, the synthesis
> results achieved in Phase I — specifically the PID latency, CNN latency, and resource
> utilization — are deterministically 1:1 representative of the flight hardware."

[PLACEHOLDER — Price the Gold license if known, otherwise: "budgeted in Phase II cost proposal."]

### 9.2 Phase II Hardware

[PLACEHOLDER — RT PolarFire SoC Development Kit procurement. SEE mitigations: TMR routing,
configuration memory scrubbing. Hardware-in-the-loop validation to reach TRL 6.]

### 9.3 Transition Target

[PLACEHOLDER — AFRL Space Vehicles Directorate or specific program. Dual-use narrative:
"The commercial variant replaces RT PolarFire with MPFS460, reducing BoM by ~60% for NewSpace
operators while sharing >80% common firmware."]

---

## Appendix: Figure & Table Production Status

| # | Item | Section | Status | Source |
|---|------|---------|--------|--------|
| 1 | KPP Scorecard | §1 | TO BE WRITTEN | All deliverables |
| 2 | ConOps diagram | §2 | TO BE CREATED | — |
| 3 | Simplex RTA block diagram | §3 | TO BE CREATED | Repo 3 architecture |
| 4 | Clamp authority table | §3 | TO BE WRITTEN | `tychon-polarfire-control/hls/` |
| 5 | Synthetic spectrum overlay | §4 | TO BE CREATED | Repo 1 SimOS |
| 6 | Corruption parameters table | §4 | TO BE WRITTEN | Repo 1 config |
| 7 | Train/test separation table | §4 | TO BE WRITTEN | Dataset manifests |
| 8 | Architecture evolution table | §5 | TO BE WRITTEN | `docs/phase1-findings.md` |
| 9 | Quantization Impact Matrix | §5 | TO BE WRITTEN | Export artifacts |
| 10 | Resource utilization table | §6 | **DONE** | `/mnt/nas/projects/tychon-artifacts/libero_reports/` |
| 11 | Execution timeline | §6 | TO BE CREATED | SmartHLS timing |
| 12 | SmartTime timing | §6 | **DONE** | Same NAS path — timing_r1_s1.rpt |
| 12b | SmartPower | §6 | NOT YET RUN | Needs Beelink session |
| **13** | **Heading error sweep** | **§7** | **EXISTS** | `experiments/heading_sweep_figure.pdf` |
| 14 | Bias histogram | §7 | TO BE CREATED / Phase 2 | — |
| 15 | PSD plot | §7 | TO BE CREATED / Phase 2 | — |
| **16** | **Allan deviation** | **§7** | **EXISTS** | `experiments/adev_figure.pdf` |
| 17 | MagNav.jl RMSE | §7 | Phase 2 plausibility | — |
