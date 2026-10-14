# Pre-registered vector comparison study — October 2026

Date: 2026-10-14. This protocol and `comparison_test_v1.manifest.json` are sealed before E2/E3 comparator code or Task 7 scoring. Apply the rule below once. Changes after sealing require a dated addendum and separate results; never tune a comparator on these test cells. Source checks: `data/sequence_train_v2/manifest.json`, `data/sequence_eval_fieldcone_v1/manifest.json`, `experiments/increment6_fieldcone.py`, and the nv-sensor-sim configs named below.

## Operating range and source lineage

The in-envelope cells use the `sequence_train_v2` recipe: 5.00 mT bias along normalized (0.2, 0.1, 1.0), isotropic direction uniform on the sphere, signed swept component endpoints in [−1.4, +1.4] mT, endpoint separation at least 1.0 mT, and held/reversal/OU family weights 0.50/0.25/0.25. The min-axis projection guard is 0.4 mT; jitter is 0.05. The observed train-split total |B| range is 3.56–6.70 mT (command: `python3 -c 'import h5py,numpy as np; f=h5py.File("data/sequence_train_v2/dataset.h5"); b=f["train/B_true"][:]; print(np.linalg.norm(b,axis=-1).min()*1e3,np.linalg.norm(b,axis=-1).max()*1e3)'`; 2026-10-14; source config hash `3341810ccda0`). The plan's 0.1–3 mT |B| line is inconsistent with this source: it is neither the training envelope nor the 5 mT-bias total-field range. We follow the user's explicit training-envelope instruction and retain this discrepancy here.

The frequency sweep is the pinned 951-point 2.6673905228636284–3.0746094771363726 GHz grid of `sequence_eval_fieldcone_v1` (source `data_md5 92dc06692d1975f6fcd101e70cc02d99`, nv-sensor-sim generator SHA `3716e1da4694c661fec798afe148635cf86875d7`). The run used nv-sensor-sim HEAD `9df6dd161719b369e90c0e284cbef0bae39a0612`; `git diff --quiet 3716e1da4694c661fec798afe148635cf86875d7..HEAD --` over both generator modules and source configs exited 0 on 2026-10-14. Each sequence has 256 frames at 1 ms. The extrapolation rung uses that generator's `bucket_class=2` beyond-envelope bucket at off-bias angle 40° and target |B| 2.5 mT. It is visibly labeled **extrapolation**. The three registered extrapolation seeds passed a 40-sequence feasibility preflight at 5 MHz on 2026-10-14. Results are always reported per rung and per cell; clean, realistic, and extrapolation results are never pooled.

## Sealed conditions and generation

Every estimator receives the same stored frames in a cell. Master seed 20261014 derives three distinct data seeds. The in-envelope cells reuse those seeds, so one-factor sweeps share trajectories and noise draws; extrapolation uses a separate three-seed stream. Each cell-seed has 40 sequences, so the 14-cell grid has 1,680 sequences. If the 2,000-sequence or 60-minute cap would be exceeded, the generator switches to 20 sequences per cell-seed before starting. The source field-cone generation log reports 47 seconds for 120 sequences; the script uses a conservative 4× projection and a 60-minute alarm. The sealed manifest records the count and measured wall time.

Generation on 2026-10-14 took 631.517854 seconds (`generation_wall_s` in `docs/comparison_test_v1.manifest.json`; command: `PYTHONPATH=~/projects/nv-sensor-sim/src ~/miniconda3/bin/python3 experiments/make_comparison_test_set.py`). The sealed manifest SHA256 is `c4a11eeb473152355ca0d8438fd9f6219fea245418eb8c9cb6b7c126c1b72ade` (`sha256sum docs/comparison_test_v1.manifest.json`). Its 14 per-cell MD5 values, not the original nv-sensor-sim inner hashes, govern Task 7 acceptance.

| Rung or factor | Fixed values |
| --- | --- |
| Clean | 1.5 MHz linewidth; 3% contrast; SNR ∞; zero baseline slope; zero frequency offset |
| Realistic anchor | 5 MHz; 1.5%; SNR 10; +2% across sweep; +0.3 MHz |
| Realistic one-factor sweeps | linewidth 1.5/3/5/7 MHz; contrast 3/1.5%; SNR ∞/30/10/3; slope 0/+2/−2%; offset 0/+0.3/−0.3 MHz |
| Extrapolation | realistic-anchor sensor condition; only field geometry changes to the source beyond-envelope bucket |

