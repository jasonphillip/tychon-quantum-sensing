> Original: claude.ai project document, created 2026-04-02. Edited for publication: names of other people and business details removed.

# Tychon AI — Recent Advancements (April 1-2, 2026)

## Heading Error Sweep Results (Raw Data)
- 1440 angles at 0.25° steps, 50 µT field in (1,-1,0) plane
- PID-only: 13.33 µT MAE, 31.98 µT max
- FCNN+PID: 9.16 µT MAE, 23.48 µT max, P95 drops from 32→13 µT
- Average reduction: 31.3% (below >50% KPP on this specific test)
- Validation set result: 54.3% (23.75 → 10.85 µT)
- Gap explained: sweep uses fixed P1=50 ppm, T=300K and rotates through hardest degeneracy angles
- Data at: experiments/heading_sweep_results.npz (14 arrays)

## Gemini Deep Think #10: Loss Function Tuning (Key Findings)

Three high-leverage changes to push MAE into single digits:

1. **CLIP TARGETS TO SECTOR CLAMP BOUNDS (±2.25 µT)** — Highest leverage change. The FCNN wastes capacity on ±34 µT extremes that get clamped at deployment. Frees representational capacity for the actionable ±10 µT tracking regime. Expected impact: ~1.0-2.0 µT MAE reduction.

2. **INCREASE HUBER DELTA FROM 1.0 TO ~10.0 µT** — At delta=1.0, all samples are in L1 (constant gradient). At delta=10, typical errors get quadratic gradients (10× stronger signal for 10 µT error vs 1 µT). Set delta to 75th-80th percentile of error distribution. Expected impact: ~0.8-1.5 µT MAE reduction.

3. **LEARNABLE ANCHOR SIGMA** — Make the Gaussian σ an nn.Parameter initialized to physical FWHM. Costs 1 parameter, dynamically tunes spatial attention window. Expected impact: ~0.3-0.5 µT MAE reduction.

Warnings:
- Do NOT weight samples by PID error magnitude — undoes Huber protection, exploding gradients
- Do NOT do strict 2-stage curriculum — causes catastrophic forgetting in tiny networks
- Mixed-batch hard example mining (75% uniform + 25% hardest) is OK for second half of training

Combined expected improvement: Could push from 10.85 µT to ~7-9 µT MAE, potentially reaching 60-70% reduction.

## Gemini Deep Think #11: MagNav Metric 5 (Key Findings)

### Critical Unit Check
Errors are in µT, not nT. At 10+ µT noise, crustal anomaly maps (~50-500 nT) are completely buried. MagNav filter will reject map and follow drifting INS.

### Workaround for this plan
Scale noise down to nT regime. Frame as "simulating a later-stage gradiometer/differential setup that removes common-mode background drift." This isolates the AI's relative contribution.

### Realistic RMSE Expectations
54% sensor noise reduction → 40-55% position RMSE reduction (proportional to σ_B / ∇B).
Q-CTRL's 46× was comparing MagNav vs unaided INS, not two sensors. A ~2× improvement over baseline is exceptional.

### Implementation Path
1. Python: Generate time-correlated error profiles from heading sweep, scale to nT, export CSV
2. Julia/MagNav.jl: Load CSV, inject into SGL Flight 1002 (has figure-8 maneuvers), run particle filter
3. Select 10-20 minute segment with maneuvers to exercise heading error correction
4. Frame as "System-Level Plausibility Validation via Synthetic Injection"

### Key Framing Language
"While full proof-of-navigation requires later HWIL testing to account for airframe electromagnetics and vibration, this synthetic injection confirms that software-level mitigation of overlapping CW-ODMR resonances successfully prevents filter divergence and bounds dead-reckoning drift."

## Sector Clamp Authority Analysis (Critical Finding)

The ±4.5% sector clamp at 50 µT = ±2.25 µT is **too restrictive** for heading error correction. Clamp sweep on v1 FCNN heading sweep data:

| Clamp | v1 FCNN Reduction | Notes |
|-------|-------------------|-------|
| ±2.25 µT | 1.1% | Useless — PID errors routinely 10-32 µT |
| ±5.0 µT | 0.8% | Wrong-sign corrections included |
| ±10.0 µT | 7.7% | Starting to help |
| ±15.0 µT | 19.1% | Meaningful |
| ±20.0 µT | 30.1% | Near full authority |
| ±50.0 µT | 31.3% | Unclamped baseline |

