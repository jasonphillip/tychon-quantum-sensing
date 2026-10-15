# Scalar repair data protocol — 2026-10-15

Gate 1b correction below supersedes the dev r1 nuisance and final access-gate descriptions in the original Gate 1 record. The original record remains for provenance.

## Scope and ownership

This is gate 1 of the accepted scalar repair cycle. The data custodian owns generation, manifests, sealing, and receipts in this worktree. The scalar executor may use development data for repair choices and profiling. The coordinator owns both freezes and integration. No method is scored by this custodian. These spectra are synthetic, single-NV-orientation data. “Realistic anchor” is a condition name, not a laboratory-realism claim.

| Partition | Independent fields | Matched spectra | Allowed use | Generation gate |
|---|---:|---:|---|---|
| dev | 256 | 1,792 | Repair choices, physical bounds, rejection thresholds, runtime profiling | Gate 1 |
| val | 512 | 3,584 | One selection pass among frozen candidates; no retuning | Only after coordinator Freeze 1 |
| final | 1,024 | 7,168 | One campaign after the final freeze | Only after coordinator Freeze 2 and an exclusive access receipt |

The 12,544 planned spectra represent 1,792 independent fields. Each field is rendered under the seven fixed stress conditions. All seven share its field vector, B1-gradient draw, OU nuisance realization, and noise seed. The source OU generator yields one varying realization at step 1 of a two-step trajectory. A distinct trajectory seed is assigned to each field. Thus each field is its own statistical nuisance block; the seven condition rows form a paired block. The source uses its single-orientation renderer, 100 points from 2.82 to 2.92 GHz, isotropic directions, and a uniform 20–70 µT magnitude prior. The stress protocol fixes the seven condition values and postprocessing order. No grid or measurement-contract value changes.

The custodian keeps data under `.scratch/scalar_repair_2026-10/{dev,val,final}`. The generator refuses an existing partition, writes per-cell NPZ files and `manifest.json`, then removes every write bit from files and the partition directory. `--verify` recomputes file SHA256 hashes and checks read-only bits, row shapes, seeds, and file inventory. A failed generation leaves `INCOMPLETE.json` and never seals. No generated data is committed.

## Seed reservation and overlap audit

The seed search reads every `*manifest*.json` in this checkout's `docs/` and `experiments/`, `~/projects/tychon-shared-data/`, `~/projects/portfolio-publication/work/scalar-stress-test/data/` and `sealing/`, and `~/projects/portfolio-publication/wt/odmr-vector-tracking-s1-comparison/docs/`. It found 16 readable manifests and 55,581 distinct used or excluded integer seeds. The target-repair holdout manifest omits row seeds; its saved `master_seed` and `row_count` reconstruct 5,000 row seeds under its saved recipe. No consumed spectrum payload was opened. Each generated manifest stores the path, hash, and seed count for every searched manifest.

The coordinator excludes `20261014`, `20261114`, `20261214`, `20270114`, `202610140`, `202610141`, `202610142`, and `20261015`. The new reserved master seeds are below. NumPy `SeedSequence(master).spawn(3)` supplies separate sample, shot-noise, and nuisance streams. Sample seeds skip all used seeds. The ordered sample-seed lists are recorded in each generated partition manifest. The SHA256 values below hash compact JSON arrays of the reserved sample seeds, without whitespace.

| Partition | Master seed | First three sample seeds | Last three sample seeds | Ordered seed list SHA256 |
|---|---:|---|---|---|
| dev | 202610160 | 688127481, 328363244, 685809729 | 2024232881, 1085840572, 1700009534 | `bf5fc9a46451578033e007d0767a5e8d533e904695724423854eb0c12652091e` |
| val | 202610161 | 32395210, 361968776, 1876901766 | 651485174, 1107739313, 217396216 | `6bea3c59840356ec254b283eb0763ca583d4815e4faf811fa251b29b50a530b3` |
| final | 202610162 | 119629343, 1694964630, 1433211386 | 1321553856, 381927594, 965085291 | `feb1f18637b7f4e4a72ec99ee1c32158dd3b0a950a27921273851c94e9ba57f5` |

The three proposed sample streams are mutually disjoint and have zero seed overlap with the searched metadata. Field-parameter fingerprints combine the reconstructed field vector and normalized B1-gradient draw from each row seed. The source renderer checks its actual field and gradient against that reconstruction during generation. The 256 proposed dev fingerprints have zero matches against 55,400 distinct fingerprints reconstructed from production_50k, production_50k_v2_aic, the target-repair holdout, and prior scalar stress manifests. These checks use saved metadata and public generator logic only. The vector-final manifests describe different sequence families and do not expose comparable scalar row-level field parameters; they receive seed-lineage checks, not an exact row-fingerprint comparison.

Retired sets are the original target-repair holdout, scalar stress final, and vector finals v1 and v2. Changed methods must never be scored on them. Their saved predictions and receipts may be reviewed without opening their spectra.

## Manifest and access contract

Each partition manifest records generator and simulator commits plus source hashes; fixed condition configuration; distributions and units; the complete frequency grid; actual broadened linewidth ranges per condition; sample, noise, and nuisance seeds; field and nuisance-group IDs; file SHA256 hashes; row counts; overlap evidence; wall and CPU time; and peak resident memory. Each field ID is unique within a partition and paired across seven conditions. No label summary or baseline score is released by generation.

