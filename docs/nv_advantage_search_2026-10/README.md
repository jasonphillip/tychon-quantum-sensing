# Advantage search, 2026-10-15: evidence packages

Measured data, development and one single-acquisition transfer test. FAILs are listed first.

| Package | Result |
|---|---|
| [localisation-redesign/](localisation-redesign/) | **FAIL**: the spatial-confirmation redesign. Its registered 95 % upper mean-ratio bound was 1.175543, above the 1.05 limit. |
| [widefield-redesign/](widefield-redesign/) | **FAIL**: eligibility. Repeat agreement R was 0.497194 (f1) and 0.439075 (f4), below the 0.50 limit; no decoder was trained. |
| [localisation-raw-compatibility/](localisation-raw-compatibility/) | PASS: a training-only check that a fresh raw-sweep extractor reproduces the published fitted features (8 sweeps, 64 fits, 192 feature comparisons). |
| [localisation-transfer/](localisation-transfer/) | Conditional PASS: one archived 25-case acquisition. See the [report](../nv_advantage_search_2026-10.md). |
| [custody/](custody/) | August 4 member manifest, seed commitment and released seed, raw custody record, compatibility-sample certification. Files ending `.public` are sanitized; see `SANITIZATION.json`. |

## Data and attribution (CC BY 4.0)
- Localisation: Hao-Cheng Weng et al., "Data/code availability for Photonic-integrated quantum sensor array for microscale magnetic localisation", Zenodo, https://doi.org/10.5281/zenodo.19855773.
- Widefield: S. Sengottuvel et al., Zenodo, https://doi.org/10.5281/zenodo.7233869, and Sci. Rep. 12, 17997 (2022), https://doi.org/10.1038/s41598-022-22610-5.
- Only derived features, predictions and arrays are included. No raw sweep or FITS file is republished.

## Seed provenance (commit and reveal)
The commitment was published before any August 4 signal access: `custody/august4-bootstrap-commitment-v1.json`, commitment_sha256 `84351fe546d6ef2c92aec11ff45c862b15ac11897bba1a3391ac06864abb7cbe`. The seed was released only after the protocol freeze (odmr-edge-ml `3683e43`, protocol sha256 `4682232f…`).
Check it: `sha256sum custody/august4-bootstrap-seed-v1.bin` must equal the commitment. The bootstrap integer in `localisation-transfer/seed.json` is `int.from_bytes(seed, "big")`.

## Public saved-output checks (no inference, no raw data)
Run from the monorepo root, with Python 3 and NumPy:
```
python3 docs/nv_advantage_search_2026-10/check_package.py --expected-artifacts-sha256 edf9957d309455244c2b1ffff9ac6215f4eef0bafb0a4289330514591571e4cf
cd workers/odmr-edge-ml
python3 experiments/localisation_acquisition_transfer/verify_saved.py --result ../../docs/nv_advantage_search_2026-10/localisation-transfer --output "$(mktemp -d)/transfer-check.json"
python3 experiments/localisation_redesign/verify_saved.py --artifact ../../docs/nv_advantage_search_2026-10/localisation-redesign
python3 experiments/widefield_redesign/verify_saved.py --bundle ../../docs/nv_advantage_search_2026-10/widefield-redesign --manifest-sha256 0bd342c8a1fb9be4648440d1fde1b85604bad90d1c8cf80116a42e93013b5d5f --out "$(mktemp -d)/widefield-check.json"
```
- The raw-compatibility package has no public saved-output verifier: its extractor needs the raw archive. Its saved arrays are covered by the hash check, and `root-verification/` holds the independent saved-output result.