The realistic anchor fixes the +/+ signs; the negative and zero variants are separate one-factor cells. This fixes the plan's otherwise ambiguous ± combination. The full Cartesian product is outside the cap. In-envelope geometry comes from `nv-sensor-sim/configs/sequence_train_v2.yaml` and `nv_sensor_sim.pipelines.sequence_generate.generate_sequence_dataset`; extrapolation comes from `configs/sequence_eval_fieldcone_v1.yaml` and `nv_sensor_sim.pipelines.fieldcone_generate.generate_fieldcone_dataset`. Both use SimOS/QuTiP rendering and the pinned field-cone frequency grid. P1 concentration is solved from `compute_linewidth(p1_ppm)` for the requested intrinsic FWHM. Rendered FWHM includes power broadening; record both in each source manifest. Frequency and field labels stay in physical coordinates.

For in-envelope cells, the sequence generator's `freq_margin_factor` precheck is set from 1.15 to 0.90. That precheck would reject the pinned grid at 5/7 MHz before generating a sample. The factor changes only the conservative config-time bound; trajectory sampling, renderer settings, and the pinned grid stay fixed. The generator still rejects any realized resonance label outside the grid. A 7 MHz pilot passed this exact containment check on 2026-10-14.

The generator lacks a direct global absolute-contrast, baseline-slope, and instrument-frequency-offset argument. These are deterministic post-processing steps in `experiments/make_comparison_test_set.py`, applied in this order: (1) for each sequence, `S1(f,t) = 1 − (1−S0(f,t)) · (C/max(1−S0))`, where `C` is 0.03 or 0.015; this preserves relative line depths and drift; (2) `S2(f,t) = interp(S1(t), f−Δf)` with endpoint fill, where `Δf` is 0 or ±0.3 MHz; (3) `S3(f,t) = S2(f,t) + s · (f−fmid)/(fmax−fmin)`, where `s` is 0 or ±0.02, making end-minus-start baseline change equal to `s`; (4) if finite SNR, add fixed-seed shot noise with `nv_sensor_sim.physics.shot_noise.apply_shot_noise` and `photons_for_dip_snr`, sized to the source line-depth ladder's faintest-to-deepest ratio. The field-cone source manifest has no line-depth ladder, so its extrapolation cell uses a predeclared 0.30 faintest/deepest ratio. SNR ∞ means no added noise. The frequency offset is unknown to estimators; it does not alter the frequency grid or truth labels. These steps are data perturbations, not extra calibration supplied to a model. Inner nv-sensor-sim `data_md5` values describe generator output before augmentation; the outer sealed manifest hashes final HDF5 files.

The checked-in manifest gives every cell's config, seeds, sequence/frame counts, source generator/config, and `data_md5`. The hash is MD5 over sorted relative `dataset.h5` array-file paths with a 4-byte big-endian path length, path bytes, and raw file bytes. `--verify` recomputes it. The script refuses an existing test-set directory without `--force` and refuses a symlinked `data/` root, because this worktree's initial `data/` link points at the main checkout. Data files stay Git-ignored and uncommitted.

## Estimators and information access

| ID | Fixed estimator | Initialization |
| --- | --- | --- |
| E1 | Published `src/odmr_vector_tracking/tracking/nls_baseline.py::NLSTracker` at this branch's pre-Task-5 revision | Coarse peak detector on frame 0, with no truth |
| E2 | Same module's Task-5 repaired `NLSTracker` (multi-start/Voigt/Γ-from-data changes, recorded in a separate commit) | Same frame-0 detector |
| E3 | Task-4 `src/odmr_vector_tracking/tracking/exact_inversion_baseline.py::ExactInversionTracker`: Lorentzian/Voigt line fit, exact Hamiltonian inversion, BLUE sign/axis handling | Same frame-0 detector |
| E4 | `src/odmr_vector_tracking/tracking/learned.py` no-association tracker, checkpoint `artifacts/portfolio-n/noassoc_s20260702/best.pt` | Its own cold-acquisition path |
| E5 | Published `src/odmr_vector_tracking/tracking/kf_baseline.py::KFHungarianTracker` | As published: truth line centers at frame 0; reference only, ineligible for the decision rule |

