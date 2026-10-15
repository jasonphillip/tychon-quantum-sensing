# Scalar repair cycle: validation decision, 2026-10-15

**Decision: STOP.** The single frozen validation run recorded `validation_can_proceed=false`. No Freeze 2 or final data was generated. The public checker independently recomputes that decision from saved validation predictions.

## Experiment and custody

The bounded S1–S3 repair changed the scalar fit, background handling, and paired center/lock choices. It kept the training constants, original prior fit, PID proxy, and direct neural inputs as unchanged controls. No trained weights, exported models, or hardware changed. The evaluation uses fresh synthetic fields across seven paired conditions. Each condition has 512 fields; all 3,584 validation spectra were retained. The same fields and nuisance groups are paired across conditions.

The corrected generator samples one independent thermal and B1 trajectory per field. It draws a uniform step from horizon H = 40,000, matching the production training horizon. Dev r1 lacked drift because it used step 1 of a two-step trajectory. Earlier stress-test cells sampled a short shared path and under-sampled drift: T standard deviation was about 0.57 K on 256 rows, versus about 6.8 K on a long simulator path. These are simulator-only computations. They are not measured thermal data. The corrected distribution also changes the comparison basis. Repair effects must be compared only with unchanged controls on the same new data, never with old headline scores. Source: `docs/scalar_repair_data_protocol_2026-10.md`, Gate 1b; `docs/scalar_repair_cycle_2026-10/data/manifests/dev-r2.manifest.json` and `data/val/manifest.json`.

Freeze 1 pinned source, models, the accepted corrected development manifest, and the validation output root. The custodian then sealed validation data, issued an exclusive access receipt and release, and the evaluator ran once. The bundle retains the original-byte receipts where path-free and labelled public derivatives where host paths occurred. The original hashes for derivatives are provenance claims; readers cannot verify unpublished original bytes. See `docs/scalar_repair_cycle_2026-10/BUNDLE.manifest.json` and `SANITIZATION.json`.

## Registered rule and result

Classical selection used the lowest realistic-anchor all-row MAE among the two repaired classical candidates. Neural selection used the lowest realistic-anchor mean seed MAE among repaired INT8 policies. Differences below 0.1 µT were ties, resolved by fallback fraction, recorded median pipeline time, then lexical name. Selection did not filter for passing gates. A primary prediction gate required the upper paired 95% MAE-difference bound below −0.5 µT against **each** original training constant and p90 absolute error at most 25 µT. Both `clean` and `realistic_anchor` had to pass. Reliability required at least 95% unambiguous, nonfallback valid estimates. Neural blanket reliability also required every seed to pass its prediction gate. Bootstrap used 10,000 nuisance-group draws and seed 202610152001.

The selected methods were `robust_prior_fit` and `joint_fit__int8`. Neither passed both primary prediction gates. Every repaired candidate failed that two-condition conjunction. The unchanged controls were descriptive and ineligible for selection. `joint_fit__int8` passed the clean prediction gate but failed realistic_anchor. `robust_prior_fit` failed both. Their reported reliable-valid fractions on realistic_anchor were 0.152 and 0.151, respectively. The frozen continuation rule therefore stopped the cycle. Sources: `results-val/SUMMARY.json` selection and each primary metrics file in the bundle.

