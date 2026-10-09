# Design review — odmr-vector-tracking / nv-sensor-sim sequence program

**Date:** 2026-07-01 (evening)
**Scope:** everything built 2026-06-29 → 07-01 for the through-crossing tracker program: the
`nv-sensor-sim` time-series generator + `sequence_sanity_v0` dataset, the `odmr-vector-tracking`
Increment-1 foundation (classical baseline, metrics, BLUE decode, learned skeleton, published
"bar"), the in-flight `sequence_train_v1` config, the in-flight Increment-2a training package,
and the thesis/novelty/IP claims in `docs/design/00–03` + `landscape_ip.md`.
**Method:** three parallel audit agents (generator physics; tracker/metrics code with empirical
re-runs; prior-art/physics skeptic over local corpora + web) plus direct artifact inspection of
`sequence_sanity_v0/dataset.h5`. Key empirical findings were independently reproduced by two
agents and corroborated by direct measurement. Evidence scripts: `evidence-2026-07-01/`.
**Status at review time:** both repo sessions were live; injections were dispatched same-evening
(nv-sim rounds 1–3 at its dry-run gate; 2a stop-ship list at the tracking session).

---

## Verdict

1. **The published Increment-1 bar is invalid — a detector-threshold artifact.**
   `ClassicalTracker.peak_min_depth` defaults to 0.03; real per-line dip depth is 0.0035–0.0076
   (~0.4% contrast). The peak detector returned **zero peaks in every frame of every real
   sequence**; the tracker never left its ground-truth t=0 initialization; the metrics scored a
   frozen tracker against moving lines. All headline numbers (16/16 loss of lock, association
   1.0→0.0, "ID-switch 0.811", 43° peak, DR ~5 mT) are artifacts. Fingerprint: in-collision
   accuracy == out-of-collision accuracy == 0.189. Proof: a Kalman tracker fed through the same
   broken detector reproduces the published numbers bit-identically (neither ever received a
   measurement).
2. **With the detector fixed, the repo PID baseline fails honestly but mildly** (post-crossing
   association ~0.75 median, in-collision ~0.63, 11/16 lock losses at depth=0.0015, GT init).
3. **A ~60-line textbook classical tracker solves the entire v0 benchmark** — per-line
   constant-velocity Kalman + Hungarian one-to-one assignment + coast-through-merge: post-crossing
   association 1.000 (median), in-collision ~0.98, ~2 ID switches/seq, peak vector error 0.1°,
   0/16 lock losses, with untuned first-try parameters (σ_accel=0.05Γ/frame², R=(Γ/5)², gate 8Γ).
   Root cause: v0's crossings are kinematically trivial — linear ramps, distinct per-axis Zeeman
   slopes, ~0.4–0.9 MHz/frame rates, ~3-frame merge windows, noiseless deterministic spectra, and
   **no line-identity cue other than the Zeeman slope** (hyperfine deferred; per-axis contrast
   identical by construction; noise absent).
4. **The thesis survives, re-aimed.** The defensible claim after this review: *greedy
   frequency-only association fails at crossings (known since the 1980s partial-tracking
   literature); velocity-aware classical tracking solves easy crossings; the learned tracker
   targets the residual, provably-ambiguous regimes — matched-slope/slow crossings,
   maneuver-during-merge, noise-dominated dips, drifting amplitude cues — fused with NV physics
   priors under deployable INT8/V250 constraints.* Every clause has a citation (below).

---

## Finding index

### A. Generator / dataset (nv-sensor-sim)

