# Dispatch 4 — coalescence-aware identity overlay decoders (zero-retrain)

**Target session:** `~/projects/odmr-vector-tracking/` on **ws2** (ws1 is DECOMMISSIONED;
its archive at `~/archives/ws1-projects-2026-07-05/odmr-vector-tracking/` is a **read-only
source** — copy from it, never modify it, never run anything in it).
**Issued:** 2026-07-06, from TVW improvement search
`tvw/audits/research-improvement-search-2026-07-06.md` (TVW commit c9894fd).
**Mode:** run end-to-end without user assistance. Stop-and-report conditions are listed —
on any of them, stop, write the report, commit what exists, and halt. Do not improvise beyond
the decoder menu.

## Why this experiment (context in four sentences)

The held-family identity gap (learned in-collision misassoc 0.31 vs CV-KF 0.10 at clean/snr30)
is the classical **track-coalescence** phenomenon — a structural property of marginal-style
trackers, not a defect unique to ours — and the verified literature's fix is to treat identity
as a **decode-side overlay that never feeds back into the state estimate** (Set-JPDA, Svensson
SPIE 2011; unresolved-measurement MHT, Koch & van Keuk IEEE TAES 1997; BP reduces coalescence,
Kropfreiter et al. arXiv:2308.06326; 2026 GLBP-unresolved form, Saucan/Meyer/Willett
arXiv:2606.31716). Our architecture already satisfies the precondition: `b_est` never consumes
the association (`learned.py:543,585`), and the 2c re-decode harness proved decoders can be
swapped with field metrics asserted byte-identical. Every decoder below is therefore
**zero-retrain and field-safe by construction**. Labeled-RFS "mixed-labelling" theory
(García-Fernández arXiv:1604.00082) warns identity through *long* merges may be partially
unrecoverable — so the goal is measured, graceful improvement, not a guaranteed solve.

## Standing rules (unchanged from increments 2c/3)

- Standing eval = the **v1 test split** (4 families × 4 SNR rungs), scored by the shared
  `sequence_metrics_row` path, fixed-seed shot noise. **Immutable — copy the archived
  original; never regenerate it.**
- Field metrics (lock-loss, angular error) must be **byte-identical** across all decodes
  (existing matrix-builder asserts). Any violation = bug; stop and fix before proceeding.
- Deployable default remains wave-2 `gated+linear+aug` with the A3 decode on OU/reversal.
  Nothing in this dispatch changes the deployed tracker.
- Never quote retracted numbers (16/16, 0.811, DR-5mT). KF SNR3 identity is reported
  **conditioned on lock** only.

## Pre-flight (all must pass before any new code)

1. Repo at `increment-2-learned-tracker` HEAD **46db71b** (verify). Create branch
   `increment-4-identity-overlay` from it.
2. Assemble inputs from the archive (copies, with `cp -r --preserve=timestamps`; verify sizes):
   - `archive/data/sequence_train_v1/` → repo `data/sequence_train_v1/` (verify
     `manifest.json` against the contract in `docs/design/03_data_contract.md`).
   - `archive/artifacts/increment2c/v2_gated_linear_snr10/` (seed **20260701** — verified: its
     `summary.json` seed is 20260701) and `…_s20260711/` → local `artifacts/increment2c/`.
     Local already has `…_s20260721/`.
   - `archive/artifacts/noise_matrix/{matrix_2c_final.json,matrix_2c_redecode.json,redecode_verdict.json}`
     → local `artifacts/noise_matrix/` (reference baselines).
3. **Parity gate:** run the existing `experiments/identity_redecode.py` against the three
   checkpoints on the standing eval and assert `decode:baseline` reproduces
   `matrix_2c_final.json`'s learned-baseline misassoc **exactly** (all seeds/rungs/families —
   the harness has this check) and field metrics byte-identical across decodes.
   **STOP-AND-REPORT if parity fails** (environment drift) — do not proceed.
4. Environment: ws2 GB10, `~/miniconda3` python. No NAS dependency at runtime. Long steps
   run via `nohup` + pidfile per house pattern (`artifacts/increment4/*.pid`).

## Step 0 — merge-dwell diagnostic (cheap; informative, NOT a gate)

From the v1 test HDF5 (`line_collision` (N,T,L), `collision_mask` (N,T)): per-sequence
merged-dwell run-length distributions per family (max + total frames per colliding pair).
Extend the matrix harness to emit **per-sequence in-collision misassoc** if not already stored,
then produce misassoc-vs-dwell-length curves per family for decode:baseline, A3, and CV-KF.
Output `artifacts/increment4/dwell_analysis.json` + a short `dwell_analysis.md`.
Purpose: test whether the held gap concentrates at long dwells (the coalescence-duration
hypothesis) and produce the graceful-degradation evidence shape; this also scopes a future
dwell-sweep dataset request to nv-sim (do NOT request it in this dispatch).

## Step 1 — decoder menu (native implementations in `tracking/redecode.py` family)

Implement natively (numpy/torch). `stonesoup` (MIT) may be added as an **optional dev
dependency** used only in a skip-if-absent cross-check unit test — not a runtime dependency.
All decoders rewrite only the per-slot claimed identity / `tracked_hz`; `b_est` untouched.

