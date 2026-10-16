# Advantage search, 2026-10-15: two failures and one narrow conditional pass

Status: **the overall goal is not met.** No broad practical advantage and no neural advantage has been shown.
The earlier measured-data pilots stay closed. This search changed assumptions those pilots had held fixed.
Every gate below was fixed before the results it judges.

## Failures first
- **Localisation, spatial-confirmation redesign: FAIL.** On held positions the mean-error ratio was 0.930743 and the p95 ratio 0.758602. The registered 95 % upper bound on the mean ratio was 1.175543, above the 1.05 limit; the family-wise upper bound was 1.231920. The 36 consumed positions are not reused. [Package](nv_advantage_search_2026-10/localisation-redesign/).
- **Widefield redesign: FAIL at eligibility.** The registered repeat-agreement measure R was 0.497194 (f1) and 0.439075 (f4), below the 0.50 limit. No decoder was trained, and no new files were opened. [Package](nv_advantage_search_2026-10/widefield-redesign/).

## Conditional pass: one archived acquisition
**Question:** does a GP calibrated with fewer stage positions transfer to a separate archived acquisition as well as one calibrated with more positions?
- **Calibration:** both GP checkpoints are unchanged from the redesign. One uses 124 and the other 248 unique calibration positions (validation included). This is a difference in calibration positions, not a proven difference in acquisition time.
- **Test data:** all 25 sweeps recorded on 2025-08-04 (see the custody records). They were opened once, after the protocol freeze and the seed release.
- **Pre-check:** a training-only compatibility check came first. A fresh extractor reproduced the published features on 8 training sweeps, with a maximum splitting difference of 0.00008 MHz ([package](nv_advantage_search_2026-10/localisation-raw-compatibility/)).

| Measure | 124 positions | 248 positions | Criterion |
|---|---:|---:|---|
| Mean error (µm) | 51.67 | 56.17 | — |
| Mean-error ratio, small/full | 0.920 | | conditional 95 % upper bound 1.0328 ≤ 1.05 |
| Upper bound on small-model mean error (µm) | 61.20 | | ≤ 63.5 (half the 127 µm sensor pitch) |
| p95 error (µm) | 84.77 | | ≤ 127 |

All 10 registered criteria passed. The independent saved-output verification passed 37 checks.

**Limits, all stated before the run or found in it:**
- **Stricter bound:** at the 98.333 % level, declared diagnostic-only before signal access, the bounds are 1.07698 and 63.68 µm. **Both would fail.**
- **Single acquisition:** this is one acquisition. The five whole y-stripe groups give only conditional spatial uncertainty within it. **No across-day or population claim.**
- **Geometry:** one test coordinate equals a training position. Five points at y = 1184 µm lie slightly outside the original range.
- **Unresolved:** stage calibration uncertainty and full raw-to-fit lineage.
- **Not claimed:** neural superiority, search-adjusted global significance, or a general sensing result. The pitch-scale criteria are engineering benchmarks, not validated tolerances.

[Transfer package](nv_advantage_search_2026-10/localisation-transfer/) · [custody and seed provenance](nv_advantage_search_2026-10/README.md#seed-provenance-commit-and-reveal)

## Reproduce
The [package README](nv_advantage_search_2026-10/README.md#public-saved-output-checks-no-inference-no-raw-data) lists a stdlib hash check and three saved-output verifiers. They use NumPy only, run no inference and read no raw data.
Each lane's manufactured tests run in CI in a separate process.

## Data
Zenodo [10.5281/zenodo.19855773](https://doi.org/10.5281/zenodo.19855773) (localisation) and [10.5281/zenodo.7233869](https://doi.org/10.5281/zenodo.7233869) (widefield), both CC BY 4.0. Only derived arrays are included.
