# 04 — Identity-gap solution survey (candidate levers for 2c+)

*Compiled 2026-07-03 (05:40 ET, during the post-outage v2 retrain). A cross-domain
literature sweep for mechanisms that fix the **per-track identity gap** — the learned tracker
wins the vector estimate through adversarial crossings but loses to CV-KF + Hungarian on
*which line is which* (IDSW/opp 0.27–0.38 vs 0.02–0.22; see `../increment2a_results.md`).*

**Status of this document: research memo, not a plan.** No implementation is proposed or
authorized here — it exists so the candidate levers are on the shelf when the v2 wave
(`v2_gated_linear_snr10_s20260711` on spark1, `_s20260721` on spark2) lands and we decide 2c.

**Method.** A fan-out web sweep (104 agents, 110 extracted claims, 3-vote adversarial
verification per claim; 59 survived at high confidence, 16 refuted) plus a manual full-text
read of the two anchor papers (Liu & Wang JASA 2017; DeepDA arXiv:1907.09915). Every load-
bearing number below was quote-verified against the primary source. Claims that failed
verification are quarantined in **§Refuted** and must not be cited as support.

---

## The one finding that reframes the problem

Across MOT, audio, and radar/RF, the field converged on the same answer, and it is **not** the
lever we have been pulling:

> **Identity is carried by an *appearance/fingerprint* signal combined *multiplicatively* with
> position — not by position/motion alone, and not by appearance alone.** Our current linear
> association head scores mostly on position; B3 (hard motion gate) doubled down on motion and
> regressed. The missing ingredient is a per-line fingerprint likelihood folded into the
> association score.

The decisive evidence (Wang, Wang, Weinberger, Campbell, arXiv:1810.08565, ICRA 2019),
PETS09-S2L1 pedestrian tracking, association likelihood factorised as
`a_ij = α · P(z_pos | θ_ij) · P(z_app | θ_ij)` (position ⟂ appearance):

| Association signal | MOTA | ID switches |
|---|---|---|
| Position only | 0.905 | 30 |
| **Position × re-ID** | **0.929** | **6** (−80%) |
| Re-ID only | 0.109 | 112 |
| Position + colour histogram | −0.168 | 218 |

MOT17-04 in the same paper: 160 → 83 IDSW (−48%). The two poles matter as much as the win:
**appearance-only is catastrophic** (112 IDSW, MOTA collapses), and a *weak* appearance feature
(colour histogram) is worse than nothing. The lesson for us is precise: a *physically
meaningful* fingerprint, multiplied into (not replacing) the position score.

Our fingerprint is free and stronger than a pedestrian's clothing: each NV axis has a
physically-determined **Zeeman slope (sign + magnitude of df/dB)**, **contrast/depth**, and
**¹⁴N hyperfine triplet** — "enrollment" is fixed by geometry, unlike the audio case which
needs per-speaker training data.

---

## Tier 1 — highest transferability (appearance/fingerprint identity)

### 1. Factorised position × fingerprint association likelihood — *rank #1*
- **Mechanism:** keep the position/motion score; multiply by a fingerprint-likelihood term
  `P(z_app|line)` built from the physics descriptors. Assignment stays a per-frame problem;
  the fingerprint breaks the tie precisely at the crossing where positions coincide.
- **Evidence:** the table above — direct, controlled, causal (appearance is the only added
  variable). Data scale: the re-ID metric was pretrained offline; the tracking gain needs no
  extra tracking data.
