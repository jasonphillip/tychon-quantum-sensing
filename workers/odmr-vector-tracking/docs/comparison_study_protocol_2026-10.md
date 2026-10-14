# Pre-registered vector comparison study — October 2026

Date: 2026-10-14. This protocol is registered before E2/E3 comparator code or Task 7 scoring. Changes after registration require a dated addendum and separate results. Never tune an estimator on final data. Source checks: `data/sequence_train_v2/manifest.json`, `data/sequence_eval_fieldcone_v1/manifest.json`, `experiments/increment6_fieldcone.py`, and the nv-sensor-sim configs named below.

## Amendment 2026-10-14

Plan review points 1–2 identified shared tuning/test data and an asymmetric decision rule. Jason relayed the protocol gate. This amendment adds separate dev, val, and final partitions. It registers symmetric accuracy outcomes and retires each final version after one decision. Tasks 4–8 remain gated until the orchestrating session accepts the amendment.

The existing generated data becomes final v1. It has not been evaluated by an estimator, according to the Task 3 generation handoff. Its earlier access covered generation, hash verification, and one pairing check. Moving its cell directories preserves every HDF5 byte and original per-cell MD5. This access statement is procedural provenance, not something a checksum can prove.

## Operating range and source lineage

The in-envelope cells use the `sequence_train_v2` recipe: 5.00 mT bias along normalized (0.2, 0.1, 1.0), isotropic direction uniform on the sphere, signed swept component endpoints in [−1.4, +1.4] mT, endpoint separation at least 1.0 mT, and held/reversal/OU family weights 0.50/0.25/0.25. The min-axis projection guard is 0.4 mT; jitter is 0.05. The observed train-split total |B| range is 3.56–6.70 mT (command: `python3 -c 'import h5py,numpy as np; f=h5py.File("data/sequence_train_v2/dataset.h5"); b=f["train/B_true"][:]; print(np.linalg.norm(b,axis=-1).min()*1e3,np.linalg.norm(b,axis=-1).max()*1e3)'`; 2026-10-14; source config hash `3341810ccda0`). The plan's 0.1–3 mT |B| line is inconsistent with this source: it is neither the training envelope nor the 5 mT-bias total-field range. We follow the user's explicit training-envelope instruction and retain this discrepancy here.

The frequency sweep is the pinned 951-point 2.6673905228636284–3.0746094771363726 GHz grid of `sequence_eval_fieldcone_v1` (source `data_md5 92dc06692d1975f6fcd101e70cc02d99`, nv-sensor-sim generator SHA `3716e1da4694c661fec798afe148635cf86875d7`). The run used nv-sensor-sim HEAD `9df6dd161719b369e90c0e284cbef0bae39a0612`; `git diff --quiet 3716e1da4694c661fec798afe148635cf86875d7..HEAD --` over both generator modules and source configs exited 0 on 2026-10-14. Each sequence has 256 frames at 1 ms. The extrapolation rung uses that generator's `bucket_class=2` beyond-envelope bucket at off-bias angle 40° and target |B| 2.5 mT. It is visibly labeled **extrapolation**. The three registered extrapolation seeds passed a 40-sequence feasibility preflight at 5 MHz on 2026-10-14. Results are always reported per rung and per cell; clean, realistic, and extrapolation results are never pooled.

## Sealed conditions and generation

Every estimator receives the same stored frames within a partition and cell. Each partition has three trajectory seeds. In-envelope cells reuse their partition's seeds, so one-factor sweeps share trajectories and noise draws. Extrapolation uses a separate three-seed stream. Derived seeds must be disjoint across partitions.

| Partition | Master seed, v1 | Sequences per cell-seed | Cells × seeds | Total sequences |
| --- | --- | --- | --- | --- |
| final | 20261014 | 40 | 14 × 3 | 1,680 |
| dev | 20261114 | 14 | 14 × 3 | 588 |
| val | 20261214 | 14 | 14 × 3 | 588 |

