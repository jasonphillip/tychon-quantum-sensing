> Original: claude.ai project document, created 2026-04-30. Edited for publication: names of other people and business details removed.

# Tychon AI — Decision Log

**Document version:** 1.1  
**Started:** March 11, 2026  
**Last revised:** April 30, 2026 (added DLOG-033 through DLOG-036 covering r6_s25 closure, audit gate calibration, safety claim retraction, and follow-on HDL prototypes)  
**Author:** Jason Phillip  
**Plan:** 90-day build plan  
**Purpose:** Single chronological record of every research finding, architecture decision, and engineering choice made during execution. Source material for the Final Technical Report Section 2 ("Technical Approach — tools adopted, architecture decisions, what changed since the original plan").

---

## How to Use This Document

- **Add entries as you go.** Every time you make a decision in a Claude/ChatGPT/Gemini session, add an entry before closing the conversation. Takes 30 seconds.
- **Copy the template** at the bottom of this file for new entries.
- **Reference this document** when writing the Final Technical Report, preparing for the kickoff, or onboarding a new LLM session.
- **This is a private document.** It contains research rationale and decision context. Keep it in your private docs directory alongside the playbook and addendum — never in a code repo.
- **When starting a new LLM session,** provide this document as context so the LLM knows what decisions have already been made and why.

---

## Phase 0: Planning Research (Feb–Mar 2026)

The following entries are reconstructed from the v4 Playbook evidence table, Fast-Track research report, Platform Addendum v4, and repo architecture decisions document. Exact dates within this phase are approximate — grouped by research session rather than calendar day.

---

### DLOG-001 | Field Landscape Research Initiated

**Date:** ~Late Feb 2026  
**Category:** Research / Field Survey  
**Triggered by:** Need to understand what changed in NV-diamond, FPGA, and quantum sensing since the original plan (August 2025)  
**Decision:** Conduct systematic multi-LLM deep research before writing any code — use Claude, ChatGPT, and Gemini independently to survey the field, then cross-reference findings  
**Rationale:** The plan was written months earlier. The quantum sensing field moves fast. Starting to code without knowing what tools, papers, and programs now exist would risk building things that already exist or missing critical developments.  
**Alternatives considered:** Just start coding from the plan as written  
**Why rejected:** Too high a risk of wasted effort and missed opportunities  
**Impact:** This research phase produced 20+ findings that fundamentally changed the execution plan (see entries below). Net timeline impact: approximately zero — time spent on research was recovered by not building things from scratch that now have open-source solutions.  
**Source:** Claude DR #1, Claude DR #2, ChatGPT DR #1, ChatGPT DR #2, Gemini DT #1, Gemini DT #2

---

### DLOG-002 | SimOS Replaces Custom Hamiltonian Solver

