> Original: claude.ai project document, created 2026-04-01. Edited for publication: names of other people and business details removed.

# Gemini Deep Think — Combined Outputs (2026-04-01)

**Compiled:** 2026-04-01
**Sources:** Gemini 2.5 Deep Think (10-prompt/day mode)
**Covering dates:** 2026-03-26 through 2026-04-01
**Project:** Tychon AI — the 90-day plan

---

## Table of Contents

1. [Training Loop Design for ODMR→B-Field Inversion](#1-training-loop-design-for-odmrb-field-inversion) (2026-03-26)
2. [3D B-Field Dataset Design](#2-3d-b-field-dataset-design) (2026-03-27)
3. [Final technical report Technical Narrative](#3-final-technical-report-technical-narrative) (2026-03-27)
4. [Coupled Noise Model & Cascaded SDEs for Synthetic Data](#4-coupled-noise-model--cascaded-sdes-for-synthetic-data) (2026-04-01)
5. [Formal Verification & Safety Analysis of Simplex RTA Architecture](#5-formal-verification--safety-analysis-of-simplex-rta-architecture) (2026-04-01)
6. [Closed-Form ODMR Resonance Frequencies & Vectorized Implementation](#6-closed-form-odmr-resonance-frequencies--vectorized-implementation) (2026-04-01)

---

# 1. Training Loop Design for ODMR→B-Field Inversion

**Source:** Gemini 2.5 Deep Think (10-prompt/day mode)
**Date:** 2026-03-26
**Prompt topic:** Loss function, optimizer, curriculum training, failure modes, and diagnostic loop for Repo 2 neural network training
**Status:** Unverified — review notes inline

---

## Claude Review Summary

**Overall assessment:** Strong analysis with several genuinely sharp physics insights. One major claim (INT8 quantization paradox) needs empirical verification before acting on it. Loss function design and diagnostic loop structure are directly usable. Sign ambiguity warning is a real physics catch that must be verified against Repo 1 code.

**Action items before using this:**
1. Check Repo 1's `generate_dataset()` for B-field sign constraints (sign ambiguity issue)
2. Test µT scaling vs raw Tesla during first training run
3. Don't implement mixed INT8/INT16 per-layer — TorchAO XNNPACKQuantizer doesn't support it. Test finite-difference preprocessing instead during QAT phase.
4. Keep dual MLP/CNN strategy through first training — don't drop MLP based on this recommendation alone

---

## INT8 Quantization Paradox

> **Claude note:** Directionally correct but overstated. The sub-LSB math for raw spectra is valid, but the INT16 input layer mitigation is wrong for TorchAO/XNNPACKQuantizer. The finite-difference preprocessing suggestion (derivative of spectrum to amplify sub-bin shifts) is the better path. File as "investigate during QAT phase" — test empirically, don't take on faith.

The NV center's gyromagnetic ratio is γ ≈ 28 Hz/nT. A 37 nT heading error produces a frequency shift of roughly ~1 kHz.

If your 100-point frequency sweep covers 100 MHz to capture all 8 resonances, each bin is 1 MHz. A 1 kHz shift is 1/1000th of a bin.

Assuming your normalized [0,1] PL dip has a linewidth of ~2 MHz, the amplitude change (ΔPL) on the steepest slope caused by a 1 kHz shift is roughly 0.001.

INT8 provides 256 quantization levels (resolution ≈ 0.0039).

**Claim:** Standard TorchAO QAT will physically erase the 37 nT heading error because the amplitude shift is ~4× smaller than the LSB of an INT8 activation.

**Mitigation options suggested:**
- ~~Leave input layer/observer in INT16~~ *(Claude: not supported by XNNPACKQuantizer)*
- Pre-process by passing the derivative (differences between adjacent bins) to amplify sub-bin shifts *(Claude: this is the viable path — test it)*

---

## 1.1 Loss Function

> **Claude note:** This is well-designed. Cosine similarity for angular alignment plus Huber for magnitude robustness matches the plan's emphasis on heading error. The µT scaling advice is correct and important. The alpha=0.7 angular weighting is a reasonable starting point — tune it.

Standard MSE will fail. The Fano-distortion bias (1500 nT) is ~40× larger than the heading error (37 nT), so MSE will optimize out Fano asymmetry but treat the 37 nT heading error as unoptimizable noise.

**Recommended: Composite Angular + Huber Loss**

- **Target Scaling (Crucial):** Never train on raw Tesla values (~10⁻⁵). Multiply ground truth by 10⁶ to train in micro-Tesla (µT).
- **Cosine Embedding Loss:** Forces vector direction alignment, explicitly penalizing heading error regardless of magnitude.
- **Huber Loss (Smooth L1):** Prevents 1500 nT Fano outliers from causing exploding gradients.

```python
import torch
import torch.nn.functional as F

def physics_informed_loss(B_pred_uT, B_true_uT, alpha=0.7):
    # 1. Angular Loss (Explicit navigation priority)
    cos_sim = F.cosine_similarity(B_pred_uT, B_true_uT, dim=-1, eps=1e-7)
    L_ang = torch.mean(1.0 - cos_sim)
    
    # 2. Magnitude Loss (Robust to 1500 nT Fano bias)
    L_mag = F.huber_loss(B_pred_uT, B_true_uT, delta=1.0)
    
    return alpha * L_ang + (1.0 - alpha) * L_mag
```

---

## 1.2 Learning Rate & Optimizer

> **Claude note:** Reasonable for the 100-sample prototype. The dead ReLU warning is valid — Kaiming He initialization is the right call. AdamW with weight decay is correct given future INT8 quantization needs bounded weights.

With 100 samples, the goal is proving the network has mathematical capacity to overfit the simulator's logic, not generalization.

- **Optimizer:** AdamW. Weight decay (1e-3) mandatory — QAT into INT8 requires tightly bounded weights.
- **Learning Rate:** Flat 1e-3 or CosineAnnealingLR.
- **Dead ReLU Risk:** VectorBlox requires strictly ReLU (no Leaky/GeLU). If gradients spike, pre-activations swing negative permanently. **Must initialize with Kaiming He Normal** (`torch.nn.init.kaiming_normal_`).

---

## 1.3 Curriculum Training vs. Simultaneous

> **Claude note:** For 100 samples, simultaneous is correct. For production, the curriculum phases map cleanly onto Repo 1's corruption parameter ranges — you can generate separate datasets with restricted ranges per phase. This is implementable without any code changes to Repo 1.

**100 samples:** Train simultaneously to test gradient plumbing.

**10K+ production:** Curriculum learning is mandatory. Starting with all corruption at once risks the network falling into a local minimum of predicting the dataset mean.

- **Phase 1 (Zeeman Topology):** Clean symmetric Voigt dips, high fields, no degeneracy. Goal: learn basic 28 GHz/T projection geometry.
- **Phase 2 (MIMO Degeneracy):** Fields near [111], [100] axes. Goal: resolve resonance bifurcations.
- **Phase 3 (Asymmetry):** Ramp up `b1_gradient_frac`. Goal: learn true zero-crossing is shifted from apparent argmin.
- **Phase 4 (Perturbation):** Introduce B_perp. Freeze early layers, drop LR by 10× to lock in tiny 2nd-order sub-bin adjustments.

---

## 1.4 Critical Physics Failure Modes

> **Claude note:** The sign ambiguity warning is a genuine catch. **MUST verify against Repo 1's `generate_dataset()` before training.** Check whether B-field labels are restricted to a single hemisphere. If not, the network will average +B and -B to predict [0,0,0]. The axial dominance and Fano/transverse aliasing points are also valid.

### Global Sign Ambiguity (+B vs -B)
The standard NV Hamiltonian is symmetric. Without a static bias field to break inversion symmetry, +B and -B yield the exact same ODMR spectrum. If the dataset contains both, the optimizer will split the difference and predict [0,0,0]. **Ensure the simulator restricts labels to a unique octant/hemisphere.**

### Axial Dominance
First-order Zeeman splitting dictates macro-structure (Bz), while 2nd-order transverse shift (γ²B⊥²/D) is a micro-perturbation. The network will learn Bz perfectly and output noise for Bx/By.

### Fano vs. Transverse Aliasing
The network will aggressively try to use the shape of the dip (Fano asymmetry from B1 gradient) to guess the shift of the dip (from B_perp). These are physically distinct effects that happen to produce correlated spectral features.

---

## 1.5 Diagnostic Training Loop

> **Claude note:** This is directly usable. The key insight is stratifying validation metrics by corruption parameter values to isolate which physics problem the network is solving or failing at. Pass corruption_params through the DataLoader alongside spectra and labels.

Do not rely on monolithic "Validation Loss." Pass corruption parameters through the DataLoader to stratify metrics physically.

```python
def validate_physics_regimes(model, val_loader):
    model.eval()
    metrics = {
        "angle_err_deg": [], "bx_err_nT": [],
        "fano_bias_nT": [], "heading_bias_deg": []
    }
    
    with torch.no_grad():
        for spectra, true_B_uT, meta in val_loader:
            pred_B_uT = model(spectra)
            
            # 1. Angular error in degrees
            cos_sim = F.cosine_similarity(pred_B_uT, true_B_uT, dim=-1)
            angle_deg = torch.acos(
                torch.clamp(cos_sim, -1.0+1e-7, 1.0-1e-7)
            ) * (180.0 / 3.14159)
            
            # 2. Component error in nanoTesla
            err_nT = torch.abs(pred_B_uT - true_B_uT) * 1000 
            
            for i in range(len(spectra)):
                metrics["angle_err_deg"].append(angle_deg[i].item())
                metrics["bx_err_nT"].append(err_nT[i, 0].item())
                
                # Problem 2: Fano asymmetry isolation
                if meta['b1_gradient_frac'][i] > 0.1:
                    metrics["fano_bias_nT"].append(err_nT[i, 2].item())
                    
                # Problem 1: Heading error isolation
                if meta['b_perp_T'][i] > 1e-5:  # > 10 uT
                    metrics["heading_bias_deg"].append(angle_deg[i].item())

    return {k: sum(v)/len(v) for k, v in metrics.items() if len(v) > 0}
```

---

## 1.6 Architecture Recommendation

> **Claude note:** The CNN preference is reasonable but don't drop the MLP yet. The dual architecture strategy exists because the NIST benchmark (DLOG-006) showed complex architectures fail synthetic-to-real transfer. Keep both through first training, evaluate, then decide. The shift-invariance argument for CNN is valid but the MLP's simplicity may win on generalization.

Gemini strongly favors the 5.6K CNN for production. Reasoning: an MLP must brute-force relearn Fano asymmetry for every frequency bin, while a 1D-CNN using pooling inherently learns spatial shift-invariance, acting as an optimal feature extractor for distorted Fano shapes regardless of where the sweeps shift them.

---

# 2. 3D B-Field Dataset Design

**Source:** Gemini 2.5 Deep Think
**Date:** 2026-03-27
**Prompt topic:** Transitioning from 1D (Bz-only) to full 3D B-field vector dataset for ODMR→B inversion
**Status:** Reviewed — one critical error corrected, several adjustments inline

---

## Claude Review Summary

**Overall assessment:** Gemini's strongest output. The B_perp removal insight and magnitude correction are genuinely sharp physics catches that would have caused real problems if missed. One critical error: the Z-score normalization recommendation is wrong for our cosine similarity loss function. Mixture distribution ratio needs adjustment.

**Critical corrections:**
1. Do NOT Z-score normalize labels — breaks cosine similarity loss. µT scaling is sufficient.
2. Adjust mixture ratio to 70/30 uniform/targeted (not 50/50)
3. Overfit test should include corruption params, not be noise-free
4. Repo 1 Hamiltonian solver already handles 3D — only batch_generate.py needs changes

**Action items for Repo 1:**
1. Update `batch_generate.py` to sample full 3D B-field vectors in spherical coords
2. Remove `b_perp` as an independent corruption parameter
3. Pass full [Bx, By, Bz] to the SimOS adapter (which already supports it)
4. Enforce Bz ≥ 0 hemisphere constraint
5. Add targeted sampling near NV symmetry axes for MIMO degeneracy coverage

---

## 2.1 Sampling Strategy: Spherical Generation, Cartesian Labels

> **Claude note:** Correct. Adopted without changes.

**Sample in spherical coordinates** (magnitude, θ, ϕ) for uniform solid-angle coverage and targeted angular clusters. **Label and train in Cartesian** [Bx, By, Bz] because:

- Neural networks struggle with angular predictions (periodic boundary discontinuities: MSE massively penalizes 359° vs 1°)
- Pole singularities in spherical coords create training instabilities
- Cartesian labels provide a smooth, continuous Euclidean loss landscape
- Our composite angular + Huber loss already operates on Cartesian vectors

---

## 2.2 Magnitude Range: 5–15 mT (Keep As-Is)

> **Claude note:** This is an important physics correction from Gemini. We were confused about the field scale. 5–15 mT is the bias magnet field, NOT Earth's field. Earth's field (~50 µT) is the perturbation that causes heading error.

**Correction:** 5–15 mT is not Earth-field scale. Earth's magnetic field is ~50 µT (0.05 mT). The 5–15 mT range represents the **bias field** from a permanent magnet used to lift the zero-field degeneracy of the NV center. The ~50 µT heading variation is Earth's field acting as a stray perturbation.

**Recommendation:** Keep the 5–15 mT range. With full 3D vector sampling at this magnitude, the ~50 µT heading error naturally emerges as small off-axis angular deviations (~0.2°–0.6°) from the dominant bias vector direction.

**Implication for training:** The network must learn to detect ~0.3° angular deviations on top of a 10 mT dominant field. This is a ~50 µT signal in a 10,000 µT background — a 1:200 ratio. This is why the cosine similarity loss (alpha=0.7) is critical: it explicitly optimizes angular accuracy regardless of the dominant magnitude.

---

## 2.3 Sign Ambiguity: Bz ≥ 0 Hemisphere Restriction

> **Claude note:** Correct. Already implemented in run_first_train.py. Now needs to be enforced at generation time.

The NV Hamiltonian is symmetric under B → -B. Identical ODMR spectrum for opposing field vectors. If the network sees both, it mode-collapses to predicting [0,0,0].

**Fix:** Restrict all labels to Bz ≥ 0 hemisphere. During generation, if a sampled vector has Bz < 0, multiply the entire vector by -1. The spectrum is identical, but the label becomes a strict bijection (one spectrum → one label).

This is already handled at load time in `run_first_train.py` (hemisphere folding), but **must also be enforced at generation time** in `batch_generate.py` to avoid confusion and ensure the manifest documents it.

---

## 2.4 Angular Sampling: Mixture Distribution

> **Claude note:** The concept is correct but 50/50 is too aggressive on targeted sampling. For the overfit test, use 100% uniform. For production, use 70/30 uniform/targeted. You can always increase targeted ratio later if MIMO metrics are weak.

Uniform random sampling on the sphere will undersample the 1D lines and 0D points where NV resonances overlap (MIMO degeneracy regimes along [100], [111], [110] axes).

**Fix: Mixture Distribution**

| Phase | Uniform Hemisphere | Targeted Clusters | Notes |
|-------|-------------------|-------------------|-------|
| Overfit test (256 samples) | 100% | 0% | Prove capacity on general coverage first |
| Production (80K+ samples) | 70% | 30% | Avoid over-biasing toward symmetry axes |
| If MIMO metrics are weak | 50% | 50% | Increase targeted ratio as needed |

**Targeted clusters:** Center on NV crystallographic symmetry axes (+Z hemisphere):

```
<100> axes: [0,0,1], [1,0,0], [0,1,0]
<111> NV axes: [1,1,1], [-1,1,1], [1,-1,1], [-1,-1,1] (normalized)
<110> edge axes: [1,1,0], [1,-1,0], [0,1,1], [0,-1,1], [1,0,1], [-1,0,1] (normalized)
```

Add Gaussian angular jitter (σ ≈ 1.5°) around each axis to simulate small heading sweeps through the degeneracy region.

**Post-generation:** flip any vectors with Bz < 0 (from jitter overshooting the equator).

---

## 2.5 Sample Counts

> **Claude note:** Order of magnitude correct. The 128-sample "zero noise" overfit test should be amended — include corruption params. The point is to verify the network can memorize the full mapping including corruptions, not just clean spectra.

| Phase | Samples | Purpose |
|-------|---------|---------|
| Overfit test | 256 | Prove network has capacity to invert full 3D Hamiltonian. Include corruption params. Loss must approach zero. |
| Small production | 50,000 | 80% train / 10% val / 10% test. Minimum for the 6D input space (Bx, By, Bz, P1, T, B1_grad). |
| Full production | 100,000 | If 50K shows interpolation gaps in validation metrics. |

**Train/test separation (mandatory per playbook):** Different random seeds AND different noise parameter distributions (shifted means, wider variance) for test set. Document explicitly.

---

## 2.6 B_perp: REMOVE as Independent Corruption Parameter

> **Claude note:** This is Gemini's sharpest insight. Critically important. If you inject a random B_perp on top of a 3D label, you create physically impossible spectra where the label doesn't match the spectrum. This makes heading error unlearnable.

**Current state:** `b_perp` is sampled as uniform(0, 50 µT) and applied as an independent corruption parameter alongside P1, temperature, and B1 gradient.

**Problem:** B_perp is NOT random noise. It is an **exact geometric consequence** of the 3D field vector projecting onto each NV axis. If you pass the full [Bx, By, Bz] vector to the QuTiP Hamiltonian solver, the transverse field component is computed naturally from the dot product of B with each NV crystallographic axis. Injecting a separate random B_perp creates physically impossible "ghost" fields that decouple the label from the spectrum.

**Fix:** Remove `b_perp` from the corruption parameter sampler in `batch_generate.py`. The remaining corruption parameters are:

| Parameter | Range | Physical Origin |
|-----------|-------|-----------------|
| P1 concentration | 1–300 ppm | Spin bath decoherence |
| Temperature | 280–320 K | D(T) zero-field splitting drift |
| B1 gradient | 5–30% | Spatial MW inhomogeneity → Fano asymmetry |

B_perp is now implicit: it equals the component of [Bx, By, Bz] perpendicular to each NV axis.

**Impact on corruption_params array in HDF5:** Changes from (N, 4) to (N, 3). The data contract in Repo 2 (`contracts.py`) must be updated to accept both formats (backward compatibility with the existing golden dataset).

---

## 2.7 Changes Needed in Repo 1

> **Claude note:** Gemini says "update the QuTiP Hamiltonian construction." This is partially wrong — the SimOS/QuTiP adapter already handles full 3D B-field vectors through the Hamiltonian H = D*Sz² + γ(Bx*Sx + By*Sy + Bz*Sz). The only change needed is in `batch_generate.py` where Bx/By are hardcoded to zero.

**What actually needs to change:**

| Component | Change | Effort |
|-----------|--------|--------|
| `batch_generate.py` line 167-171 | Replace `Bz = uniform(*bz_range_T)` + `B = [0, 0, Bz]` with full 3D spherical sampling | Medium |
| `batch_generate.py` | Remove `b_perp` from corruption param sampling | Small |
| `batch_generate.py` | Add hemisphere enforcement (Bz ≥ 0 folding) | Small |
| `batch_generate.py` | Add targeted sampling near symmetry axes | Medium |
| SimOS adapter | **No changes needed** — already accepts 3D B-field vector | None |
| QuTiP Hamiltonian | **No changes needed** — already computes H_Zeeman = γ(Bx·Sx + By·Sy + Bz·Sz) | None |
| Dataset manifest | Update to document 3D sampling params, remove b_perp_range_T | Small |
| Repo 2 `contracts.py` | Accept corruption_params with 3 or 4 columns | Small |

---

## 2.8 Output Normalization — CRITICAL CORRECTION

> **Claude note: Gemini's recommendation here is WRONG for our loss function.** Z-score normalization would break the cosine similarity component of our composite loss.

**Gemini recommends:** Z-score standardize [Bx, By, Bz] labels so all three dimensions have mean=0 and variance=1.

**Why this is wrong for us:** Our loss function is `alpha * (1 - cos_sim) + (1-alpha) * huber`. The cosine similarity component is **scale-invariant by definition** — it only cares about the angle between vectors. Z-score normalization would transform the vectors such that their angular relationships no longer correspond to physical field directions. The cosine loss would be optimizing for angles in Z-score space, not physical space.

**The real problem Gemini is trying to solve:** With raw mT labels, Bz (~10 mT) dominates Bx, By (~0.05 mT) by 200:1. MSE gradient would be 40,000× larger for Bz than Bx/By.

**Our solution (already in place):**
1. Cosine similarity loss (alpha=0.7) is scale-invariant — it naturally weights angular error equally across all components regardless of magnitude ratio
2. Convert to µT at load time (already implemented) — puts all components in a numerically reasonable range
3. Huber loss (alpha=0.3) operates on µT values — delta should be scaled to ~1-5% of label range

**If angular error on Bx/By is still poor after training:** Add a per-component weighting to the Huber term that upweights the transverse components. This is a better fix than Z-score because it preserves physical units.

---

## 2.9 Concrete Sampling Code Specification

> **Claude note:** Gemini's code is usable with modifications. Key changes: 70/30 ratio, include corruption params in overfit test, remove b_perp.

```python
import numpy as np

def generate_3d_bfield_labels(
    num_samples: int,
    mag_range: tuple[float, float] = (5e-3, 15e-3),
    targeted_fraction: float = 0.3,
    jitter_sigma_deg: float = 1.5,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generate [Bx, By, Bz] labels (Tesla) with mixture sampling.

    Parameters
    ----------
    num_samples : int
    mag_range : tuple
        B-field magnitude range in Tesla.
    targeted_fraction : float
        Fraction of samples clustered near NV symmetry axes.
        0.0 = all uniform (overfit test), 0.3 = production default.
    jitter_sigma_deg : float
        Gaussian angular scatter around symmetry axes in degrees.
    rng : numpy Generator or None

    Returns
    -------
    ndarray, shape (num_samples, 3) — B-field vectors in Tesla, Bz >= 0.
    """
    if rng is None:
        rng = np.random.default_rng()

    labels = np.zeros((num_samples, 3))
    magnitudes = rng.uniform(mag_range[0], mag_range[1], num_samples)

    n_tgt = int(num_samples * targeted_fraction)
    n_uni = num_samples - n_tgt

    # --- Uniform hemispherical sampling ---
    phi = rng.uniform(0, 2 * np.pi, n_uni)
    cos_theta = rng.uniform(0, 1, n_uni)  # Bz >= 0 natively
    sin_theta = np.sqrt(1 - cos_theta**2)

    labels[:n_uni, 0] = sin_theta * np.cos(phi)
    labels[:n_uni, 1] = sin_theta * np.sin(phi)
    labels[:n_uni, 2] = cos_theta

    # --- Targeted MIMO degeneracy sampling ---
    if n_tgt > 0:
        # NV symmetry axes (positive hemisphere)
        sym_axes = np.array([
            [0, 0, 1], [1, 0, 0], [0, 1, 0],                     # <100>
            [1, 1, 1], [-1, 1, 1], [1, -1, 1], [-1, -1, 1],      # <111>
            [1, 1, 0], [1, -1, 0], [0, 1, 1], [0, -1, 1],        # <110>
            [1, 0, 1], [-1, 0, 1],
        ], dtype=np.float64)
        sym_axes /= np.linalg.norm(sym_axes, axis=1, keepdims=True)

        chosen = sym_axes[rng.choice(len(sym_axes), n_tgt)]
        jitter = rng.normal(0, np.radians(jitter_sigma_deg), (n_tgt, 3))
        tgt_vecs = chosen + jitter
        tgt_vecs /= np.linalg.norm(tgt_vecs, axis=1, keepdims=True)

        labels[n_uni:] = tgt_vecs

    # --- Hemisphere enforcement ---
    flip_mask = labels[:, 2] < 0
    labels[flip_mask] *= -1

    # --- Scale by magnitude and shuffle ---
    labels *= magnitudes[:, np.newaxis]
    rng.shuffle(labels)

    return labels
```

**Corruption parameters (b_perp REMOVED):**

```python
# Sample ONLY physical scalar corruptions
p1_ppm = rng.uniform(1, 300, num_samples)
temps_K = rng.uniform(280, 320, num_samples)
b1_grads = rng.uniform(0.05, 0.30, num_samples)

# NO b_perp — it's now implicit in the 3D B-field vector
```

---

## 2.10 Implementation Priority

| # | Action | When | Repo |
|---|--------|------|------|
| 1 | Update `batch_generate.py` with 3D sampling | Before production training | Repo 1 |
| 2 | Remove `b_perp` from corruption params | Same PR as #1 | Repo 1 |
| 3 | Generate 256-sample 3D overfit dataset | Immediately after #1 | Repo 1 |
| 4 | Update Repo 2 `contracts.py` for 3-column corruption params | Before training on 3D data | Repo 2 |
| 5 | Run overfit test with ThrowawayMLP on 3D data | Verify capacity | Repo 2 |
| 6 | Generate 50K+ production dataset on DGX Spark | After overfit passes | Repo 1 |
| 7 | Production training with OdmrMLP and OdmrCNN | Days 30-45 | Repo 2 |

---

# 3. Final technical report Technical Narrative

**Source:** Gemini 2.5 Deep Think
**Date:** 2026-03-27
**Prompt topic:** Report structure, narrative arc, audience strategy, Silver license framing
**Status:** Reviewed — Claude recommendations inline

---

## Claude Review Summary

**Overall assessment:** Excellent strategic framework. The three-audience model (Program Manager, ML scientist, GNC engineer) and "build the cage before the beast" narrative arc are exactly right. The Silver license framing language is strong enough to use nearly verbatim. Five specific adjustments needed before using as a template.

**Key adjustments:**
1. Rebalance page budget — validation section needs more space
2. Add explicit train/test separation documentation requirement
3. Replace Nyquist plot with annotated block diagram (lower risk)
4. Hedge MagNav.jl metric as "plausibility validation"
5. Add explicit Limitations subsection with page allocation

---

## 3.1 Report Outline with Page Budget

> **Claude note:** Gemini's original budget adjusted below. Stole 1 page each from ConOps and Safety Architecture, gave both to Validation. Added half-page Limitations subsection.

| # | Section | Pages | Feeds From |
|---|---------|-------|------------|
| 1 | Executive Summary & BLUF | 1 | All deliverables |
| 2 | Operational Context: Quantum Navigation in Cislunar Space | 1 | Background |
| 3 | Safety Architecture: Bounded Hybrid Simplex RTA | 3 | Deliverable 3 (Safety) |
| 4 | Deliverable 1: Validated Synthetic Data Pipeline | 3 | Deliverable 1 |
| 5 | Deliverable 2: Cognitive Control & Edge Quantization | 4 | Deliverable 2 |
| 6 | Deliverable 3: FPGA Implementation & SWaP-C Analysis | 3 | Deliverable 3 (Timing/Power) |
| 7 | System Validation & 5-Metric Evaluation | 8 | All deliverables |
| 8 | Limitations & Future Work | 0.5 | Honest gap analysis |
| — | **Total** | **23.5** | — |

### Section Details

**Section 1: Executive Summary & BLUF (1 page)**
- Bottom Line Up Front: problem, solution, KPP met/not met
- Essential: "KPP Scorecard" table (5 metrics, target vs achieved, pass/fail)
- One paragraph on bounded hybrid safety — the reviewer reads this first

**Section 2: Operational Context (1 page)**

> **Claude note:** Gemini allocated 2 pages here. Overkill for this plan — the reviewer already knows the problem space from the original plan. One page with a ConOps figure is sufficient. Save the space for validation.

- Why NV-diamond magnetometers, why classical PID fails for long-duration drift
- Essential figure: high-level ConOps diagram (satellite, magnetometer, control loop)

**Section 3: Safety Architecture (3 pages)**

> **Claude note:** Gemini allocated 4 pages. The safety argument is critical but 3 pages is sufficient if the block diagram is well-annotated. The formal Lur'e/Circle Criterion framing needs 1 paragraph, not a full page — reviewers who understand it will get it fast, reviewers who don't will trust the NASA IFCS and Auto-GCAS precedents more than the math.

- The "cage before the beast" section — this goes BEFORE any AI discussion
- Essential figure: Simplex RTA block diagram with sector bounds, slew-rate limiter, watchdog, bumpless transfer path clearly annotated
- Formal framing: 1 paragraph on Lur'e/Circle Criterion + Absolute Stability
- Precedents: NASA IFCS F-15, Air Force Auto-GCAS (both 1-2 sentences each)

> **Claude note (important):** Gemini recommends a Nyquist plot. I'd skip it unless you've actually computed plant transfer functions. A schematic Nyquist plot will look like bluffing to a controls reviewer. The annotated block diagram with sector bounds is provably correct from architecture alone — no plant model parameters needed.

**Section 4: Deliverable 1 — Synthetic Data Pipeline (3 pages)**
- SimOS + coupled noise model (OU processes for temperature, B1)
- Asymmetric lineshape corruption (Fano distortion)
- Essential figure: synthetic spectrum overlay showing corruption effects
- Essential table: corruption parameter ranges and physical justification

> **Claude addition:** Include explicit train/test separation protocol documentation here or in Section 7. The playbook requires this. Table format: split sizes, seed ranges, parameter distribution shifts between train and test.

**Section 5: Deliverable 2 — Cognitive Control & Edge Quantization (4 pages)**
- Dual MLP/CNN architecture with VectorBlox op constraints
- Composite angular + Huber loss function rationale
- INT8 QAT via TorchAO → ONNX → TFLite → vnnx_compile pipeline
- Essential table: Quantization Impact Matrix (FP32 vs INT8: accuracy, latency, memory)
- Essential figure: export pipeline flow diagram

**Section 6: Deliverable 3 — FPGA Implementation & SWaP-C (3 pages)**
- SmartHLS PID timing: target <150 µs, achieved X ns
- VectorBlox CNN inference: target <1 ms, achieved X ms
- Resource utilization: LUTs, LSRAM, Math Blocks, DSPs
- Power estimation: SmartPower post-P&R analysis
- Essential figure: execution timeline (Gantt-style showing PID cycles vs CNN async updates)
- Essential table: resource utilization breakdown

**Section 7: System Validation & 5-Metric Evaluation (8 pages)**

> **Claude note:** This is the most important section. Each metric needs ~1.5 pages (figure + discussion + interpretation). Gemini's 6-page allocation was too tight.

- Metric 1: Spherical Heading Error Profile (1.5 pages)
  - Heatmap figure showing error vs rotation angle
  - PID-only vs AI-augmented overlay
- Metric 2: Asymmetric Inversion Bias (1.5 pages)
  - Histogram of bias across B1 gradient range
  - <5 nT target line
- Metric 3: Frequency-Partitioned PSD (1.5 pages)
  - Log-log PSD plot with drift band (<0.1 Hz) and white noise band (>1 Hz) highlighted
  - >10× suppression demonstrated in drift band
- Metric 4: Allan Deviation — THE MONEY SHOT (1.5 pages)
  - Log-log ADEV plot: PID drifts upward at τ > 5 sec, AI-augmented flattens
  - This is the single most compelling figure in the report
- Metric 5: MagNav.jl Positioning RMSE (2 pages)

> **Claude note (important):** This is the weakest metric. You're injecting synthetic noise characteristics into the SGL 2020 flight data framework. A reviewer who knows MagNav.jl will probe whether your noise model is realistic. Frame this as "system-level plausibility validation" — NOT "proof of navigation performance." Be explicit: "This metric validates that the sensor-level improvements demonstrated in Metrics 1-4 translate to meaningful navigation error reduction when integrated into a representative flight framework. Full validation requires later-stage hardware-in-the-loop testing."

**Section 8: Limitations & Future Work (0.5 pages)**

> **Claude addition:** Gemini mentions "don't hide limitations" but doesn't allocate page space. You need this. Builds reviewer trust faster than anything else.

- Bz-only golden dataset: 1D inversion demonstrated, 3D heading correction requires expanded dataset (in progress)
- Synthetic-to-real gap: trained on SimOS, not hardware data. A later hardware-in-the-loop stage would address this.
- Silver license: synthesis on commercial PolarFire, not RT PolarFire
- 100-sample overfit vs production training: gradient plumbing verified, production 50K+ dataset in scope

---

## 3.2 Technical Narrative Arc

**Gemini's framing (adopted with modifications):**

The core storytelling strategy: **"Build the cage before you introduce the beast."**

1. **The Hook (Sections 1-2):** NV-diamond magnetometers are essential for GPS-denied PNT, but nonlinear drift makes them unusable for long-duration missions. Classical PID is too rigid; AI is smart enough but unsafe for spaceflight.

2. **The Preemption (Section 3):** Before the controls reviewer writes "NN will crash the satellite," you introduce the bounded hybrid architecture. You prove: even if the CNN hallucinates due to an SEU, the spacecraft cannot destabilize. *This must come before any ML discussion.*

3. **The Engine (Sections 4-6):** Now that the reviewer trusts you won't crash the ship, they're mentally freed to be impressed by the edge-ML engineering. Rigorous data generation → elegant INT8 compression → deterministic FPGA timing.

4. **The Climax (Section 7):** The Allan Deviation plot. Because safety bounds were established in Section 3, the reviewer sees the flattened drift curve not as "overfit ML simulation" but as a mathematically verified, deployable hardware reality.

5. **The Ask (Section 8):** Honest limitations.

---

## 3.3 Bounded Hybrid Architecture Language

> **Claude note:** This paragraph from Gemini is excellent. Use it nearly verbatim in Section 3. The only change I'd make: add the specific sector bound values (±5%) and the watchdog timeout (1.0 ms) inline rather than in a separate table — the controls reviewer wants to see the numbers in the prose.

**Recommended language for Section 3:**

"To resolve the inherent tension between deep learning's non-determinism and strict aerospace safety requirements, the cognitive control engine is structured as a bounded hybrid Simplex Run-Time Assurance (RTA) architecture. The foundational stabilization is governed by a strictly proper, deterministic classical PID controller (SmartHLS C++, <150 µs latency), ensuring mathematically verifiable, high-bandwidth linear tracking.

Rather than placing the neural network in the direct feedback path, the INT8-quantized CNN operates purely as a bounded feedforward compensator for adaptive bias cancellation. The CNN's control authority is hardware-limited to ±5% of the total actuator range via sector saturation clamps, and the discrete derivative du_AI/dt is clamped by a slew-rate limiter — together ensuring the AI physically cannot push the plant outside the linear capture range of the underlying PID.

By geometrically restricting the AI's output, we formalize the hybrid system as a Nonlinear Lur'e Problem. Because the linear plant and PID controller satisfy the strict positive realness condition, and the AI acts as a memoryless nonlinearity restricted to the sector [0, K], Absolute Stability is formally guaranteed via the Circle Criterion. Furthermore, an execution watchdog continuously monitors the VectorBlox AXI bus. If inference exceeds the 1.0 ms deadline, the watchdog triggers a deterministic bumpless transfer (I_new = I_old + u_AI_old), smoothly zeroing the feedforward path without inducing control transients."

---

## 3.4 Common Final Report Mistakes

From Gemini (all valid, Claude-endorsed):

1. **"Death by Math" with No ConOps:** Translate component physics into operational capability. "Flattening ADEV at τ > 5 sec allows a satellite to maintain X-meter positioning CEP for Y hours longer without GPS."

2. **Treating the work as Basic Research:** This is applied R&D. Frame every deliverable as a retired risk, not "more research needed."

3. **Ignoring SWaP-C:** Space customers care about watts and logic elements as much as AI accuracy. Don't bury Deliverable 3.

4. **Hiding Limitations:** If bias hit 5.2 nT instead of <5 nT, say so and explain the mitigation. Honest gap analysis builds trust.

> **Claude addition:**

5. **Underselling the Safety Story:** The bounded hybrid architecture is your single strongest differentiator. Most AI-for-space reports hand-wave safety. You have a formal mathematical guarantee. Lead with it, repeat it, and make sure it's in the executive summary.


---

## 3.6 Essential Figures Checklist

| # | Figure | Section | Priority |
|---|--------|---------|----------|
| 1 | KPP Scorecard table | Exec Summary | Must-have |
| 2 | ConOps diagram | Section 2 | Must-have |
| 3 | Simplex RTA block diagram (annotated) | Section 3 | Must-have |
| 4 | Synthetic spectrum overlay (clean vs corrupted) | Section 4 | Must-have |
| 5 | Train/test separation table | Section 4 or 7 | Must-have |
| 6 | Quantization Impact Matrix | Section 5 | Must-have |
| 7 | Export pipeline flow diagram | Section 5 | Nice-to-have |
| 8 | Execution timeline (PID + CNN async) | Section 6 | Must-have |
| 9 | Resource utilization table | Section 6 | Must-have |
| 10 | Heading Error heatmap | Section 7 | Must-have |
| 11 | Asymmetric Inversion Bias histogram | Section 7 | Must-have |
| 12 | Frequency-Partitioned PSD plot | Section 7 | Must-have |
| 13 | Allan Deviation log-log plot (THE MONEY SHOT) | Section 7 | Must-have |
| 14 | MagNav.jl RMSE visualization | Section 7 | Must-have |

---

# 4. Coupled Noise Model & Cascaded SDEs for Synthetic Data

**Source:** Gemini 2.5 Deep Think
**Date:** 2026-04-01
**Prompt topic:** Physical realism of T(t) and B₁(t) coupling in synthetic data, mathematical framework, defensible parameters, and narrative implications
**Status:** Raw — not yet Claude-reviewed

---

## 4.1 Is Independent Sampling of T(t) and B₁(t) Physically Realistic?

No, independent sampling is a significant oversimplification for a highly integrated space-borne sensor. In a miniaturized, tightly packed payload (like SBQuantum's 483g, <6W unit), thermal and electronic states are intimately and causally coupled.

The primary physical mechanisms that couple T(t) to B₁(t) include:

**Microwave Amplifier/VCO Gain Drift:** Commercial off-the-shelf (COTS) RF solid-state amplifiers have deterministic temperature coefficients. As the CubeSat thermal bus cycles, the amplifier gain typically drops by ∼−0.02 to −0.05 dB/°C, causing the output power to drift.

**Resonator/Antenna Thermal Expansion:** The microwave delivery structure (e.g., a split-ring resonator or planar loop) will expand and contract with temperature, and its PCB substrate's dielectric constant will shift. This alters the resonant frequency and changes the impedance match (S₁₁). Consequently, the actual B₁ amplitude delivered to the diamond fluctuates even if the electrical source power remains perfectly constant.

**Power Bus Loading:** In a CubeSat, thermal extremes alter battery discharge efficiency and DC-DC converter load profiles, injecting low-frequency voltage ripple into the RF synthesizer.

---

## 4.2 Mathematical Framework: Cascaded SDEs

Option (b) — where T(t) drives B₁(t) causally, with its own OU fluctuations superimposed — is the most physically accurate and mathematically robust framework.

Temperature acts as a macroscopic, slow-moving latent variable. The microwave amplitude has a deterministic, causal dependence on T(t), but also suffers from fast, independent electronic phase/amplitude noise. Furthermore, for a LEO CubeSat, T(t) should not revert to a static mean; it should revert to a deterministic orbital sine wave representing the Sun/eclipse cycle.

**Recommended Cascaded SDE Implementation:**

**Orbital Thermal Baseline:**

T_env(t) = T_mean + ΔT_orb · sin(2πt / τ_orb)

**Sensor Temperature:** Models heat transfer from the bus and internal stochastic heating.

dT(t) = −θ_T · (T(t) − T_env(t)) · dt + σ_T · dW_T(t)

**Coupled Microwave Drive:** The target mean drifts with temperature, while the OU process captures fast electronic noise (like Automatic Level Control loops).

B₁,target(t) = B₁,nom · [1 + α_B1 · (T(t) − T_mean)]

dB₁(t) = −θ_B1 · (B₁(t) − B₁,target(t)) · dt + σ_B1 · dW_B1(t)

---

## 4.3 Physically Defensible Parameters for a 12U CubeSat

The SBQuantum reference (-65°C to +125°C) describes Thermal Vacuum (TVAC) survivability qualification testing (e.g., MIL-STD-883), not nominal operations. Operational internal baseplate temperatures for a passively managed 12U payload in LEO typically cycle by about ±10°C to ±15°C over a 90-minute orbit.

| Parameter | Recommended Value | Physical Justification |
|-----------|------------------|----------------------|
| τ_orb | 5400 s | Standard 90-minute Low Earth Orbit duration |
| T_mean, ΔT_orb | 20°C, 15°C | Simulates standard payload bay cycling from +5°C in eclipse to +35°C in sun |
| θ_T | 1.0×10⁻³ s⁻¹ | Thermal time constant (τ=1/θ) of ~16 minutes. 500g metallic payload has significant thermal mass, acts as low-pass filter |
| σ_T | 0.05 K·s⁻¹/² | Yields steady-state thermal standard deviation of ~1.1°C, matching random localized power cycling of nearby satellite subsystems |
| α_B1 | −0.0035 K⁻¹ | Coupling coefficient. Corresponds to COTS amplifier gain drop of roughly −0.03 dB/°C. (Since B₁ ∝ √Power, a 0.7% power drop per K is a ~0.35% amplitude drop per K) |
| θ_B1 | 10 s⁻¹ | Electronic regulation loops (VCOs, power regulators) stabilize much faster than thermal mass. τ_B1 = 0.1 s |
| σ_B1 | 0.006 × B₁,nom · s⁻¹/² | Intrinsic fast RF electronic noise. Yields steady-state fractional standard deviation of ~0.2% in microwave amplitude |

---

## 4.4 Spectral Diversity and ML Training

The independent OU model produces a physically impossible spectral landscape that will actively degrade your ML model's real-world accuracy.

Heading error in vector NV magnetometers is heavily driven by asymmetric AC Stark shifts across the four crystallographic axes. The AC Stark shift depends on B₁² and the detuning Δ from the NV resonance. Because temperature directly shifts the NV's Zero-Field Splitting (dD/dT ≈ −74 kHz/°C), an increase in temperature changes the detuning Δ while simultaneously dropping the B₁ amplitude.

This creates a highly specific, low-dimensional "correlation manifold" of spectral distortions. If you train on independent data, the ML model simply learns to denoise two separate, unconstrained channels, wasting network capacity on physical impossibilities. If trained on the coupled model, the AI learns that T telemetry is a predictive proxy for upcoming asymmetric Stark shifts. This allows the AI to correctly attribute these spectral distortions to thermal hardware drift rather than mistaking them for an actual physical rotation of the background magnetic field (heading error).

---

## 4.5 Defensibility: AI vs. PID

From a reviewer's perspective, using an independent OU model is a significant gap that could jeopardize the justification for the entire plan.

**Strategic reality:** Reviewers are highly skeptical of "AI for AI's sake." If your noise sources are independent, zero-mean SDEs, standard linear Single-Input Single-Output (SISO) control theory (e.g., decoupled PID loops or a classical Kalman filter) is mathematically optimal. An AI model will struggle to show a >50% improvement over a well-tuned PID in a decoupled simulation.

**Your strongest selling point for >50% heading error reduction is this:** Classical PIDs systematically fail on Multi-Input Multi-Output (MIMO) non-linearities with mismatched time constants.

By implementing the cascaded SDEs, you hand yourself the perfect narrative for why your AI is vastly superior to PID. You can explicitly state:

"Unlike traditional classical PID control — which treats temperature and RF fluctuations as independent error sources and fails to resolve their cross-sensitivities — our synthetic data pipeline models the causal thermal-RF cross-coupling inherent to SWaP-constrained CubeSats (α_B1 ≈ −0.35%/°C). This coupling induces complex, asymmetric AC Stark shifts across the NV axes that mimic magnetic heading errors. Our ML architecture is specifically trained to untangle this deterministic physical manifold — a task classical linear control theory cannot easily achieve — yielding a projected >50% reduction in heading error."

Implementing this framework takes only a few extra lines of Python, but it turns your synthetic data from a "toy math problem" into a rigorously grounded aerospace engineering digital twin.

---

# 5. Formal Verification & Safety Analysis of Simplex RTA Architecture

**Source:** Gemini 2.5 Deep Think
**Date:** 2026-04-01
**Prompt topic:** Formal mathematical verification of the Bounded Simplex RTA framework for the Final Technical Report
**Status:** Raw — not yet Claude-reviewed

---

## 5.1 Verification of Absolute Stability (Lur'e Problem & ISS Formulation)

**Objective:** Formally prove that the sector-bounded AI feedforward network preserves the absolute stability of the closed-loop system, regardless of the neural network's internal behavior.

**Proof Framework:**
We formulate the architecture as a Lur'e problem. The strictly proper, linear time-invariant (LTI) forward path consists of the baseline PID controller C(s) and the NV magnetometer plant P(s). The closed-loop transfer function mapping an injection at the AI node to the tracking error e(t) is H_{u→e}(s) = −P(s) / (1 + P(s)C(s)). Because the classical PID loop is strictly asymptotically stable by design, H_{u→e}(s) is Hurwitz.

The AI inference acts as a state-dependent nonlinearity Φ(e,t). The Simplex hardware enforces a strict, absolute saturation clamp:

|u_AI_clamped| = |Φ(e,t)| ≤ α · ΔU_range

In the standard Circle Criterion, absolute stability requires the nonlinearity to reside within a sector [0,K]. Because the RTA clamp enforces an absolute magnitude bound rather than a state-proportional bound, the effective secant gain K_eff = |Φ(e,t)/e| mathematically decays to zero as the state magnitude |e| increases (lim_{|e|→∞} K_eff = 0). Consequently, for any arbitrary ε > 0, the AI nonlinearity resides in the local sector [0, ε] for all states outside a finite compact region near the origin.

To formalize this for infinite domains, we map the bounding to Input-to-State Stability (ISS):

1. The unperturbed baseline LTI system (H_{u→e}(s)) is strictly proper and bounded-input bounded-output (BIBO) stable.
2. The hardware clamp rigorously ensures the AI injection is an L∞-bounded disturbance (‖u_AI_clamped‖_∞ ≤ α · ΔU_range).
3. By the Convolution Theorem, driving a strictly stable LTI system with a uniformly bounded input guarantees a strictly bounded state.

**Conclusion:** The state trajectories of the closed-loop system are mathematically proven to be Globally Uniformly Ultimately Bounded (GUUB). Regardless of whether the AI's behavior is optimal, chaotic, or actively adversarial, the system cannot mathematically diverge. Absolute stability is inherently preserved.

---

## 5.2 Maximum Sector Bound (α_max) for the NV Magnetometer Plant

**Objective:** Determine the theoretical limit for the hardware clamp α to prevent the AI from forcing a loss-of-lock on the quantum resonance.

**Analysis:**
The NV magnetometer FLL fundamentally acts as an integrator P(s) = K_nv / s, where the gain relies on the linear region of the Optically Detected Magnetic Resonance (ODMR) continuous-wave lineshape. This LTI approximation is valid only within the linear capture range, bounded by half of the full-width at half-maximum linewidth (±Γ/2).

With a classical PI controller C(s) = K_p + K_i/s, the disturbance rejection transfer function becomes a second-order bandpass filter:

H_{u→e}(s) = K_nv · s / (s² + K_nv · K_p · s + K_nv · K_i)

The peak disturbance amplification occurs exactly at the resonant crossover frequency ω_n = √(K_nv · K_i), yielding a peak magnitude response of ‖H(s)‖_∞ = 1/K_p.

The worst-case transient disturbance injected by the AI is a maximum-amplitude step bounded by the sector clamp (±α · ΔU_range). To guarantee physical stability, the maximum induced frequency error must not exceed the ODMR linear bound:

‖e‖_∞ = ‖H(s)‖_∞ · (α · ΔU_range) = α · ΔU_range / K_p ≤ Γ/2

Solving for the maximum safe sector bound:

**α_max ≤ K_p · Γ / (2 · ΔU_range)**

**Conclusion:** The maximum permissible AI control authority (α) is directly proportional to the classical proportional gain (K_p) and the physical ODMR linewidth (Γ). The hardware clamp parameter must be parameterized strictly below this α_max threshold to guarantee that no instantaneous AI anomaly can break the quantum lock.

---

## 5.3 Fixed-Point Truncation Risk and Margin Analysis

**Objective:** Verify that Q16.16 fixed-point arithmetic rounding safely enforces the 4.5% bounds without risking a truncation-induced violation of the 5.0% safety compliance limit.

**Analysis:**
The SmartHLS pipeline evaluates the clamp bounds utilizing hls::ap_fixpt<32,16> (1 sign bit, 15 integer bits, 16 fractional bits), establishing a least significant bit (LSB) resolution of 2⁻¹⁶ ≈ 1.526×10⁻⁵.

**Static Coefficient Quantization:**
The hardware target α = 0.045 is compiled natively as ⌊0.045 × 65536⌉ = 2949. The actual constant executed in hardware is 2949/65536 ≈ 0.04499817. This strictly bounds the static representation error to ε_α ≈ 1.83×10⁻⁶.

**Dynamic Multiplication Truncation:**
During runtime evaluation of the dynamic limits (±α_FP × ΔU_range), the SmartHLS II=1 multiplier generates an intermediate Q32.32 product. Truncating this pipeline back to Q16.16 drops the lower 16 fractional bits, contributing a maximum flooring truncation error of exactly 1 LSB = 1.526×10⁻⁵.

Normalizing the error relative to the fractional scale, the absolute worst-case arithmetic drift is:

ε_worst = ε_α + ε_trunc ≈ 1.83×10⁻⁶ + 1.526×10⁻⁵ = 1.71×10⁻⁵

**Conclusion:** The engineering safety margin between the hardware limit and the compliance target is 0.050 − 0.045 = 0.005 (0.5%). This margin is roughly 292 times larger than the absolute worst-case combined arithmetic truncation error (1.71×10⁻⁵). The 5.0% compliance boundary is definitively guaranteed to never be breached due to bit-width quantization.

---

## 5.4 Verification of Bumpless Transfer at Watchdog Timeout

**Objective:** Mathematically prove that the anomaly recovery algorithm (I_new = I_old + u_AI_old) creates zero discontinuous voltage steps upon a 1 ms watchdog timeout.

**Proof:**
At the standard discrete step k−1 (prior to timeout), the total actuator output is:

u_total(k−1) = P(k−1) + I(k−1) + D(k−1) + u_AI_old

At cycle k, the watchdog triggers. The AI inference is zeroed out (u_AI → 0), and the SmartHLS pipeline executes the bumpless transfer algorithm, seamlessly injecting the stalled AI output into the base integrator state prior to the PID sum:

I_base(k) = I(k−1) + u_AI_old

The standard II=1 pipelined PID calculates the new integrator state based on the current cycle error e(k):

I_new(k) = I_base(k) + K_i · e(k) = [I(k−1) + u_AI_old] + K_i · e(k)

The new total actuator output at step k evaluates to:

u_total(k) = P(k) + [I(k−1) + u_AI_old + K_i · e(k)] + D(k) + 0

To evaluate the voltage discontinuity generated at the DAC handoff, we calculate Δu = u_total(k) − u_total(k−1):

**Δu = [P(k) − P(k−1)] + [D(k) − D(k−1)] + K_i · e(k)**

**Conclusion:** The term u_AI_old perfectly and algebraically cancels out. The voltage step discontinuity Δu consists exclusively of the natural discrete progression of the classical PID algorithm. Because the physical state changes over a single 200 MHz cycle (dt = 5 ns) are functionally zero, the transfer inherently guarantees zero artificial phase shock to the RF actuator.

---

## 5.5 Slew-Rate Limiter, Sector Clamp, and Limit Cycle Resonance

**Objective:** Assess the physical vulnerability of the FLL to resonant limit cycles generated by the interaction of the slew-rate limiter and the sector clamp.

**Analysis via Describing Functions:**
An architectural vulnerability exists if the CNN degrades to an antagonistic "bang-bang" mapping (e.g., alternating between ±∞). The slew-rate limiter restricts this toggling to a deterministic ±Δ_max rate, mathematically transforming the square wave into a triangular or trapezoidal wave constrained by the sector clamp (±α · ΔU_range).

The fundamental oscillation frequency of this induced triangular wave is:

f_osc = Δ_max · f_clk / (4 · α · ΔU_range)    (where f_clk = 200 MHz)

Under Describing Function (N(A,ω)) analysis, a cascaded rate-limiter and saturation block introduces a significant frequency-dependent phase lag approaching −90°. If this induced fundamental frequency f_osc aligns with the closed-loop natural resonant crossover frequency of the PID loop (f_n = (1/2π)√(K_nv · K_i)), the FLL acts as a resonant bandpass filter.

Because the baseline PID loop satisfies the Barkhausen criterion under forced oscillation, the closed-loop Q-factor will amplify this triangle wave. While Section 5.1 guarantees this oscillation is mathematically bounded from divergence, it acts as a persistent resonant forcing function that will artificially widen the error variance, severely degrading the DC steady-state sensitivity (Allan variance) of the magnetometer.

**Engineering Recommendation:**
To comprehensively neutralize this physical limit cycle, the slew-rate limiter Δ_max must be statically configured such that the fastest possible limit cycle f_osc is located strictly at least a decade above or below the closed-loop PID bandwidth (f_n). This allows the natural LTI roll-off of the plant inertia to harmlessly filter out the forced oscillation.

---

# 6. Closed-Form ODMR Resonance Frequencies & Vectorized Implementation

**Source:** Gemini 2.5 Deep Think
**Date:** 2026-04-01
**Prompt topic:** Analytical O(1) replacement for numerical O(N³) matrix diagonalization in SimOS/QuTiP ODMR spectrum generation
**Status:** Raw — not yet Claude-reviewed

---

## 6.1 Closed-Form Resonance Frequencies

For a single NV crystallographic orientation in its local reference frame (ẑ is the NV axis, x̂ aligns with strain), the 3×3 electron-spin Hamiltonian is:

H_elec = D·Sz² + E·(Sx² − Sy²) + γ_e·(Bx·Sx + By·Sy + Bz·Sz)

where γ_e ≈ 28.024 MHz/mT.

By applying a shift of −(2/3)D·I to make the matrix traceless, the characteristic equation det(H − λI) = 0 reduces exactly to a depressed cubic polynomial x³ + px + q = 0, where:

p = −D²/3 − E² − γ_e²|B|²

q = 2D³/27 − 2DE²/3 + γ_e²[D/3·(Bx² + By² − 2Bz²) − E·(Bx² − By²)]

Because the Hamiltonian is strictly Hermitian, all roots are real and can be computed non-iteratively via Cardano's trigonometric formula. The three exact electronic energy levels (k ∈ {0,1,2}) are:

λ_k = 2D/3 + 2·√(−p/3) · cos((1/3)·arccos[(3q/2p)·√(−3/p)] − 2πk/3)

Sorting these roots continuously guarantees λ₀ < λ₁ < λ₂, where λ₀ is the m_s = 0 ground state (for Bz < 102 mT).

---

## 6.2 Analytical Hyperfine Splitting (Avoiding 9×9 Diagonalization)

Instead of solving eigenvectors numerically, we use the Hellmann-Feynman theorem to extract the exact electron spin expectation values ⟨S_i⟩_k = (1/γ_e)·∂λ_k/∂B_i. Implicitly differentiating the characteristic polynomial gives exact analytical equations for each state k:

N_k = 3λ_k² − 4Dλ_k + D² − E² − γ_e²|B|²

⟨Sx⟩_k = 2γ_e·Bx·(λ_k − D + E) / N_k

⟨Sy⟩_k = 2γ_e·By·(λ_k − D − E) / N_k

⟨Sz⟩_k = 2γ_e·Bz·λ_k / N_k

The ¹⁴N nuclear spin effectively quantizes along this vector. The effective hyperfine coupling for state k is:

A_eff^(k) = √(A_⊥²·(⟨Sx⟩_k² + ⟨Sy⟩_k²) + A_∥²·⟨Sz⟩_k²)

The 6 CW-ODMR resonance frequencies for this NV orientation (branches k ∈ {1,2} and nuclear spin m_I ∈ {−1,0,1}) are:

f_{k,m_I} = (λ_k − λ₀) + m_I·(A_eff^(k) − A_eff^(0))

---

## 6.3 Voigt Profile Lineshape Parameters

The spectrum is modeled using a Voigt profile V(f; f_c, σ, γ) which natively handles the convolution of the homogeneous and inhomogeneous broadening:

**Lorentzian HWHM (γ):** Dominated by the short T₂* from the fluctuating P1 (Nitrogen) spin bath. Given 1–7 MHz FWHM for 1–300 ppm P1, the linear mapping for the Half-Width at Half-Maximum is γ ≈ (1/2)·(1.0 MHz + 0.02 × [P1 ppm]).

**Gaussian Std Dev (σ):** Represents unresolved static distributions (e.g., ¹³C isotopic presence, microscopic strain gradients across the focal volume). It is fixed by experimental fits: σ = Δ_Gauss / (2√(2ln2)) ≈ Δ_Gauss / 2.355.

---

## 6.4 Ensemble Summation over the {111} Lattice

To compute the bulk diamond spectrum, define the 4 crystallographic NV axes in the lab frame:

û₁ = (1/√3)·(1,1,1), û₂ = (1/√3)·(1,−1,−1), û₃ = (1/√3)·(−1,1,−1), û₄ = (1/√3)·(−1,−1,1)

Select arbitrary orthogonal unit vectors x̂_i, ŷ_i strictly normal to each û_i.

For your lab field B_ext, pre-compute the 4 local vectors B^(i) = (B_ext · x̂_i, B_ext · ŷ_i, B_ext · û_i).

Run the analytical model above on the 4 projected fields to extract 4 × 6 = 24 central frequencies f_c^(j).

Sum the 24 Voigt distributions.

---

## 6.5 Cache & Recomputation Strategy

Splitting evaluation boundaries drastically accelerates MCMC fitting or spatial field mapping:

| Sweeping Parameter | Resonance Frequencies f_c | Lineshape Widths | Execution Path |
|---|---|---|---|
| P1 Concentration | Cached | Recompute | Frequencies are static. Update Lorentzian γ and only re-sum the Voigt profiles. |
| Temperature (T) | Recompute | Cached | Recompute D(T) and polynomial roots. Local geometric field projections B^(i) remain static and should be cached! |
| B-field Vector | Recompute | Cached | Roots must be updated. Re-evaluate the local geometry projections B^(i). |

---

## 6.6 Complexity Breakdown & Approximation Limits

**Speed (SimOS vs. Analytical):** QuTiP dynamically instantiates Hermitian 3×3 or 9×9 Qobj matrices and calls iterative LAPACK eigensolvers (np.linalg.eigh), resulting in O(M³) complexity. The pure Python object overhead causes executions to stagnate at ~8 ms. Because the analytical path relies purely on C-mapped NumPy vectorized scalars (np.arccos, np.cos), its computational complexity is mathematically O(1). Generating spectra over 10,000 spatial bins simultaneously executes in roughly 40 µs per spectrum (a >100× speedup).

**Where the Analytical Approximations Break Down:**
The exact trigonometric roots for the electron Hamiltonian never break down. They unconditionally match numerical diagonalization up to infinite field/strain because they are exact algebraic solutions, not Taylor expansions.

The analytical model only fails in the secular hyperfine approximation (the Hellmann-Feynman step), which fails when electron states physically mix and destroy the Δm_I = 0 selection rules. This happens exactly at the Ground State Level Anti-Crossing (GSLAC) (Bz ≈ 102.4 mT) or at strictly zero-field if transverse strain drastically outweighs the hyperfine field. For standard vector magnetometry regimes, it is completely rigorous.

---

## 6.7 Drop-in Vectorized Implementation

This script takes an array of magnetic fields (e.g. 10 spatial bins at once) and processes them identically without a single Python for-loop.

```python
import numpy as np
from scipy.special import wofz

def get_nv_orientations():
    """Returns the 4 crystallographic axes and local x,y bases."""
    u = np.array([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]) / np.sqrt(3)
    x = np.array([[1, -1, 0], [1, 1, 0], [1, 1, 0], [1, -1, 0]]) / np.sqrt(2)
    y = np.cross(u, x)
    return x, y, u

def analytical_nv_resonances(B_ext_mT, T=300.0, E_strain=5.0):
    """
    B_ext_mT: Array of shape (..., 3) representing B-fields in mT
    Returns: Array of shape (..., 24) containing the 24 resonance frequencies in MHz
    """
    gamma_e = 28.024
    D = 2870.0 - 0.0742 * (T - 300.0)
    A_par, A_perp = -2.14, -2.70
    
    # 1e-8 mT infinitesimal offset prevents 0/0 singular limits mathematically
    B_ext = np.atleast_2d(B_ext_mT) + 1e-8 
    x, y, u = get_nv_orientations()
    
    # Fast Projection B-field to local frames. Shape: (..., 4 axes)
    Bx = np.einsum('...j,ij->...i', B_ext, x) * gamma_e
    By = np.einsum('...j,ij->...i', B_ext, y) * gamma_e
    Bz = np.einsum('...j,ij->...i', B_ext, u) * gamma_e
    
    B2 = Bx**2 + By**2 + Bz**2
    Bperp2 = Bx**2 + By**2
    
    # Depressed cubic coefficients
    p = -(D**2)/3 - E_strain**2 - B2
    q = (2*D**3)/27 - (2*D*E_strain**2)/3 + (D/3)*(Bperp2 - 2*Bz**2) - E_strain*(Bx**2 - By**2)
    
    # Exact trigonometric roots
    arg = np.clip((3*q / (2*p)) * np.sqrt(-3/p), -1.0, 1.0)
    theta = np.arccos(arg) / 3.0
    r = 2 * np.sqrt(-p / 3.0)
    
    # Eigenvalues: Shape (..., 4, 3 states)
    lams = np.stack([
        2*D/3 + r * np.cos(theta),
        2*D/3 + r * np.cos(theta - 2*np.pi/3),
        2*D/3 + r * np.cos(theta - 4*np.pi/3)
    ], axis=-1)
    lams = np.sort(lams, axis=-1) # m_s = 0 is lams[..., 0]
    
    # Hellmann-Feynman expectation values
    den = 3*lams**2 - 4*D*lams + D**2 - E_strain**2 - B2[..., None]
    
    Sx = 2 * Bx[..., None] * (lams - D + E_strain) / den
    Sy = 2 * By[..., None] * (lams - D - E_strain) / den
    Sz = 2 * Bz[..., None] * lams / den
    
    # Effective hyperfine coupling
    A_eff = np.sqrt(A_perp**2 * (Sx**2 + Sy**2) + A_par**2 * Sz**2)
    
    # Extract 24 Frequencies
    f_res = []
    for k in [1, 2]: # m_s = -1, +1 branches
        f_center = lams[..., k] - lams[..., 0]
        for mI in [-1, 0, 1]:
            f_res.append(f_center + mI * (A_eff[..., k] - A_eff[..., 0]))
            
    return np.stack(f_res, axis=-1) # Shape: (..., 24 lines)

def fast_odmr_spectrum(f_scan_MHz, freqs_MHz, P1_ppm=10.0, delta_G=1.0, contrast=0.01):
    """ Builds Voigt lineshapes around cached analytical frequencies. """
    gamma_L = (1.0 + 0.02 * P1_ppm) / 2.0  # Lorentzian HWHM (MHz)
    sigma_G = delta_G / 2.355              # Gaussian Std Dev (MHz)
    
    # Broadcast frequencies: z shape -> (..., 24, M_freqs)
    z = (f_scan_MHz[None, None, :] - freqs_MHz[..., None]) + 1j * gamma_L
    z /= (sigma_G * np.sqrt(2))
    
    # scipy Faddeeva function mapped to real-part Voigt profile
    voigt = wofz(z).real / (sigma_G * np.sqrt(2 * np.pi))
    
    # Sum over the 24 lines 
    spectrum = 1.0 - contrast * np.sum(voigt, axis=-2)
    return np.squeeze(spectrum)
```

---

# Appendix: Document Index

| # | Topic | Date | Status | Key Insight |
|---|-------|------|--------|-------------|
| 1 | Training Loop Design | 2026-03-26 | Claude-reviewed | Composite angular + Huber loss; INT8 quantization paradox; sign ambiguity catch |
| 2 | 3D B-Field Dataset Design | 2026-03-27 | Claude-reviewed | Remove b_perp as independent param; Z-score normalization WRONG; hemisphere constraint |
| 3 | Final Report Narrative | 2026-03-27 | Claude-reviewed | "Cage before beast" arc; Silver license framing; 25-page budget |
| 4 | Coupled Noise Model / SDEs | 2026-04-01 | Raw | T→B₁ causal coupling; cascaded OU processes; AI vs PID defensibility narrative |
| 5 | Formal Safety Verification | 2026-04-01 | Raw | Lur'e/ISS proof; α_max derivation; Q16.16 margin analysis; bumpless transfer proof |
| 6 | Closed-Form ODMR Solver | 2026-04-01 | Raw | Cardano trigonometric roots; Hellmann-Feynman hyperfine; >100× speedup over QuTiP |

---

*End of combined document. The three outputs dated 2026-04-01 (Sections 4, 5, 6) have NOT been Claude-reviewed. Review before incorporating into any deliverable.*

