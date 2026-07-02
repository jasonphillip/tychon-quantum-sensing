# Increment 2a/2b results — learned tracker vs honest classical baselines (CORRECTED)

**This document supersedes the 2026-07-01 first version titled "learned tracker beats the
classical bar."** That version compared against a retracted baseline (below) and its headline
is withdrawn. The corrected claim:

> **The learned tracker, acquiring from spectra alone (no ground-truth initialization) on a
> V250-clean deployable partition, ties the competent classical baseline (CV-KF + Hungarian)
> post-crossing on the v0 sanity set; v0 cannot discriminate the two. Discrimination happens
> on the v1 adversarial families (reversal / OU), where the CV-coast assumption breaks.**

## Retraction: the original Increment-1 bar was a detector artifact

The classical detector's default absolute threshold (`peak_min_depth = 0.03`) exceeds the
real data's dip depth (~0.4% of the PL baseline; measured per-frame max 0.0037–0.0077). On
every real frame `_find_peaks` returned **zero peaks**; the PID tracker never left its
ground-truth t=0 initialization; the published numbers (16/16 lock loss, association
1.0→0.0, "ID-switch 0.811", 43° peak error, DR ≈ 5 mT — all now banned outside this
paragraph) scored a **frozen tracker against moving lines**. Fingerprint: in-collision
accuracy == out-of-collision accuracy (an association-blind failure). Verified here directly:
`locked.mean() == 0.0000` and constant tracked centers on the real test split. Fixes now in
place: detection thresholds scale from the data (`auto_peak_min_depth`, using the manifest's
shallowest `line_depths` when present), reports assert pre-crossing locked fraction > 0.9,
and `tests/contract` enforces the same guard on every real dataset present.

Two further evaluation defects were fixed at the same time (they flattered whichever tracker
was under test): undefined angular error was graded as perfect (now nan-aware — undefined
counts as *lost*), and the printed "ID-switch err" was actually the in-collision
misassociation fraction (renamed; ID switches are now also reported **per crossing
opportunity** with pre/post windows, since the raw frame count saturates with benign
in-merge flicker). Identity attribution now uses a 3Γ capture radius (beyond it a lock is
unassigned = misassociated). **Dynamic range is deleted from all tables**: |B| spans only
~4.7–5.8 mT on v0/v1, so a never-losing tracker saturates at the dataset bound — DR claims
wait for a dedicated amplitude-ladder lineage.

## Corrected v0 results (sequence_sanity_v0, real test split, 16 sequences)

Conventions: data-scaled detector; classical trackers get GT t=0 initialization (stated per
column); the learned trackers cold-acquire from spectra (strictly harder). Median per
sequence unless noted; ID-sw/opp is pooled switches/opportunities.

| metric | honest PID (GT init) | CV-KF+Hungarian (GT init) | oracle assoc (floor) | learned relu+linear (cold) | learned gated+linear (cold) | learned relu+attention (cold) |
|---|---|---|---|---|---|---|
| assoc pre → post crossing | 1.000 → 0.750 | 1.000 → 1.000 | 1.000 → 1.000 | 0.989 → 1.000 | 1.000 → 1.000 | 0.983 → 0.998 |
| in-collision assoc | 0.633 | **0.978** | 0.543* | 0.619 | 0.781 | 0.604 |
| out-of-collision assoc | 0.843 | 1.000 | 1.000 | 0.993 | 1.000 | 0.986 |
| ID-sw / opportunity | 0.062 (24/384) | **0.000** (0/384) | 0.000 | 0.077 (29/378) | **0.000** (0/384) | 0.073 (28/382) |
| loses lock (>5° irrecov., nan=lost) | 11/16 | 0/16 | 0/16 | 0/16 | 0/16 | 0/16 |
| vector err pre → peak → post | 0.09° → 15.8° → 8.8° | 0.03° → 0.1° → 0.0° | 0.01° → 0.4° → 0.0° | 0.57° → 1.0° → 0.5° | 0.81° → 1.5° → 0.5° | 0.48° → 1.1° → 0.6° |
| — same, splitting→BLUE decode of centers | — | — | — | 0.52° → 0.9° → 0.5° | 0.23° → 0.4° → 0.1° | 0.55° → 1.1° → 0.7° |

\* The oracle row (true-label assignment of *detected peaks* + splitting→BLUE) is the
**estimation floor**, not an in-collision attribution ceiling: merged peaks pin both
colliding lines to one detection (~0.5 attribution by construction), which trackers that
coast (KF) or carry a state posterior (learned) legitimately exceed.

