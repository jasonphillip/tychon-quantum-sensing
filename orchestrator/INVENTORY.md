# Tychon — Honest Technical Inventory

**Audience:** skeptical government (AFRL) engineering review.
**Purpose:** an accurate, citation-backed account of what was actually built across the five repos — separating what is *demonstrated* from what is *designed, modeled, or asserted*. No marketing. Where evidence is missing it is said so.
**Reconstructed:** 2026-07-01, from the actual repository state (git history, source, tests, logs, Libero reports, program logs), not from memory. Several load-bearing claims were re-verified first-hand this session (tests re-run, program logs and timing reports read directly); those are noted inline.

---

## 0. How to read this document

### Maturity tags (exactly one per capability/number)

| Code | Meaning |
|---|---|
| **[HW]** | MEASURED ON PHYSICAL HARDWARE — observed on the running MPFS250T silicon |
| **[TB]** | MEASURED ON TESTBED — a real test/sim run produced the artifact (pytest, C++ testbench, HLS cosim) |
| **[SIM✓]** | SIMULATED, validated against lab physics — **used nowhere in this project; see below** |
| **[MODEL]** | MODELED ONLY — a tool/analysis computed it (STA timing, SmartPower, P&R utilization, physics sim output) with no lab validation |
| **[DESIGN]** | DESIGNED, NOT YET TESTED — code/spec exists, no passing test or run |
| **[DOCS]** | IN DOCS ONLY — the claim rests solely on a commit message, README, or prose doc |

**Deliberate discipline:** the tag *"SIMULATED (validated against lab physics)"* is applied to **nothing** in this system. The one attempt to validate the simulator against real NV data **failed** (§3-sim, §6). All simulator and ML numbers are therefore tagged **[MODEL]** ("modeled, not lab-validated") even when they come from real, passing test runs — the run is real, the *physics validation* is not. FPGA synthesis/timing/power/utilization numbers are tool outputs (STA, SmartPower, P&R), tagged **[MODEL]** with the tool named; the *fact that the design programs and runs* is separately **[HW]**.

### Provenance caveat that affects everything below
The newest and strongest FPGA evidence (the 2 ms fabric-watchdog image, the on-kit latency numbers, the safety-build attempts) is **uncommitted working-tree material** in `polarfire-hybrid-control` — 53 uncommitted paths, all dated 2026-06-21, on top of HEAD `cde1e4e` (2026-06-19). An auditor cloning the repo at HEAD would not see it. It is real (real FlashPro6 logs, real IDCODE), but it is not in git history. Flagged again where relevant.

### Bottom line up front
A hybrid PID + neural-network controller **is genuinely running on production PolarFire MPFS250T silicon**: the device programs, a CoreVectorBlox V250 neural net completes inference in fabric, a decoded control plane and a live PID actuator with a saturating safety clamp work, and a watchdog falls back to PID-only. **But** it is **not a real-time closed loop** (it is host-paced with *injected*, not sensed, error, and inference is run separately from the control step); it uses **100% simulated NV data** with a **failed** sim-to-real check and **zero owned-hardware data**; **end-to-end fabric latency, workload power, and any formal AI-stability certificate are unmeasured/unproven**; and the deployed model's benefit is **~5% relative** MAE reduction over a weak baseline (absolute residual still ~22 µT ≈ half the field). The newest "vector tracking" work is a **2-day-old foundation** whose central learned model is an untrained skeleton.

---

## 1. The system in one picture

```
 nv-sensor-sim ──(synthetic ODMR spectra, SimOS/qutip)──▶ odmr-edge-ml ──(INT8 TFLite)──▶ polarfire-hybrid-control
     │  physics simulator + dataset generator               │  static scalar residual NN     │  .vnnx on V250 NPU +
     │                                                       │                                │  SmartHLS PID + safety RTA,
     └──(time-series crossing sequences)──▶ odmr-vector-tracking (NEW, 2 days old)            │  on MPFS250T silicon
                                             learned through-crossing tracker (skeleton)      
 tychon-verification-workbench ── LLM audit/orchestration harness that audits the report + these repos (software only)
```

| Repo | Branch / HEAD / last commit | What it is | Honest one-line status |
|---|---|---|---|
| **polarfire-hybrid-control** | `bringup/2026-06-17-two-slot-pid` / `cde1e4e` / 2026-06-19 (+53 uncommitted, 2026-06-21) | Hybrid PID + NN control on PolarFire SoC (SmartHLS + CoreVectorBlox) | Hybrid datapath demonstrated on production silicon, host-paced with injected error; not real-time closed-loop |
| **odmr-edge-ml** | `feature/op-set-check-and-fcnnv2-docstring` / `ac840a1` / 2026-05-17 (working tree dirty) | Edge ML: synthetic spectrum → scalar ΔB residual, INT8 for V250 | 139/139 unit tests pass; deployed model = ~5% relative MAE gain on synthetic data; not lab-validated |
| **nv-sensor-sim** | `feat/sequence-generator` / `6ad3be5` / 2026-06-30 | NV-diamond CW-ODMR physics simulator + dataset generator | 110 tests pass (internal self-consistency); **never validated against a measured spectrum** |
| **odmr-vector-tracking** | `increment-1-foundation` / `840eb0e` / 2026-06-30 | NEW: learned tracker to hold NV line identity through frequency crossings | 2 days old; classical baseline + skeleton done; the learned model is untrained |
| **tychon-verification-workbench** | `main` / `6736b16` / 2026-05-17 | LLM corpus + critic audit harness; multi-repo orchestration | Ran Stages 0–4.8, produced real audit punch-lists; ~6 weeks stale; software only |

---

## 2. History — initial intent → pivots → today