The orchestrating session deliberately raised the v1 sequence cap from 2,000 to 3,000 on 2026-10-14. This preserves the existing 1,680 sequences as final while providing separate development and validation data. The total is 2,856 sequences. The cumulative generation cap remains 3,600 seconds, including the original generation's 631.5178541119676 seconds and any failed generation attempts. Counts are fixed; the amended generator does not silently reduce them. A cap failure stops generation and requires review before further work.

The original generation completed on 2026-10-14. Its schema-1 manifest SHA256 was `c4a11eeb473152355ca0d8438fd9f6219fea245418eb8c9cb6b7c126c1b72ade`. That hash identifies the original seal, not the amended schema-2 manifest. The schema-2 manifest preserves the original final cell hashes verbatim and records each partition's wall time. Its 14 final per-cell MD5 values govern Task 7 data acceptance. Generation receipts and the final schema-2 manifest provide the amended cumulative time.

Data lives under `data/comparison_test_vN/{dev,val,final}/`. Manifest paths are `docs/comparison_test_vN.manifest.json`. Version 1 is the default. The generator accepts `--partition dev|val|final`, positive `--version N`, and `--verify`. Existing final data cannot be overwritten or regenerated. A separate explicit adoption operation migrates the original schema-1 layout without changing its data. Version 2 uses final master seed 20270114; every new version receives fresh partition masters.

| Rung or factor | Fixed values |
| --- | --- |
| Clean | 1.5 MHz linewidth; 3% contrast; SNR ∞; zero baseline slope; zero frequency offset |
| Realistic anchor | 5 MHz; 1.5%; SNR 10; +2% across sweep; +0.3 MHz |
| Realistic one-factor sweeps | linewidth 1.5/3/5/7 MHz; contrast 3/1.5%; SNR ∞/30/10/3; slope 0/+2/−2%; offset 0/+0.3/−0.3 MHz |
| Extrapolation | realistic-anchor sensor condition; only field geometry changes to the source beyond-envelope bucket |

The realistic anchor fixes the +/+ signs; the negative and zero variants are separate one-factor cells. This fixes the plan's otherwise ambiguous ± combination. The full Cartesian product is outside the cap. In-envelope geometry comes from `nv-sensor-sim/configs/sequence_train_v2.yaml` and `nv_sensor_sim.pipelines.sequence_generate.generate_sequence_dataset`; extrapolation comes from `configs/sequence_eval_fieldcone_v1.yaml` and `nv_sensor_sim.pipelines.fieldcone_generate.generate_fieldcone_dataset`. Both use SimOS/QuTiP rendering and the pinned field-cone frequency grid. P1 concentration is solved from `compute_linewidth(p1_ppm)` for the requested intrinsic FWHM. Rendered FWHM includes power broadening; record both in each source manifest. Frequency and field labels stay in physical coordinates.

For in-envelope cells, the sequence generator's `freq_margin_factor` precheck is set from 1.15 to 0.90. That precheck would reject the pinned grid at 5/7 MHz before generating a sample. The factor changes only the conservative config-time bound; trajectory sampling, renderer settings, and the pinned grid stay fixed. The generator still rejects any realized resonance label outside the grid. A 7 MHz pilot passed this exact containment check on 2026-10-14.

The generator lacks a direct global absolute-contrast, baseline-slope, and instrument-frequency-offset argument. These are deterministic post-processing steps in `experiments/make_comparison_test_set.py`, applied in this order: (1) for each sequence, `S1(f,t) = 1 − (1−S0(f,t)) · (C/max(1−S0))`, where `C` is 0.03 or 0.015; this preserves relative line depths and drift; (2) `S2(f,t) = interp(S1(t), f−Δf)` with endpoint fill, where `Δf` is 0 or ±0.3 MHz; (3) `S3(f,t) = S2(f,t) + s · (f−fmid)/(fmax−fmin)`, where `s` is 0 or ±0.02, making end-minus-start baseline change equal to `s`; (4) if finite SNR, add fixed-seed shot noise with `nv_sensor_sim.physics.shot_noise.apply_shot_noise` and `photons_for_dip_snr`, sized to the source line-depth ladder's faintest-to-deepest ratio. The field-cone source manifest has no line-depth ladder, so its extrapolation cell uses a predeclared 0.30 faintest/deepest ratio. SNR ∞ means no added noise. The frequency offset is unknown to estimators; it does not alter the frequency grid or truth labels. These steps are data perturbations, not extra calibration supplied to a model. Inner nv-sensor-sim `data_md5` values describe generator output before augmentation; the outer sealed manifest hashes final HDF5 files.

