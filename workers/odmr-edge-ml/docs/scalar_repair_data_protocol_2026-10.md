# Scalar repair data protocol — 2026-10-15

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

The sandbox makes this worktree's external Git metadata read-only. The requested commit could not be created because Git could not create its `index.lock`. The dev manifest records the base repository commit and the exact generator SHA256, with `generator_commit_contains_script=false`; the base commit does not contain this new script. This state must be resolved before a freeze treats the generator as committed.