### 2.1 Initial intent (what was set out to build)
- **ML (both `odmr-edge-ml` and `nv-sensor-sim` initial commits, 2026-04-03):** a VectorBlox-compatible model zoo (MLP / 1D-CNN / FCNN) predicting a **full 3-D B-field vector** `[Bx,By,Bz]` from NV-diamond ODMR spectra, trained on a physics simulator, with a stated ambition to "validate synthetic spectra against published reference data." Every model still defaults to `output_dim=3` (`odmr-edge-ml/models/{mlp,cnn1d,fcnn}.py`, `configs/default.yaml:4`). The real Zenodo reference CSVs shipped in the very first `nv-sensor-sim` commit (`data/experimental/zenodo_odmr/f*.csv`). **[DOCS]** for the intent.
- **FPGA (`polarfire-hybrid-control` initial commit `1d57150`, 2026-04-03):** "hybrid PID + neural network control system for PolarFire SoC" — SmartHLS C++ PID with a bounded-safety architecture (sector clamps, slew limiter, watchdog → bumpless transfer to pure PID) and CoreVectorBlox integration, targeting MPFS250T. The safety framing (Lur'e/Circle-Criterion sector bound) was present from the start. **[DOCS]** for the intent.

### 2.2 What changed, and why (pivots, with evidence)

| Pivot | Evidence (commit / file · date) | Why |
|---|---|---|
| 3-D vector → **scalar residual ΔB** (predict |B|−B_PID, not direction) | `odmr-edge-ml/docs/design_decisions.md:84-93`; shipped `37b7f09` (2026-04-28) | +B and −B produce identical CW-ODMR spectra at 20–70 µT (quantum degeneracy); direction is unrecoverable in that regime. `output_dim:3` is now legacy. |
| Model **v1 → v2** (learnable anchor σ, target clamp ±2.25 µT, Huber loss) | `odmr-edge-ml/models/scalar_residual_v2.py`; promoted `c22d2c4` (2026-05-02) | v1 (unclamped) clipped **97.4%** of its outputs — not deployable. |
| Retrain on **"Dataset A"** = anti-inverse-crime shifted test ranges | `nv-sensor-sim` `f89906c` (2026-04-04); `odmr-edge-ml` `faf9fd5` (2026-04-28) | Prevent inverse-crime contamination (test split shifted +12.5% mean / +20% width vs train). |
| **Hierarchical INT8 cascade** attempted, then **abandoned** | `odmr-edge-ml/docs/phase2/cascade_saturation_finding.md`; `851c4c4` (2026-05-02) | Cascade did **not** beat the monolithic model; 70% of INT8 outputs saturated the boundary. Documented negative result. |
| **Vector direction re-opened** (8 FCNNs + BLUE least-squares fusion, forward-reconstruction metric, PCA-vs-real check) | `odmr-edge-ml` `51bc049`,`46baa56`,`ac840a1` (2026-05-17); `nv-sensor-sim` `30677a3` (2026-05-17) | Exploratory attempt to recover 3-D readout; still exploratory, not deployed (§4.2). |
| **FPGA silicon: engineering-sample → production.** Package designator corrected `FCSG536` → `FCVG484E`; ES board that blocked bring-up on 2026-05-18 replaced by a **Production** kit | `tvw/audits/audit-005-fpga-package-correction.md` (F-018); `polarfire-hybrid-control/docs/silicon_production_confirmed_2026-06-02.md` | The ES board could not be programmed for rung-A; the production kit (IDCODE `1F81A1CF`, no `_ES`) passes. **[HW]** for the IDCODE. |
| **CoreVectorBlox V500 → V250** rebuild | `polarfire-hybrid-control/docs/rung_f_v250_on_silicon_results_2026-06-16.md` | The rung-A program (2026-06-15) shipped a V500 bitstream; the V250 rebuild (2026-06-16) is the design target and the current NPU. |
| **Two-slot `idfix2` bitstream + live PID actuator** (fixed two latent RTL bugs: M0 AXI-completion demux truncation, un-latched actuator) | `polarfire-hybrid-control` `95d946b`,`263d030` (2026-06-18); `docs/two_slot_handoff_2026-06-17.md` | Get a clean decoded control plane + a live actuator that tracks Kp·error with a saturating clamp. Verified in ModelSim and on silicon. **[HW]**. |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **Program pivot: AFWERX Phase I "Not Selected."** Reframed to methodology and FPGA-stack portfolio; no Phase II DTP2 | project record (DLOG-049); global memory `afwerx_pivot_2026-05-17` | External program outcome, not a technical result. Affects who funds the open work below. (proposal submitted 2025-08-05, not selected 2026-05-12) |
| **NEW: `odmr-vector-tracking`** repo scaffolded (through-crossing vector tracker) | `odmr-vector-tracking` `738b70c` (2026-06-29) → `840eb0e` (2026-06-30); `nv-sensor-sim` time-series generator `303b07e` (2026-06-29) | Extend usable vector dynamic range at a fixed bias by learning to hold line-identity through inter-axis crossings (§5). |

### 2.3 The current running artifact on the FPGA today

**What programs and runs — [HW], verified first-hand this session** (program logs read directly):
- **Device:** MPFS250T, **Production** silicon, **IDCODE `1F81A1CF`** (no `_ES`), read by a real Embedded FlashPro6 (`F31E000A`). Corroborated across scan logs 2026-06-02 / 06-15 / 06-21.
- **Two committed PROGRAM PASSes:** rung-A seed_7/V500 (`libero/reports/2026-06-15-program/program.log:60` → `device 'MPFS250T' : Executing action PROGRAM PASSED.`, `Chain programming PASSED.`, 57 s), and the two-slot `idfix2`/V250 build (2026-06-18, `docs/two_slot_handoff_2026-06-17.md`). A **third**, the 2 ms-watchdog image, also PROGRAM-PASSED (`libero/reports/2026-06-21-watchdog-2ms/program_2ms.log:60`) but is **uncommitted**.
- **V250 neural inference completes in fabric:** `vbx_probe` → `INFERENCE COMPLETED`; `vnnx_smoke` → `out[0]=-2.9506`; model = `fcnn_v2_residual_dataset_a.vnnx` (post-program probe JSON, `dashboard_v250_probe_post_program.json`). Requires a **cold power-cycle** after any fabric program (V250 POR).
- **Decoded two-slot control plane:** M0 gains slave + M1 `pid_csr` read/write bit-exact on silicon (`csr_version=0x00010000`).
- **Live PID actuator:** set gains via M0, inject error via M1, pulse start, read latched actuator — it tracks `Kp·error` and the **sector clamp saturates** (err 0.50→0.3999, 2.00→**1.0000** clamp). Streamed via `tools/rung_g_replay.py`.
- **Watchdog → bumpless PID-only fallback:** register reads back on silicon; enters `PID_ONLY_FALLBACK` when no recent V250 completion.

**What it does NOT do (all confirmed, load-bearing):**
- **Not a real-time closed loop.** The sequence (set-gains → inject-error → pulse → read-actuator) is driven step-by-step over SSH; the **error is injected into a CSR, not sensed from a sensor**; V250 inference is run **separately**, not per-row inside the loop. There is no fabric-resident sensor→PID→actuator loop. (`docs/skeptic_qa_honest_claims.md` Q1.)
- **No real NV sensor / no real data** anywhere in the loop.
- **No measured end-to-end fabric latency** (§3.2), **no measured watchdog trip-time**, **no workload-driven power** (§3.4), **no formal AI-stability certificate** (§3.3).
- The **PID control fabric runs at 125 MHz**, not the "200 MHz" headline (that is the V250 core clock; §3, §6).

---

## 3. The hard-scrutiny five — demonstrated vs specified

### 3.1 Hardware watchdog / run-time assurance (RTA)

**Implemented and unit-tested [TB]; on-silicon behavior only partial [HW/DESIGN].**

- **Implemented in SmartHLS C++:** free-running watchdog counter (`hls/src/watchdog.cpp`), rising-edge → `bumpless_transfer` with a 1000-cycle cooldown (`hls/src/nv_pid.cpp:51-69`), hybrid sector clamp — **immutable outer ±4.5%** + AXI-configurable inner + SEU re-clamp — and slew limiter (`hls/src/safety_clamps.cpp`). Constants in `hls/include/rta_config.hpp`: `OUTER_SECTOR_CLAMP_FRACTION=0.045`, `MAX_SLEW_PER_CYCLE=0.001`, `WATCHDOG_TIMEOUT_CYCLES=250000`, `WATCHDOG_COOLDOWN_CYCLES=1000`. **[DESIGN→TB]**
- **C++ testbench passes — re-run first-hand this session:** `make hls-test-local` (g++ against the `ap_fixpt` software shim) → **`ALL TESTS PASSED`, exit 0**. Ten tests: bumpless transfer (delta at trip = natural PID step), clamp widen-rejected / tighten-accepted / **SEU-outer-holds** (0.225 V bound holds under a forced 10% corrupted soft-state), cooldown chatter, missed/stuck-high completion → stable PID-only, derivative-filter DC-gain=1 and HF-step attenuation (`hls/tb/tb_bumpless.cpp`). **[TB]** — but this is a **software-model** test (bit-accurate fixed-point C++), **not** a SmartHLS C/RTL cosim, **not** ModelSim, **not** on-silicon fault injection.
- **On silicon:** the watchdog counter synthesizes to real fabric (~26 LUT / 20 DFF, `tvw/audits/audit-002` F-008), is programmed, its register reads back, and it sits in `PID_ONLY_FALLBACK` when V250 stops completing. **[HW]** at the register/behavior level. **The watchdog trip-TIME (the 2 ms) was never measured** — post-program telemetry shows only steady-state `watchdog_timeout:1` / `PID_ONLY_FALLBACK`, never a timed clear→trip (`dashboard_live_stream_5_post_program.sse`). The sector clamp *saturation* is separately demonstrated on the live actuator (err 2.0→1.0). **[HW]** for the clamp; **[DESIGN]** for a measured on-silicon trip event.
- **Reviewer landmines (real):**
  - **Watchdog value is inconsistent across the repo.** Working-tree `rta_config.hpp` = 250000 (2 ms @ 125 MHz); `watchdog.cpp:5-10` comment still says "1 ms / 200,000 cycles / 200 MHz" (stale); plan docs variously say 125000 (1 ms), 250000 (2 ms), and "1 ms trip"; the **committed-HEAD** demo shipped a **500 ms host-paced** watchdog. The 2 ms fabric image is **uncommitted**.
  - **Clock-frequency mismatch in the RTA config.** `rta_config.hpp` assumes `CLOCK_FREQ_HZ = 200 MHz` and derives slew ("200 V/ms at 200 MHz") and cooldown ("1000 cycles = 5 µs") from it — but the **PID fabric actually closed at 125 MHz**. Cycle-derived wall-clock bounds are off by ~1.6× on the shipped fabric. `rta_config.hpp:16` also self-flags a design-report clamp inconsistency (±2.5 vs ±2.25 µT).

### 3.2 Inference latency and jitter

**Measured on hardware but coarse, API-level, and not closed-loop [HW, heavily caveated]. End-to-end fabric latency = a genuine GAP.**

- Source: `docs/latency_measured_2026-06-21.md` (**uncommitted**). Critical caveat in the doc itself: userspace `rdcycle` **traps** on this Linux image, so timing falls back to `rdtime` at a **1 MHz timebase → 1 µs resolution**; the numbers are *"not U54 cycle counts and not pure fabric/V250 internal cycle latency."*

| Path | median | p99 | max | n | Note |
|---|---|---|---|---|---|
| V250 model start + poll (already-loaded) | 32 µs | 33 µs | 58 µs | 1000 | on-kit API/start+poll **bound** |
| PID M0 pulse + M1 read | 4 µs | 4 µs | 50 µs | 5000 | on-kit MMIO pulse/read **bound** |
| Host-paced rung-G loop period | 10,122 µs | 15,412 µs | 15,658 µs | 119 | host-visible replay period (~10 ms) |

- **Jitter is only partially characterized:** tail maxima (58 µs vs 32 µs median; 50 µs vs 4 µs median) exist, but there is no distribution/std/worst-case-bound analysis. **[HW]** for the min/median/p99/max; **[DESIGN]** for any rigorous jitter bound.
- The fabric PID is an **II=1 pipeline by construction** (`hls/src/nv_pid.cpp`); the "<150 µs safety-loop latency" in `README.md:82` and the "<150 µs guarantee" in `libero/scripts/03_smartdesign.tcl` are **design targets, never measured** (`03_smartdesign.tcl` is additionally flagged as a stale scaffold). **[DOCS/MODEL]**. The doc's own next step: a true fabric-latency claim needs a hardware cycle counter latched from `acc_start` to actuator-valid, or a post-layout timing sim — **neither done**.

### 3.3 Bounded-AI guarantees

**Practical guards demonstrated [TB/HW]; formal certificate = does not exist [DOCS].**

- **What is real:** the sector clamp (±4.5% immutable outer), slew limiter, and watchdog/bumpless transfer **bound the AI output magnitude and rate** — implemented, unit-tested (§3.1), clamp-saturation shown on silicon. This is a *practical* guard.
- **What is NOT real:** any formal stability/robustness certificate. `docs/nn_sector_certificate_plan_2026-06-21.md:5` (verbatim): *"PARTIAL research setup only. No sector, Lipschitz, IQC, or closed-loop certificate was produced in this pass."* Formal NN-in-loop stability *"is still a residual proof obligation"* (`:7`). The verification tools (α,β-CROWN, auto_LiRPA, LipSDP, Marabou) are listed as **leads, never run**; the only artifacts are frozen model hashes (float `e0c31426…`, INT8 `e3b55da9…`). `README.md:130`: the mechanisms *"do not constitute a proof that the AI cannot destabilize the loop."* `docs/safety_architecture.md` lists **six Residual Proof Obligations, ALL OPEN** (plant-model ID, ZOH phase margin, transport-delay bound, derivative-filter SI, ReLU/NN sector verification, workload-driven SmartPower). **[DOCS]**.
- **Do not say "verified by the verification workbench."** TVW is an LLM **document** audit (§4.5); it retrieved the report's own prose and rated it "supported." It does **not** verify the safety bound, HLS→RTL equivalence, or INT8 equivalence, and its own critic-independence gate failed.

### 3.4 Power draw

**Estimate only — [MODEL], and even the estimate is unbacked as a headline.**

- README table: FPGA fabric **2,664 mW**, total system **~5.2 W**, SWaP budget **12 W**, margin **~57%** — all labeled "default-toggle estimate" (`README.md:181-190`).
- **The 2,664 mW headline traces to an *acceptance target in an explicitly unexecuted plan*:** `libero/constraints/LOAD_CRASH_FIX_PLAN.md:224,235` ("within ±5% of 2,664 mW"), with `:10` stating *"Nothing here has been executed."* **[DOCS/aspirational]**.
- The actual SmartPower run (2026-06-21, uncommitted) is **vectorless/default-activity**: Total **2,622.855 mW**, Static 445.612 mW, Dynamic 2,177.243 mW — with *"no annotation log/result produced,"* i.e. **not workload-driven**. **[MODEL]**.
- **No VCD-annotated (workload) SmartPower and no on-board power measurement exist anywhere.** Workload-driven SmartPower is an open Residual Proof Obligation. `smartpower_report.rpt` is regenerated per synthesis, not committed.

### 3.5 Logic utilization

**Tool P&R report [MODEL]; the shipped-image full table is a GAP.**

| Design | Numbers | Source | Tag |
|---|---|---|---|
| **Base design** (committed P&R, % of MPFS250T) | 4LUT **62,837/254,196 = 24.7%**, DFF 25.2%, uSRAM 18.5%, LSRAM 11.8%, Math/DSP **164/784 = 20.9%** | `libero/reports/MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_resources.rpt` | [MODEL] (P&R, older base) |
| **seed_7 rung-A** (the 2026-06-15 programmed bitstream) | +0.274 ns worst slack, **25.88% 4LUT** | `docs/track0_bringup_runbook.md:16` | [MODEL] |
| **Two-slot** (shipped lineage) | **109 DSP / 54,491 LUT** — a **synthesis-survival gate note only**, no full post-layout util table (no LSRAM/reg/% breakdown) | `libero/reports/2026-06-17-two-slot/README.md`; `docs/two_slot_register_map_2026-06-17.md:91` | [MODEL], incomplete |

- **Landmines:** committed util reports carry an internal **FCVG1152-vs-FCVG484** package-label inconsistency (die totals identical, so percentages hold, but a reviewer will notice). **Do not confuse external comparables** cited in `docs/remediation_roadmap.md` (e.g. V500-on-MPFS250T 18.35% LUT4 / 19.11% DFF / 22.45% Math; V250 MobileNet-v1 37 ms / 27 FPS) with this design's numbers — those are **external datasheet/benchmark figures**, not measurements of this system.

---

## 4. Per-repo capability + number inventory

### 4.1 polarfire-hybrid-control

| Capability / number | Source | Tag |
|---|---|---|
| Programs Production MPFS250T, IDCODE `1F81A1CF`, PROGRAM PASSED ×2 committed | `libero/reports/2026-06-15-program/program.log:60-72`; `docs/two_slot_handoff_2026-06-17.md` | **[HW]** |
| V250 NN inference completes in fabric (`out[0]=-2.9506`, model `fcnn_v2_residual_dataset_a.vnnx`) | `dashboard_v250_probe_post_program.json`; `docs/rung_f_v250_on_silicon_results_2026-06-16.md` | **[HW]** |
| Two-slot decoded CSR plane (M0 gains, M1 `pid_csr`, bit-exact) | `docs/two_slot_demo_scope_2026-06-18.md:35` | **[HW]** |
| Live PID actuator tracks Kp·error; sector clamp saturates (2.0→1.0) | `docs/two_slot_handoff_2026-06-17.md:120`; `tools/rung_g_replay.py` | **[HW]** |
| Watchdog register + PID-only fallback on silicon | `docs/skeptic_qa_honest_claims.md` Q1 | **[HW]** (register/behavior); trip-time **[DESIGN]** |
| RTA (clamp/slew/watchdog/bumpless/deriv-filter) C++ testbench | `hls/tb/tb_bumpless.cpp`; `make hls-test-local` → ALL TESTS PASSED (re-run 2026-07-01) | **[TB]** (software-model) |
| Timing: two-slot r10_s29 — PID 125 MHz **+0.977 ns**, V250 200 MHz **+0.950 ns** | `libero/reports/2026-06-17-two-slot/two_slot_timing_r10_s29.rpt` (read first-hand) | **[MODEL]** (SmartTime STA); design runs on silicon **[HW]** |
| Timing: shipped 2 ms image r13_s32 — PID **+1.006 ns**, V250 **+1.050 ns** | `libero/reports/2026-06-21-watchdog-2ms/..._timing_r13_s32.rpt` (uncommitted; read first-hand) | **[MODEL]** |
| Timing: base PID path +0.728 ns (r6_s25); audit re-run +0.634 ns (r8_s27) | `tvw/audits/audit-006`; `libero/reports/2026-04-29-pid-real/...r6_s25.rpt` | **[MODEL]**; **not reproducible from current netlist** (audit-006 F-031) |
| Latency bounds (32 µs V250 start+poll; 4 µs PID MMIO; ~10 ms host loop) | `docs/latency_measured_2026-06-21.md` (uncommitted) | **[HW]**, coarse/API-level (§3.2) |
| Utilization (24.7% 4LUT / 20.9% DSP base; 109 DSP/54.5k LUT two-slot) | §3.5 | **[MODEL]** |
| Power (2.66 W fabric est / ~5.2 W system / 57% margin) | §3.4 | **[MODEL]** / aspirational |
| Cascade serving layer | `firmware/cascade_compose.c` **does not exist**; `docs/cascade_serving_design.md:113` "[The first build] produced no .job/.stp/.bit artifacts" | **[DOCS]** (not built) |
| Fabric PCIe @ `0x3000000000` | broken in 2.0.1/V250 rebuild; worked around via U-Boot `fdt set` disable | known open blocker |

**Toolchain fragility note:** the whole synthesis/P&R/program flow depends on a single Windows/Beelink Libero host; `libero/constraints/LOG_ARCHAEOLOGY_FINDINGS.md` documents a 2026-04-28 Libero project-file crash (byte-level forensics). The `+0.728 ns` headline was generated against a **now-overwritten netlist** and does not reproduce from current artifacts (audit-006 §2.2).

### 4.2 odmr-edge-ml

| Capability / number | Source | Tag |
|---|---|---|
| Unit suite 139 passed | `pytest tests/unit -q` (re-run this session) | **[TB]** |
| Deployed model: `fcnn_v2_residual_dataset_a`, fully-conv, ReLU, **2,905 params**, INT8 | `models/fcnn_v2.py`; instantiated this session | **[TB]** (README "~3.3K" is imprecise) |
| Trained **100% synthetic**, 20–70 µT **longitudinal-only** (`b_perp=0`), 40k/5k/5k | `production_50k_v2_aic/manifest.json` | **[MODEL]** |
| **Deployed benefit: INT8 clamped MAE 22.38 µT vs PID 23.54 µT = 4.90% reduction** (on synthetic AIC test) | `experiments/fcnn_v2_int8_float_equivalence_2026-06-21.json` (untracked) | **[MODEL]** (synthetic, not lab-validated) |
| Absolute residual after ML ≈ **22 µT ≈ 49% of the ~45 µT mean field** | same | **[MODEL]** |
| θ-binned: model is **worse than PID at "easy" bins** (bin0 4.07→5.11 µT) | `phase_c_comparison_table.csv` (tracked) | **[MODEL]** |
| INT8 **not bit-exact** vs float (max gap 0.70 µT) | `..._int8_float_equivalence_2026-06-21.json` | **[MODEL]** |
| "54% / 96%" figures = **non-deployable v1 unclamped** (clips 97.4% of outputs) | `phase_c_comparison_table.csv` | **[MODEL]**, misleading if cited |
| Cascade (P3-11B) = **documented negative result** (does not beat monolithic) | `docs/phase2/cascade_saturation_finding.md` | **[TB]** (negative) |
| Vector/3-D BLUE fusion: residual RMS **2216 µT ≈ 97.8% of |B|**; BLUE is deterministic least-squares, not learned. ⊘ 2026-10-10: 2216 µT measured bf16-trained artifacts whose checkpoints did not reproduce their validation error; fp32-trained models give 548 µT on the same 3632 samples, still with anchors from the test labels (odmr-edge-ml `docs/vector_v1_anchor_ablation.md`) | `exports/vector_v1/vector_v1_test_eval.json` | **[MODEL]**, exploratory |
| Quantization: deployed INT8 is **TF post-training calibration, not QAT-exported** | `train_stage.py:151-160` | **[TB]** (code-path confirmed) |
| **No `.vnnx` in repo** (0 files); deployed TFLite = 7,656 bytes; `exports/` gitignored | `find . -name '*.vnnx'` → 0 | handoff to polarfire; "12.5 KB clean vnnx compile" is **[DOCS]** here |
| **No inference-latency measurement** (every "ms" figure is data-gen wall-clock) | `adev_simulation.py`, `forward_recon_eval.py` | **[DOCS]** claim, not measured |
| "NVRNet" | target/comment only — **no such class exists** | **[DOCS]** |

### 4.3 nv-sensor-sim (the data source under every ML claim)

| Capability / number | Source | Tag |
|---|---|---|
| Test suite 110 passed, 4 skipped | `pytest` (this session); 4 skips = orbit (deps uninstalled) | **[TB]** (internal self-consistency only) |
| CW-ODMR spectrum = eigenvalue diagonalization + **hardcoded phenomenological Lorentzian** (`base_contrast=0.03`, `s0=0.1`) | `adapters/simos_adapter.py:171-318,301` | **[MODEL]** |
| Docstrings advertise "Lindblad master equation / steady-state CW-ODMR" — **production path uses neither** | `simos_adapter.py:5-8` vs `:171`; `docs/architecture.md:30` | **[DOCS]** overclaim |
| ZFS ≈ 2.871 GHz reproduced (SimOS constant) | `test_resonances.py` | **[TB]** internal |
| Linewidth model (¹³C floor + P1 broadening) checks its own arithmetic, not a measured linewidth | `parameters.py:107-145`; `test_p1_linewidth.py` | **[MODEL]** |
| Flagship `production_50k_v3_vector`: **`noise_mode: deterministic`** — no OU noise; **no shot/detector/readout noise ever applied** | `.../manifest.json`; grep-confirmed absent | **[MODEL]** (clean, noiseless) |
| **Sim-vs-real validation: NONE quantitative.** No PCA in this repo; `validation/reference_comparison.py` feeds an **unexecuted notebook (0 outputs)**; committed Zenodo ref is ~0.5%-contrast smeared, repo-flagged unsuitable | grep; `experiments/01_visual_sanity_check.ipynb` | **[DOCS]** / no evidence |
| Zenodo reference data (25 spectra, real, record 7233869, Sengottuvel 2022) | `data/experimental/zenodo_odmr/*.csv` | **[HW upstream]**, unused quantitatively |
| "BLUE recovery 0 nT" figure | inverts the same geometry that made the dips → **inverse crime**, 0 nT by construction | not an accuracy result |
| Orbit stack (SGP4 `sgp4.Satrec`, IGRF `ppigrf`/IGRF-14) | real library wrappers; **deps uninstalled → all 4 tests skip**; no benchmark artifact ever produced; `orbit_trajectory()` = `NotImplementedError` | **[DESIGN]** |
| "**96.1% ADEV**" orbit-benchmark claim | **only in YAML comments**; no Allan-deviation code anywhere; v1 config self-labels its ADEV power "MARGINAL"; v2 is a commented stub | **[DOCS]** |
| Adapters QuaCCAToo / CUDA-Q / QDsiM | `NotImplementedError` stubs | **[DESIGN/DOCS]** |

### 4.4 odmr-vector-tracking (the new work) — see §5.

### 4.5 tychon-verification-workbench (the audit harness — software only)

| Capability / number | Source | Tag |
|---|---|---|
| Corpora built: `tychon-docs` 280 chunks, `tychon-code` 187 chunks | `tvw/...stage-1-process-log-rerun.txt:13`, `stage-2-build.log:23` | **[TB]** build logs |
| `tychon-code` has **0 symbols / 0 xrefs** (universal-ctags never installed) — chunk-retrieval only | `stage-2-build.log:24-25` | **[TB]** |
| LLM critic loop ran (97 claims / 374 s, etc.) | `stage-4-critic-loop.log:22-23` + 5 verdict CSVs | **[TB]** |
| **Critics that ran = fallback Ollama pair** (`qwen3-coder:30b` + `nemotron-mini`), **not** the documented NIM/Llama-3.3-70B lineup | `tvw/configs/endpoints.yaml`; `STAGES.md:13` | **[TB]** vs **[DESIGN]** for NIM/Llama |
| **Critic independence FAILED** (Stage 3: 10/10 identical; Stage 4 "disagreements" are mostly nemotron parse ERRORs) | `stage-3-verdicts-sample.csv`; `audit-001:22-24` | **[TB]** (negative) |
| Air-gap rule enforced **by config convention only** — no guard code in this repo | `endpoints.yaml` (127.0.0.1); loader is in `~/projects/skills/` | **[DESIGN]** |
| Audit punch-lists: audit-001 (11 findings, 3 CRIT) → audit-004 (0 CRIT); audit-005 (package correction); audit-006 (timing revalidation); audit-007 | `tvw/audits/*.md` | **[TB]** (real deliverables) |
| audit-007 caught the **report** overstating sensitivity ~19× ("18 pT/√Hz" → ~344 pT/√Hz) and undercounting tests (55 → 99 actual) | `tvw/audits/audit-007-soft-narrative-verification.md` | **[TB]** |
| Stages 5–9 (Llama-3.3-70B reviewer, chatbot, txt2kg, fine-tune, publish) | pending, **zero artifacts** | **[DESIGN]** |

Note: TVW HEAD is 2026-05-17 — ~6 weeks stale vs the live project; its "legitimacy ≥80%" gates were left "manual triage pending."

---

## 5. The new work (last few days) — intent and target end-state

**What it is.** `odmr-vector-tracking` (scaffolded 2026-06-29, foundation landed 2026-06-30) + the `nv-sensor-sim` time-series generator (`303b07e`, 2026-06-29) that feeds it. Goal: a **learned, sequential tracker** that keeps each NV resonance line associated to its crystallographic axis **through frequency-space crossings**, to **extend usable vector dynamic range at a fixed (smaller) bias field** — success is defined *relative to bias*, never as an absolute record (`docs/design/00_problem.md`, `02_approach_and_testbed.md`).

**Intended end-state ("done").** A physics-informed tracker deployed **deployable-first** on the same PolarFire split as the FPGA repo: the per-frame INT8 feature/peak extractor on the **V250 NPU** (ops-whitelisted: Conv2d+ReLU+Linear), the recurrence + association + fixed BLUE decode on the **MSS RISC-V host** (attention/gated-RNN are V250-banned). Handoff = quantized TFLite; `vnnx_compile` is owned by `polarfire-hybrid-control` (`02_approach_and_testbed.md:29-43`). Success bar = **beat the classical baseline** below (hold lock through the crossing; push dynamic range beyond ≈bias).

**What is DONE (Increment 1) — a tested foundation [TB], on simulated data.** 74 tests pass. Reproduced first-hand by the review this session by running the repo's own code:

| Number | Value | Tag |
|---|---|---|
| Classical baseline **loses lock 16/16** at crossings | 100% | **[MODEL]** (simulated input) |
| In-collision **ID-switch error 0.811** (assoc 0.189) | 0.811 | **[MODEL]** |
| **Dynamic range 5.01 mT @ 5.0 mT bias** | ≈bias | **[MODEL]** |
| Never recovers in 11/16; assoc pre 1.00 → post 0.00 | — | **[MODEL]** |

Caveats a reviewer must be told: input is **simulated** (`nv-sensor-sim`/SimOS `sequence_sanity_v0`), not a sensor; the numbers are **not committed** (regenerated from a gitignored artifact); **CI only enforces "≥1 of 4 mock sequences degrades,"** far weaker than "16/16."

**What is NOT done.** The **learned tracker itself — the entire thesis — is an untrained skeleton with random weights**: no training loop, no loss, no optimizer, no fitted weights, no evaluation vs the baseline (`src/.../tracking/learned.py:1` docstring: *"SKELETON / INTERFACE ONLY (no training)"*). **[DESIGN]**. Deployment (Increment 3) is not started (no `exports/`, no `.tflite`, no `.vnnx`); the V250 "deployability" that passes today is a **static op-whitelist check on random-init modules**, not a compile and not silicon. **[DESIGN]**. Only the scaffold is on GitHub; the Increment-1 code lives on the internal NAS remote branch. Precision claims ("~0.35·Γ residual," "0.08% γ scatter," "~0.1% verified") are **docstring-only, no test measures them** (**[DOCS]**).

---

## 6. Weakest claims — what would not survive a sharp reviewer

Ranked by how fast a competent AFRL engineer sinks them. Lead with the honest version of each; do not let them be discovered.

1. **"Validated against real NV physics / sim-to-real."** False. **100% simulated data, zero owned-hardware data.** The one sim-vs-real check **FAILED**: PCA principal-angle **min cos = 0.009** vs ≥0.80 threshold (`06_research_inputs/pca_fidelity_zenodo_2026-05-17.md`), and the memo's own verdict is *"Do NOT cite this PCA test as sim-to-real validation… non-diagnostic"* (regime mismatch: sim 20–70 µT vs the only real dataset at ~mT). The simulator has **never been compared to a measured spectrum with a fitted residual**, its validation notebook is **unexecuted**, and its flagship dataset is **noiseless**. Everything downstream inherits an unvalidated physics model.
2. **"Real-time closed-loop AI control on the FPGA."** No. It is **host-paced, error injected via CSR (not sensed), inference run separately** from the control step. There is no fabric-resident sensor→PID→actuator loop.
3. **"~5% is the model's accuracy."** It is a **~5% *relative* MAE reduction over a weak PID-lock baseline**; the absolute residual after ML is still **~22 µT ≈ half the field**, and the model is *worse* than the baseline at easy operating points. The flashier "8.71% / 54% / 96% / bit-exact INT8" numbers belong to **abandoned or non-deployable** models/metrics.
4. **"Bounded/certified AI."** Only **practical** clamps/slew/watchdog are demonstrated. **No formal certificate exists** — the NN-sector/Lipschitz/IQC work is *"PARTIAL research setup only, no certificate produced,"* six proof obligations are open, and the tools were never run. "Verified by the verification workbench" is unsupportable — that workbench is an LLM **document** audit whose own independence gate failed.
5. **"Measured latency / <150 µs guarantee."** No end-to-end fabric latency exists. The on-kit numbers are **1 µs-resolution API/MMIO bounds, not fabric-internal, not closed-loop**; "<150 µs" is a **design target**. Jitter is not rigorously characterized. The watchdog **trip-time was never measured**.
6. **"Power / SWaP margin."** The **2,664 mW headline is an acceptance target in an unexecuted plan**; the only real SmartPower run is **vectorless (not workload-driven) ≈2,623 mW**; there is **no board-measured power**. Treat 57% margin as preliminary at best.
7. **"200 MHz timing closure."** The **PID control fabric runs at 125 MHz**; 200 MHz is the V250 core clock. Slack is positive (+0.977…+1.05 ns) but is **SmartTime STA**, the base-design headline (+0.728 ns) is **not reproducible from the current netlist**, and no seed-controlled variance was obtained.
8. **"Utilization."** Real for the base design (~25% 4LUT / ~21% DSP) but the **shipped two-slot image has only a synthesis-survival gate note, not a full post-layout table**; committed reports carry a package-label inconsistency; external V250/V500 benchmark figures must not be mistaken for this design's.
9. **Environmental / flight readiness.** **None.** Benchtop Icicle Kit over LAN only — no thermal, vibration, radiation, or flight testing. The "space-qualification" framing lives only in simulator noise parameters and a synthetic (uninstalled, unrun) orbit benchmark whose "96.1% ADEV" exists only in YAML comments.
10. **The new vector-tracking capability is aspirational.** The learned through-crossing tracker — the reason the repo exists — is an **untrained random-weight skeleton**; there is zero evidence it beats the classical baseline. Present only the classical baseline (loses lock 16/16 on simulated crossings) as demonstrated.

### What is genuinely solid (do not under-sell)
- A hybrid PID + **V250 neural-net** design that **programs and runs on Production MPFS250T silicon** (IDCODE-verified, two committed PROGRAM PASSes, inference completes in fabric). **[HW]**
- A decoded two-slot control plane + **live PID actuator with a saturating sector clamp** on silicon; two real latent RTL bugs found and fixed (ModelSim + silicon). **[HW]**
- A watchdog/bumpless-transfer RTA that is implemented and **passes a thorough fixed-point testbench** (re-run this session: all pass). **[TB]**
- Disciplined ML engineering: V250-op-clean architecture (real `torch.export` checks), a real data-contract validator, correctly diagnosed export footguns, 139/139 unit tests. **[TB]**
- **Candid self-documentation.** The repos' own artifacts — the skeptic Q&A sheet, the cascade-saturation negative result, the PCA-FAIL memo, the "retire bit-exact INT8" note, audit-006's non-reproducibility finding — catch most of the overclaims before a reviewer does. The engineering honesty is real; the *performance/validation claims* are the weak point.

### Missing / needed before this survives sharp review
Real NV-sensor data at the deployed regime (to make sim-to-real diagnostic) · a fabric-internal latency measurement (cycle counter or post-layout sim) · a measured watchdog trip event · workload-driven SmartPower + on-board power · at least one discharged formal proof obligation (or an honest "practical-guard-only" framing) · a committed post-layout utilization table for the shipped bitstream · commit the 2026-06-21 working-tree evidence so the record is auditable.

---

*Every number above is tied to a file, commit, test, or log. Uncertainties and inconsistencies are flagged in place. Where evidence was absent, this document says so rather than inferring. Tags follow §0; nothing modeled or testbench-run is reported as measured on hardware.*

---

## Addendum — 2026-07-01 easy-win execution (same day, later session)

The cheap fixes this inventory prescribed have been executed. Where the body above says "uncommitted," read it against this record:

- **§0 provenance caveat / §2.3 / §3.2 / §4.1 "uncommitted" flags — RESOLVED.** The 2026-06-21 working tree is committed on `bringup/2026-06-17-two-slot-pid` and pushed to the nas mirror: `94aec7a` (2 ms watchdog code + workload-power flow + on-kit latency tools), `75825ba` (Rung G silicon replay evidence), `c7e5fe4` (the 2026-06-21 doc set incl. `latency_measured_2026-06-21.md`), `d4e2a8e` (16 curated Libero report bundles incl. the r13_s32 PROGRAM PASS log and timing rpt). Curation: the 64 MB `libero_pnr.log` and Synplify `.srr`/`.srm` dumps are excluded via scoped `.gitignore` entries (copies remain on disk and on the Beelink); bundle READMEs summarize them.
- **§3.1 landmines — FIXED** (`a818074`): `rta_config.hpp` clock = 125 MHz (constant verified referenced by no code or test → documentation-only change; RTL untouched); watchdog comments reconciled to 250,000 @ 125 MHz = 2 ms everywhere current-state (r6_s25-era 1 ms/200 MHz retained as annotated history; 500 ms demo stays labeled host-paced; the 125,000/1 ms register-map row marked superseded). Derivative-filter clock-rate note added: baked a/β literals give effective Tf = 8 µs at 125 MHz (corner ≈19.9 kHz ≈ 6.6× above the 3 kHz bandwidth vs ~10× intent); DC gain still 1; literals kept to preserve RTL equivalence with the programmed image; exact recompute = future resynthesis item.
- **§3.5 / §4.1 package + slack landmines — FIXED** (`a818074`): README package-label explainer (Synplify mapper prints its internal `mpfs250tfcg1152std` device-DB name for all MPFS250T packages; project targets FCVG484; tool-generated reports untouched). +0.728 ns citations in living docs replaced/annotated with r10_s29 (+0.977/+0.950 ns) and r13_s32 (+1.006/+1.050 ns); CLOSURE_DELIVERABLE and frontier_comparison carry historical-record headers.
- **Dead claims — PURGED** (`d1d9716` polarfire: README 2,664 mW → actual vectorless 2,622.9 mW, <150 µs labeled design budget; `444e05c` odmr-edge-ml NVRNet → external-paper citations; `18b43f3` nv-sensor-sim Lindblad docstring/architecture corrected + 96.1% ADEV YAML status stamps; `fd29134` odmr-vector-tracking precision-figure labels). The technical report v3.4 needed **no** purge edits — verified already carrying the honest framing from audits 004–007.
- **Sibling evidence committed:** odmr-edge-ml `6827e3f`/`99014d9` (INT8-equivalence artifact this inventory cites in §4.2 is now tracked; 139 unit tests re-passed at commit time); nv-sensor-sim `2ec432d` (flagship-dataset generation log as provenance).
- **Phase B measurements LANDED (same day, later):**
  - **Fabric PID latency [TB] bound** (EV-FABRIC-LATENCY → partial): 6 cycles = **48 ns** start-accept→actuator-we, constant across 128 iterations on the real two-slot RTL (`polarfire` `18bf55a`, `docs/fabric_latency_sim_2026-07-01.md`) — exactly reproduces the report's ~48 ns pipeline-fill figure. §3.2's "<150 µs is a target, never measured" now reads: simulated [TB] bound exists; on-SILICON fabric number still open.
  - **Workload-annotated SmartPower** (EV-SMARTPOWER-VCD → closed, PID-subsystem scope): Annotated Pins **1.28%**, Total **2550.042 mW** vs same-netlist vectorless 2562.215 mW on the seed7 two-slot r12_s31 netlist (`42f26ac`). §3.4 gains two provenance corrections: this was the FIRST VERIFYPOWER ever run on the actual two-slot project, and the previously-cited 2622.855 mW "vectorless rerun" came from the Microchip REFERENCE-design project per its own log header. V250/MSS remain vectorless; RPO-6 full-design closure + board power still open.
- **Still open:** measured watchdog trip-time [HW] (EV-WDT-TRIP — needs the kit plugged in; `watchdog_trip.c` + runbook staged in `389699f`). §"Missing / needed" items beyond these (real NV data, formal proof obligation, on-board power, committed post-layout util table for the shipped image) are unchanged.

---

## Addendum 2 — 2026-07-01 (evening): §5 odmr-vector-tracking Increment-1 bar INVALIDATED

A three-agent TVW design review (generator physics audit, tracker/metrics code audit, prior-art/physics skeptic; consolidated in TVW `tvw/audits/design-review-odmr-vector-2026-07-01.md`) found §5's headline metrics are a measurement artifact:

- **§5 metrics table (loses lock 16/16, "ID-switch error 0.811", DR ~5 mT @ 5 mT bias) — RETRACTED.** `ClassicalTracker`'s default `peak_min_depth=0.03` exceeds the real dataset's dip depth (0.0035–0.0076, ~0.4% contrast): the peak detector returned **zero peaks in every frame of every sequence**, the tracker never left its ground-truth t=0 initialization, and the metrics scored a frozen tracker against moving lines. Fingerprint nobody caught: in-collision accuracy == out-of-collision accuracy == 0.189 (a genuine crossing failure would separate them). Independently reproduced by two audit agents (a Kalman tracker fed through the same broken detector produces bit-identical numbers — neither ever received a measurement), corroborated by direct artifact dip-depth measurement.
- **Honest re-measurements** (same data, detector threshold fixed; evidence scripts preserved at TVW `tvw/audits/evidence-2026-07-01/`): the repo's PID baseline shows a real but much milder crossing failure (post-crossing association ~0.75 median, in-collision ~0.63, 11/16 lock losses); a textbook per-line constant-velocity Kalman + Hungarian assignment + coast-through-merge classical tracker **solves the v0 benchmark outright** (post-crossing association 1.000 median, in-collision ~0.98, 0/16 lock losses, untuned parameters). Root cause: v0's crossings are kinematically trivial — linear ramps, distinct per-axis Zeeman slopes, ~3-frame merge windows, deterministic noise-free spectra, and no line-identity cue other than the slope.
- "In-collision ID-switch error 0.811" was additionally a metric mislabel: it is the in-collision misassociation fraction, not an ID-switch statistic.
- **Consequence for §6.10:** direction unchanged (the learned tracker remains aspirational), but the supporting sentence must now read: *the published classical-failure bar was a detector-threshold artifact; re-baselining (threshold fix + competent classical comparator) is dispatched before any learned-vs-classical claim.* Neither §5 headline number should be quoted anywhere until re-derived.
- Re-baseline + eval-correctness injections dispatched to the active odmr-vector-tracking session and dataset-redesign injections to the active nv-sensor-sim session, 2026-07-01; full 30+-finding list (generator, tracker, literature/IP) in the design-review doc.

---

## Addendum 3 — 2026-07-01 (late evening): EV-WDT-TRIP CLOSED — watchdog trip-time measured [HW]

The kit was re-plugged (read-only inventory: polarfire `docs/kit_replug_inventory_2026-07-01.md`,
`84b3f6c` — connectivity/COM mapping unchanged, 2 ms image confirmed resident by CSR signature,
no reprogram) and the staged `389699f` tooling executed per the runbook:

- **Watchdog clear→trip time [DESIGN] → [HW]:** median **2.000 ms** over **N=120** events
  (min 1.978 / p95 2.003 / p99 2.026 / max 2.032 ms), every `trip_count_delta=1`; equals the
  250,000-cycle @ 125 MHz design value at the 1 µs rdtime resolution; distribution tails match
  recorded observer poll gaps (4–39 µs Linux preemption, both directions). Stimulus one-shots
  reproduced the 2026-06-21 smoke bit-identically (`nn_out0=-2.538894653`, ~33 µs V250).
  Evidence: `libero/reports/2026-07-01-watchdog-trip/` + `docs/watchdog_trip_measured_2026-07-01.md`
  (polarfire commit `7661322`); README + skeptic Q&A upgraded off the stale 500 ms host-paced
  framing; fix-list row `EV-WDT-TRIP` → **closed**.
- The Addendum-1 "Still open" list shrinks accordingly: measured watchdog trip-time is no longer
  open. On-board power was probed the same evening and is a hardware no-go on this kit
  (PAC1934 electrically absent on all I²C buses — see the re-plug inventory doc); it stays on
  the open list as a board-level item, now with a concrete root-cause note.

## Addendum 4 — 2026-07-02: EV-MSS-PACED CLOSED — kit-resident MSS-paced loop measured [HW]

On the same resident 2 ms golden image (no reprogram; `csr_version=0x00010000`; stimulus
one-shot reproduced `nn_out0=-2.538894653` bit-identically), the on-kit `v250_pid_loop --daemon`
was measured as a standalone closed loop and then left running as the item-3 soak:

- **Sustained MSS-paced rate [HW]:** **3329.8 Hz** (per-sample 3321.4–3338.1 Hz, ±0.5 %) over
  **14.6 min / 2 911 944 steps**, proven by distinct monotonic counters — the fabric
  `axi_write_count` CSR advanced `8 735 832 = 3 × steps` **exactly** (not wall-clock division).
  Free-running ceiling ≈ 9.07 kHz; the soak config keeps the live-state JSON on tmpfs because
  an eMMC live-state throttles the loop to ~536 Hz and straddles the 2 ms watchdog (~165 trips /
  12 s), whereas tmpfs runs ~3.3 kHz with the watchdog held cleared.
- **Laptop-disconnected continuity [HW]:** across a 13.4-min window in which the host issued
  zero ssh/scp, the loop advanced ~2.75 M iterations standalone and an on-kit heartbeat logged
  ~26 autonomous, wall-clock-stamped samples to eMMC (`/root/bringup/mss_paced/heartbeat.log`);
  both processes were alive on reconnect; counters monotonic. Watchdog: 1 transient trip in
  2.91 M steps (recovered), MemFree flat, summarizer VERDICT=PASS.
- **Boundary UNCHANGED:** the loop is MSS software (not fabric-resident) and the input is a
  replayed vector (not a live sensor) — both remain NOT-YET-SHOWN. This upgrades the demo from
  *host-paced over SSH* to *kit-resident MSS-paced standalone*, nothing more.
- Evidence: polarfire `libero/reports/2026-07-02-mss-paced/` + `docs/mss_paced_loop_measured_2026-07-02.md`;
  tools `firmware/linux/mss_paced_heartbeat.sh` + `mss_paced_soak_summary.sh`; fix-list row
  `EV-MSS-PACED` → **closed**. The identical daemon config then ran as the item-3 daytime soak
  and **PASSED at 8.01 h (harvested 19:15Z): 95,681,736 steps monotonic, 3318.9 Hz sustained,
  5 transient trips / 95.7 M steps (0.05 ppm) all recovered by the 2 ms fabric watchdog,
  memory flat, Δaxi = 3×steps exact** — against criteria pre-registered in the log header
  (polarfire `libero/reports/2026-07-02-mss-paced/heartbeat_8h.log` + `soak_summary_8h.txt`,
  commit `311263a`).
