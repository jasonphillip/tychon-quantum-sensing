# Dispatch: Increment 2b — doc fixes, GitHub push, noise re-eval, NLS baseline

**To:** the odmr-vector-tracking session (branch `increment-2-learned-tracker`, HEAD 1c4a6c9)
**From:** TVW review lane, 2026-07-02. The re-baseline execution and the corrected results
doc passed review with three required fixes (Part A). After they land, the GitHub push is
approved. Part B is the next increment of work, in priority order: it defends the surviving
claim before extending it.

## Part A — doc fixes (required before the GitHub push)

A1. **Verdict #3 is false as written.** "Honest PID is the weakest tracker on every family
and metric" contradicts your own v1 table: on the `held` family PID beats both learned
variants on identity metrics (in-coll misassoc 0.198 vs 0.510/0.697; ID-sw/opp 0.245 vs
0.321/0.375), and on `reversal` in-coll misassoc PID 0.465 ≈ gated 0.457 < relu 0.542.
Correct to: PID is weakest on lock-loss and vector metrics in every family; on identity
attribution the learned variants are the weakest on held (a diagnostic worth one sentence —
see B4).

A2. **State the noiseless-benchmark caveat in the v1 section and the bottom line.** The
"wins vector-estimate robustness" result is currently a noiseless-sim result; say so
explicitly and point at the Part-B noise re-evaluation as the hardening step. (v0's section
already says "no noise"; v1's does not.)

A3. **Add the missing strongest-classical-baseline caveat to the 2c list**: per-frame
warm-started nonlinear least-squares on the raw spectrum (Part B2) is not yet in the
matrix, and until it is, the vector-estimate claim is provisional.

Then: commit, push nas, and **push the branch to GitHub (approved once A1–A3 are in)**.
Origin is the private `jasonphillip/odmr-vector-tracking`.

## Part B — Increment 2b work, in order

### B1. Noise re-evaluation of the ENTIRE matrix (highest priority)

Upstream shipped the physics-owned noise model for exactly this:
`nv_sensor_sim.physics.shot_noise` (commit 0524686) — `shot_noise_sigma(spectrum, N)`,
`apply_shot_noise(...)` (seeded; Gaussian approx default, exact Poisson optional),
`photons_for_dip_snr(depth, snr)`.

- Choose a 3-point photon-budget ladder sized against the faintest line: SNR_faintest ∈
  {~3, ~10, ~30} via `photons_for_dip_snr(min(manifest["line_depths"]), snr)` (v1 faintest
  depth ≈ 0.0012). Record the budgets in the results doc.
- **Evaluation**: fixed-seed noise realizations, identical for every tracker (classical and
  learned see the same noisy spectra). Re-derive the full v0 + v1-per-family tables at each
  budget. Note the classical detector and the KF gate may need noise-aware retuning — tune
  them honestly (their best reasonable config), state the tuning.
- **Training**: retrain the learned variants WITH per-epoch shot-noise augmentation
  (fresh seeds per epoch, budget sampled from the ladder or fixed at the middle rung —
  your call, document it). Evaluate both the noise-augmented and the original
  noiseless-trained models so the augmentation benefit is itself measured.
- Expected physics: at SNR_faintest ~3 the faintest-axis dips are barely detectable —
  detection-based classical should degrade hard; NLS and learned should degrade more
  gracefully. Whatever happens, report it — this is where the INT8/deployment robustness
  story starts too.

### B2. The NLS baseline (the strongest classical attack on the surviving claim)

Implement `tracking/nls_baseline.py`: per-frame nonlinear least-squares fit of the raw
spectrum against the known forward model (8 Lorentzians; import lineshape/geometry from
`nv_sensor_sim` — physics stays upstream), warm-started from the previous frame's solution
(continuity = the association), decoding B̂ per frame from the fitted splittings (and/or
direct 3-parameter B-fit through the forward model — pick one, justify it). GT init like
the other classical baselines. It has no detection stage, so merged blobs are handled
natively — this is the classical tracker most likely to survive reversal/OU.
- Add it to every table from B1 onward (it matters most under noise, so B1+B2 land
  together in one re-derived matrix).
- If NLS survives the adversarial families at realistic noise: the claim narrows to
  deployability/compute (an NLS fit per 1 ms frame on an MSS core is a real cost argument —
  estimate its FLOPs vs the learned pipeline's). If it degrades: the learned claim is
  hardened. Either outcome is progress; report it straight.

### B3. Only then: the identity gap (your 2c list, unchanged)

Motion prior in the learned association head, hybrid Hungarian gating on learned scores
with motion-gated costs, soft/merged in-collision CE targets, more data / longer training.
If the train→val gap diagnosis still says data-limited after B1's augmentation, request a
`sequence_train_v2` (~4× sequences) from the nv-sim lane via Jason — do not generate data
in this repo.

### B4. One diagnostic question to answer along the way (cheap)

Why is learned in-collision attribution WORSE than PID on `held` (0.510/0.697 vs 0.198)?
Check whether the 3Γ capture-radius attribution is penalizing the state-posterior claimed
centers during merges (posterior sits between the merged lines → unassigned → scored
misassociated) vs a genuine association failure. If it is a metric artifact for
posterior-style trackers, say so in the doc and report both attribution conventions.

## Claims discipline (unchanged)

Retracted numbers stay banned. No DR claims (amplitude-ladder lineage still future). The
outward deck does NOT get a tracker line until B1+B2 numbers exist — the current v1 result
is noiseless and NLS-unchallenged; shipping it externally now risks a second retraction.
Wilson/binomial CIs on everything; per-family reporting; conventions (init, tuning) stated
per column. nas pushes routine; further GitHub pushes after this one need Jason's OK.

## Report back

A: confirmation the three fixes landed + GitHub push done (hashes). B1/B2: the re-derived
noise-ladder matrix with NLS included, and the one-paragraph honest verdict. B3: only after
B1/B2 are reported. B4: one paragraph with evidence.