| Method | Role | Clean MAE / p90 (µT) | Realistic-anchor MAE / p90 (µT) |
|---|---|---:|---:|
| `training_mean` | unchanged constant | 12.295 / 22.395 | 12.295 / 22.395 |
| `training_median` | unchanged constant | 12.297 / 22.493 | 12.297 / 22.493 |
| `unchanged_PID` | unchanged PID | 23.857 / 50.036 | 812.430 / 873.492 |
| `original_prior_fit` | unchanged classical control | 10.467 / 21.425 | 12.015 / 22.473 |
| `identity__C_direct_seed42__fp32` | unchanged direct | 10.644 / 20.691 | 35.983 / 57.775 |
| `identity__C_direct_seed42__int8` | unchanged direct | 10.603 / 20.459 | 33.199 / 53.061 |
| `identity__C_direct_seed20261014__fp32` | unchanged direct | 10.555 / 20.488 | 49.737 / 71.985 |
| `identity__C_direct_seed20261014__int8` | unchanged direct | 10.552 / 20.472 | 41.419 / 61.543 |
| `identity__C_direct_seed20261015__fp32` | unchanged direct | 10.587 / 21.084 | 27.055 / 45.981 |
| `identity__C_direct_seed20261015__int8` | unchanged direct | 10.556 / 20.275 | 27.074 / 46.001 |
| `robust_prior_fit` | selected repair | 11.885 / 25.585 | 12.842 / 25.183 |
| `joint_fit__int8` | selected repair, mean seed loss | 10.588 / 20.619 | 12.900 / 27.711 |

All clean numbers come from `docs/scalar_repair_cycle_2026-10/results-val/clean_metrics.json`; all realistic-anchor numbers come from `docs/scalar_repair_cycle_2026-10/results-val/realistic_anchor_metrics.json`. Family rows average three per-seed losses per field; they do not average predictions. The two primary prediction files are adjacent to those metrics files. The table compares methods only on the new validation fields.

What the same-data comparison shows, from the table above: on `realistic_anchor` the repair removes the large failure of the unchanged direct models (unchanged INT8 seeds 27.074, 33.199 and 41.419 µT; repaired `joint_fit__int8` 12.900 µT, mean seed loss), but the repaired estimators do not beat the two training constants (12.295 and 12.297 µT), and the unchanged `original_prior_fit` (12.015 µT) is the lowest realistic-anchor MAE in the table, still inside the registered 0.5 µT margin of the constants. On `clean` the repaired `joint_fit__int8` (10.588 µT) is level with the unchanged direct INT8 seeds (10.552 to 10.603 µT). Only 15.1 % of realistic-anchor rows are reliable-valid for `joint_fit__int8` (`valid_fraction` 0.151). These are descriptive comparisons; the registered decision is the gate result above.

## Public evidence and verification boundary

The bundle contains all seven saved prediction archives, per-condition metrics and fit diagnostics, sealed validation archives and manifests, source Freeze 1 and custody receipts, and the original independent verifier. `QUANTIZATION.manifest.json` binds recorded input/output scale and zero point to the three frozen TFLite hashes. TFLite bytes are not public. `BUNDLE.manifest.json` lists every other bundle file; it excludes itself because a self-hash would be circular.

BUNDLE.manifest.json sha256: 7150142ed4ffbd318ac3ba9ee8f9b87a85cf82faf8ce2c10a0c74c67a4f9b36b

The public checker hashes the bundle before loading arrays. It independently recomputes all seven conditions' metrics, flags, FP32/INT8 raw disagreement, paired comparisons, seed gates, neural `all_seeds_reliable`, selection and STOP. It reconstructs INT8 output codes, checks support and exact float32 dequantization, and compares output endpoint counts and fractions. With `--cross-check-truth`, it compares prediction labels, IDs, and seeds with the sealed validation truth arrays and manifest. It does not open spectra.

Recorded diagnostics remain recorded: input endpoint occupancy; CPU timing and tie-break measurements; fit diagnostics; spectrum-level derivation of common quality flags; uncalibrated likelihood intervals; source/model/custody identities; and TFLite interpreter metadata. Hash-bound records support provenance but saved-output arithmetic does not independently establish those origins. The original verifier's PASS covered the primary decision; the public extension adds secondary bootstrap and output occupancy. Tolerances are absolute 1e-9 and relative 1e-10 for numeric fields, with exact structure, counts, and hashes.

## Compute and limits