The checked-in manifest gives each partition's master seed, wall time, and cells. Each cell records config, derived seeds, sequence/frame counts, source generator/config, and `data_md5`. MD5 covers sorted relative `dataset.h5` paths, using a four-byte big-endian path length, path bytes, and raw file bytes. Moving a complete cell directory preserves this relative-path hash. `--verify` checks every present partition and requires all final directories and files to have no write bits. The generator refuses symlinked destination data roots and incomplete output. Data stays Git-ignored and uncommitted.

### Partition access

| Partition | Permitted use | Required boundary |
| --- | --- | --- |
| dev | Task 5 diagnosis, comparator tuning, Task 4/6 development checks | Record changes before val selection and final scoring. |
| val | Protocol sanity runs, best-classical selection, and precomparison Astra review | Select E2 or E3 and commit the choice before final scoring. |
| final | Task 7 only: one complete comparison decision per version | Hash and permission verification are allowed; estimator tuning and exploratory scoring are forbidden. |

A hash proves the data unchanged; the access table plus the commit log of Tasks 4–6 (all committed before Task 7 runs) are the procedural evidence that nobody tuned on final. Filesystem read-only permissions prevent accidental writes, not unauthorized reads. “One read” means one registered scoring campaign across the fixed estimators, not one filesystem read. Record the consumed version, protocol revision, estimator revisions, and selected classical method in the Task 7 decision artifact.

## Estimators and information access

| ID | Fixed estimator | Initialization |
| --- | --- | --- |
| E1 | Published `src/odmr_vector_tracking/tracking/nls_baseline.py::NLSTracker` at this branch's pre-Task-5 revision | Coarse peak detector on frame 0, with no truth |
| E2 | Same module's Task-5 repaired `NLSTracker` (multi-start/Voigt/Γ-from-data changes, recorded in a separate commit) | Same frame-0 detector |
| E3 | Task-4 `src/odmr_vector_tracking/tracking/exact_inversion_baseline.py::ExactInversionTracker`: Lorentzian/Voigt line fit, exact Hamiltonian inversion, BLUE sign/axis handling | Same frame-0 detector |
| E4 | `src/odmr_vector_tracking/tracking/learned.py` no-association tracker, checkpoint `artifacts/portfolio-n/noassoc_s20260702/best.pt` | Its own cold-acquisition path |
| E5 | Published `src/odmr_vector_tracking/tracking/kf_baseline.py::KFHungarianTracker` | As published: truth line centers at frame 0; reference only, ineligible for the decision rule |

E4 was chosen solely by the three runs' `summary.json` `best_val_total`: 20260701 = 0.013324334286153316; **20260702 = 0.010473894886672497**; 20260703 = 0.011100411415100098 (lower is better). Its `best.pt` SHA256 is `0cc0f9ce5969043dfbe2afbb8337eeb2bd4f3df213a1d1b57f161c49ff6b9f99` (`sha256sum artifacts/portfolio-n/noassoc_s20260702/best.pt`, 2026-10-14). No comparison-test cell influenced this choice. E1 must be run from its frozen original module/commit or a faithful copy after Task 5 changes the same path. Do not silently score E1 through E2 code.

All methods may read the cell manifest's intrinsic/rendered linewidth and 5 mT bias vector, pinned frequency grid, frame period, and common NV constants. None may read the true field, true resonance centers, or post-processing offset at inference. E5's published truth-at-t0 initialization is the sole stated exception; report it separately as a favorable reference. Detector settings are fixed before sealed scoring, including a noise-scaled threshold where applicable. Calibration and fit changes use training and dev data. Use val only as allowed in the access table. Freeze detector settings, estimator revisions, and the classical selection before final scoring.

## Metrics and timing

