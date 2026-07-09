# Increment 6 — results (v3 angular-coverage retrain, frozen recipe, tri-eval)

*Dated 2026-07-08. TVW dispatch 6 §2 (`dispatch-6-coverage-retrain-2026-07-07.md`; GO per
audit Addendum C, TVW db107c9). Data: `sequence_train_v3` (2048/512/512, off-bias cone widened
to ≥60°, |B| floor 3.0 mT, ~28% directed at the (0,2)/(4,6) degeneracies, ~53% cold starts)
and `sequence_eval_fieldcone_v1` (120 seqs; failure/control/beyond buckets) — consumer-side
pre-flight in `experiments/increment6_preflight.py` (raw md5s bit-identical to the handoff;
manifest data_md5s match the dispatch; note: content `data_md5` is a generation-determinism
signal, not recomputable from the delivered h5 — the writer casts dtypes at write time).
Training: wave-2 `gated+linear+aug`, **frozen v2 recipe** (settings byte-matched to the v2
checkpoints; input_gain/photon budget data-derived by the same law — photons landed identical
at 7.743e7), seeds 20260701/11/21, v3 only, cues-OFF. Early stops at epochs 210/270/250, best
val 0.6581/0.6995/0.6456 — ~10× the v2 val floor (0.068), expected for the harder widened
task; no divergence. Verdict rules were committed PRE-HOC in `experiments/increment6_verdict.py`
(6074f41) before any result existed. Artifacts: `artifacts/noise_matrix/matrix_6_coverage.json`,
`artifacts/increment6/{coverage_split_v6.json, fieldcone_v6.json, increment6_verdict.md,
fieldcone_boundary.png}`; reproduce via `increment6_preflight.py` → training chain →
`noise_matrix_report.py --only v1 --v1-runs artifacts/increment6/runs` →
`increment6_coverage_split.py` → `increment6_fieldcone.py` → `increment6_verdict.py`.*

## Question

Increment 5 measured a deterministic training-coverage gap: field acquisition fails 216/216 on
merge templates requiring 41°/53° off-bias at 3.9/3.3 mT — outside the v1/v2 ≤18° envelope.
Dispatch 6 asks: does retraining the same architecture, same recipe, on angular-coverage data
(v3) clear that acquisition failure without giving back the standing v1/v2 claims?

## Verdict (per the pre-hoc rules)

**SUCCESS — the off-cone acquisition failure clears completely, the field-lock guard holds,
finding (b) reconfirms on the new checkpoints — and the cost is a measured, report-only
identity regression on the v1 standing eval.** No defaults change in this increment; v6
adoption is a separate decision that must weigh the trade-off below.

### Part 1 — regression guard (immutable v1 standing eval): NO TRIPS

Classical parity gate: pid/kf/nls reproduce `matrix_2c_final.json` **exactly** at every rung ×
family (fixed-seed noise; eval path unchanged). Field lock v6 vs v2: CI-neutral at all 12
rung × family cells — no guard trip. Honest lean: at snr3 the v6 point estimates are worse
(reversal 12/69 → 22/69, ou 16/90 → 25/90, both CI-overlapping) with wide per-seed spread
(reversal per-seed 0.174/0.304/0.478) — reported, not a trip under the pre-hoc rule, but real.

**The trade-off (report-only per dispatch; guard scope is lock):** v6 identity on the v1
standing eval regresses substantially and CI-disjointly at clean/snr30/snr10 — e.g. clean
held misassoc 0.311 → 0.540, exit IDSW/opp 0.171 → 0.398; reversal 0.424 → 0.538 / 0.181 →
0.382; ou 0.505 → 0.576 / 0.204 → 0.273. The pattern holds at snr30/snr10 and softens to
mixed at snr3. Angular coverage was bought with in-distribution identity sharpness at fixed
capacity (175,790 params) and a frozen recipe — the network now spreads the same capacity
over a ~3.4× wider angle cone.

### Part 2 — PRIMARY: the acquisition gap clears