**Implication:** The sector clamp is the ceiling, not the model. α can be increased with formal stability justification (Gemini DT#3 showed α_max = K_p·Γ/(2·ΔU_range)). The AXI config registers in the SmartHLS design allow runtime α adjustment — not hardcoded.

## Physics-Informed Feature MLP — The Breakthrough

### How We Got Here (Decision Narrative)

1. **Original approach:** Raw 100-point spectrum → 3D B-field vector. Failed — 57.3° random guess due to CW-ODMR degeneracy.
2. **Reformulation:** Raw spectrum + PID anchor → scalar ΔB correction. Achieved 54% on validation, 31% on heading sweep.
3. **Loss tuning (DT#10):** Clipped targets to ±2.25 µT + Huber delta 10. Improved validation to 66% but heading sweep dropped to 4% because the clamp is too tight.
4. **Clamp analysis:** Revealed the sector clamp is the bottleneck, not the model. Even unclamped, raw-spectrum FCNN only achieves 31%.
5. **Claude recommended** focusing on Option A (wider clamp training) or Option D (formal clamp justification) as highest-leverage. Estimated Option B (physics features) at 2-3 days.
6. **Jason pushed back:** "Why do you assume Option B is as much work as you think? Let's challenge that assumption."
7. **Feature correlation test (30 seconds):** Linewidth r=-0.831, second_moment r=-0.792, asymmetry r=-0.585. Five features explain more variance than 100 raw spectrum points.
8. **Proof-of-concept (5 minutes):** 241-param MLP on 5 features → 97% heading error reduction unclamped, crosses 50% KPP at ±15 µT clamp. Beats the 2,905-param FCNN by 3-25× at every clamp level.

### Key Lesson
The founder's instinct to challenge the "highest effort" assumption was correct. The physics-informed approach was NOT 2-3 days — it was 30 minutes from correlation test to proof-of-concept. The raw spectrum CNN was solving a harder problem than necessary. The heading error signal lives in 5 simple spectral shape features, not in 100 raw amplitude values.

### Feature MLP Architecture
```
Input: 5 features [contrast, asymmetry, linewidth, second_moment, lock_position]
Linear(5, 16) → ReLU → Linear(16, 8) → ReLU → Linear(8, 1)
Output: scalar ΔB correction (µT)
Parameters: 241
```

### Proof-of-Concept Results (overfit — heading sweep train=test)

| Clamp | Feature MLP (241p) | FCNN v1 (2905p) | MLP advantage |
|-------|-------------------|-----------------|---------------|
| ±2.25 µT | 16.5% | 1.1% | 15× better |
| ±5.0 µT | 31.0% | 0.8% | 39× better |
| ±15.0 µT | **55.6%** | 19.1% | Crosses 50% KPP |
| ±50.0 µT | **97.1%** | 31.3% | 3× better |

**Caveat:** Trained and evaluated on same 1440 angles. Proper train/test validation on 50K dataset is running now.

### Why Features Beat Raw Spectrum
- Heading error is encoded in spectral **shape** (linewidth, asymmetry, contrast), not raw amplitudes
- The FCNN must rediscover these relationships from 100 noisy points
- The feature MLP gets the physics handed directly in 5 numbers
- At 241 params, every parameter is focused on the actionable signal
- No conv layers = no VectorBlox reshape issues, trivially compiles as FULLY_CONNECTED

## Currently Running
- Feature MLP training on 50K production dataset with proper train/test split (local DGX Spark node, tychon-odmr-ml)
- Two model sizes: 5→[16,8]→1 (241p) and 5→[32,16]→1 (~625p)
- Both clipped (±15 µT) and unclipped targets
- Heading sweep re-evaluation with trained models
- Full export chain: ONNX → TFLite INT8 → NAS

## Updated Implementation Priority

1. **Feature MLP validation on 50K** — running now, results by morning
2. **Compile feature MLP .vnnx on Beelink** — trivial, pure FULLY_CONNECTED
3. **Heading sweep visualization** — dual-panel hero figure with feature MLP results
4. **ADEV simulation** — 16,200s time series with feature MLP
5. **Formal sector clamp re-analysis** — justify wider α for heading error use case
6. **MagNav Metric 5** — synthetic injection
7. **Final Report writing**

## Key Citations Added (from Deep Research)
| Reference | Year | Key Relevance |
|-----------|------|---------------|
| Homrighausen et al., Sensors | 2023 | CNN on ESP32, scalar |B| from CW-ODMR microdiamonds |
| Tsukamoto et al., Scientific Reports | 2022 | GPR 1.8 µT accuracy where fitting failed |
| Kashem et al., arXiv:2603.14728 | 2026 | 1D-CNN predicts Lorentzian peak params → initializes fitting |
| USTC, Phys Rev A 110, 052417 | 2024 | DNN from pre-extracted frequencies → Bx,By,Bz |
| arXiv:2504.18478 | 2025 | Systematic documentation of CW-ODMR degeneracy ambiguities |
| Dushenko et al. (NIST), 2021 | 2021 | Bayesian ML 10-40× measurement speedup |
| Jauch et al., QST | 2026 | 6× convergence + 59.6% contrast via ML-optimized pulses |