For each sequence, call `src/odmr_vector_tracking/evaluation/rows.py::fieldcone_metrics_row`. It calls `evaluation/metrics.py::vector_rmse` (Tesla; multiply by 1,000 for mT), `vector_angular_error` (degrees; mean and p90), `magnitude_error` (signed `|B_est|−|B_true|`; mean in mT is magnitude bias), `full_vector_lock` (absolute magnitude error ≤5% of truth and angle ≤5°), and `full_vector_lock_stats` (lock fraction and lost). `lost` means never acquired or an unlocked suffix after first acquisition, as `docs/full_vector_metric_and_association_ablation.md` defines it. Undefined/nonfinite angles do not count as good frames. Report valid-frame count as well as the metrics, so a method cannot improve RMSE by emitting NaNs. Cell summaries use per-sequence mean/p90 and sequence-blocked 95% bootstrap intervals (`evaluation/noninferiority.py`); lost rate is the fraction of sequences with `lost=True`. The registered angular p90 comparison is the p90 of the per-sequence `ae_p90_deg` values; RMSE comparison is the mean of per-sequence `rmse_T` values. Report each rung and cell separately.

Measure CPU latency per frame with `time.perf_counter`, one thread, on this host. Include detector/initialization and model preprocessing in end-to-end time; report median and p90 across frames after one warm-up sequence per estimator. Record CPU identity, Python/NumPy/PyTorch versions, and thread limits with results. No GPU is used for latency.

## Decision rule

Primary cells = clean and realistic. Secondary = the one-factor sweeps and extrapolation. Margins: angular p90 ≥ 5° AND RMSE ≥ 10 %, and the paired sequence-blocked bootstrap 95 % CI of the difference must exclude zero.

- `classical_wins`: best classical beats E4 by the margins on BOTH primary cells.
- `network_wins`: E4 beats best classical by the margins on both primary cells.
- `niche_to_confirm`: either side wins by the margins on exactly one primary cell or on ≥ 3 secondary cells — not a verdict; names the cells; must be confirmed on the next untouched final set before any branch runs.
- `neither_reliable`: the best estimator's lost rate > 50 % on the clean rung.
- `inconclusive`: otherwise; no retraining follows.

Latency is reported beside every outcome and never substitutes for accuracy. Best classical = whichever of E2/E3 has the lower angular p90 on the val partition's realistic cell, fixed and recorded before final is read. Retirement: a final set is consumed by one decision; niche confirmation reads v2; any result-driven change after that (retraining, filtering) needs v3.

### Operational definitions fixed before scoring

The clean and realistic primary cells are the named anchors, not their pooled one-factor variants. A win requires both accuracy margins and both paired 95% confidence intervals to exclude zero in the winner's direction. RMSE improvement is `(loser_RMSE − winner_RMSE) / loser_RMSE`; a zero loser RMSE cannot support an improvement. Angular improvement is `loser_angular_p90 − winner_angular_p90`. Resample paired whole sequences, preserving estimator pairing, and recompute the registered cell statistic on every bootstrap draw. Use 10,000 bootstrap draws, NumPy `default_rng(20261014)`, and percentile endpoints 2.5% and 97.5%. Identify a sequence by `(data_replicate, sequence_index)`; different data seeds are different sequences. The existing `compare_paired` helper estimates a mean paired difference. Do not use that mean directly for the registered angular p90 statistic; resample pairs and recompute each method's p90 before differencing.

Choose best classical by the registered p90-of-sequence-p90 statistic on val's realistic cell. Break an exact tie by lower mean sequence RMSE, then E2. E1 and E5 are diagnostics and never enter the decision. Nonfinite predictions cannot qualify as wins by discarding failures; an accuracy result with unresolved missing predictions is ineligible until its failure accounting is specified before final.

Apply `neither_reliable` first if the lowest clean-cell lost rate among E2/E3/E4 exceeds 50%. Otherwise apply a two-primary-cell win before a niche outcome. If neither two-primary win applies, apply `niche_to_confirm` and name each qualifying side and cell. All remaining cases are `inconclusive`. These tie and precedence rules resolve overlaps without inspecting final results.

Do not run result-driven retraining, filtering, or a niche branch against a consumed final version. Confirmation uses the next untouched final version with frozen methods. A subsequent method change requires another untouched version. Dev and val remain available for permitted development. Synthetic results remain synthetic; this study cannot establish live-diamond or hardware accuracy.