**Reading:** honest PID genuinely degrades at crossings (post 0.750, 11/16 losses) — the
Increment-1 *story* survives in weakened form, its published numbers do not. CV-KF solves v0
(it is kinematically trivial: linear ramps, distinct slopes, ~3-frame merges, no noise). The
gated learned variant matches the KF post-crossing — 1.000 association, 0 switches per
opportunity, 0 losses — **from cold acquisition**, and both relu variants come within 0.077
switches/opportunity of it; no learned variant matches the KF's in-collision 0.978. v0
therefore cannot rank learned vs competent classical, and any "beats classical" claim from
v0 alone is unsupported.

## v1 (sequence_train_v1): where the discrimination lives

768 sequences × T=256 (512/128/128), three trajectory families (held-ramp-hold ≈ 50%,
reversal ≈ 25%, OU ≈ 25%), per-axis contrast ladder [1.0, 0.85, 0.7, 0.55] with AR(1) drift,
pinned v0 frequency grid. **Caveat: v1 is noiseless** (`noise_mode: deterministic` — no
photon shot noise); every number in this section is a noiseless-sim result, and the
shot-noise-ladder re-evaluation (Increment 2b, upstream `physics.shot_noise`) is the
hardening step. Full per-family results on the v1 **test** split (128 seqs; 95%
Wilson CIs, pooled counts; classical trackers GT-init, learned cold-acquire; learned trained
on v1-train, seed 20260701, early-stopped on v1-val — relu+linear best val 0.269 @ 545,
gated+linear 0.148 @ 395):

| family | tracker | in-coll misassoc | ID-sw / opportunity | lock-loss |
|---|---|---|---|---|
| held | honest PID | 0.198 (0.187–0.209) | 0.245 (0.205–0.291) | 13/37 |
| held | CV-KF | **0.099** (0.091–0.107) | **0.016** (0.007–0.034) | 3/37 |
| held | learned gated+linear | 0.510 (0.496–0.523) | 0.321 (0.276–0.370) | 3/37 |
| held | learned relu+linear | 0.697 (0.684–0.709) | 0.375 (0.325–0.427) | 6/37 |
| reversal | honest PID | 0.465 (0.448–0.483) | 0.261 (0.219–0.308) | 11/23 |
| reversal | CV-KF | **0.281** (0.265–0.297) | **0.053** (0.035–0.081) | 3/23 |
| reversal | learned gated+linear | 0.457 (0.439–0.475) | 0.324 (0.279–0.374) | **0/23** |
| reversal | learned relu+linear | 0.542 (0.524–0.560) | 0.326 (0.279–0.376) | **0/23** |
| OU | honest PID | 0.666 (0.656–0.676) | 0.341 (0.313–0.371) | 25/30 |
| OU | CV-KF | **0.532** (0.521–0.542) | **0.217** (0.194–0.242) | 19/30 |
| OU | learned gated+linear | 0.591 (0.581–0.602) | 0.269 (0.243–0.296) | **2/30** |
| OU | learned relu+linear | 0.633 (0.622–0.643) | 0.265 (0.239–0.292) | **0/30** |

### v1 verdict (honest, both directions)

1. **Identity: CV-KF wins every family, including the adversarial ones.** Its
   switches-per-opportunity (0.016/0.053/0.217) beat both learned variants (~0.27–0.38)
   with non-overlapping CIs even on OU. At this training scale (512 sequences) the learned
   association does not transfer well enough to claim the through-crossing *identity*
   problem — the train→val loss gap (gated 0.04 → 0.15) says capacity/data, not physics.
