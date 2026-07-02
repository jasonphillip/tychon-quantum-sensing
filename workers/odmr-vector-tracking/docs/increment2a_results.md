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
pinned v0 frequency grid. The classical baselines on the v1 **test** split (128 seqs; 95%
Wilson CIs, pooled counts):

| family | tracker | in-coll misassoc | ID-sw / opportunity | lock-loss |
|---|---|---|---|---|
| held | CV-KF | 0.099 (0.091–0.107) | 0.016 (0.007–0.034) | 3/37 |
| reversal | CV-KF | 0.281 (0.265–0.297) | 0.053 (0.035–0.081) | 3/23 |
| OU | CV-KF | 0.532 (0.521–0.542) | 0.217 (0.194–0.242) | 19/30 |
| reversal | honest PID | 0.465 (0.448–0.483) | 0.261 (0.219–0.308) | 11/23 |
| OU | honest PID | 0.666 (0.656–0.676) | 0.341 (0.313–0.371) | 25/30 |

The KF that solved v0 degrades exactly where its constant-velocity coast assumption breaks:
reversals inside/near collision dwells and OU (stochastic) trajectories. This is the regime
the learned tracker exists for. **Learned-on-v1 results: pending (training in progress);
this table will be completed from `experiments/increment2b_report.py` when the v1
checkpoints land.** v0 remains the frozen sanity lineage.

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

## Next

1. Complete the v1 table (learned variants, per family, same conventions) — the decisive
   numbers are reversal-family in-collision association and ID-switches-per-opportunity,
   learned vs CV-KF vs honest PID.
2. Estimation-head open question: for the gated variant the splitting→BLUE decode of tracked
   centers beats its own projection head (0.4° vs 1.5° peak) — consider dropping the
   regression head.
3. GitHub push held until this corrected doc + v1 results land (per TVW dispatch); nas
   pushes fine. Amplitude-ladder lineage needed before any dynamic-range claim.