- **D-BP — marginal-association decode.** Per-frame association *marginals* over the (8,K)
  score matrix after top-M gating (M≤5 per line): exact enumeration where tractable, else
  loopy sum-product on the bipartite graph (reference: Stone Soup `JPDAwithLBP`;
  Kropfreiter 2308.06326). Identity read-out from temporally accumulated marginals — never
  hard per-frame argmax.
- **D-OV — Set-JPDA-style identity overlay** (Svensson 2011). Positions stay label-free (the
  existing `track_pos` readout, unchanged); maintain an 8×8 identity-belief matrix updated
  each frame from D-BP marginals with doubly-stochastic renormalization. The belief *spreads*
  during merges instead of switching, and re-concentrates after separation using evidence from
  both sides. Read-outs: instantaneous, fixed-lag {5,15}, and end-of-sequence. (Note:
  Sinkhorn-style normalization at *decode time* is permitted — the 2c elimination was Sinkhorn
  as a *training loss*, a different mechanism.)
- **D-UM — unresolved-measurement hypotheses** (Koch & van Keuk 1997; Saucan/Meyer
  2606.31716). When two lines' predicted positions fall within a resolution radius r (sweep
  r ∈ {0.5, 1, 2} anchor cells), extend the hypothesis space with "lines i,j jointly claim
  candidate k" merged hypotheses under a simple resolution-probability model (e.g. Gaussian in
  separation/r). During the dwell the pairing hypothesis carries identity instead of a forced
  exclusive pick.
- **D-JV — joint fixed-lag Viterbi** over the gated joint-assignment space with one-to-one
  constraints + transition penalties, lags {5,15}, optionally including D-UM merged states.
  Generalizes smooth5/15 (per-slot) to a *joint* decode; its lag-0 no-penalty limit must
  reproduce `greedy` (unit test).

Composition is allowed (D-UM inside D-BP / D-JV), but report each decoder standalone plus the
single best composition. Unit tests per decoder: permutation-invariance sanity, belief/marginal
normalization, merged-hypothesis bookkeeping, D-JV lag-0 == greedy parity.

## Step 2 — full matrix + deterministic verdict

Run every decoder through the SAME noise-matrix harness (4 families × 4 rungs × 3 seeds) →
`artifacts/noise_matrix/matrix_4_overlay.json`. Verdict via a new
`experiments/increment4_verdict.py` mirroring `leverB_verdict.py`:

- **Survival rule (primary):** held in-collision misassoc, pooled 3 seeds, **CI-disjoint
  improvement vs decode:baseline AND every seed improves** (clears the 0.072 seed spread), at
  **clean AND snr30**.
- **Guards (any trip = that decoder FAILS):** no CI-disjoint regression at any family×rung vs
  the current default decode policy (A3 on OU/reversal, baseline elsewhere); field metrics
  byte-identical (assert); comparison table includes CV-KF **and NLS**; KF SNR3 identity
  conditioned-on-lock.
- **Report-only:** IDSW/opportunity; decoder latency in frames (any >15-frame latency is a
  stated deployment caveat — honest for a magnetometer, but must be explicit).

**Decision rule: keep-what-survives.** If nothing survives, **stop and report the per-family
evidence — do not improvise decoders beyond the menu.** If a decoder survives, it becomes the
default identity decode *proposal* for its winning cells (adoption is the user's call; document,
don't flip defaults).

## Step 3 — docs + wrap

- `docs/increment4_results.md` in house style (Question / Verdict / tables / Decision /
  Disposition), including the Step-0 dwell curves.
- `docs/references.md` additions: Svensson et al. SPIE 8050 805010 (2011); Koch & van Keuk
  IEEE TAES 33(3) (1997); Blom & Bloem IEEE TAC 45(2) (2000); Kropfreiter et al.
  arXiv:2308.06326; Saucan/Meyer/Willett arXiv:2606.31716; García-Fernández arXiv:1604.00082
  (mixed-labelling caveat); Maggiolino et al. arXiv:2302.11813 (SNR-graceful gating — reference
  for any future appearance retry, not used here); **arXiv:2606.02749 Rieckmann et al. (2026)
  flagged: "NN vector magnetometry, STATIC single-shot solver — no tracking/identity/crossing;
  cite to distinguish."**
- Commits on `increment-4-identity-overlay`: specific-path `git add`, clean messages,
  **no AI/tool references** (repo convention). Push to the NAS remote only if reachable
  (NAS powers off ~21:30 ET — do not block on it; leave a note if unreachable).
  **NO GitHub push — held for Jason.**

## Stop-and-report conditions (halt, write up, commit, stop)

1. Pre-flight parity gate fails. 2. Field-metric byte-identity assert fires and the cause is
not a local bug you can fix within the decoder (never touch model/training code). 3. No decoder
survives Step 2. 4. Anything requires regenerating datasets, retraining, GitHub push, or
touching the ws1 archive in place — those are out of scope for this dispatch.

## Out of scope (explicitly deferred; do not start)

Retraining of any kind; Samba-style architecture work; appearance/fingerprint retry (needs the
Q3a seed-stability answer first); nv-sim dataset requests (dwell-sweep, cross-relaxation,
hyperfine, DR-ladder — Step 0 only *scopes* the first); corpus ingestion (TVW-side); any deck
or outward-facing material (TVW-only lane; the A3-physics/appearance mechanisms remain under
the standing IP hold for outward use).