| # | Sev | Finding | Fix state |
|---|-----|---------|-----------|
| A1 | crit | Spectra 100% noiseless (`noise_mode:"deterministic"`; no noise path in sequence pipeline; OU machinery exists but unwired). Dips 0.35–0.39% of baseline → noise-free tracking is unrealistically easy; INT8 robustness untested | Decision: datasets stay deterministic; physics-owned noise helper applied consumer-side (train-augment + fixed-seed eval). Follow-up commit queued |
| A2 | crit | Frequency window/F derived per-config; isotropic v1 would get F=1024 over ±219 MHz vs v0's 951 over ±204 MHz; **no freq_range override existed** | Injected (round 1+2): add `freq_range_Hz` override; pin v1 to v0's exact 951-pt grid; containment asserts |
| A3 | major | Isotropic ramps can push axis-4 projection through zero (bias proj 1.972 mT < worst-case 2.3 mT sweep) → diagonalized labels jump discontinuously; ~0.2% of sequences; no guard/stat | Injected (round 2): reject-resample min per-axis \|B∥\| < 0.4 mT + manifest stat |
| A4 | major | v1 difficulty drifts easier vs v0 (T=256 same magnitude → per-frame motion 0.11Γ typ vs v0's 0.34Γ; dwell ~2×; ~6.5% zero-collision seqs); nothing recorded | Injected (rounds 1+2): sub-interval ramps span v0 velocities; manifest stats; honest PID bar to be re-derived on v1-test |
| A5 | major | Instrument model notional and undocumented: full 951-pt spectrum per 1 ms frame ≠ any real CW lock-in front-end; deployable input representation (probe tones / lock-in error channels) unaddressed | Docs note now; sparse-acquisition mode = future lineage before deployment claims |
| A6 | major | All 4 axes identical contrast/linewidth (mw_scale never passed) — removes a real, published identity cue; contradicts docs' own fingerprint story | Injected (round 3): per-axis contrast knob + optional slow drift; document |
| A7 | minor | v0 manifest provenance: git SHA predates the generator (dirty-tree generation), no contract_version | Injected (round 2 rider): `-dirty` suffix in `_get_git_sha`; regenerate v0 manifest at clean HEAD |
| A8 | minor | Collision labels use intrinsic FWHM 1.5012 MHz; rendered lines power-broadened ~4.9% wider; intra-axis pairs counted but undocumented | Injected (round 2): keep intrinsic for v0-consistency; record both; document |
| A9–A13 | minor | No structured sweep-geometry manifest fields; loader exposes labels+inputs in one flat dict; stale "exact to second order" docstring; soft window-containment; numpy version unrecorded | Injected (round 2) / queued docs |

### B. Tracker / metrics / eval (odmr-vector-tracking)

| # | Sev | Finding | Fix state |
|---|-----|---------|-----------|
| B1 | crit | Published bar = detector artifact (verdict §1); `locked` computed but consumed nowhere; contract has no contrast field (the seam) | Injected (2a): auto-threshold from data contrast; assert pre-crossing locked>0.9 in report+contract test; re-derive + re-publish bar |
| B2 | crit | CV-KF+Hungarian+coast solves v0 (verdict §3) | Injected: add as baseline #2 (`tracking/kf_baseline.py`, ref impl in evidence dir); claims rescope |
| B3 | crit | v0 carries no identity cue beyond kinematics → success on v0 can only demonstrate learned CV-coasting | Dataset redesign injected upstream; claims rescope |
| B4 | major | DR metric can't measure extension on v0 (\|B\| spans 4.73–5.82 mT; perfect tracker caps at 1.16× classical) | Injected: 2a claims = association/lock only; DR needs amplitude-ladder lineage |
| B5 | major | "ID-switch 0.811" is a mislabel (in-collision misassociation fraction); id_switch_rate ungated (nearest-line attribution inflates switches once derailed) | Injected: rename; capture-radius gate; MOT-style IDSW per crossing opportunity; per-event pre/post windows |
| B6 | major | Learned-vs-classical scoring asymmetry: tracked_freqs in normalized units vs Hz metrics; GT init for classical vs cold learned | Injected: denormalize via manifest; parity unit test; document t=0 convention |
| B7 | major | `nan_to_num(ae, nan=0.0)` grades undefined angular error as perfect — flatters a zero-init learned tracker | Injected: nan-aware aggregation; undefined = lost |
| B8 | major | Statistical power: 16 near-replicate test seqs (one scenario family; effective n≈1); 16/16 → 95% CI [0.79,1.0] | v1 = 128 test + scenario diversity; report per-family CIs |
| B9 | major | Sign recovery by inherited slot identity only; Σproj=0 redundancy unused as consistency check; sign flips never exercised | Σproj residual monitor queued; sign-flip lineage = v2 (with A3 label work) |
| B10 | minor | Inference assignment = per-line independent argmax (two slots can claim one candidate forever) | Injected: Hungarian / mutual-exclusion at inference; CE-on-scores training loss is sound as-is |
| B11 | minor | Leakage boundary is convention not API (committed training path verified clean) | Injected: observables_only view / trainer assertion |
| B12 | minor | ops_guard allow-by-default on unknown ops | Injected: unknown → fail/triage |
| B13 | minor | Geometry parity producer↔consumer VERIFIED clean (axes order, γ=28.035 GHz/T, FWHM conventions) but parity test still a skip | Wire or hash-pin |
| B14 | minor | Report provenance: free parameters unstated (LOSS_DEG=5°, recovery_window=None), no dataset hash echoed, no JSON artifact; `ScenarioConfig` defaults mirror fixture not real data | Injected: echo provenance + params + lock fraction; JSON artifact; strict config keys |

### C. Literature / novelty / IP (skeptic sweep; citations verified this session)

| # | Threat | Finding |
|---|--------|---------|
| C1 | high | "No classical method does real-time multi-line association at collisions" is falsified as worded: Depalle ICASSP'93 (HMM, "allows frequency line crossing"); Lagrange IEEE TASLP 2007; **Neri & Depalle DAFx-18 (real-time Hungarian partial tracking through crossings)**; Paris & Jauffret IEEE TAES 2003 (f-dot state); Pace SPIE 2000 (MHT+IMM lofargram). Surviving hard core: matched-kinematics+matched-amplitude crossings are provably ambiguous (Kropfreiter IEEE OJSP 2024 "bounce more often than cross"; JPDA coalescence, Fitzgerald 1985); slow crossings (Coraluppi SPIE 7445 analytic model); maneuver/branch choice at crossing (mode-veering, du Bois JSV 2009). No frequency-line paper handles avoided crossings — open sliver |
| C5 | med | NV–NV cross-relaxation at inter-orientation degeneracy is real crossing-localized physics the independent-axis renderer cannot produce: contrast dips/broadening 1–4% for NV ≳1 ppm (Mrózek EPJ QT 2015; Lazda PRB 2021; Dhungel PRB 2024; Pellet-Mary PRApplied 2023) — rivals the 0.4% lines exactly in the crossing window; MW-free magnetometers are built on these dips. Absent from generator AND corpora (zero grep hits). Action: pin diamond spec ≲0.5 ppm or add phenomenological CR term; note the dip is itself a crossing marker a tracker could exploit |
| C6 | low | ESLAC ~51 mT / GSLAC ~102.4 mT ceilings verified correct (Clevenson §IV; Zheng PRApplied 2020). Gradual orientation-dependent contrast loss + discrete CR features pepper 30–50 mT |
| C7 | low | Wildcard: paywalled Stuttgart APL 2026 (doi:10.1063/5.0310526, "High-dynamic-range vector magnetometry…", already cited as "locking + DDS hopping") — **pull full text before any external claim** |
| C8 | low | Corpus hygiene: 404-stub files for Clevenson/Barry RMP/Schloss/Zheng in odmr-pnt-nv-docs; Dubey arXiv:2504.18478 (2025 experimental map of inter-orientation overlap ambiguity) in corpus but missing from references.md |

### D. Process / infrastructure

- **D1.** Both running sessions had built-in approval gates (plan-mode; dry-run go-ahead) — injections landed without killing either session. Keep designing dispatch prompts with gates.
- **D2.** The artifact bar survived two sessions and an honest-inventory pass because no report asserted the instrument sanity invariant (lock fraction) and no control separated "fails at the hard part" from "fails everywhere." Lesson filed: `wiki/lessons/benchmark-sanity-invariants.md`.
- **D3.** GPU: training runs on spark1 GB10 (torch 2.11 cu130 verified); generator is CPU/qutip single-process — adequate (5-min full run); levers if lineages grow: multiprocessing → batched `torch.linalg.eigh`. Two-Spark leverage = parallel experiment matrix (config-addressable runs, ssh+nohup+pidfile dispatch), not memory.
- **D4.** external outreach (+48h window) lists "Increment-2a tracker result" as a deck item — **only post-re-baseline claim language may ship**; the retracted numbers must not appear in any outbound material.
- **D5.** INVENTORY.md §5 corrected via Addendum 2 (both copies). nv-sim & odmr-edge-ml still GitHub-only remotes (nas mirrors recommended, carried from daily log).

## Queued follow-ups (post-run, not yet dispatched)

1. Repo docs corrections in odmr-vector-tracking (after 2a session lands): `01_research_findings.md` C1/C4 rewording; `landscape_ip.md` C2/C4 rewrite; references.md additions (C1/C2/C3/C5 citations + Dubey).
2. nv-sim: physics-owned measurement-noise helper (A1); v2 items — sparse/probe-tone acquisition mode (A5), sign-flip lineage with near-merge label semantics (A3/B9), phenomenological CR term or diamond-spec pin (C5), hyperfine lineage (the docs' own fingerprint cue + the regime where association complexity actually rises).
3. Corpus: re-acquire C8 stubs; ingest CR literature (C5 refs) + the C1 classical-tracking set into odmr-pnt-nv-docs (or a tracking-specific corpus); pull the Stuttgart APL 2026 paper (C7).
5. Amplitude-ladder (DR) eval lineage design before any dynamic-range claim (B4).
