> Original: claude.ai project document, created 2026-03-09. Edited for publication: names of other people and business details removed.
> Conversation: [how the playbook was created and reviewed](../excerpts/playbook-creation-2026-03.md).

**TYCHON AI**

Execution Playbook v4

90-Day Plan

March 9, 2026

Prepared for: Jason Phillip, Tychon AI

*Sources synthesized: Original plan document (OCR'd), Claude deep research
reports #1 and #2, ChatGPT deep research reports #1 and #2, Gemini Deep
Think analyses #1 (cross-sensor physics) and #2 (ICD/safety/CSAC),
Claude deep research #3 (market intelligence), project context document*

**Reality check: You are one person executing a 90-day plan that
lists four people. Everything below is scoped to what one person with
two DGX Sparks, an x86 machine, star-tracker pipeline artifacts, and no
team can actually deliver.**

Master Timeline (Solo-Adjusted)

  ---------- ---------------------------------- ---------------------------
  **Days**   **Primary Focus**                  **Parallel Track**

  1-7        Environment setup (all tools       Kickoff prep
             installed, Spark verified,
             VectorBlox v3.0 + SmartHLS tested)

  7-30       Sensor model (SimOS + QDsiM +
             coupled noise injection +
             asymmetric lineshapes) + synthetic 
             data generator

  25-50      MLP + CNN dual architecture,       SmartHLS PID implementation
             training with realistic spectra,   
             INT8 QAT

  45-65      End-to-end simulation (hybrid loop FPGA timing analysis on x86
             vs PID), 5-metric evaluation stack machine
             incl. ADEV + heading error sweep   

  55-75      FPGA power estimation, SWaP-C      Draft ICD
             closure, safety architecture
             design

  70-90      Final Technical Report
  ---------- ---------------------------------- ---------------------------

*Net timeline impact from v3.1 physics changes: approximately zero.
Asymmetric lineshape generation and coupled noise injection absorbed
into Days 7-30. Heading error sweep adds 1-2 days in Days 55-65.
Dropping the surface noise model saves \~2 days.*

Deliverable 1: Validated NV-Diamond Magnetometer Sensor Model +
Synthetic Data Generator

**Plan commitment:** Task 1, Days 1-45. What "validated" means per
the plan: A physics-based model of the NV-diamond magnetometer with
stochastic noise models that produces synthetic ODMR spectra for CNN
training.

Exactly What You Must Build

Your sensor model has three layers:

Layer 1 --- NV Physics Engine (Hamiltonian + Dynamics)

Use SimOS as your core. It provides the NV ground-state spin Hamiltonian
(seven-level photophysics: ground triplet, excited triplet, metastable
singlet), ensemble ODMR simulation with temperature dependence and
strain, Lindblad master equation solvers with multiple backends, and
stochastic time-dependent Hamiltonians. It has CUDA GPU acceleration via
Docker images --- your DGX Sparks can run it directly.

**Install:** pip install simos

**Backend:** QuTiP 5.2.3 (pip install qutip==5.2.3, released Jan 2026)
--- includes JAX backend for GPU acceleration (benchmarked up to 100×
speedup on NVIDIA A100 for spin chain sims)

Use QuaCCAToo for cross-validation and pulse-sequence library. Pre-built
NV ground-state Hamiltonian with zero-field splitting, hyperfine
coupling, Zeeman interaction, and P1 center DEER sensing example
(Example 07).

Use the CUDA-Q Dynamics NV+P1 demo as your GPU-accelerated reference
architecture. This exact demo --- NV center with coherently coupled ¹³C
and ¹⁴N nuclear spins and incoherent P1 spin bath --- ran on Blackwell
with a 64% runtime reduction. Your physics problem on your hardware.

**Install:** pip install cudaq (ARM64 wheels for Spark)

Layer 2 --- Sensor-Level Noise Model (Coupled Stochastic Injection)

Use QDsiM as your noise injection and ODMR reconstruction backbone if
code is available. QDsiM provides a complete parameterized ODMR digital
twin with seven-level NV model for CW wide-field ODMR, parameterized
noise catalog (photon shot noise, laser RIN, MW power noise, MW phase
noise, MW frequency jitter, temperature-dependent ZFS shifts, dephasing
distributions), and complete vector magnetic-field reconstruction from
ODMR spectra.

**⚠ RISK: QDsiM has no confirmed public GitHub repository as of March
2026. Mitigation: use SimOS as the guaranteed foundation and implement
QDsiM's documented noise injection approach as wrappers around SimOS.**

**Critical v4 change --- Coupled Noise Injection:**

The v3 three-layer decomposition treated noise sources as independent
post-processing steps. This misses physical cross-couplings: temperature
affects both the zero-field splitting D and the spin-lattice relaxation
T1, while MW power fluctuations alter the driven Rabi frequency and
induce localized heating during quantum evolution. In v4, inject the key
stochastic noise parameters (temperature fluctuations, MW power/phase
variations) directly into the SimOS time-dependent Hamiltonian using the
StochasticLiouvilleParameters and stochastic_evol APIs. This ensures the
Lindblad master equation captures state-mixing and cross-couplings
inherently, rather than layering them on after the fact. QDsiM's noise
catalog still defines the parameter distributions; the change is where
those parameters enter the simulation pipeline.

**Implementation:** In your SimOS simulation loop, parameterize the
temperature T(t) and MW amplitude B1(t) as Ornstein-Uhlenbeck stochastic
processes drawn from QDsiM-defined distributions. Pass these as
time-dependent Hamiltonian parameters to stochastic_evol rather than
applying them as post-processing noise on the output ODMR spectra.

Layer 3 --- Noise Parameterization (Published Values)

DO NOT derive noise parameters from first principles. Use published,
peer-reviewed values. This saves \~3 weeks and is more defensible to
reviewers.

**P1 bath noise:**

Parameterize as Lorentzian PSD: S(ω) = Δ²·2τ_c/(1 + ω²τ_c²). Published
parameter ranges: Δ \~ 1--7 MHz, τ_c \~ 5--50 µs. CCE study
(arXiv:2503.05404) for T₂ values at 1-300 ppm P1 concentrations. Cite
this paper for its measured T₂ values at specific P1 concentrations
only; do not reference the pulse-number scaling behavior, which applies
only to dynamical decoupling protocols and is irrelevant to your CW ODMR
architecture.

**Thermal drift:**

Linear ZFS temperature coefficient: dD/dT ≈ −74.2 kHz/K (textbook
value). Model as Ornstein-Uhlenbeck process. SBQuantum space
qualification (arXiv:2509.19179): thermal cycling -65°C to +125°C for
335+ hours, \~400 pT/√Hz sensitivity, heading errors below 5 nT.

**v4 change --- Surface noise model REMOVED:**

The Nagura et al. surface noise model (DFT-derived Lindblad jump
operators for surface spin interactions) is physically relevant only for
shallow NV centers at depths below \~20 nm. Your sensor architecture
uses a macroscopic bulk diamond ensemble where \>99.99% of NV centers
are deeply embedded in the lattice. Surface states have negligible
impact on the ensemble ODMR lineshape. Removing this model saves DGX
simulation time with zero loss of physical fidelity.

**v4 addition --- Asymmetric Lineshape Generation:**

Real bulk diamond CW ODMR spectra exhibit significant asymmetric
distortions from two sources: (1) spatial gradients in the MW B1 field
across the mm-scale diamond, causing non-uniform power broadening, and
(2) transverse background field components (B_perp) that break the
secular approximation and mix spin eigenstates. A 1.5% asymmetric shift
in a 2 MHz linewidth creates \~30 kHz tracking offset, equivalent to
\~1,000 nT of systematic measurement error.

When generating synthetic ODMR training spectra via SimOS, add two
corruption parameters to every generated spectrum:

**(a) Spatial B1 gradient:** Apply a linear spatial gradient to the MW
drive amplitude across the simulated diamond volume. Draw the gradient
magnitude from a uniform distribution spanning 5-30% variation across
the diamond.

**(b) Transverse field injection:** For each training sample, add a
random transverse magnetic field component B_perp drawn uniformly from 0
to 50 microtesla (representing all possible sensor orientations relative
to Earth's field). This enters the SimOS Hamiltonian directly as
off-diagonal terms.

This forces the CNN to learn on realistic, asymmetric, Fano-like
lineshapes rather than idealized symmetric Voigt profiles.

**Fast spectrum generation:** Lönard et al. analytical formulas
(arXiv:2504.20750): exact resonance frequencies, Voigt profile fitting,
orders of magnitude faster than numerical diagonalization.

Validation Strategy

1\. Generate synthetic ODMR spectra across a parameter sweep (P1
concentration, temperature, magnetic field orientation, B1 gradient,
transverse B_perp).

2\. Compare spectral features (dip positions, linewidths, contrast)
against the Zenodo ODMR dataset and SBQuantum published data.

3\. Verify P1 bath decoherence times match the CCE study at
corresponding concentrations.

4\. Show Allan deviation stability curves match published NV
magnetometer behavior (SBQuantum: white noise to \~5 sec, then thermal
drift dominance).

5\. Cross-validate against Tsunaki et al. digital-twin paper
(arXiv:2510.14907) stability patterns.

What NOT to Build

Do NOT attempt a physics-informed neural network (PINN) for ODMR.
Extensive search found no published work combining a physics prior with
a learned model for NV-diamond ODMR signal processing. Save this for later work.

Deliverable 2: Trained and INT8-Quantized Neural Network

**Plan commitment:** Task 2, Days 30-75. Metrics promised: \>99%
state classification accuracy, \>10× noise suppression vs PID baseline,
\>50% heading error reduction vs PID baseline.

The Core Reframe: From Noise Filter to Nonlinear Hamiltonian Inverter

The neural network does NOT beat the PID by lowering the broadband noise
floor. Above the 1/f corner frequency (\~1-5 Hz), NV magnetometer noise
is quantum shot-noise limited, and no causal digital filter or neural
network can predict or cancel uncorrelated white noise. A properly tuned
PI controller already drives low-frequency error to zero and sits at the
shot noise floor within its tracking bandwidth.

The correct framing: the neural network solves three specific nonlinear
problems that a linear SISO PID controller is mathematically incapable
of handling. These are not incremental improvements; they are
qualitatively different capabilities.

AI Advantage 1: Heading Error Correction

In Earth's \~50 microtesla field, a transverse magnetic field component
B_perp mixes the m_s=0 and m_s=±1 spin eigenstates via second-order
perturbation theory. This shifts the resonance frequency by Δf
proportional to B_perp²/D. At worst-case transverse field (50 µT), this
creates \~37 nT of systematic geometric bias. A frequency-locking PID
tracks the shifted resonance perfectly but has no mechanism to detect
the transverse-mixing bias. The CNN performs multivariate nonlinear
regression, mapping ODMR spectral features plus temperature directly to
the true 3D magnetic field vector. Its hidden layers implicitly learn
the tetrahedral projection geometry and off-diagonal perturbation terms.
Expected: heading errors reduced from 30-40 nT to sub-5 nT (\>85%
reduction; report the \>50% KPP and let results speak).

AI Advantage 2: Real-Time Asymmetric Lineshape Inversion

Real bulk CW ODMR spectra are asymmetric due to spatial MW B1 gradients
and overlapping hyperfine structure. Applying a symmetric Voigt fit to a
skewed profile drags the calculated center toward the heavier tail,
creating \~500-1,500 nT of systematic bias. The INT8 CNN maps
higher-order shape features (skewness, kurtosis, shoulder asymmetry)
directly to the correct underlying field vector, bypassing
center-finding heuristics entirely. It performs this as a deterministic
O(1) forward pass in \<0.1 ms. Classical Levenberg-Marquardt achieves
comparable accuracy but requires 10-50 ms per cycle, violating the \<1
ms latency budget. The AI is not just more accurate --- it is a
latency-enabling capability.

AI Advantage 3: MIMO Degeneracy Tracking

The four NV crystallographic orientations create up to 8 ODMR
resonances. When the external field rotates to specific symmetry
orientations, multiple resonance frequencies converge and merge.
Independent SISO PID channels cross-talk, mode-hop, and lose frequency
lock entirely. This is not a tuning problem; it is a structural
limitation of independent scalar tracking. The CNN processes the full
ODMR spectrum holistically as a MIMO estimator, implicitly learning the
rigid geometric constraints of the tetrahedral axes. During degeneracy
events, the AI maintains \<5 nT tracking error while PID-based systems
experience complete loss of lock.

Dual Architecture Strategy (MLP + CNN)

Implement both an MLP and a 1D-CNN in parallel, then select the best
performer. The NIST benchmark (Zwolak et al., Nov 2025,
arXiv:2511.22451) found CNNs gave the best accuracy-per-parameter
tradeoff while MLP-based architectures were the most computationally
efficient. Complex architectures that excelled on synthetic data FAILED
to generalize to experimental data --- directly relevant to your
synthetic-to-real gap risk.

**Architecture A: MLP (Primary)**

2-3 hidden layers, 128-256 neurons. Input: \~100-point ODMR frequency
sweep. Output: magnetic field vector estimate. Composed entirely of
FULLY_CONNECTED + RELU. Expected inference: \<0.1 ms on PolarFire.

**Architecture B: 1D-CNN (Secondary)**

2-4 conv layers with depthwise-separable convolutions, residual
connections, global average pooling. Target \<1,000 parameters
post-pruning. Reference: Feb 2026 MDPI Electronics paper (3,121 → 358
params with INT8 QAT).

**VectorBlox v3.0 compilation rules:**

No separate CONV_1D operator. Implement 1D convolutions as CONV_2D with
kernel shape (1×k) on input tensors reshaped to (1×N×channels). Stick
to: CONV_2D, DEPTHWISE_CONV_2D, FULLY_CONNECTED, RELU/RELU6, ADD
(residuals), MEAN (global avg pooling). Validate frozen TFLite graph
against the ops list BEFORE training at scale.

The Training Pipeline

1\. Generate training data using SimOS with coupled noise injection and
asymmetric lineshape corruption. 2. Train BOTH architectures in PyTorch
on DGX Spark. 3. INT8 QAT via TorchAO: torch.export.export() →
prepare_qat_pt2e() → training → convert_pt2e(). XNNPACKQuantizer for
symmetric INT8. 4. Export: PyTorch → ONNX → TFLite INT8 → VNNX binary
(vnnx_compile). 5. Validate with VectorBlox bit-accurate simulator. 6.
Select the architecture that compiles cleanly AND generalizes best.

The PID Baseline

Use SmartHLS C++ for PID implementation. SmartHLS motor controller case
study achieves \~2 µs deterministic latency at 200 MHz. A PID is \~3
multiplies, 2-3 adds, 1 accumulation at 200 MHz with II=1 pipelining:
50-250 ns (600× faster than your 150 µs requirement). Every published
NV-diamond frequency-locking system uses PID or PI control. Do not
change the algorithm.

Evaluation Methodology (Five-Metric Stack)

  -------- ----------------------- ---------------------- ---------------------------
  **\#**   **Metric**              **What It Measures**   **Plan KPP**

  1        Spherical Heading Error Peak-to-peak vector    \>50% heading error
           Profile                 error across 360° 2D   reduction
                                   rotation in 50 µT      
                                   field                  

  2        Asymmetric Inversion    Absolute vector bias   \>99% accuracy (reframed as
           Bias                    on skewed ODMR spectra \<5 nT bias)
                                   vs ground truth        

  3        Frequency-Partitioned   Noise comparison:      \>10× suppression (drift
           PSD                     sub-0.1 Hz drift band  band only)
                                   AND \>1 Hz white noise 
                                   band separately        

  4        Allan Deviation (ADEV)  Stability across       Complements PSD
                                   timescales; show       
                                   flattened drift at τ   
                                   \>5 sec                

  5        MagNav.jl Positioning   Navigation error using System-level validation
           RMSE                    SGL 2020 flight data   (cf. Q-CTRL 11×)
                                   with Zenodo-derived    
                                   noise                  
  -------- ----------------------- ---------------------- ---------------------------

**Critical: Train/Test Data Separation Protocol**

Train on SimOS/QDsiM synthetic data with corruption parameters. Evaluate
Metrics 1-4 on a held-out synthetic test set generated with DIFFERENT
random seeds AND different noise parameter distributions (shifted means,
wider variance). Evaluate Metric 5 using the empirical Zenodo ODMR
dataset characteristics injected into real SGL 2020 flight data.
Document the train/test split explicitly.

**Required Simulation: 2D Rotational Field Sweep**

Continuous 360-degree rotation of a 50 µT background field vector within
the {110} crystallographic plane. This passes through symmetry angles
triggering PID degeneracy failures, varies B_perp continuously mapping
the full heading error profile, and provides a single visually
compelling plot showing PID loss-of-lock alongside continuous AI
tracking. Budget 1-2 additional days in Days 55-65.

Deliverable 3: FPGA Implementation Analysis on RT PolarFire SoC

**Plan commitment:** Task 3, Days 45-75. Metrics: Static timing
confirms \<150 µs classical loop and \<1 ms AI loop. Power estimation
certifies \<12 W total PNT payload.

Timing Analysis

1\. Implement PID via SmartHLS C++ targeting RTPF500ZT. 2. Instantiate
VectorBlox IP alongside SmartHLS PID in custom Libero SmartDesign
project (separate FIC ports). 3. Run synthesis and P&R in Libero SoC
v2025.2 on x86 machine. 4. Generate SmartTime reports: Classical PID
loop 50-250 ns (SmartHLS at 200 MHz, 600×+ margin); AI inference \<1 ms
(VectorBlox references). 5. Document timing margin explicitly.

Power Estimation

Use MPE spreadsheet for early estimates, SmartPower (Libero 2025.2) for
post-P&R analysis. Budget: RISC-V subsystem \~0.12 W, FPGA fabric \~1 W,
VectorBlox AI \<5 W, I/O + SerDes \~1-2 W. Estimated total: 5-9 W
(comfortable margin within 12 W). Use SmartPower multi-mode/scenario
analysis for both active PID and AI inference modes.

v4 Addition: Bounded Hybrid Safety Architecture

The system must implement a Simplex Run-Time Assurance (RTA)
architecture with bumpless transfer. This addresses the strongest
anticipated reviewer objection about NN stability. Three
hardware-enforced boundaries in the FPGA fabric:

**Sector Saturation Clamps:** AI output limited to ±5% of total actuator
range via hard digital limiter. AI physically cannot push the plant
outside PID capture range.

**Slew-Rate Limiting:** Discrete derivative du_AI/dt clamped in
hardware. Step hallucinations become slow ramps within classical loop
bandwidth.

**Execution Watchdog:** FPGA counter monitors VectorBlox AXI bus. If
inference exceeds 1.0 ms, AI feedforward decoupled for that cycle.

**Bumpless Transfer:** Upon AI fault, FPGA executes integral state
back-calculation: I_new = I_old + u_AI_old. Physical actuator sees zero
voltage change. Classical PI smoothly assumes full load. Formal framing:
Nonlinear Lur'e Problem, Circle Criterion, Absolute Stability.
Precedents: NASA IFCS F-15, Air Force Auto-GCAS.

See Platform Addendum v4 Section 3 for complete specification.

v4 Addition: Multi-Sensor Power Budget Summary

VectorBlox core: \~60,000 LEs (\~12.5% of RTPF500ZT). Classical PID:
\<1,000 LEs and \~4 DSP blocks per channel. Instantiating additional PID
channels for CSAC and OPM consumes \<0.5% of remaining fabric. Dynamic
switching power of kilohertz PID blocks is \<0.1 W. All VNNX models (\<4
KB each) reside simultaneously in 33 Mb LSRAM. Model-swap latency is
clock-cycle regime. The 5-9W budget is entirely secure for concurrent
multi-sensor operation. See Platform Addendum v4 Section 6 for detailed
analysis.

RT PolarFire SoC: 481K LEs, 33 Mb SRAM, 1,480 DSP blocks, 24×10 Gbps
SerDes. SONOS config immune to SEU, TID \>100 krad (confirmed \>300
krad). QML Class B and Q qualified, roadmap to Class V and Y.
Engineering samples since July 2025.

Deliverable 4: Draft ICD and CONOPS

Draft ICD

Define physical and logical interfaces for the AI Cognitive Engine:
SpaceWire / MIL-STD-1553 / Ethernet interfaces, data protocols between
sensor front-end and control loop, command/telemetry interface for
ground station, power interface requirements (within 12 W), mechanical
envelope (12U CubeSat form factor). A 10-15 page draft with block
diagrams, interface tables, and protocol descriptions is sufficient.

**v4 Addition: Sensor Abstraction Layer**

The ICD must include the universal AFE specification and NN input/output
contract per sensor type. See Platform Addendum v4 Section 4 for the
detailed interface table (ADC/DAC specs, channel counts, NN formats per
modality).

CONOPS for On-Orbit Demo

The CONOPS should describe: mission scenario, operational environment, system
architecture on spacecraft, data flow, ground segment interface, success
criteria.

**v4 Addition: Multi-Sensor Payload Paragraph**

The CONOPS should include a forward-looking paragraph on future quantum
PNT payloads supported by firmware-only changes on the same RT PolarFire
hardware. By hot-swapping NN weights in LSRAM and adding classical PID
channels (\<0.5% fabric per sensor), a single avionics box can control
an NV magnetometer, a CSAC, and an OPM concurrently. This transforms the
flight demo from a single-sensor experiment into a platform validation.

Deliverable 5: Final Reporting

Final Technical Report

1\. Executive Summary. 2. Technical Approach (tools adopted,
architecture decisions, what changed since the original plan). 3. Results (sensor
model validation, neural network performance across both architectures,
FPGA timing/power, five-metric evaluation stack including ADEV and
heading error profile). 4. Comparison to Objectives (\>99% accuracy,
\>10× noise suppression in drift band, \>50% heading error reduction,
\<150 µs / \<1 ms latency, \<12 W power). 5.
Appendices.

**v4 Addition: Narrative Strategy (from v3.1 physics review)**

Lead with heading error correction. Show degeneracy crossing failure
mode plot. Frame asymmetric inversion as latency argument. Be
transparent about shot noise limits. Use the
plan-claims-to-deliverables mapping table (see Addendum Section 8
for copy-paste control theory argument).

**v4 Addition: Cross-Sensor Platform Applicability Subsection**

Include in Discussion/Future Work. Reference Addendum Section 2 for
transfer table and Section 8 for the 4-part control theory argument.

**v4 Addition: Bounded Hybrid Safety Architecture Subsection**

Include in Technical Approach. Reference Addendum Section 3 for complete
specification.

ICD

Keep v3 interface definitions (SpaceWire, MIL-STD-1553, Ethernet). Add
sensor abstraction layer specification with universal AFE concept and NN
input/output contract per sensor type. See Addendum Section 4 for the
detailed interface table.

CONOPS

Keep v3 on-orbit NV magnetometer demo. Add multi-sensor payload
paragraph about future quantum PNT payloads supported by firmware-only
changes on same hardware.

**v4 Additions:**

**CSAC integration:** Stretch goal. Tap TIA output at 500 kSPS,
digital lock-in on PolarFire, MLP with 3,777 parameters, \<10 µs
inference. See Addendum Section 5 for complete plan.

**Platform extensibility:** Section describing firmware-only extension
to OPM, Rydberg, and CSAC modalities with the same hardware.

Key Risks and Mitigations

**Risk 1: You listed 4 people and you're 1 person.** If asked at
kickoff: team members are available on a consulting basis but you're
leading all technical execution directly.

**Risk 2: \>99% accuracy on a problem you haven't fully defined.** Your
test data is from your simulator --- you control the distribution. Use
full noise catalog to make the test set harder than training. Dual
MLP/CNN gives two shots. Use different noise distributions for test vs
train to avoid inverse crime.

**Risk 3: \>10× noise suppression is a strong claim.** Now correctly
scoped to the sub-0.1 Hz drift band only. Benchmark against a properly
tuned PID. Use the five-metric stack. Q-CTRL's published \>11× validates
achievability.

**Risk 4: QDsiM code may not be available.** Fall back to SimOS.
Implement QDsiM's documented noise injection as custom wrappers. Noise
models are well-specified in the paper.

**Risk 5: SmartHLS + VectorBlox co-integration untested.** Both generate
standard AXI IP cores. Icicle Kit reference design supports both as
build flags. Standard FPGA integration work, not research risk.
OpenCores PID Verilog as fallback.

**Risk 6 (NEW): Platform claim credibility.** Mitigation: Gemini Deep
Think physics analysis confirms direct transfer to alkali OPMs and
Rydberg metrology with retraining only, partial transfer to CSAC/SERF
with input layer refactoring. Cold-atom explicitly excluded as requiring
architectural extension. Honest scoping strengthens credibility.

What Changed Since the Original Plan (Complete Evidence Table)

  ---------------------- ---------- ------------ ------------------------------
  **Finding**            **Date**   **Source**   **Impact**

  SimOS released         Nov 2025   Claude #1    Replaces custom Hamiltonian
                                                 solver, saves 4-6 weeks

  QDsiM released         Jan 2026   ChatGPT #2,  Drop-in ODMR digital twin with
                                    Claude #2    noise catalog

  CUDA-Q Dynamics NV+P1  Jun 2025   Claude #1    Your physics on your hardware
  demo on Blackwell                              

  VectorBlox SDK v3.0    Feb 2026   All reports  Concrete supported-op list,
                                                 eliminates compilation risk

  cuDensityMat v26.1.0   Jan 2026   Claude #1    GPU Lindblad dynamics on Spark
  aarch64 + gradient                             with backprop
  APIs                                           

  QuaCCAToo published    2025       Claude #1    Pre-built NV Hamiltonian with
                                                 P1 DEER example

  Lightweight 1D-CNN on  Feb 2026   Claude #1    Validates architecture
  FPGA (358 params, INT8                         approach
  QAT)                                           

  NIST quantum state     Nov 2025   Claude #2    Justifies dual MLP/CNN
  benchmark (MLP vs CNN)                         strategy

  SmartHLS motor         Pre-2026   Claude #2    Justifies SmartHLS for PID
  controller on                                  
  PolarFire (\~2 µs)                             

  MagNav.jl + Q-CTRL     Apr 2025   Claude #2    Air Force MagNav standard +
  \>11× field trial                              validates \>10×

  Published PID          2025       Claude #2    Don't change PID algorithm
  confirmation (3 NV                             
  systems)                                       

  RT PolarFire SoC       Jul 2025   Claude #1    Hardware prototyping possible
  engineering samples                            in later work

  SBQuantum space        Sep 2025   Claude #1    On-orbit noise params + ADEV
  qualification + ADEV                           reference
  data                                           

  Bounded hybrid safety  Mar 2026   Gemini DT    Addresses strongest reviewer
  architecture validated                         objection

  CSAC integration plan  Mar 2026   Gemini DT    Technical plan now
  detailed                                       concrete
  ---------------------- ---------- ------------ ------------------------------

Early Actions

Environment Setup (This Week)

Verify dual-Spark QSFP link. Install CUDA-Q (pip install cudaq on
Spark). Install cuQuantum/cuDensityMat v26.1.0 (verify aarch64 wheels).
Install SimOS (pip install simos + QuTiP 5.2.3). Clone QuaCCAToo. Clone
VectorBlox SDK v3.0. Install Libero SoC v2025.2 + SmartHLS 2025.2 on x86
machine. Install Julia + MagNav.jl. Install BASILISK and allantools.
Read VectorBlox supported ops list end-to-end. Run CUDA-Q Dynamics NV+P1
demo on one Spark. Run QuaCCAToo Example 07. Attempt to access QDsiM
code (contact authors if no public repo).

Pipeline Scaffolding (This Month)

Adapt star tracker synthetic data generator for ODMR spectra. Prototype
SimOS → noisy ODMR spectrum → neural network input pipeline. Design BOTH
MLP and CNN architectures on paper using only VectorBlox v3.0 supported
ops. Set up TorchAO QAT flow with toy model. Prototype full pipeline:
PyTorch → ONNX → TFLite INT8 → vnnx_compile → VectorBlox simulator.
Write minimal SmartHLS PID in C++ and compile through Libero. Download
Zenodo ODMR dataset. Test MagNav.jl and BASILISK basic examples.