Validation is generated only after coordinator Freeze 1. It supports one candidate-selection pass and no method retuning. Final is generated only after coordinator Freeze 2 and an exclusive access receipt. The final payload stays sealed until that receipt reserves its sole scoring campaign. A prior receipt or output blocks a second campaign. A failed campaign retires the accessed final set and requires a new cycle. The generator enforces local freeze-file and receipt presence before val or final generation; the coordinator must review their content and committed hashes before authorizing access.

The cycle allows local CPU only, zero training or GPU, at most four workers and 8 GiB memory, and one thread per numerical library worker. The dev generation cap is ten minutes wall time; all generation is capped at twenty minutes. Every numerical job records wall time, CPU time, and peak memory in `.scratch/compute_ledger.jsonl`.

## Gate 1 dev seal

The dev partition was generated on 2026-10-15 with one numerical worker and `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and `OPENBLAS_NUM_THREADS=1`. It contains 256 fields and 1,792 spectra. Its manifest SHA256 is `bc022e7650c9ef34ff123640d4d9ec659495bcc07c36252f6046c14de85dc2b0`. The manifest reports zero used-seed overlap and zero reconstructable field-fingerprint overlap. Generation used 8.256 seconds wall time, 8.241 seconds CPU time, and 284,663,808 bytes peak resident memory. The exact `--verify` command passed after sealing. Neither val nor final was generated.

⊘ superseded 2026-10-15 → The generator and dev r1 manifest are associated by the provenance receipt below. The historical generation-before-commit order remains unchanged.

## Gate 1b incident and correction — 2026-10-15

Dev r1 is startup-only development data. Its two-step nuisance rows lack orbital thermal drift. The sealed dev r1 files and manifest remain immutable. No validation or final spectra may be generated during this correction. Dev r2 has a separate path and master seed.

Provenance association receipt: commit `4517a737b94d62e5821e405c37123fb767880646` contains the historical generator with SHA256 `e9bdbdc4900ae33049d7d0faaa5c20f968c8ef23e9bb4d87b5a32cfb04af3527`. The immutable dev r1 manifest has SHA256 `bc022e7650c9ef34ff123640d4d9ec659495bcc07c36252f6046c14de85dc2b0`. Dev r1 was generated before that commit. This association does not rewrite the generation time or the manifest.

The production `production_50k_v2_aic` recipe records 40,000 stochastic training rows (`docs/production_50k_v2_aic.manifest.json:23-25`, `:54`). The simulator uses one trajectory sample per row (`batch_generate.py:204-222`). Freeze H = 40,000 for dev r2, validation, and final. Each field has one independent trajectory seed. A separate per-field stream draws k uniformly from integers 0 through H−1. The simulator's `sample_ou_trajectory_pair` starts at nominal T and B1 and runs only through k. The renderer uses the selected (T, mw_power_scale) once per field and pairs that realization across all seven conditions. Each field's trajectory seed, H, k, T_K, mw_power_scale, and nuisance group ID are recorded in its manifest. Each field is one statistical nuisance block.

The historical stress generator used one shared path per partition from t = 0. A 256-row split covered 256 seconds of the 5,400-second orbit and had T standard deviation near 0.57 K, compared with near 6.8 K over a 50,000-step path. Dev r1 restarted a two-step path for every field and saved step 1, which removed that drift. The corrected rule keeps independent fields while matching the production training split's time-uniform marginal. It does not recreate the historical shared-path correlation.

Dev r2 reserves master seed `202610163`; validation retains `202610161` and final retains `202610162`. Sample, shot-noise, and trajectory seeds are disjoint within and across partitions. The generator rejects a collision before sealing. Seed searches accept repeated `--seed-search-root` arguments. Their manifest entries use neutral root labels and relative paths. The simulator loads from the normal Python import, `--sim-src`, or `NV_SENSOR_SIM_SRC`. Validation and final generation require an existing `--gate-doc` named `FREEZE1.md` or `FREEZE2.md`; the manifest records its SHA256. Final generation does not require an access receipt. After generation, the custody tool issues a single exclusive final access receipt and binds it to a release. The coordinator still checks freeze content and committed hashes before access.

Generation checks prior generation wall time plus current elapsed time during its loops and before sealing against 1,200 seconds. Development generation also checks its 600-second cap. Failed attempts stay unsealed with `INCOMPLETE.json` and enter the shared ledger. The generator's `--test` and `--verify` commands enter that ledger under separate job types. Nested test generation is covered by the parent test entry.

## Gate 1b dev r2 seal — 2026-10-15

Dev r2 is sealed under `.scratch/scalar_repair_2026-10/dev-r2`. Its manifest SHA256 is `63ef0c87e56294d657d5550fe71b7cd97e03c771f8de6c43cc30e58b4d61d2e1`. It records master seed `202610163`, 256 fields, 1,792 spectra, and generator SHA256 `082f2bdd214b5cbbde25996247abe9da42899211666fafcc0295d14be5ac8f38`. Generation used 8.233 seconds wall time and 8.220 seconds CPU time. Its exact `--verify` command passed. The SHA256 of the dev r1 `sha256sum` file list remained `24ece1507e35e1229274dd25975b9106bbcd04d480c00458bc2bba466530a9f9` before and after this correction.

The dev r2 manifest names HEAD `4517a73` as the repository revision at generation time. The corrected generator was uncommitted then; that commit contains the historical script, not SHA256 `082f2bdd…`. `generator_commit_contains_script=true` means only that the path exists in HEAD. The coordinator must commit the corrected source and verify its committed blob against the manifest's generator SHA256 before Freeze 1. This historical manifest must not be rewritten to imply that the later commit existed at generation time.
