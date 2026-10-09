# Dispatch: Increment-2a re-baseline — supersedes the truncated review message

**To:** the odmr-vector-tracking session (branch `increment-2-learned-tracker`)
**From:** TVW design-review lane, 2026-07-01
**You received only the tail of the original review** (mid-item-4 onward: strict YAML,
hash-pin, input gain, run keys, oracle ablation, v1/per-family plan — all of which you
applied correctly). **Items 1–3 below never reached you, and they change your headline.**
Full review record: `~/projects/tychon-verification-workbench/tvw/audits/design-review-odmr-vector-2026-07-01.md`.

## Context you're missing

A three-agent design review on 2026-07-01 (before your training run) **retracted the
Increment-1 bar**. Your 2a results are genuinely promising — cold-start acquisition,
0/16 lock losses, the overfit gate catching two real bugs, the oracle ablation — but the
comparison column you beat is an instrument artifact, and several surfaces you wrote today
(results doc, wiki README, your session memories) now carry invalid claims. Work the items
in order; your architecture work survives untouched.

## Item 1 — The Increment-1 bar is a detector artifact. Re-baseline first.

`ClassicalTracker`'s default `peak_min_depth=0.03` exceeds the real data's dip depth
(0.0035–0.0076, ~0.4% contrast). On every real frame `_find_peaks` returned **zero
peaks**; the classical tracker never left its ground-truth t=0 initialization; the
published bar (16/16 loss, association 1.0→0.0, "ID-switch 0.811", 43° peak, DR ~5 mT)
scored a frozen tracker against moving lines. Fingerprint: in-collision accuracy ==
out-of-collision accuracy == 0.189. Verified independently by two auditors (a KF fed
through the same broken detector reproduces the published numbers bit-identically —
neither ever received a measurement) and by direct dip-depth measurement.

**Your oracle-ablation conclusion needs a correction**: "the classical collapse is pure
association failure" is wrong — it is pure DETECTION failure. The estimation chain being
near-exact is consistent with both; the detector never returned a measurement for
association to act on.

Fixes:
- Auto-scale the detection threshold from the data's own contrast (per-sequence depth
  percentile or the manifest's `line_depths`).
- Add `assert locked.mean() > 0.9` pre-crossing to `increment1_report.py` output AND to
  `tests/contract/test_real_dataset_contract.py`.
- Re-run the Increment-1 report and publish the honest bar. Expect approximately:
  post-crossing association ~0.75 median, in-collision ~0.63, 11/16 lock losses
  (measured during review at depth=0.0015, GT init).
- Purge/annotate the retracted numbers everywhere they appear (see Item 5).

## Item 2 — Add the competent classical baseline (CV-KF). This flips your headline.

With the detector fixed, a per-line constant-velocity Kalman filter + Hungarian
one-to-one assignment + coast-through-merge **solves v0 essentially perfectly**:
post-crossing association 1.000 median, in-collision ~0.98, ~2 ID switches/seq, 0/16
lock losses — untuned (σ_accel=0.05Γ/frame², R=(Γ/5)², gate 8Γ). Reference
implementation: `~/projects/tychon-verification-workbench/tvw/audits/evidence-2026-07-01/kf_hungarian_baseline.py`.
Adapt into `tracking/kf_baseline.py` and include it in every evaluation.

What this means for your table: your deployable variant's in-collision 0.631 (gated
0.78) vs the KF's ~0.98 → **on v0, the learned tracker does NOT beat competent classical
in-collision; it ties it post-crossing.** v0 is kinematically trivial (linear ramps,
distinct slopes, ~3-frame merges, no noise) and cannot discriminate learned from
classical — that's why v1 exists. The corrected claim for 2a: *"learned tracker with
cold spectra acquisition and a V250-clean deployable partition ties CV-KF post-crossing
on the sanity set; discrimination happens on the v1 adversarial families."* Do not use
"beats classical" against the PID-artifact column.

## Item 3 — Eval correctness fixes (verified findings)

a. `nan_to_num(ae, nan=0.0)` in `increment1_report.py:55` and
   `test_baseline_loses_lock.py:46` grades undefined angular error as PERFECT and
   flatters a cold-start tracker. Nan-aware aggregation; undefined frames count as lost.
b. The printed "ID-switch err" is actually the in-collision misassociation fraction —
   rename it. Give `physical_line_index` a capture radius (beyond it: "unassigned");
   report MOT-style ID switches per crossing opportunity, with per-event pre/post
   windows (the current in/out-collision split saturates once identity corruption
   persists).
c. `tracked_freqs` must be denormalized to Hz (via manifest freq range) in the eval
   path if not already; add a unit test asserting oracle-scoring parity between
   classical and learned output formats.
d. t=0 convention: your cold-start choice for the learned tracker is fine and is the
   stronger story — but then the classical baselines must either also cold-acquire or
   the asymmetry must be stated in every table caption. Pick one and document it.
e. **Delete the DR row from all tables.** DR is unmeasurable on v0 and v1 (|B| spans
   only ~4.7–5.8 mT; a never-losing tracker saturates at the dataset bound — you noted
   this yourself). Keep a footnote; DR claims wait for a dedicated amplitude-ladder
   lineage.
f. Verify your relational-distance rework eliminated shared-candidate claiming at
   inference; if any per-line independent argmax remains, add Hungarian
   (`scipy.optimize.linear_sum_assignment`) or mutual-exclusion greedy on the scores.

## Item 4 — Re-derive everything on sequence_train_v1 (it's ready now)

`data/sequence_train_v1` symlink is live (768×256: 512/128/128; families
hold-ramp-hold/reversal/OU ≈ 50/25/25; per-axis contrast [1.0,0.85,0.7,0.55] with
AR(1) drift 0.05/64; pinned v0 grid; producer-side contract test 4/4). Train on
v1-train; evaluate v1-test **per-family with binomial CIs** (as you already planned);
v0 stays the frozen sanity lineage. The decisive numbers = in-collision association and
ID-switches-per-opportunity on the REVERSAL family (16 reversals inside collision
dwells across the dataset; turn frames recorded per sequence), learned vs CV-KF vs
honest PID, all under identical detector/init/metric conventions.

## Item 5 — Correct the claim surfaces you wrote today

- `docs/increment2a_results.md`: retitle (not "beats the classical bar"); corrected
  table = honest-PID + CV-KF + your variants + oracle floor, identical conventions;
  state the Increment-1 retraction explicitly.
- `~/Desktop/Shared/wiki/projects/odmr-vector-tracking/README.md` (you wrote it today):
  the Increment-1 bullet must state the bar was retracted as a detector artifact; the
  2a bullet must use the corrected claim language; remove the DR sentence.
- Your session memories recording "beats the classical bar on every metric" — update
  them to the corrected state.
- The retracted numbers (16/16, 0.811, 1.0→0.0, 43°, DR≈5 mT) are banned from all new
  text except explicitly labeled as "retracted artifact." (The outward-facing deck was
  already scrubbed by another lane; keep it that way.)

## Item 6 — Keep / status

Keep unchanged: the state-posterior claimed-centers design (MOT convention), the
relational-distance association rework, small-gain recurrence init, the overfit gate,
commit 58f6d37's hardening. GitHub push stays HELD until the corrected results doc
lands; nas pushes remain fine. When done, report the corrected headline table and
per-family v1 results.