- **Transfer:** very high. This is a change to the *association score*, not the architecture,
  and runs host-side float (no NPU op constraints). It is the explicit-likelihood form of what
  Liu & Wang do implicitly (#2).
- **Caveat:** the fingerprint must be discriminative under our SNR. At SNR 3 the faintest line
  is ~1 LSB and undetectable — the fingerprint likelihood must degrade gracefully to
  position-only there, exactly as re-ID-only fails when appearance is uninformative.

### 2. Per-line observation channels + FHMM temporal decode (Liu & Wang JASA 2017) — *rank #2*
- **Mechanism (manual full-text read):** a DNN outputs the posterior over *pitch-state pairs*
  `p(x¹,x²|y)`; a factorial HMM with **one Markov chain per speaker** and exact junction-tree
  inference decodes the most-likely joint track. Identity is baked into the *observation model*
  (each output channel = one speaker, learned from that speaker's spectral signature); there is
  **no separate association step**. The decode is *smoothed over time* — identity may resolve a
  few frames after the crossing rather than instantaneously.
- **Evidence:** permutation error E_Perm 6.47% (speaker-independent) → **0.15%** (speaker-pair
  DNN); the pair-joint model beat independent per-speaker models (1.01% → 0.15%), i.e. jointly
  modelling the *collision state* helps.
- **Transfer:** high, two ways. (a) **Per-axis channels keyed on the physics fingerprint** —
  our free "enrollment." (b) **A short-horizon Viterbi/FHMM relabel on the host** (8 lines,
  float, kHz budget is ample) that *defers* the identity decision instead of committing
  instantaneously — this sidesteps the B3 self-confirmation trap because it smooths rather than
  gates. We have never tried a deferred/smoothed decode.
- **Data scale:** audio needed 57k mixtures/pair; our per-axis channels are physics-fixed so
  the analogue is cheaper, but the *joint-collision* modelling is where their data went.
- **Caveat (see §Refuted):** their same-gender-crossing advantage is *average-regime* evidence;
  do not claim it as proof of crossing-*specific* benefit.

### 3. Slope (chirp-rate) fingerprint — lift crossings into a non-overlapping space — *rank #3*
- **Mechanism (Sensors 25, 2030 (2025), verified):** intersecting ridges in the 2-D
  time-frequency plane become **non-overlapping in 3-D time-frequency-chirp-rate space** —
  components that cross in frequency separate by instantaneous slope (df/dt). Directly
  analogous to using the **Zeeman df/dB slope** as the disambiguator at a crossing.
- **Bonus finding:** "frequency-gradient matching at crossings works only when the number of
  ridges is known a priori" — a limitation *in general*, but our 8-line count **is** known a
  priori, so this family is *more* transferable to ODMR than to its home domain.
- **Related architecture (same source):** decouple detection from association — U-Net ridge
  map → CNN counts components → **fixed-P multi-branch net regresses each component's whole IF
  trajectory in its own branch**. A concrete "one branch per line, identity = branch index"
  design that echoes both #1 and #2.
- **Transfer:** high and physics-grounded; the slope sign alone resolves the 48-fold axis
  degeneracy direction. Cheap to add as a feature.

---

## Tier 2 — training-strategy fixes for the self-confirming-lock failure (B3), *without* scheduled sampling

These target *exposure bias* — the train (teacher-forced) vs rollout (closed-loop) mismatch
that makes a wrong lock self-confirm. All avoid the scheduled-sampling family that already
failed here.

### 4. DAgger-style rollout aggregation — *rank #4*
- **Mechanism (Ross et al., arXiv:1011.0686):** run the current policy, label the states it
  *actually visits* with ground-truth actions, aggregate, retrain — train on the deployment
  state distribution.
- **Why it fits our failure:** behavioural cloning compounds error **quadratically in horizon
  T**; DAgger is **linear in T** — the formal statement of our closed-loop drift. The
  parameter-free variant (`β = 1{i=1}`: expert labels only on iteration 1, pure on-policy after)
  "often performs best" — evidence that full on-policy beats gradual expert/learner *mixing*
  (the family scheduled sampling belongs to, which already failed for us).
- **Evidence on sequence tasks:** OCR greedy accuracy 83.6% (teacher-forced) → 85.5% (DAgger).
- **Tracking-specific instance (arXiv:1811.10984, verified):** iterative rollout-aggregation for
  a tracker — add the tracker's own tracklets to the training set, retrain one epoch, iterate
  until <5% growth. Data gen <6 h on 20 CPUs, converged <30 epochs of <10 min. **Modest scale —
  feasible for our synthetic 8-line setting.**
- **Transfer:** high; it is a training-loop change, model-agnostic.

### 5. BAgger — DAgger without an oracle — *rank #5*
- **Mechanism (arXiv:2512.12080, verified):** **time-reverse the model's own rollouts** (which
  start clean and degrade) so the reversed sequences are self-supervised *corrective*
  trajectories teaching recovery from drifted states. Standard supervised objective; **no
  backprop through the rollout, no teacher/oracle**.
- **Evidence:** long-horizon drift cut sharply (ΔAesthetic 3.57 at round 3 vs 7.34 / 14.56 for
  baselines); subject consistency up.
- **Transfer:** high and attractive for a *small* recurrent tracker — no oracle, no differentiable
  rollout. Note: demonstrated on video generation, not association; transfer is by analogy.

### 6. Professor Forcing — *rank #6*
- **Mechanism (arXiv:1610.09038):** adversarially force the hidden-state dynamics under
  teacher-forcing and under free-running sampling to be **indistinguishable**, without mixing
  model predictions into inputs (the scheduled-sampling move).
- **Evidence:** benefit concentrates in **long free-running rollouts** — our exact regime — and
  it acts as a regulariser (does not trade away open-loop accuracy).
- **Transfer:** medium — all evidence is on *generation* tasks (language, handwriting, audio),
  none on association/tracking. Lower confidence than #4/#5.

---

## Tier 3 — differentiable / loss-level identity mechanisms

### 7. Differentiable IDS loss via a Deep Hungarian Net (DeepMOT, arXiv:2004.…) — *rank #7*
- **Mechanism:** a frozen bi-directional-RNN "Deep Hungarian Net" makes the assignment step
  differentiable, so a **differentiable identity-switch term** can enter the loss.
- **Evidence (causal isolation):** Tracktor ablation — vanilla 152 IDS → full dMOTA+dMOTP loss
  **118 IDS**; zeroing just the IDS weight (γ=0) returns it to 124 — the IDS term is the cause.
  DHN trained on 114,483 synthetic distance/assignment matrices (92.88% acc) then frozen —
  matrices are cheap to synthesise.
- **Transfer:** medium-high; lets us *directly* optimise the metric we are losing on. Pairs
  naturally with a fingerprint feature (#1).

### 8. UniTrack differentiable graph loss — *rank #8*
- **Mechanism (arXiv 2026-02, verified):** a plug-and-play graph-theoretic loss unifying
  detection, identity, and spatiotemporal consistency; **no architecture change**.
- **Evidence:** up to **−53% IDSW**, +12% IDF1 across trackers; ~5% training-memory overhead,
  **zero inference cost**.
- **Caveat:** it is a *per-frame supervised* objective — it does **not** address exposure bias.
  Complementary to Tier 2, not a substitute.

### 9. Neural message passing / learned solver (MPNTrack, IJCV 2022) — *rank #9*
- **Mechanism:** a GNN over detection+track nodes with time-aware **separate past/future**
  aggregation learns the association, replacing handcrafted costs + external solver.
- **Transfer:** medium; a clean host-side float association module, natural place to inject the
  fingerprint as an edge feature. Heavier lift than #1.

---

## Tier 4 — end-to-end query propagation (architecturally heaviest)

### 10. TrackFormer / MOTR track queries — *rank #10*
- **Mechanism:** an **identity-preserving track query** autoregressively follows each track
  frame-to-frame; identity is carried by the query embedding, not a post-hoc matcher.
- **Two transferable sub-ideas even if we don't adopt the full model:**
  - **MOTR "collective average loss" over multi-frame clips** — trains on the model's own
    propagated rollouts; a *non-scheduled-sampling* exposure-bias fix in its own right
    (MOTR +6.5 HOTA over ByteTrack on DanceTrack, the association-heavy benchmark).
  - **TrackFormer track-query augmentation** — randomly drop queries (p=0.4, simulate FN),
    inject spurious queries (p=0.1, simulate FP), widen the inter-frame gap. Cheap robustness
    trick portable to any recurrent tracker.
- **Transfer:** lower — a substantial rewrite, transformer-heavy. It lands **host-side** under
  our partition (recurrence/association are float-CPU; only the per-frame extractor is INT8-NPU
  constrained), so the op-guard is not the blocker — engineering cost is.

---

## What NOT to re-derive (from DeepDA full read + our own history)

- **DeepDA (arXiv:1907.09915, full read):** its identity signal is *KF-predicted position
  distance only* — the authors explicitly flag appearance as "straightforward to extend" but
  never do. STTI (ID-switch metric) 0.844 vs JPDA 0.980 / Hungarian 1.072 (~14–21% better), but
  it wins OSPA only at *high* clutter. **It is the position-only tracker whose weakness we
  already have** — informative as a boundary, not a lever. The one portable detail: an explicit
  **"no-measurement" null column** in the association head for missed detections (worth checking
  our head has a "this line is currently undetectable" hypothesis, given the SNR-3 vanishing
  faint line).
- **Already-failed here (do not re-propose):** soft-CE association targets, Sinkhorn/OT matching,
  scheduled sampling, hard motion-prior gate (B3). The Tier-2 fixes are chosen specifically to
  be *outside* the scheduled-sampling family.

---

## Suggested ordering when 2c is decided (for discussion — not authorized)

1. **Fingerprint likelihood into the association score (#1 + #3 slope sign).** Highest
   evidence-to-effort; a score change, host-side, physics-grounded, our free "enrollment."
2. **Deferred/smoothed identity decode (#2 FHMM/Viterbi relabel).** Directly attacks the
   instantaneous-commit trap that B3 made worse; cheap for 8 lines on the host.
3. **If exposure bias persists after 1–2:** DAgger rollout-aggregation (#4) or oracle-free
   BAgger (#5), both modest-scale.
4. **Differentiable IDS loss (#7) / UniTrack loss (#8)** as a metric-aligned finisher, once a
   fingerprint signal exists to optimise.

Cross-cutting: **appearance is a multiplier on position, never a replacement** (the re-ID-only
collapse), and a *weak* fingerprint is worse than none — so any fingerprint feature needs an
SNR-graceful fallback to position-only.

---

## Implementation scoping (added 2026-07-03, pre-wave-2-verdict; read-only code survey)

Where each lever plugs into `src/odmr_vector_tracking/tracking/learned.py`, and — decisive for
ordering — what retraining each one requires.

**Architecture facts that reorder the levers:**

1. **The field estimate never touches the assignment.** `b_est` comes from
   `state_to_proj(state)` → BLUE (`learned.py:543-544`); `assignment` is inference bookkeeping
   (`learned.py:585`). This is *why* the vector claim survives while identity fails — and it
   means **identity can be re-decoded post-hoc without touching `b_est` at all.**
2. **The plain/gated baseline has no output feedback.** The state consumes only per-frame
   candidate features (`learned.py:447-452` docstring: "never the model's own outputs"), so the
   Tier-2 exposure-bias levers (DAgger/BAgger/Professor Forcing) **do not apply to the deployed
   default** — they only matter for variants that feed back (ss/motion-prior, both failed).
   Tier 2 is deprioritized accordingly.
3. **The association head already receives candidate appearance** (`feat` from the extractor,
   `learned.py:565`) — but `track_feats` is a readout of the single *global* recurrent state
   (`state_to_tracks`, `learned.py:546`), not a per-slot fingerprint memory, and the head
   (`LinearScoreAssociation`, `learned.py:331-375`) has a **relational branch for position only**
   (`relu(±Δpos)`, `learned.py:366-368`). Appearance enters additively — `f(track)+g(cand)` —
   which the module's own docstring identifies as separable/identity-blind. **The fingerprint
   lever = add the same rectified-difference relational trick for the appearance vector**
   (`relu(track_app−cand_app)`/`relu(cand_app−track_app)` → proj), staying linear+relu+add.
   The head runs HOST_MSS anyway (`learned.py:346`), so even richer similarity ops are legal.

**Revised ordering by cost (retrain = ~2–7 h/run on a GB10 at v2 scale):**

| # | Lever | Change surface | Retrain? |
|---|---|---|---|
| A | **Deferred Viterbi/FHMM identity re-decode (#2)** | eval-side only: re-decode the saved `(B,T,L,K)` scores with one-to-one + transition-penalty smoothing over a short window; `b_est` untouched | **NO — runs against existing v2 checkpoints** |
| B | **Fingerprint relational branch (#1)** | `LinearScoreAssociation`: +1 projection layer on rectified appearance differences | yes |
| C | **Per-slot appearance memory (DeepSORT-style EMA gallery)** | host glue in the rollout loop; feeds B's track-side fingerprint | yes; NOTE: introduces output feedback → re-opens Tier-2 exposure-bias question — pair with B4-style caution |
| D | **Slope/chirp feature (#3)** | track-side velocity readout + candidate Δpos across frames into the head | yes |
| E | **Differentiable IDS / graph loss (#7/#8)** | `training/losses.py` addition | yes |

**Immediate consequence:** lever A is a zero-retrain experiment — it can run against
`matrix_2c_final.json`'s checkpoints the moment the wave-2 verdict lands, before any 2c
training decision. If a smoothed decode alone closes a chunk of the IDSW gap, the 2c retrain
scope shrinks to B(+C) as the fingerprint pass.

## Refuted (verification-failed — must not be cited as support)

- **QDTrack "appearance ALONE decouples identity from motion":** refuted. The paper's 30% IDSW
  reduction is attributed to the **full cumulative training+inference stack**, not to the
  appearance-scoring mechanism in isolation (arXiv:2210.06984 §4.6/Table VIII). Appearance-only
  association is *not* shown to carry identity by itself — consistent with the re-ID-only
  collapse in #1.
- **Liu & Wang ICASSP 2018 (uPIT) "same-gender gain proves crossing-specific benefit":**
  refuted as overreach. The source states only "improvement is more significant for
  same-gender mixtures" (an average-regime statement) and imports label permutations from a
  *separately trained* uPIT speech-separation module — the identity assignment is supplied by
  that external model, not proven to be a crossing-specific tracker mechanism. uPIT (permutation-
  invariant training) remains a *valid* lever to note, but not on this evidentiary basis.

## Primary sources (verified this sweep)
- Wang, Wang, Weinberger, Campbell — arXiv:1810.08565 (re-ID probabilistic DA; the #1 table).
- Liu & Wang — JASA 141(2):710 (2017), PMC6909980 (DNN+FHMM, E_Perm 0.15%).
- Sensors 25, 2030 (2025) — mdpi.com/1424-8220/25/7/2030 (3-D TF-chirp-rate crossing separation).
- Ross, Gordon, Bagnell — arXiv:1011.0686 (DAgger; quadratic vs linear-in-T).
- arXiv:1811.10984 (DAgger-style iterative aggregation for tracking; scale numbers).
- arXiv:2512.12080 (BAgger; oracle-free reverse-rollout).
- arXiv:1610.09038 (Professor Forcing).
- DeepMOT — arXiv:2004.… / Xu et al. (Deep Hungarian Net, differentiable IDS: 152→118).
- UniTrack — arXiv 2026-02 (differentiable graph loss, −53% IDSW).
- MPNTrack — IJCV 2022, DOI 10.1007/s11263-022-01678-6 (arXiv:2207.07454 / 1912.07515).
- TrackFormer — arXiv:2101.02702 (CVPR 2022). MOTR — arXiv:2105.03247 (ECCV 2022).
- DeepDA — arXiv:1907.09915 (position-only boundary case; full read).