| rung | population | v2 lock-loss | v6 lock-loss | rule |
|---|---|---|---|---|
| clean | offcone/cross | 216/216 | **1/216** | CI-disjoint, every seed ✓ |
| clean | offcone/bounce | 216/216 | **2/216** | CI-disjoint, every seed ✓ |
| snr30 | offcone/cross | 216/216 | **1/216** | CI-disjoint, every seed ✓ |
| snr30 | offcone/bounce | 216/216 | **2/216** | CI-disjoint, every seed ✓ |

In-coverage lock stays perfect (0/216 every population, both rungs — no in-cone give-back).
The increment-5 deterministic failure is gone: the tracker now cold-acquires and holds the
field on the exact geometries that broke it, at 214–215/216 per population.

### Part 3 — field-cone boundary (chart: `fieldcone_boundary.png`)

Per-geometry lock-loss, clean rung, pooled 3 seeds (12 seqs/geometry; snr30 near-identical;
KF keeps GT t=0 init — a hold reference, not a cold-acquisition comparator):

| geometry | v2 | v6 | v6 never-acq | KF ref |
|---|--:|--:|--:|--:|
| failure 41°/3.92 mT ((0,2) merge) | 36/36 | **0/36** | 0/36 | 0/12 |
| failure 53°/3.26 mT ((4,6) merge) | 36/36 | **0/36** | 0/36 | 0/12 |
| control 10°/5.0 mT | 0/36 | 2/36 | 0/36 | 0/12 |
| control 30°/4.5 mT | 36/36 | **8/36** | 6/36 | 1/12 |
| control 45°/4.0 mT | 36/36 | 30/36 | 14/36 | 1/12 |
| control 52°/3.6 mT | 36/36 | 27/36 | 14/36 | 2/12 |
| beyond 40°/2.5 mT (< |B| floor) | 36/36 | 36/36 | 30/36 | 1/12 |
| beyond 50°/2.0 mT (< |B| floor) | 36/36 | 36/36 | 35/36 | 9/12 |
| beyond 66°/3.6 mT (past cone) | 36/36 | 35/36 | 35/36 | 0/12 |
| beyond 70°/3.3 mT (past cone) | 36/36 | 36/36 | 36/36 | 2/12 |

The pre-hoc widened-envelope claim rule passes (classes 0+1 pooled CI-disjoint + every-seed,
both rungs). Read the structure honestly, though:

1. **The directed geometries cleared completely** (0/72 lost, zero acquisition failures) —
   the ~28% directed training component did exactly what it was aimed at.
2. **v2's real envelope was narrower than documented**: it loses 36/36 even at the 30°
   control — the ≤18° "envelope" was the training draw, not the capability edge.
3. **v6's reliable cone ends around 30–40° for generic geometries**: 45°/52° controls remain
   majority-lost (30/36, 27/36; never-acq 14/36 each). Angle-stratified density (~23
   seqs/degree) taught the band; directed oversampling taught its aim points. Coverage is
   geometry-specific, not a blanket angle capability.
4. **Beyond the envelope is a cliff, not decay**: never-acquires in 135–144/144 past the cone
   or below the |B| floor. Unlike the graceful dwell-length degradation (increment 5), the
   angular/field envelope binds hard. The generalization statement is: none.

### Part 4 — finding (b) reconfirmed on v6 (dwell in-coverage, clean)

KF conditioned-on-lock per the 2c house rule (dispatch-6 §1 convention):

- **bounce**: v6-A3 **133/1728 = 0.077** vs KF 0.407 uncond / **0.508 conditioned** —
  CI-disjoint, every seed ✓ (~6.6× conditioned).
- **pooled topologies**: v6-A3 **0.122** vs KF 0.287 conditioned — CI-disjoint, every seed ✓.
- **cross**: v6-A3 0.166 vs KF 0.136 conditioned — neutral; **stays no-claim** (as retracted
  at dispatch-6 §1; v6 does not clear the bar either).