E4 was chosen solely by the three runs' `summary.json` `best_val_total`: 20260701 = 0.013324334286153316; **20260702 = 0.010473894886672497**; 20260703 = 0.011100411415100098 (lower is better). Its `best.pt` SHA256 is `0cc0f9ce5969043dfbe2afbb8337eeb2bd4f3df213a1d1b57f161c49ff6b9f99` (`sha256sum artifacts/portfolio-n/noassoc_s20260702/best.pt`, 2026-10-14). No comparison-test cell influenced this choice. E1 must be run from its frozen original module/commit or a faithful copy after Task 5 changes the same path. Do not silently score E1 through E2 code.

All methods may read the cell manifest's intrinsic/rendered linewidth and 5 mT bias vector, pinned frequency grid, frame period, and common NV constants. None may read the true field, true resonance centers, or post-processing offset at inference. E5's published truth-at-t0 initialization is the sole stated exception; report it separately as a favorable reference. Detector settings are fixed before sealed scoring, including a noise-scaled threshold where applicable. Calibration and fit changes use training/validation data only.

## Metrics and timing

For each sequence, call `src/odmr_vector_tracking/evaluation/rows.py::fieldcone_metrics_row`. It calls `evaluation/metrics.py::vector_rmse` (Tesla; multiply by 1,000 for mT), `vector_angular_error` (degrees; mean and p90), `magnitude_error` (signed `|B_est|−|B_true|`; mean in mT is magnitude bias), `full_vector_lock` (absolute magnitude error ≤5% of truth and angle ≤5°), and `full_vector_lock_stats` (lock fraction and lost). `lost` means never acquired or an unlocked suffix after first acquisition, as `docs/full_vector_metric_and_association_ablation.md` defines it. Undefined/nonfinite angles do not count as good frames. Report valid-frame count as well as the metrics, so a method cannot improve RMSE by emitting NaNs. Cell summaries use per-sequence mean/p90 and sequence-blocked 95% bootstrap intervals (`evaluation/noninferiority.py`); lost rate is the fraction of sequences with `lost=True`. The registered angular p90 comparison is the p90 of the per-sequence `ae_p90_deg` values; RMSE comparison is the mean of per-sequence `rmse_T` values. Report each rung and cell separately.

Measure CPU latency per frame with `time.perf_counter`, one thread, on this host. Include detector/initialization and model preprocessing in end-to-end time; report median and p90 across frames after one warm-up sequence per estimator. Record CPU identity, Python/NumPy/PyTorch versions, and thread limits with results. No GPU is used for latency.

## Decision rule

**Classical wins** if the best of E2/E3 beats E4 on angular p90 by ≥ 5° and on RMSE by ≥ 10 % in every cell with SNR ≥ 10, and E4 wins nothing but latency. **Network niche** if E4 beats the best classical by those margins in any realistic-rung cell, or matches within the margins at ≥ 10× lower latency. **Neither reliable** if the best estimator's lost rate exceeds 50 % on the clean rung. Otherwise "mixed": report both and follow the network-niche branch limited to the cells E4 wins.

Apply once to the sealed set in Task 7. “Best classical” means the better of E2/E3 under the two named accuracy metrics; E1 and E5 remain diagnostics. A claim about synthetic spectra cannot become a live-diamond or hardware claim.

### What would change the verdict

One realistic-rung cell where E4 clears both margins against E2/E3, or matches them with ≥10× lower latency, changes a classical-wins case to network niche. Conversely, one SNR≥10 cell where E2/E3 fails either classical margin blocks classical wins. If the lowest clean-rung lost rate among eligible E2/E3/E4 crosses above 50%, the case becomes neither reliable under the registered rule. The exact cell and metric crossing each threshold must be named in the Task 7 decision file; an extrapolation-only win cannot establish a realistic network niche.

## Scalar sub-study — odmr-edge-ml

S1: bench `src/odmr_edge_ml/models/mlp.py::OdmrMLP` on 200 held-out test spectra. S2: Task-6 two-Lorentzian line fit followed by |B| from splitting. S3: deployed `fcnn_v2_residual_dataset_a` INT8 (`exports/fcnn_v2_residual_dataset_a_int8.tflite`) on its 5,000-spectrum held-out split. S4: `src/odmr_edge_ml/evaluation/pid_proxy.py::DerivativeZeroCrossingPID`. Use held-out labels for scoring only; record the source split and model hash. Report MAE and RMSE in µT and CPU latency per spectrum (median/p90) separately for each scalar cohort. The scalar comparison is descriptive and does not enter the vector decision rule.