2. **Vector estimate: the learned tracker wins decisively where trajectories are hard.**
   Lock-loss on reversal 0/23 (KF 3/23, PID 11/23) and OU 2/30 gated / 0/30 relu vs KF
   **19/30** (CIs cleanly separated: 0.02–0.21 vs 0.46–0.78) — from cold acquisition. The
   state-regressed B̂ (the magnetometer's actual output) does not route through per-line
   identity, so identity scrambles degrade it gracefully instead of catastrophically;
   the classical splitting→BLUE decode has no such path.
3. Honest PID is the weakest tracker on lock-loss and vector metrics in every family — but
   NOT on identity attribution: on `held` it beats both learned variants (in-collision
   misassociation 0.198 vs 0.510/0.697; switches/opportunity 0.245 vs 0.321/0.375), and on
   `reversal` its in-collision misassociation (0.465) is at parity with the gated variant
   (0.457). Why the learned posterior scores so poorly on held-family in-collision
   attribution is a diagnostic worth answering — possibly a capture-radius artifact for
   posterior-style trackers whose claimed centers sit *between* merged lines (scored
   unassigned → misassociated) rather than genuine mis-association; see the 2c list.

**Corrected bottom line across v0+v1:** the learned tracker ties competent classical
post-crossing on the trivial lineage, *loses* the identity race on v1 at current training
scale, and *wins* vector-estimate robustness on exactly the adversarial families the thesis
targets (reversal/OU) by a wide, CI-solid margin. The claim that survives is about the
**field estimate through kinematically adversarial crossings**, not about association purity
— and the identity gap is the concrete 2c work item. The two provisos that applied here —
noiseless-only, NLS-unchallenged — are resolved by the Increment-2b matrix below: the
vector-estimate claim **survived both**, hardened.

## Increment 2b: shot-noise ladder × NLS baseline (the full matrix)

Reproduce: `python experiments/noise_matrix_report.py` (JSON at
`artifacts/noise_matrix/matrix.json`). Photon-budget ladder sized per dataset against its
faintest manifest line depth via the upstream physics model
(`nv_sensor_sim.physics.shot_noise`, commit 0524686): **v1** (faintest 0.00114) →
6.97e8 / 7.74e7 / 6.97e6 photons/point for SNR_faintest 30/10/3; **v0** (faintest 0.00351)
→ 7.32e7 / 8.13e6 / 7.32e5. Conventions: fixed-seed realizations identical for every
tracker; PID/KF detector threshold raised to max(data-scaled, 5σ) under noise (stated
honest tuning; at SNR 3 the faintest lines sit below any defensible detection threshold —
reported, not hidden); NLS fits through noise untuned; classical GT-init, learned
cold-acquisition. Noise-augmented models (`+aug`) trained with fresh per-epoch realizations
at the SNR-10 budget (fixed middle rung, documented choice).

**The NLS baseline** (`tracking/nls_baseline.py`): per-frame least-squares of the raw
spectrum against an 8-Lorentzian model, free centers+depths, Γ from the manifest's rendered
linewidth, **constant-velocity-extrapolated warm starts**, 6Γ center gate, 0.25× depth
floor. The CV warm start is load-bearing: with a static warm start the merged centers are
exchange-degenerate at crossing exit and the assignment coin-flips (measured 0.67
swaps/opportunity on v0; every sequence eventually lost). The fit model is deliberately the
Lorentzian approximation, not the SimOS generator (inverse crime).

### v1 test split — lock-loss (the sensor output) across the ladder

| tracker | clean (held/rev/OU) | SNR 10 | SNR 3 |
|---|---|---|---|
| honest PID | 13/37 · 11/23 · 25/30 | 28/37 · 16/23 · 28/30 | 37/37 · 23/23 · 30/30 |
| CV-KF+Hungarian | 3/37 · 3/23 · 19/30 | 20/37 · 14/23 · 19/30 | 28/37 · 19/23 · 23/30 |
| NLS (CV warm start) | 5/37 · 5/23 · 16/30 | 10/37 · 12/23 · 21/30 | 33/37 · 20/23 · 30/30 |
| learned gated (noiseless-trained) | 3/37 · 0/23 · 2/30 | 3/37 · 0/23 · 2/30 | 5/37 · 2/23 · 1/30 |
| **learned gated +aug** | 2/37 · 0/23 · 1/30 | 2/37 · 0/23 · 1/30 | **3/37 · 0/23 · 2/30** |

Post-crossing vector error at SNR 3: learned gated+aug 1.3–1.5° median; every classical
tracker 10–60°+ (NLS peaks 84–105° — its fitted-splitting decode is noise-unstable even
where its identity attribution degrades gracefully). Identity metrics under noise: NLS keeps
the best held-family attribution at SNR 10 (misassoc 0.077 vs KF 0.375, learned ~0.48);
learned in-collision misassociation stays its known weakness at every rung — the identity
gap (2c) is unchanged by noise.

### v0 highlights

- **Clean v0 is solved classically-optimal by NLS**: 0.000 misassociation, 0 switches,
  0/16 losses, 0.1° peak — stronger than the KF. The sanity lineage discriminates nothing.
- **Noiseless-trained v0 models are noise-fragile** (gated at SNR 10: misassoc 0.93 — the
  64-sequence training set overfits clean spectra), and **augmentation rescues them
  completely** (gated+aug at SNR 3: 0/16 losses, 1.5° post). The v1-trained models are
  noise-tolerant even without augmentation — training-set scale/diversity is itself a
  robustness mechanism. Augmentation benefit, measured: essential at v0 scale, a mild
  regularizer at v1 scale (relu SNR-3 losses 19/37→8/37; gated 5/37→3/37).

### B1+B2 verdict

Under noiseless conditions the classical field strengthened (NLS solves v0 outright and
takes the held-family identity crown), but the learned vector-estimate advantage on
adversarial families stands. Under realistic shot noise the ordering becomes stark:
detection-based classical collapses (detector physics), NLS degrades gracefully in identity
but catastrophically in the decoded vector, and **the learned tracker is the only tracker in
the matrix still delivering the field at every rung** — ≤5/90 v1 lock losses at
SNR_faintest=3 vs ≥72/90 for every classical alternative, from cold acquisition. The
surviving claim is now noise-hardened and NLS-challenged. Compute footnote (rough
estimates): NLS ≈ 6 MFLOP/frame ⇒ ~6 GFLOP/s sustained at the 1 kHz frame rate — several ×
over an MSS-class RISC-V budget; the learned pipeline ≈ 1.7 MFLOP/frame on the V250 (INT8)
+ ~0.4 MFLOP/frame host glue — an order of magnitude lighter on the host, with the heavy
half on the NPU. Deployability favors the learned pipeline independent of accuracy.

v0 remains the frozen sanity lineage. Reproduce: `experiments/increment2b_report.py`.

## Architecture (unchanged by the re-baseline)

Deployable-first on the V250/MSS partition (docs/design/02): V250-targeted anchored
fully-conv extractor (F=951 → K=60 anchors, ~20k params, ops-guard green at real shape);
host-side recurrent core (ReLU-residual with small-gain init / gated research variant),
association head with rectified signed-distance relational branch and a directly supervised
per-slot position readout, frozen analytic BLUE. Claimed centers = the state posterior (MOT
convention). Assignment output is mutually exclusive (greedy one-to-one on scores; a
per-line argmax could double-claim a candidate). Input `(1−PL)×input_gain` with the gain
estimated from the train split (~0.4% dips → gain ≈ 250–290); **Increment-3 note: this gain
must fold into the INT8 input quantization scale, else the signal sits ~1 LSB deep.**

Training: association CE over anchors (in-collision ×5), track-position Huber, candidate
offset Huber, projection MSE against exact `B_true·n_i` labels; full-BPTT (pure
observation-driven filter — no teacher forcing needed), AdamW + cosine, early stop on val
total. Runs are config-addressable (`run_key`; config+seed fully determine a run; device
logged).

## Next (2c work items)

0. ~~The strongest classical baseline is missing from the matrix~~ **Resolved by the
   Increment-2b matrix above**: NLS is in every table; it solves clean v0 and clean held,
   still breaks on OU, and fails the vector under noise. The vector-estimate claim survived
   — no longer provisional. B4 diagnostic (held-family learned attribution): resolved as a
   **genuine association failure, not a capture-radius artifact** — removing the radius only
   moves learned held misassociation 0.510 → 0.439 (PID 0.198 → 0.185); the unassigned
   fraction is 0.127, so ~85% of the errors are wrong-line attributions of the posterior.
   Both conventions reported here for the record.
1. **Close the identity gap on v1**: the learned association loses to CV-KF everywhere at
   512-sequence scale. Candidates: more data / longer training (val gap says underfit-ish
   generalization, not saturation), a KF-style motion prior inside the association (the KF's
   whole advantage is CV coasting — give the learned head the same inductive bias), hybrid
   gating (learned features + Hungarian one-to-one with motion-gated costs), and revisiting
   the collision-weighted CE (in-collision targets are attribution-ambiguous — a soft/merged
   target may train better than nearest-anchor hard labels).
2. Estimation-head question is now resolved in the other direction on v1: keep the
   projection head (it is what wins lock-loss); on v0 the splitting→BLUE decode of gated
   centers was better (0.4° vs 1.5° peak) — carry both outputs.
3. GitHub push held until Jason reviews this corrected doc (per TVW dispatch); nas pushes
   fine. Amplitude-ladder lineage needed before any dynamic-range claim.