The custody ledger has 279 records and sums to 930.089207 CPU-seconds and 465.331757 wall-seconds. The executor ledger has 12 records and sums to 161.635374 CPU-seconds and 166.376484 wall-seconds. Their numeric-field sums total 1,091.724581 CPU-seconds (0.3033 CPU-hours) and 631.708241 wall-seconds (0.1755 wall-hours). These are sums of recorded numeric `cpu_seconds` and `wall_seconds`, including adjustment records. The registered cycle caps were four CPU-hours and two cumulative numerical wall-hours, with at most four workers and 8 GiB memory. They include the kit-evidence publication checks logged before this record; runs of the scalar publication checker are logged after it.

## Reproduction

Run the public checker from a fresh clone, with only NumPy installed, and write the report outside the clone. Set `ROOT` to an empty directory and `SHA` to the public commit you want to check:

```sh
ROOT=/tmp/tychon-public-acceptance
SHA=<40-character public commit>
git clone https://github.com/jasonphillip/tychon-quantum-sensing.git "$ROOT/public"
git -C "$ROOT/public" checkout --detach "$SHA"
python3 -m venv "$ROOT/.venv" && "$ROOT/.venv/bin/pip" install numpy==2.1.3
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "$ROOT/.venv/bin/python" \
  "$ROOT/public/workers/odmr-edge-ml/scripts/recompute_published_scalar_validation.py" \
  --bundle "$ROOT/public/workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10" \
  --no-network --cross-check-truth \
  --expected-bundle-manifest-sha256 7150142ed4ffbd318ac3ba9ee8f9b87a85cf82faf8ce2c10a0c74c67a4f9b36b \
  --out "$ROOT/recomputed-scalar-validation.json"
```

The checker refuses an output path inside the clone or an existing output file. The acceptance script performs the same steps, pins the bundle-manifest hash from this record, writes a receipt outside the clone and checks that the clone stays clean:

```sh
workers/odmr-edge-ml/scripts/public_scalar_validation_acceptance.sh \
  https://github.com/jasonphillip/tychon-quantum-sensing.git <40-character public commit> <empty directory>
```

Run on 2026-10-15 against public commit `5dacae6caafcd8d739ff8a8481304bb5255c3ffc` (Python 3.13.11, NumPy 2.1.3): PASS, 12,288 checks, the STOP decision reproduced, clean clone afterwards. The report records its completion time (`completed_utc`), so its file hash differs between runs; a second run of the command above on the same commit produced a report identical in every other field.

## Source provenance exception

Freeze 1 pins the sha256 of 16 source files. In the public repository, 15 of them match their pinned hashes. The 16th, `experiments/fcnn_v2_int8_float_equivalence.py`, does not: its Freeze 1 (and private source) sha256 is `eae1316fc5dd0bd57522e75f0223d73b672fc105e2630b6253c673eb677070c3`, its public sha256 is `64a50a263af99c690744fc84ac9bd873b50e32d5958eceaa9e13218e7ec5e06c`. The only difference is line 166, the default value of that script's own `--dataset` command-line argument inside `main()`: the publication step replaces the private home-directory prefix of an absolute path with `~` in every tracked text file (the linux rule of the publication path scrub). The frozen evaluator never used that default. It loads the file as a module under another name (`experiments/scalar_repair_cycle/models.py:32`, `importlib.util.spec_from_file_location`), so `main()` does not run, and it calls only `preprocess` and `run_tflite` (`models.py:59-60`, `69-70`). A public reader can see the substitution in the file but cannot reproduce the pinned hash, because the original prefix is not published; for this one file the pin is a provenance claim, not something the public tree can confirm.

## Scientific limit

The validation data are synthetic single-orientation ODMR. No diamond was connected in this cycle. The work establishes no measured sensitivity, no validated field accuracy on public measured spectra, and no useful neural advantage. Sensing remains unresolved. All three reviewed public measured-data candidates are **NOT QUALIFIED** for an independently labelled field-accuracy test. See `docs/measured_data_feasibility_2026-10.md` for their evidence and limits.