The balanced-topology identity claim survives the checkpoint swap — weaker in absolute terms
than v2's (A3 bounce 0.045 → 0.077, cross 0.111 → 0.166; the same capacity trade-off as Part
1c), but the claim was learned-vs-KF and it holds with margin.

**New territory — off-cone exit identity** (report-only; acquisition now succeeds there):
v6-A3 offcone/bounce 0.048 [0.039–0.059], offcone/cross 0.158 [0.142–0.176]. KF conditioned
on the off-cone is essentially vacuous (0 bounce survivors; 2/184 on its 23/72 cross
survivors — short-dwell survivor bias at its most extreme). The learned tracker is now the
only tracker with measurable through-merge identity at the off-cone geometries.

## Decision

Per keep-what-survives: **no defaults change here.** The deployable default remains the v2
`gated+linear+aug` checkpoints with A3 on OU/reversal, baseline on held. What this increment
establishes for the program:

1. **Angular coverage is trainable and was the right lever** (dispatch confirmed): the
   deterministic acquisition failure clears completely under a frozen recipe — data, not
   architecture, was the binding constraint. The v1-eval identity price says the *next*
   binding constraint is capacity/recipe, not data breadth.
2. **The deploy decision is now a real trade** (routes UP to TVW): v6 = acquisition across
   the widened cone + only tracker with off-cone identity; v2 = sharper in-cone identity.
   Options a TVW dispatch could weigh: adopt v6 where acquisition dominates; keep v2 where
   identity dominates; or a follow-up increment (capacity bump or v2+v3 curriculum — both
   are recipe changes needing a fresh dispatch) to buy back identity at coverage.
3. **The claim boundary is now a measured chart**: reliable to ~30–40° generic / the directed
   geometries specifically; hard cliff past the training envelope; |B| floor binds at 3.0 mT.
   Any outward statement must carry the geometry-specific caveat (TVW owns outward).

## Disposition (2026-07-08)

Branch `increment-6-coverage-retrain`; doc-only + experiment scripts committed (checkpoints/
artifacts gitignored per standing practice, preserved on disk); pushed NAS + private GitHub;
main promotion after this doc per dispatch. Training watchdog cron installed for the overnight
run and torn down after completion. 175 tests untouched (no library code changed; eval scripts
only). No cue data used; spark1 archive untouched; no dataset regeneration; outward material
untouched.

## Addendum — dispatch-7 default flip (2026-07-09)

The "no defaults change in this increment" line above is superseded by TVW dispatch-7
(`dispatch-7-v6-default-2026-07-08.md`), which ruled v6 the deployable default (acquisition
dominates the deployable field claim) with v2 pinned as the in-cone identity reference. The flip
is zero-retrain (checkpoint swap + a pre-hoc re-selection of the decode policy on the v6 weights;
no training, no new decoders) and is recorded canonically in
[`docs/deployable_default.md`](deployable_default.md).

Policy re-selection (`experiments/v6_redecode_policy.py`, rule committed PRE-HOC at 9d9a554;
result `artifacts/increment6/v6_redecode_policy.{json,md}`): on the standing menu
`baseline / A1(physics) / A3(stack5)`, selection metric in-collision misassoc, pooled 3 seeds,
Wilson 95% CI-disjoint + every-seed to switch a family, ties → keep the v2-era choice —
**no family switched.** The v2-era per-family policy transfers unchanged to v6: held → baseline,
ou → A3, reversal → A3; the dwell through-merge decode stays A3 (it wins every dwell population,
in-cone and off-cone, both rungs). Stop-conditions all cleared: field lock is decode-invariant
and v6-vs-v2 CI-neutral at all 12 standing cells (flip does not damage the field claim); the
re-decode `baseline` reproduces the `matrix_6_coverage.json` learned column exactly; v6 md5s match
this run record. The v6 trade-off caveat (in-cone identity regression CI-disjoint clean→snr10;
snr3 lock lean CI-neutral) and the geometry-specific boundary language travel with the default —
see `deployable_default.md`. The identity-recovery retrain remains a separate dispatch
(dispatch-8 / increment-7), pending Jason's go.