### What would change the verdict

Losing either required accuracy margin or confidence-interval condition on one primary cell blocks a two-primary-cell win. A one-primary-cell win or three secondary-cell wins creates a candidate niche requiring untouched-set confirmation. A latency improvement alone never changes the accuracy outcome. If every eligible E2/E3/E4 clean-cell lost rate exceeds 50%, the outcome becomes `neither_reliable`. Name the exact cells and threshold crossings in the Task 7 decision file. Extrapolation-only improvement cannot establish a realistic-cell niche.

## Scalar sub-study — odmr-edge-ml

S1: bench `src/odmr_edge_ml/models/mlp.py::OdmrMLP` on 200 held-out test spectra. S2: Task-6 two-Lorentzian line fit followed by |B| from splitting. S3: deployed `fcnn_v2_residual_dataset_a` INT8 (`exports/fcnn_v2_residual_dataset_a_int8.tflite`) on its 5,000-spectrum held-out split. S4: `src/odmr_edge_ml/evaluation/pid_proxy.py::DerivativeZeroCrossingPID`. Use held-out labels for scoring only; record the source split and model hash. Report MAE and RMSE in µT and CPU latency per spectrum (median/p90) separately for each scalar cohort. The scalar comparison is descriptive and does not enter the vector decision rule.

## Addendum 2026-10-14 (b): failure accounting and the pre-comparison review

Registered before any comparator code and before any scoring. **Failure accounting.** A frame whose estimate is nonfinite, or for which the estimator returns no estimate, counts as *unlocked* for the lock fraction and as a frame of error equal to the estimator's own fallback (its last finite estimate; if none yet, the bias field) for RMSE and angular error, so a failure can never improve a metric by being dropped. A sequence with more than 10 % such frames counts as *lost*. Every results table reports, per estimator and cell, the count of nonfinite frames and of sequences with any. These rules apply identically to E1–E5.

**Pre-comparison review (2026-10-14 15:20 EDT).** The plan's Step 4 named GPT-6 Astra for this review; the Codex weekly budget stop blocks it until 2026-10-20, so the review was done by the orchestrating session (Claude Fable 5.1) and is recorded here. Checked: partitions and seeds disjoint (final 20261014, dev 20261114, val 20261214); access table per task; final read-only and verified by `--verify`; symmetric rule with primary cells, CI condition, precedence and ties fixed; best classical chosen on val before final; retirement v2/v3; sequence cap raised 2,000 → 3,000 deliberately and recorded in the manifest; E5 diagnostic only; extrapolation rung excluded from primary cells. Noted, not changed: dev and val hold 14 sequences per cell-seed (42 per cell) against 40 for final, which is enough for a two-way p90 choice on val's realistic cell but gives wide CIs on dev/val sanity runs; the failure-accounting paragraph above was the one gap found. Astra may add a second opinion after the reset; any change it motivates goes in a dated addendum before Task 7 or in v2.

## Addendum 2026-10-14 (c): scalar sub-study cohorts and the meaning of S2

Registered 2026-10-14 16:40 EDT, after Task 6's implementation found two facts about the data, not about any result: (1) the bench spectra (2.866–2.874 GHz, 100 points) and the `production_50k_v2_aic` spectra (2.82–2.92 GHz) are different frequency grids, so a model trained on one cannot be scored on the other; the sub-study therefore has two cohorts — bench (S1 MLP, S2 fit, S4 PID proxy) and production (S2 fit, S3 deployed INT8 FCNN as B_PID + clip(ΔB, ±2.25 µT), S4 PID) — and cross-cohort rows are reported as not applicable with the reason. (2) S2's two-line fit yields the splitting of one line pair, i.e. an axial projection, not |B|; its original "< 1 µT noiseless" acceptance for spherical labels was invalid and is replaced by exact recovery on valid two-line fixtures plus the reported bench error. Failed fits fall back to the PID estimate with their time counted; no rows are dropped and the failure counts are reported. An S2b (four line pairs → BLUE → |B|) is deferred and, if added, enters as a dated addendum before any scoring that uses it.