**Date:** ~Feb–Mar 2026 (discovered in Claude DR #1)  
**Category:** Toolchain / Physics Engine  
**Triggered by:** Field survey — SimOS (ETH Zürich Degen group) released Nov 2025  
**Decision:** Use SimOS as the core NV physics engine instead of building a custom Hamiltonian solver from scratch  
**What SimOS provides:** NV ground-state spin Hamiltonian (seven-level photophysics), ensemble ODMR simulation with temperature dependence and strain, Lindblad master equation solvers with multiple backends, stochastic time-dependent Hamiltonians, CUDA GPU acceleration via Docker  
**Rationale:** SimOS is peer-reviewed, pip-installable, GPU-accelerated, and solves exactly the physics problem we need. Building this from scratch would have taken 4–6 weeks.  
**Alternatives considered:** (a) Custom Hamiltonian solver from first principles, (b) QuACCAToo alone, (c) CUDA-Q Dynamics alone  
**Why rejected:** (a) Too slow for a 90-day sprint, (b) QuACCAToo lacks stochastic dynamics framework, (c) CUDA-Q is GPU-only and lower-level  
**Impact:** Saved ~4–6 weeks of development. SimOS becomes Layer 1 of the sensor model. QuACCAToo and CUDA-Q retained for cross-validation.  
**Source:** Claude DR #1, Fast-Track report Section 1

---

### DLOG-003 | QDsiM Identified as Noise Model Backbone (With Risk Flag)

**Date:** ~Feb–Mar 2026 (discovered in ChatGPT DR #2 and Claude DR #2)  
**Category:** Toolchain / Noise Model  
**Triggered by:** Field survey — QDsiM paper published Jan 2026  
**Decision:** Use QDsiM as the noise injection and ODMR reconstruction backbone IF code is publicly available. Fall back to SimOS with custom wrappers if not.  
**What QDsiM provides:** Seven-level NV model for CW wide-field ODMR, parameterized noise catalog (photon shot noise, laser RIN, MW power/phase noise, MW frequency jitter, temperature-dependent ZFS shifts, dephasing distributions), vector magnetic-field reconstruction  
**Risk:** No confirmed public GitHub repository as of March 2026  
**Mitigation:** SimOS is the guaranteed foundation. QDsiM's documented noise injection approach can be implemented as wrappers around SimOS using published parameter values.  
**Impact:** QDsiM's noise catalog defines the parameter distributions even if the code isn't available. The documented approach is what matters.  
**Source:** ChatGPT DR #2, Claude DR #2

---

### DLOG-004 | CUDA-Q Dynamics Validated for NV+P1 on Blackwell

**Date:** ~Feb–Mar 2026 (discovered in Claude DR #1)  
**Category:** Toolchain / GPU Simulation  
**Triggered by:** Field survey — AWS/NVIDIA/UW capstone project published Jun 2025  
**Decision:** Use CUDA-Q Dynamics NV+P1 demo as the GPU-accelerated reference architecture for DGX Spark  
**What was demonstrated:** NV center with coherently coupled ¹³C and ¹⁴N nuclear spins and incoherent P1 spin bath, running on Blackwell GPUs with 64% runtime reduction vs prior generations  
**Rationale:** This is our exact physics problem running on our exact hardware. No need to prove GPU feasibility — it's already been demonstrated.  
**Impact:** De-risks GPU simulation path entirely. Confirms DGX Spark as the right platform.  
**Source:** Claude DR #1, Fast-Track report Section 1

---

### DLOG-005 | VectorBlox SDK v3.0 Release Eliminates Compilation Risk

**Date:** Feb 10, 2026 (discovered across all research reports)  
**Category:** Toolchain / FPGA Deployment  
**Triggered by:** Microchip released VectorBlox SDK v3.0  
**Decision:** Target VectorBlox v3.0 for all neural network deployment. Design architectures using ONLY v3.0 supported ops.  
**Key constraint:** No separate CONV_1D operator. Must implement 1D convolutions as CONV_2D with kernel shape (1×k) on reshaped tensors. Safe ops: CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, RELU/RELU6, ADD (residuals), MEAN (global avg pooling).  
**Rationale:** Concrete supported-op list eliminates the risk of training a model that can't compile to hardware.  
**Impact:** VectorBlox ops compatibility guard (ops_guard.py) becomes a mandatory pre-training check in Repo 2.  
**Source:** All research reports, Fast-Track report Section 2

---

### DLOG-006 | Dual MLP + CNN Architecture Strategy Adopted

**Date:** ~Feb–Mar 2026 (triggered by Claude DR #2 finding NIST benchmark)  
**Category:** Architecture / Neural Network  
**Triggered by:** NIST quantum state benchmark (Zwolak et al., Nov 2025, arXiv:2511.22451) — CNNs gave best accuracy-per-parameter tradeoff, MLPs were most computationally efficient. Complex architectures that excelled on synthetic data FAILED to generalize to experimental data.  
**Decision:** Implement both an MLP and a 1D-CNN in parallel, then select the best performer based on compilation success and generalization  
**Architecture A (MLP):** 2-3 hidden layers, 128-256 neurons. FULLY_CONNECTED + RELU only. Expected inference <0.1 ms.  
**Architecture B (1D-CNN):** 2-4 conv layers with depthwise-separable convolutions, residual connections, global average pooling. Target <1,000 parameters post-pruning.  
**Rationale:** The NIST finding that complex architectures fail synthetic-to-real transfer is directly relevant to our risk. Two architectures gives us two shots. The lightweight 1D-CNN paper (Feb 2026 MDPI Electronics, 3,121→358 params with INT8 QAT) validates the CNN approach.  
**Impact:** Both architectures designed from Day 1 to compile cleanly on VectorBlox v3.0.  
**Source:** Claude DR #2 (NIST benchmark), Claude DR #1 (lightweight CNN paper)

---

### DLOG-007 | Noise Injection Changed from Post-Processing to Coupled Stochastic (v4 Critical Change)

**Date:** ~Mar 2026 (v3→v4 playbook revision)  
**Category:** Physics / Sensor Model Architecture  
**Triggered by:** Physics review during v3.1→v4 playbook update  
**Decision:** Inject stochastic noise parameters (temperature fluctuations, MW power/phase variations) directly into the SimOS time-dependent Hamiltonian via StochasticLiouvilleParameters and stochastic_evol APIs, instead of layering them on as independent post-processing  
**What the v3 approach did wrong:** Treated noise sources as independent. Temperature affects both the zero-field splitting D AND the spin-lattice relaxation T1. MW power fluctuations alter the Rabi frequency AND induce localized heating. Independent post-processing misses these cross-couplings entirely.  
**Implementation:** Parameterize T(t) and MW amplitude B1(t) as Ornstein-Uhlenbeck stochastic processes drawn from QDsiM-defined distributions. Pass as time-dependent Hamiltonian parameters to stochastic_evol.  
**Rationale:** Physically more accurate. The Lindblad master equation captures state-mixing and cross-couplings inherently when the noise enters at the Hamiltonian level.  
**Impact:** More realistic synthetic training data → better CNN generalization. Zero timeline impact — absorbed into Days 7-30.  
**Source:** v4 Playbook (critical v4 change), physics review

---

### DLOG-008 | Surface Noise Model Removed (v4 Change)

**Date:** ~Mar 2026 (v4 playbook revision)  
**Category:** Physics / Sensor Model Scope  
**Triggered by:** Physics review — Nagura et al. surface noise model analysis  
**Decision:** Remove the surface noise model (DFT-derived Lindblad jump operators for surface spin interactions) from the sensor model  
**Rationale:** Surface noise is physically relevant only for shallow NV centers at depths <20 nm. Our sensor uses a macroscopic bulk diamond ensemble where >99.99% of NV centers are deeply embedded. Surface states have negligible impact on the ensemble ODMR lineshape.  
**Impact:** Saves ~2 days of DGX simulation time with zero loss of physical fidelity.  
**Source:** v4 Playbook (v4 change), physics review

---

### DLOG-009 | Asymmetric Lineshape Generation Added (v4 Addition)

**Date:** ~Mar 2026 (v4 playbook revision)  
**Category:** Physics / Training Data Realism  
**Triggered by:** Physics review — real bulk diamond CW ODMR spectra are asymmetric, not symmetric Voigt profiles  
**Decision:** Add two corruption parameters to every generated synthetic spectrum: (a) spatial B1 gradient (5-30% variation), (b) transverse field injection B_perp (0-50 µT)  
**Why this matters:** A 1.5% asymmetric shift in a 2 MHz linewidth creates ~30 kHz tracking offset = ~1,000 nT of systematic measurement error. Training on symmetric-only spectra would produce a CNN that fails on real data.  
**Rationale:** Forces CNN to learn on realistic, Fano-like lineshapes rather than idealized profiles. This is a critical element of synthetic-to-real gap mitigation.  
**Impact:** Zero timeline impact — absorbed into Days 7-30. Directly improves AI Advantage 2 (asymmetric lineshape inversion).  
**Source:** v4 Playbook (v4 addition), physics review

---

### DLOG-010 | CNN Reframed from "Noise Filter" to "Nonlinear Hamiltonian Inverter"

**Date:** ~Mar 2026 (v4 playbook revision)  
**Category:** Architecture / Narrative / Technical Framing  
**Triggered by:** Physics review — realization that the CNN does NOT beat the PID by lowering broadband noise floor  
**Decision:** Reframe the entire CNN value proposition around three specific nonlinear capabilities the PID mathematically cannot handle  
**The three AI advantages:**  
1. **Heading Error Correction** — PID tracks shifted resonance but can't detect transverse-mixing bias (~37 nT worst case). CNN maps full spectrum to true 3D field vector.  
2. **Asymmetric Lineshape Inversion** — PID uses symmetric fit on skewed profile, creating 500-1,500 nT bias. CNN does O(1) forward pass in <0.1 ms. Classical Levenberg-Marquardt achieves similar accuracy but needs 10-50 ms, violating <1 ms budget.  
3. **MIMO Degeneracy Tracking** — 4 NV orientations create 8 resonances that merge at symmetry angles. Independent SISO PID channels cross-talk and lose lock. CNN processes full spectrum as MIMO estimator.  
**Key insight:** Above the 1/f corner (~1-5 Hz), noise is quantum shot-noise limited. No digital filter or NN can predict white noise. A properly tuned PI already sits at the shot noise floor within its tracking bandwidth. The CNN's value is qualitatively different, not incrementally better.  
**Why this matters for narrative:** "Our AI suppresses noise" is vague and invites skepticism. "Our AI solves three specific nonlinear problems a PID cannot" is concrete and defensible.  
**Impact:** Changes how results are reported in the Final Technical Report. Lead with heading error correction, frame asymmetric inversion as latency argument, be transparent about shot noise limits.  
**Source:** v4 Playbook (core reframe), v4 Addendum Section 8 (control theory argument)

---

### DLOG-011 | Bounded Hybrid Safety Architecture Added (v4 Addition)

**Date:** ~Mar 2026 (triggered by Gemini Deep Think analysis)  
**Category:** Architecture / Safety / Reviewer Objection Mitigation  
**Triggered by:** Gemini DT analysis identified the strongest anticipated reviewer objection: NN "hallucinations" lack BIBO stability guarantees  
**Decision:** Implement a Simplex Run-Time Assurance (RTA) framework with three hardware-enforced boundaries and bumpless transfer  
**The Safety Triad:**  
1. **Sector Saturation Clamps** — AI output hard-limited to ±5% of total actuator range. AI physically cannot push plant outside PID capture range.  
2. **Slew-Rate Limiting** — du_AI/dt clamped in hardware. Step hallucinations become slow ramps.  
3. **Execution Watchdog** — FPGA counter monitors VectorBlox AXI bus. If inference >1.0 ms, AI feedforward decoupled for that cycle.  
**Bumpless Transfer:** On AI fault, FPGA executes I_new = I_old + u_AI_old. Zero voltage change at actuator. Classical PI smoothly assumes full load.  
**Formal framing:** Nonlinear Lur'e Problem, Circle Criterion, Absolute Stability  
**Precedents:** NASA IFCS F-15, Air Force Auto-GCAS  
**Rationale:** Addresses the strongest reviewer objection preemptively. Makes the system certifiably safe regardless of CNN behavior.  
**Impact:** Added to FPGA implementation deliverable and Final Technical Report.  
**Source:** Gemini DT #1, v4 Playbook, v4 Addendum Section 3

---

### DLOG-012 | Cross-Sensor Platform Positioning Validated

**Date:** ~Mar 2026 (triggered by Claude DR #3 + Gemini DT physics analysis)  
**Category:** Strategy / Technical Scope  
**Triggered by:** Gemini DT physics analysis confirmed transfer feasibility  
**Decision:** Position Tychon as a cross-sensor quantum control platform, not just an NV magnetometer controller  
**Transfer feasibility (per Gemini DT):**  
- Direct transfer (retrain only): Alkali OPMs, Rydberg DC metrology  
- Partial transfer (input layer refactoring): CSAC, SERF  
- Excluded (requires architectural extension): Cold-atom  
**Rationale:** Every sensor company surveyed uses AMD/Xilinx FPGAs — Microchip RT PolarFire offers vendor diversification. Honest scoping (excluding cold-atom) strengthens credibility.  
**Impact:** Changes ICD (adds sensor abstraction layer) and CONOPS (adds multi-sensor payload paragraph).  
**Source:** Claude DR #3, Gemini DT #1, v4 Playbook, v4 Addendum Sections 1-2

---

### DLOG-014 | >10× Noise Suppression Claim Scoped to Drift Band Only

**Date:** ~Mar 2026 (v4 playbook revision)  
**Category:** Metrics / Claim Scoping  
**Triggered by:** Physics review — realization that >10× broadband is physically impossible (shot-noise limited above 1/f corner)  
**Decision:** Scope the >10× noise suppression KPP to the sub-0.1 Hz drift band only, where the CNN's advantages (heading error correction, thermal drift compensation) actually operate  
**Rationale:** A properly tuned PI already sits at the shot noise floor within its tracking bandwidth. Claiming broadband suppression invites reviewers to correctly call it out. Scoping to the drift band is both honest and achievable — Q-CTRL published >11× improvement in field trials (MagNav.jl, Apr 2025), validating the target.  
**Impact:** Changes how the 5-metric evaluation stack reports results. Allan deviation and heading error sweep become the primary evidence.  
**Source:** v4 Playbook, physics review

---

### DLOG-015 | Published Noise Parameters Used Instead of First-Principles Derivation

**Date:** ~Mar 2026  
**Category:** Physics / Development Efficiency  
**Triggered by:** Scope reality check — one person, 90 days  
**Decision:** Use published, peer-reviewed noise parameter values instead of deriving from first principles  
**Key parameters:**  
- P1 bath: Lorentzian PSD, Δ ~1-7 MHz, τ_c ~5-50 µs (CCE study arXiv:2503.05404)  
- Thermal drift: dD/dT ≈ −74.2 kHz/K (textbook), modeled as Ornstein-Uhlenbeck  
- SBQuantum space qual data: ~400 pT/√Hz, heading errors <5 nT (arXiv:2509.19179)  
**Rationale:** Saves ~3 weeks. Published values are more defensible to reviewers than custom derivations. CCE study cited for T₂ values only — NOT for pulse-number scaling (applies to dynamical decoupling, irrelevant to CW ODMR).  
**Source:** v4 Playbook Layer 3, Fast-Track report

---

### DLOG-016 | PINN Explicitly Deferred

**Date:** ~Mar 2026  
**Category:** Architecture / Scope Control  
**Triggered by:** Literature search found no published work combining physics prior with learned model for NV-diamond ODMR  
**Decision:** Do NOT build a physics-informed neural network (PINN) for ODMR in this plan. Defer to later work.  
**Rationale:** No precedent in the literature means higher risk and longer development time. The standard CNN approach is well-validated. Deferring the PINN is lower risk than building it in this plan.  
**Source:** v4 Playbook (What NOT to Build)

---

### DLOG-017 | Repo Strategy: Sequential Build, Not Simultaneous

**Date:** Mar 11, 2026  
**Category:** Engineering / Repository Architecture  
**Triggered by:** ChatGPT generated a plan to scaffold all three repos simultaneously  
**Decision:** Build repos sequentially — Repo 1 (tychon-nv-sim) first, Repo 2 (tychon-odmr-ml) parked as spec in Repo 1 docs, Repo 3 (tychon-polarfire-control) deferred entirely  
**Rationale:** One person. Can't context-switch across three repos. Repo 2 depends on Repo 1's dataset manifest. Repo 3 depends on Repo 2's trained models. Sequential execution matches the dependency chain.  
**ChatGPT's original plan:** All three repos scaffolded on Day 1 with deep file trees (~50+ files each)  
**What we kept from ChatGPT:** Three-repo split naming, adapter pattern, dataset manifest contract, VectorBlox ops guard  
**What we rejected:** Simultaneous scaffolding, deep initial file trees, CI pipelines on Day 1, pre-commit hooks on Day 1  
**Source:** Repo architecture decisions doc (Appendix A)

---

### DLOG-018 | Adapter Pattern Mandated for All External Dependencies

**Date:** Mar 11, 2026  
**Category:** Engineering / Software Architecture  
**Triggered by:** Multiple uncertain external dependencies (SimOS, QuACCAToo, CUDA-Q, QDsiM)  
**Decision:** Wrap ALL external physics libraries behind adapter interfaces with explicit NotImplementedError stubs  
**Rationale:** SimOS might have API changes. QDsiM code might not exist. CUDA-Q requires specific GPU hardware. Adapters allow: (a) swapping backends without touching pipeline code, (b) CPU smoke paths that work without any vendor toolchain, (c) clean testing against mock data  
**Constraint:** CPU smoke paths are mandatory — every pipeline must have a mode that runs without CUDA, Julia, vendor compilers, or QDsiM  
**Source:** Repo architecture decisions doc Section 2

---

### DLOG-019 | Lönard et al. Fast Spectrum Generation for Bulk Data

**Date:** ~Mar 2026  
**Category:** Toolchain / Performance Optimization  
**Triggered by:** Need to generate 50,000+ training spectra efficiently  
**Decision:** Use Lönard et al. analytical formulas (arXiv:2504.20750) for bulk spectrum generation, full Hamiltonian diagonalization for validation only  
**Rationale:** Analytical formulas provide exact resonance frequencies and Voigt profiles at orders of magnitude faster than numerical diagonalization. Full SimOS Hamiltonian for validation ensures the fast path doesn't introduce errors.  
**Source:** Fast-Track report Section 1, v4 Playbook

---

### DLOG-020 | Heading Error Sweep Added to Evaluation (v4 Addition)

**Date:** ~Mar 2026  
**Category:** Evaluation / Simulation Design  
**Triggered by:** Heading error correction identified as primary AI advantage (DLOG-010)  
**Decision:** Add a required 2D rotational field sweep simulation — continuous 360° rotation of 50 µT background field within {110} crystallographic plane  
**What this tests:** Passes through symmetry angles triggering PID degeneracy failures, varies B_perp continuously mapping full heading error profile, provides single visually compelling plot showing PID loss-of-lock vs continuous AI tracking  
**Impact:** Adds 1-2 days in Days 55-65. Produces the single most important figure for the Final Technical Report.  
**Source:** v4 Playbook (required simulation)

---

### DLOG-021 | SmartHLS for PID, Not Custom Verilog

**Date:** ~Mar 2026 (validated by Claude DR #2)  
**Category:** Toolchain / FPGA Implementation  
**Triggered by:** Claude DR #2 found SmartHLS motor control example validates C++→PID→PolarFire path  
**Decision:** Implement PID controller via SmartHLS C++ targeting RTPF500ZT, not hand-written Verilog  
**Rationale:** SmartHLS generates standard AXI IP cores. Motor control reference design proves the PID-on-PolarFire path works. Achieves ~2 µs latency, giving 600×+ margin against <150 µs target.  
**Fallback:** OpenCores PID Verilog module if SmartHLS path fails  
**Source:** Claude DR #2, v4 Playbook Deliverable 3

---

### DLOG-025 | Five-Metric Evaluation Stack Defined

**Date:** ~Mar 2026  
**Category:** Evaluation / Metrics  
**Triggered by:** Need for rigorous comparison between hybrid AI loop and PID baseline  
**Decision:** Evaluate using five metrics: (1) classification accuracy (>99%), (2) noise suppression ratio (>10× in drift band), (3) heading error reduction (>50%), (4) Allan deviation stability, (5) heading error profile from rotational field sweep  
**Anti-inverse-crime protocol:** Evaluate Metrics 1-4 on held-out test set with DIFFERENT random seeds AND different noise parameter distributions (shifted means, wider variance). Evaluate Metric 5 using Zenodo ODMR dataset characteristics injected into real SGL 2020 flight data.  
**Source:** v4 Playbook Deliverable 2

---

## Execution

*Entries added during execution. Decisions below were made in Gemini Deep Think sessions (March 26-27, 2026) and Claude review/consolidation sessions (March 27 – April 1, 2026).*

---

### DLOG-026 | VectorBlox SDK v2.0.x Pinned — v3.0 Excluded for this plan

**Date:** 2026-03-27  
**Category:** Toolchain / Architecture  
**Triggered by:** Gemini Deep Think Repo 3 architecture analysis identified version mismatch risk  
**Decision:** Pin VectorBlox SDK to v2.0.3 across Repos 2 and 3. Exclude SDK v3.0 entirely for this plan.  
**Rationale:** CoreVectorBlox IP in MegaVault is v2.0.1. Major SDK version bumps (v2→v3) frequently alter the .vnnx intermediate representation, header magic numbers, operator support, or V-ISA instruction set. Using SDK v3.0 to generate binaries for IP core v2.0.1 creates risk of silent AXI bus deadlocks or hard faults. Re-evaluate when Microchip releases matching v3.x IP.  
**Alternatives considered:** Use SDK v3.0 (latest release, Feb 10 2026)  
**Why rejected:** No confirmed compatibility between SDK v3.0 and CoreVectorBlox IP v2.0.1. Risk of silent failures outweighs potential new operator support.  
**Impact:** Propagates to Repo 2 export pipeline — `vnnx_compile` must use v2.0.3. Updated beelink snapshot, toolchain reference, and both repos' CLAUDE.md files.  
**Source:** Gemini DT Repo 3 architecture analysis, Claude review

---

### DLOG-027 | Bare-Metal C on MSS — Linux Excluded

**Date:** 2026-03-27  
**Category:** Architecture / RTOS  
**Triggered by:** Gemini Deep Think Repo 3 architecture analysis  
**Decision:** Use bare-metal C (no OS) on the RISC-V MSS. Exclude Linux.  
**Rationale:** Linux kernel scheduling jitter (~ms scale) violates the <150 µs deterministic PID loop guarantee. Bare-metal eliminates OS overhead and provides fully deterministic execution. The MSS only needs to configure VectorBlox and PID registers at boot, then the fabric runs autonomously.  
**Alternatives considered:** FreeRTOS, Linux with RT_PREEMPT  
**Why rejected:** FreeRTOS adds complexity with no benefit for this architecture (fabric is autonomous). Linux jitter is disqualifying.  
**Source:** Gemini DT Repo 3 architecture analysis, Claude review

---

### DLOG-028 | MPFS250T Primary Target, MPFS460T Fallback

**Date:** 2026-03-27  
**Category:** Architecture / Hardware Target  
**Triggered by:** Need to select the synthesis target within Silver license scope  
**Decision:** Target MPFS250T (Icicle Kit) for this plan. MPFS460T as fallback if resource estimation shows insufficient headroom for CoreVectorBlox V250.  
**Rationale:** Both are covered by the free Silver license. MPFS250T is the smallest SoC; V250 is the smallest CoreVectorBlox preset. If they fit together, a later move to RTPF500ZT (which has 481K LEs vs 254K) is guaranteed. If MPFS250T is too small, MPFS460T still proves the architecture within Silver license.  
**Open question:** Need to run resource estimation after `02_import_ip.tcl` to confirm fit.  
**Source:** Gemini DT Repo 3 architecture analysis, Microchip toolchain reference

---

### DLOG-029 | 3D B-Field Vector Dataset — Replace 1D Bz-Only

**Date:** 2026-03-27  
**Category:** Physics / Dataset Design  
**Triggered by:** Gemini Deep Think 3D dataset analysis identified that 1D (Bz-only) datasets cannot train heading error correction  
**Decision:** Generate full 3D B-field vector datasets. Sample in spherical coordinates for uniform solid-angle coverage, label in Cartesian [Bx, By, Bz] for smooth loss landscape.  
**Rationale:** The heading error correction (KPP metric) requires the CNN to detect ~0.3° angular deviations of Earth's field (~50 µT) on top of a 10 mT bias magnet field. This is inherently a 3D vector problem. 1D Bz-only data cannot train this capability.  
**Key corrections from review:** (1) Do NOT Z-score normalize labels — breaks cosine similarity loss. µT scaling is sufficient. (2) Remove `b_perp` as independent corruption parameter — it's now part of the 3D field vector. (3) Enforce Bz ≥ 0 hemisphere constraint.  
**Impact:** Requires updates to Repo 1's `batch_generate.py` to sample full 3D vectors. Repo 1 Hamiltonian solver already handles 3D — only the batch generation script needs changes.  
**Source:** Gemini DT 3D dataset design, Claude review (gemini-dt-3d-dataset-design-reviewed.md)

---

### DLOG-030 | SmartHLS PID Code Reviewed — Two Safety Components Missing

**Date:** 2026-03-27  
**Category:** Engineering / Safety Architecture  
**Triggered by:** Claude review of Gemini Deep Think SmartHLS PID implementation  
**Decision:** Adopt Gemini's PID code as scaffold starting point. Two missing safety components (sector saturation clamps, slew-rate limiter) must be implemented in `safety_clamps.cpp` before any claims about safety architecture compliance.  
**What's correct:** Bumpless transfer algorithm (I_new = I_old + u_AI_old), AI-as-feedforward architecture, watchdog rising-edge detection, Q34.30/Q16.16 fixed-point analysis, II=1 pipelining.  
**What's missing:** (1) Sector saturation clamps — ±5% of actuator range on AI output, per Addendum §3.1. (2) Slew-rate limiter — du_AI/dt clamped per cycle, per Addendum §3.1.  
**Additional concern:** SmartHLS pragma syntax needs verification against 2025.2 docs on Beelink. Architecturally correct but syntax may have shifted.  
**Source:** Gemini DT SmartHLS PID, Claude review (now consolidated in tychon_repo3_scaffold_spec.md §7)

---

### DLOG-031 | Beelink FPGA Machine Configured

**Date:** 2026-03-26  
**Category:** Engineering / Infrastructure  
**Triggered by:** Need for x86 machine to run Libero SoC / SmartHLS synthesis (not supported on ARM64 DGX Spark)  
**Decision:** Use Beelink GTI15 (i9-285H, 64GB, Win11 Pro) as dedicated synthesis machine. DGX Spark remains source-of-truth for code; Beelink is build-only.  
**Toolchain installed:** Libero SoC 2025.2, SmartHLS 2025.2, Synplify Pro, ModelSim/QuestaSim  
**Still needed:** VectorBlox SDK v2.0.3 clone, Python 3.11+, tools in PATH  
**Cross-machine workflow:** Git push from Spark → git pull on Beelink → synthesize → push reports → git pull on Spark  
**Source:** Beelink machine snapshot (beelink-fpga-machine-snapshot-2026-03-26.md)

---

### DLOG-032 | Project Knowledge Consolidated — Repo 3 Scaffold Spec Created

**Date:** 2026-04-01  
**Category:** Engineering / Project Management  
**Triggered by:** ~20 project files accumulated over 3 weeks with contradictions and redundancies. Pre-Repo 3 cleanup needed.  
**Decision:** Consolidate gemini-dt-repo3-architecture-reviewed.md, gemini-dt-smarthls-pid.md, and Repo 3 portions of gemini-dt-vectorblox-export.md into a single `tychon_repo3_scaffold_spec.md`. Fix SDK v3.0 contradictions across beelink snapshot and toolchain reference. Update repo architecture decisions doc to v1.1. Archive stale files.  
**Impact:** Reduced project context from ~20 files to ~16 active files. Eliminated 4 contradictions (C1-C4 in cleanup plan). Created single authoritative scaffold input for Repo 3.  
**Source:** Claude project cleanup session (tychon_project_cleanup_plan.md)

---

### DLOG-033 | First Real PID-in-Loop FPGA Closure (r6_s25) — All Prior Closures Were Paper-Shells

**Date:** 2026-04-29 (closure landing 19:52 EDT)  
**Category:** Engineering / FPGA Implementation / Closeout  
**Triggered by:** External audit and red-team review converged on the finding that all closures preceding r6_s25 — including the April 2 baseline (+0.165 ns), the April 28 overlay (PRPF_009-aborted), and the April 29 r3_s22 paper-shell (+1.215 ns) — closed on a SmartDesign top in which `nv_pid_top_0` was pruned by Synplify CL168. Synplify removed the instance during optimization stage 1 because (a) `actuator_out_write_en` and `actuator_out_write_data` outputs were unbound at the SmartDesign top (`MPFS_ICICLE_KIT_BASE_DESIGN.v:1904-1905`, both bound to `( )`), and (b) `error` and `u_AI_in` inputs were tied to constants (`64'h0` and `32'h0` via `error_const_net_0` and `u_AI_in_const_net_0`). The pruned-shell numbers therefore described the integration shell, not a synthesized PID, with the entire integrator/multiplier datapath constant-folded by upstream propagation. Earlier project reports citing `inner_clamp_state_inferred_reg`, `prev_watchdog_inferred_reg`, and `cooldown_counter_inferred_reg` as RTL evidence referenced registers that did not survive into the placed netlist.  
**Decision:** Land four SmartDesign-top integration interventions in sequence to bind the PID's input/output ports to real consumers, instance the watchdog driver, defeat the gain-fold on Kp/Ki/Kd inputs, and gate the result on a CI-style synthesis audit script. Specifically:

1. **`pid_io_block_0` AXI4-Lite slave** (`hdl/pid_io_block.v`, ~250 lines, 5 RW/RO 32-bit registers, instantiated via `libero/scripts/patch_smartdesign_top.py`). Captures `actuator_out_write_data`/`_en` to a readback register; provides MSS-writable `error_input_low`/`_high` (64-bit error split across +0x08/+0x0C) and `u_ai_input` (32-bit at +0x10). Adds an LED0 OR-tap for top-level observability that defeats the prune-cascade. WVALID/AWVALID conflation bug fixed in commit `884a21e`.
2. **`watchdog_timer_0`** (`hdl/watchdog_timer.v`, ~12 lines, 200 MHz × 200,000-cycle counter with `$clog2`-derived width, instantiated via `libero/scripts/patch_smartdesign_watchdog.py`). Drives `nv_pid_top_0.ai_watchdog_timeout` from the timer's `timeout` output. The `ai_heartbeat` input is wired to `MSS_WRAPPER_1_GPIO_2_M2F_28` as a later HITL bring-up stimulus; final source will be the CoreVectorBlox `output_valid` IP-level export per HB0919 §2.4, pending follow-on SmartDesign canvas refresh on `Vectorblox_ss.v` + `FIC_0_PERIPHERALS.v` sub-components.
3. **AXI4 target tap from FIC_0 master** (`libero/scripts/patch_smartdesign_axi_target_experiment.py`). Routes `axi4target_awvalid`/`wvalid`/`awaddr[5:0]`/`wdata[63:0]` from FIC_0 master to defeat the gain-fold on Kp/Ki/Kd inputs. Same FIC_0 master tap pattern as `pid_io_block`, not address-decoded for `nv_pid_top`'s address slot — follow-on proper AXI4-Lite interconnect routing replacement is the clean fix (carry-forward below).
4. **CI synthesis audit gate** (`libero/scripts/audit_synthesis.sh`, commit `b6bc06f`). Greps `.srr` for `@W: CL168` and the `compile_netlist_hier_resources.csv` for required instance presence; aborts the pipeline pre-PLACEROUTE if either fails. Sanity-tested against the existing pruned r3_s22 `.srr` (correctly fired); r6_s25 passes.

**Rationale:** All four interventions are standard FPGA integration patterns documented in Microchip and Synplify reference material (SmartDesign User Guide on connecting unused output ports, Synplify CL168 attribute reference, AMBA AXI4-Lite specification on read/write channel handshakes, CoreVectorBlox HB0919 Output Valid path). The closeout requires post-place-and-route evidence that the synthesized PID datapath actually exists in the placed netlist; without these interventions, the r3_s22 closure was not evidence for the PID hardware.  
**Alternatives considered:** (a) Add `syn_noprune` directive to `nv_pid_top_top` — preserves the instance against CL168 but does not address the constant-folded inputs; the netlist would still constant-fold the multipliers and integrator. (b) Defer the integration entirely to follow-on and ship this plan with the paper-shell numbers, scoped honestly. (c) Wire `actuator_out_write_*` to GPIO pads or InitMon trace ports.  
**Why rejected:** (a) violates the principle of accurate reporting and is a kludge; (b) is acceptable only if (a) and the integration work both fail, which they did not; (c) loses follow-on HITL leverage.  
**Impact:** First closure in this project's history that produces post-place-and-route numbers reflecting the integrated PID compute datapath. Headline numbers (r6_s25):

- Worst slack: **+0.728 ns** on FIC_0 PLL OUT0 (125 MHz / 8 ns), critical path internal to PID integrator (`nv_pid_top_pid_integral_inferred_reg[2]:CLK → [24]:D`, delay 6.989 ns under slow_lv_ht).
- Resources: **25.90% 4LUT** (65,834), 26.24% DFF (66,713), 32.30% LE (82,102).
- Power: **2,692.88 mW** total fabric (445.61 static + 2,247.27 dynamic).
- `nv_pid_top` is the 3rd-largest instance in the placed netlist (2,390 LUTs / 1,728 DFFs / 25 MACC), behind only Vectorblox internal MSC datapath instances.
- 25 PID gain multipliers mapped to dedicated 18×18 MACC blocks (production-quality DSP mapping).
- `pid_io_block_0`: 146 LUTs / 205 DFFs. `watchdog_timer_0`: 26 LUTs / 20 DFFs.
- All clock domains pass multi-corner timing (slow_lv_lt, fast_hv_lt, slow_lv_ht). Audit gate passes (CL168=0). PRPF_009 zero across all r6_s25 logs.
- Cumulative seed budget across all 6 runs: 25, within the 25-seed ceiling.

These numbers replace the paper-shell baseline numbers in the Final technical report. All references to "+0.165 ns" / "24.72% LUT" / "84.2% ADEV" in older project knowledge files are stale.  
**Source:** `polarfire-hybrid-control` `decision-2-option-c` branch commits `b6bc06f` (audit gate), `0db2c0d`/`397994e`/`68da1d3`/`884a21e` (Task 1 prune fix, including WVALID/AWVALID conflation fix on `884a21e`), `a85b138` (Task 2 watchdog), `ba573d6`/`ba70e97` (axi_target experiment with gain-fold hypothesis confirmation), `469a5b3` (closure-watchdog wrapper `closure_with_watchdog.sh`), `30746ce`/`7dba7a0`/`812f4e5` (closure-watchdog wrapper Tcl fixes — broader scope, SYNTHESIZE-before-PLACEROUTE ordering, explicit `close_project`+exit), `9de366c` (closure deliverable). All artifacts under `libero/reports/2026-04-29-pid-real/`.  
**Verified by:** `MPFS_ICICLE_KIT_BASE_DESIGN_compile_netlist_hier_resources.csv` (per-instance breakdown), `MPFS_ICICLE_KIT_BASE_DESIGN_timing_violations_max_r6_s25.rpt` (worst-path inside PID integrator), `MPFS_ICICLE_KIT_BASE_DESIGN_power_report.xml` (per-rail breakdown), `timing_analysis_jitter_report.txt` (jitter unchanged from prior runs at 0.054 ns system / 0.135 ns PLL), `place_and_route_jitter_report.txt` (P&R-stage jitter agreement), `MPFS_ICICLE_KIT_BASE_DESIGN_iteration_summary.rpt` (single-seed closure at run 6 / seed 24).  
**follow-on carry-forward (TODO, not in scope for this plan):**

1. Real AXI4-Lite interconnect routing for `nv_pid_top_0`'s gain registers — replace the FIC_0 master tap with a dedicated AXI4-Lite slave slot at a stable base address.
2. CoreVectorBlox `output_valid` wiring to `watchdog_timer_0.ai_heartbeat` — patch `Vectorblox_ss.v` + `FIC_0_PERIPHERALS.v` sub-components to propagate the IP-level export to the subsystem boundary. (See DLOG-036: prototype HDL already drafted.)
3. Workload-driven SmartPower run — current 2,692.88 mW reflects default toggle rates; a VCD-driven run with the actual PID activity profile yields more accurate dynamic-power estimates.

---

### DLOG-034 | Synthesis Audit Gate Calibrated — BN115/MO129 Demoted, `legup_mult_*` Excluded From Coefficient Regex, Write-Then-Readback Acceptance Criterion Added

**Date:** 2026-04-30  
**Category:** Engineering / Audit Tooling / follow-on Readiness  
**Triggered by:** Review of the `audit_synthesis.sh` gate from DLOG-033 against the Microchip Synplify Pro Reference Manual, the SmartHLS User Guide, and the AMBA AXI4-Lite specification. Two false-positive patterns were identified in the existing gate, and one architectural acceptance criterion was missing. If left uncorrected, the gate would (a) reject legitimate r6_s25-style closures going forward, blocking follow-on CI, and (b) admit single-slave eavesdropping integrations as architectural proof of PID-datapath survival when they are only proof of constant-fold defeat.  
**Decision:** Re-implement the audit pipeline as `tools/audit_libero_reports.py` (entry point: `make verify-local`). Three substantive changes vs the bare `audit_synthesis.sh` gate:

1. **Speculative Synplify message IDs demoted from fail-fast to warning.** The Synplify Pro reference manual verbatim-confirms CL189, CL260, BN362 as the constant-folding cascade for unbound output ports and constant-tied inputs; CL279 (output port not connected at top) is added per the same reference. BN115 and MO129 are flagged in Microchip support material as "implementation-dependent" / "verify against local log" rather than verbatim-confirmed prune indicators. The new gate treats CL189 / CL260 / CL279 / BN362 as critical-fail and BN115 / MO129 as warnings unless `--strict-mo129` is opted in.
2. **`legup_mult_*` removed from the PID coefficient regex.** SmartHLS-generated arithmetic primitives (`legup_mult_pipelined_inst`, `legup_mult_unsigned_15_17_1_23`, etc.) are arithmetic-primitive *alternatives* that Synplify routinely removes when only one variant is wired to the live datapath; this is benign optimization, not coefficient constant-folding. The PID coefficient regex now matches only Kp / Ki / Kd / clamp limits / inner_clamp_setpoint signals.
3. **`--check-readback-contract` gate added.** Per AMBA AXI4-Lite specification on read/write transaction symmetry, software write-then-readback through the AXI4-Lite slave is the architectural proof that the targeted register is truly writable and that subsequent reads return the written value. The gate verifies that audited slaves expose readback paths for all Kp / Ki / Kd / clamp registers. The existing `pid_io_block_0` from DLOG-033 satisfies this for the captured actuator output; the follow-on two-slot CoreAXI4Interconnect canvas refresh extends it to the gain registers.

A citation linter (`tools/audit_corpus_citations.py`) verifies that all references in the audit rules and project documentation resolve to source files. Run on the closeout commit, all 62 references resolve.  
**Rationale:** A binary fail-fast gate that includes implementation-dependent message IDs and SmartHLS arithmetic-primitive names produces high false-positive rates in real netlists. A proper follow-on CI gate must distinguish verbatim-confirmed prune cascades from speculative ones, and must distinguish coefficient signals from arithmetic primitives. Separately, the architectural meaning of "PID datapath survived synthesis" is not "the instance was preserved against CL168"; it is "software can write the gain registers and read back the written values." The DLOG-033 axi_target tap defeats constant-folding (the first criterion); a real two-slot interconnect closes the second. The gate now enforces both.  
**Alternatives considered:** (a) Keep `audit_synthesis.sh` as-is — acceptable for the one-time r6_s25 gate, but the false-positive rate on SmartHLS primitives makes it unsuitable for follow-on CI; engineers would learn to ignore strict-mode failures, defeating the purpose of the gate. (b) Hand-tune the audit per false positive as encountered — reactive; would require maintaining a manual exception list that drifts from authoritative reference material over time. (c) Drop the readback-contract criterion as follow-on scope.  
**Why rejected:** (a) blocks follow-on CI on legitimate netlists; (b) drifts from authoritative documentation; (c) loses the architectural distinction between "constant-fold defeated" and "datapath software-validated."  
**Impact:**

- The audit gate from DLOG-033 (`audit_synthesis.sh`) is preserved as the gate and supersedes nothing. Follow-on work adds `make verify-local` as the richer gate: critical-fail on CL189 / CL260 / CL279 / BN362; warning on BN115 / MO129; readback-contract gate active.
- follow-on CI runs `make verify-local` as a pre-PLACEROUTE gate without false-positive rejection of SmartHLS arithmetic primitives.
- The architectural acceptance criterion for follow-on canvas-refresh deliverables is now explicit: write-then-readback through both the existing `pid_io_block` slave (actuator capture) and the new `pid_csr_block` slave (gain registers) on a CoreAXI4Interconnect with two distinct address bases (see DLOG-036).
- The this plan framing of `pid_io_block_0` and the FIC_0 master tap experiment is correctly characterized as bring-up, not production.

**Source:** `polarfire-hybrid-control` `claude/corpus-verification` branch commit `3e0ba12` (Phase A — `Makefile`, `tools/audit_libero_reports.py`, `tools/audit_corpus_citations.py`, `tools/run_beelink_verification.sh`, `.gitignore`); commit `12d263d` (Phase D — `tools/audit_libero_reports.py` column-name parser fix from Round 2 closure capture). Reference: Microchip Synplify Pro Reference Manual (CL189 / CL260 / CL279 / BN362 / BN115 / MO129); SmartHLS User Guide (`legup_mult_*` arithmetic primitive nomenclature); AMBA AXI4-Lite specification (read/write channel symmetry, WSTRB byte-strobe semantics).  
**Verified by:** Audit re-run against the `2026-04-29-pid-real` bundle: 0 critical pruning hits, 1 legitimate `output_valid` wiring issue (CD279/CD638/CL240) that the bundle inherently contains pending follow-on canvas refresh. Audit re-run against the `2026-04-30-claude-r2` fresh closure (same Beelink Libero project state, all stages OK, Timing constraints met): same classification, real-pid-evidence. Citation linter resolves 62/62 citations (`make verify-local` passes).

---

### DLOG-035 | Safety Claim Language Retracted: "Cannot Destabilize" → "Sector-Bounded Within this plan Assumptions"

**Date:** 2026-04-30  
**Category:** Engineering / Safety / Honest Framing  
**Triggered by:** Review of stability-claim language in `README.md` and `docs/safety_architecture.md` (Repo 3) against textbook references (Khalil, *Nonlinear Systems* 3rd ed.; Astrom & Hagglund, *Advanced PID Control*) and the project's Follow-on Stability Analysis. The existing "the AI component cannot destabilize the classical PID control loop, regardless of inference output" wording overstates what is provable from the evidence. The Circle Criterion result requires a sector-bounded plant model; this plan assumes "any positive gain" without identification.  
**Decision:** Walk back the strong stability claim across `README.md` and `docs/safety_architecture.md`. New language: "sector-bounded by design within the assumptions documented in `Follow-on Stability Analysis`." Accompanied by a "Residual follow-on Proof Obligations" table enumerating six items that must be discharged before any "cannot destabilize" claim is admissible:

| Obligation | Why required | Reference |
|---|---|---|
| Plant model identification | Circle Criterion needs a sector-bounded plant; this plan assumes "any positive gain" | Khalil §7 |
| Quantitative phase margin under ZOH | Sampled-data closure changes the Nyquist contour | Khalil §11; Astrom-Hagglund Ch.6 |
| Bounded transport delay verification | 1 ms watchdog is the worst case; nominal delay bound must be measured | ODMR closed-loop FPGA-PID architecture references |
| Derivative filter system identification | Unfiltered first-difference amplifies HF noise at expanded ±30% authority | Astrom-Hagglund Ch.4 |
| ReLU sector verification (NN-in-loop) | The AI block is sector-bounded only if trained weights satisfy the bound | Recent literature on sector-bounded NN feedback (2025) |
| Workload-driven SmartPower | Default-toggle estimate is an upper bound, not an operational measurement | Microchip SmartPower User Guide 2025.2 |

**Rationale:** The evidence supports "the safety chain physically bounds the AI feedforward path within stated assumptions." It does not support the unconditional claim "cannot destabilize." Walking the language back before the report goes out is defensive — strong claims that can't survive a reviewer's stability question do more damage than properly scoped claims. The follow-on Final Report deliverable explicitly tied this Lur'e/Circle Criterion result to the assumptions used; the README had drifted off that footing.  
**Alternatives considered:** (a) Keep the strong claim — risk: a reviewer with stability-theory background flags the unmodeled plant assumption, the unmodeled ZOH phase loss, or the unverified ReLU sector bound; the strong claim collapses under questioning, taking the rest of the safety narrative with it. (b) Soften only the README, keep `safety_architecture.md` unchanged. (c) Add caveats as footnotes without changing headline language.  
**Why rejected:** (a) is the failure mode this retraction is designed to prevent; (b) creates a documentation contradiction; (c) hides the caveat from the readers most likely to need it.  
**Impact:**

- `README.md` updated: safety chain mechanisms now described as "sector-bounded by design within the assumptions" with explicit pointer to the Residual Proof Obligations table.
- `docs/safety_architecture.md` updated: Residual follow-on Proof Obligations section added.
- Power claims similarly hedged: SmartPower numbers labeled "default-toggle estimates" (preliminary) until workload-driven SmartPower runs.
- Final technical report (`Tychon_Phase_I_Final_Report.docx`) already uses the careful framing — this entry brings the Repo 3 docs into alignment with the report.

**Source:** `polarfire-hybrid-control` `claude/corpus-verification` branch commit `21bce03` (Phase C — `README.md`, `docs/safety_architecture.md`, `docs/corpus_grounded_evaluation.md`, `docs/frontier_comparison.md`, `tools/run_beelink_verification.sh` spark1 fallback); commit `bb1198f` (closeout — `docs/phase1_closeout_findings.md`); commit `8fbf81b` (closeout reframe — `docs/phase1_closeout_findings.md` revised to authoritative-source citations only). Reference: Khalil §7 / §11; Astrom-Hagglund Ch.4 / Ch.6; Microchip SmartPower User Guide 2025.2; project Follow-on Stability Analysis.  
**Verified by:** Comparison against the Final technical report's Section 3 / Section 9 framing — the report and the repo docs now use consistent language.

---

### DLOG-036 | follow-on Canvas-Refresh HDL Prototyped: `pid_csr_block.v` and `vbx_pulse_gen.v`

**Date:** 2026-04-30  
**Category:** Engineering / FPGA Implementation / follow-on Prep  
**Triggered by:** DLOG-033 follow-on carry-forward items 1 and 2 (real AXI4-Lite interconnect routing for `nv_pid_top_0`; CoreVectorBlox `output_valid` to `ai_heartbeat`). Drafting these as follow-on deliverable prototypes now reduces follow-on execution risk and gives the SmartDesign canvas runbook a concrete artifact to import.  
**Decision:** Land prototype HDL on `claude/corpus-verification` branch for both follow-on carry-forward items, validated by HLS testbench but not yet by netlist re-import (the SmartDesign canvas surgery requires a Libero GUI session per Microchip SmartDesign User Guide guidance, not a regex patch — documented as a runbook).

1. **`libero/hdl/pid_csr_block.v`** — proper AXI4-Lite slave with WSTRB byte-strobe support per the AMBA AXI4-Lite specification (and per SmartHLS User Guide on `axi_target` element-aligned WSTRB rules; **note:** the SmartHLS rule applies to `axi_target` ports on HLS-generated slaves, not to hand-written CSR slaves — the CoreVectorBlox HB0919 control-slave all-or-nothing rule applies to a different signal path and must not be conflated). Full RW + status CSR set including coefficient shadows, saturation flag+counter, watchdog flag+counter, ai_active, cooldown, integrator, derivative, and pre/post-clamp values. Replaces the bring-up `pid_io_block.v` (FIC_0 master tap) from DLOG-033. Will be address-decoded at a stable base for `nv_pid_top_0`'s gain registers.
2. **`libero/hdl/vbx_pulse_gen.v`** — 2-FF synchronizer + edge detector for CoreVectorBlox `output_valid`. Per HB0919 §2.4 and the per-IP register documentation (HB0919 §361, §499, §784), `output_valid` is a level-held W1C bit; the watchdog needs a one-cycle pulse on the rising edge. The synchronizer crosses the VBX clock domain to the watchdog clock domain, with assertion-correct behavior under repeated completions (D.1), missed-then-recovered completions (D.2), and stuck-high firmware no-clear scenarios (D.3).
3. **Three new HLS edge-case tests** in `hls/tb/tb_bumpless.cpp`: D.1 (repeated completions hold AI+PID basin), D.2 (missed completion → recovery), D.3 (stuck-high `output_valid` from firmware no-clear). All three pass on Beelink real toolchain.
4. **`docs/smartdesign_two_slot_canvas_runbook.md`** — follow-on GUI procedure for canvas surgery: CoreAXI4Interconnect with two distinct address bases (one for the existing `pid_io_block` actuator capture, one for the new `pid_csr_block` gain registers), `pid_csr_block_0` instantiation, `Vectorblox_ss.v` + `FIC_0_PERIPHERALS.v` sub-component patching, re-import and re-synthesis steps. Acceptance criterion: software write-then-readback through both slaves (per DLOG-034 readback-contract gate).
5. **`libero/scripts/patch_smartdesign_pid_csr.py`** — this plan bring-up shortcut: instantiates `pid_csr_block_0` on the FIC_0 master tap (same pattern as `pid_io_block_0` in DLOG-033) so the HDL is verified end-to-end at the testbench level. Explicitly **not** the production path; the production path is the follow-on canvas refresh per the runbook.

**Rationale:** Drafting follow-on deliverables in closeout has three benefits: (a) reduces follow-on execution risk by validating the HDL against the testbench before the canvas-refresh schedule pressure begins; (b) gives the SmartDesign canvas runbook a concrete artifact to import rather than a paper specification; (c) produces a concrete claim ("the canvas-refresh deliverable has working HDL prototypes ready to import") rather than a speculative one ("we'll write the HDL later").  
**Alternatives considered:** (a) Defer the HDL drafting entirely to follow-on — acceptable but loses the schedule-risk reduction and there are no concrete prototype artifacts. (b) Force a canvas re-import in this plan to netlist-validate the new HDL — the Microchip SmartDesign User Guide indicates that CoreAXI4Interconnect canvas surgery requires GUI/Tcl object work that cannot be reliably regex-patched against design-specific object names; a 2–3 hour synthesis run wouldn't change the follow-on framing because the canvas refresh is itself the follow-on deliverable.  
**Why rejected:** (a) loses optionality cheaply available now; (b) does GUI work that's properly follow-on scope and produces no plan claim that the testbench validation doesn't already produce.  
**Impact:**

- **this plan claim:** `pid_csr_block.v` and `vbx_pulse_gen.v` are testbench-validated HDL prototypes for the follow-on canvas refresh. They are **not** netlist-validated. The Final technical report does not reference them as this plan evidence.
- **follow-on claim:** follow-on canvas-refresh deliverable has working HDL prototypes ready to import per `docs/smartdesign_two_slot_canvas_runbook.md`. Reduces later execution risk.
- **Audit gate update:** follow-on audit gate (DLOG-034) requires `pid_csr_block` and `watchdog_timer` instances present in `compile_netlist_hier_resources.csv` after canvas refresh, plus passes the `--check-readback-contract` gate.
- **WSTRB rule attribution discipline:** `pid_csr_block.v` correctly attributes WSTRB rules to the AXI4-Lite specification (with SmartHLS-specific element-alignment guidance kept separate for HLS-generated slaves and CoreVectorBlox HB0919 all-or-nothing rule kept separate for control-slave paths). This separation matters because conflating the rules produces over-strict CSR slaves that return SLVERR on legitimate AXI4-Lite-spec-compliant byte writes.

**Source:** `polarfire-hybrid-control` `claude/corpus-verification` branch commit `72dbe7c` (Phase B — `libero/hdl/pid_csr_block.v`, `libero/hdl/vbx_pulse_gen.v`, `libero/scripts/patch_smartdesign_pid_csr.py`, `docs/smartdesign_two_slot_canvas_runbook.md`, and the D.1/D.2/D.3 HLS edge-case tests in `hls/tb/tb_bumpless.cpp` — all landed in the same commit). Reference: AMBA AXI4-Lite specification (WSTRB byte strobes); SmartHLS User Guide (`axi_target` element-aligned WSTRB); CoreVectorBlox HB0919 §2.4 / §361 / §499 / §565-635 / §784 (Output Valid path, control-slave WSTRB); Microchip SmartDesign User Guide (canvas-surgery GUI requirement).  
**Verified by:** `make hls-test-local` passes D.1/D.2/D.3 on Beelink real toolchain. `make verify-local` passes audit and citation linter (62/62 citations resolve). PR #1 on `polarfire-hybrid-control` open at head `8fbf81b` with `claude/corpus-verification` → `main`, awaiting review.

---

## Entry Template

Copy and fill in for each new decision:

```
### DLOG-0XX | [Short Decision Title]

**Date:** [YYYY-MM-DD]  
**Category:** [Research / Toolchain / Architecture / Physics / Engineering / Strategy / Evaluation / Metrics / Scope Control]  
**Triggered by:** [What finding, test result, or conversation prompted this decision]  
**Decision:** [What was decided]  
**Rationale:** [Why — what evidence or reasoning led to this choice]  
**Alternatives considered:** [What else was on the table]  
**Why rejected:** [Why the alternatives didn't win]  
**Impact:** [What changed in the plan, timeline, or architecture]  
**Source:** [Which LLM session, paper, test result, or conversation]  
**Verified by:** [How you confirmed this was the right call — test results, published data, cross-validation, etc.]  
```

**Shorthand for quick entries** (when full template is overkill):

```
### DLOG-0XX | [Title]

**Date:** [date] | **Category:** [cat]  
**Decision:** [what]  
**Why:** [one sentence]  
**Source:** [source]  
```

---

## Cross-Reference: Evidence Table → Decision Log

| Playbook Evidence Table Finding | DLOG Entry |
|---|---|
| SimOS released (Nov 2025) | DLOG-002 |
| QDsiM released (Jan 2026) | DLOG-003 |
| CUDA-Q Dynamics NV+P1 demo on Blackwell | DLOG-004 |
| VectorBlox SDK v3.0 (Feb 2026) | DLOG-005 |
| NIST quantum state benchmark (MLP vs CNN) | DLOG-006 |
| Lightweight 1D-CNN on FPGA (358 params) | DLOG-006 |
| SmartHLS motor control reference | DLOG-021 |
| MagNav.jl + Q-CTRL >11× field trial | DLOG-014 |
| Published PID confirmation (3 NV systems) | DLOG-021 |
| RT PolarFire SoC engineering samples (Jul 2025) | DLOG-005 |
| Cross-sensor platform = uncontested white space | DLOG-012 |
| Bounded hybrid safety architecture validated | DLOG-011 |
| CSAC integration plan detailed | DLOG-012 |
| v4 change: Coupled noise injection | DLOG-007 |
| v4 change: Surface noise model removed | DLOG-008 |
| v4 addition: Asymmetric lineshape generation | DLOG-009 |
| v4 addition: Heading error sweep | DLOG-020 |
| First real PID-in-loop FPGA closure (r6_s25, +0.728 ns slack) | DLOG-033 |
| All prior closures were paper-shells (CL168 prune detection) | DLOG-033 |
| Synthesis audit gate calibrated for follow-on CI | DLOG-034 |
| Write-then-readback architectural acceptance criterion | DLOG-034 |
| Safety claim language retraction | DLOG-035 |
| Six Residual follow-on Proof Obligations | DLOG-035 |
| follow-on canvas-refresh HDL prototypes | DLOG-036 |
| WSTRB rule attribution (AXI4-Lite vs SmartHLS vs CoreVectorBlox) | DLOG-036 |

---

*End of document. Last updated: April 30, 2026*

