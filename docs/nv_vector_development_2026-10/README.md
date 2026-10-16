# Vector inversion speed evidence package, 2026-10-15


This package holds the saved evidence for the [vector inversion speed report](../nv_vector_development_2026-10.md):
the P1 development comparison (2× gate PASS) and the stronger baseline challenge (2× gate FAIL).
All data is synthetic. Nothing here was measured on a sensor or on the FPGA board.

## Layout

- `p1/`: the P1 bundle. 44 original files in 50 parts, plus `PUBLIC-MANIFEST.json` and `ORIGINAL-MANIFEST.json`. Every P1 artifact is included except `checkpoint-progress.pt`, an intermediate training checkpoint; the manifest records the omission.
- `challenge/`: the baseline-challenge bundle. 29 original files in 53 parts, plus both manifests.
- `verification/`: both original independent verification reports, byte-exact.
- `custody/`: the consumed P1 and challenge seed certificates, byte-exact.
- `decision/`: the root stage decision for the challenge, byte-exact.
- `receipts/`: public projections of the six fixture, development and verification resource receipts, and `PROJECTION.json`.
- `ARTIFACTS.sha256.json`: SHA256 and size of every file above. `check_package.py` checks them.

All eight P1 training-count blocks are included, so outsiders can recompute the train-only input normalization.
Every prediction, flag, proposal diagnostic, timing repetition and failed result is included.

## Rebuilding split files

Every original file is stored as ordered parts of at most 6 MiB, so no file exceeds the repository's 10 MiB limit.
Each bundle's `PUBLIC-MANIFEST.json` lists, for every original file name, its SHA256, size and ordered parts (relative file, SHA256, size).
The parts concatenate to the exact original bytes. No array or value is converted.
The checkers verify every part and the whole logical file before NumPy reads it. They never write a rebuilt file inside the checkout.
`ORIGINAL-MANIFEST.json` keeps the original manifest bytes as provenance.

## Model files

The `.pt` files are PyTorch checkpoints. PyTorch checkpoints are pickles, and loading an untrusted pickle can run code.
The public checks only hash these files. They never load them or run inference.
The recorded tensor inspection of the original model stays as evidence. It is not repeated here.

## Public saved-only checks

The checkers recompute error metrics, guard flags, timing ratios, train-only normalization, route selection and both gates from saved arrays.
They do not call a generator, estimator, model, optimizer or random sampler, and they do not retime anything.
They need Python with NumPy and SciPy. Do not run Python with `-O`: the checks rely on assertions.
Run from any directory. Each `--out` must be a new path outside the whole Git checkout; `$(mktemp -d)/…` is safe.

```sh
PYTHON=/absolute/path/to/python3
REPO=/absolute/path/to/public-checkout
"$PYTHON" "$REPO/docs/nv_vector_development_2026-10/check_package.py" --expected-artifacts-sha256 90d07580754aaf95376f433fad84cd074c7b01b394d7eca92b28df80e39bc6b4
SOURCE="$REPO/workers/odmr-edge-ml"
CONFIG="$SOURCE/experiments/vector_direct_screen/config.json"
"$PYTHON" "$SOURCE/scripts/vector_public_saved/verify_p1_saved.py" --bundle "$REPO/docs/nv_vector_development_2026-10/p1" --expected-manifest-sha256 33227a10dbb88865a4947b7eccc89822e49501f7366443150410fc983f13f22a --config "$CONFIG" --out "$(mktemp -d)/p1-check"
"$PYTHON" "$SOURCE/scripts/vector_public_saved/verify_challenge_saved.py" --bundle "$REPO/docs/nv_vector_development_2026-10/challenge" --expected-manifest-sha256 c2008011a48b3ce7af69f2334710317072d54f2a6a7c233d38cf2b15d98dd969 --config "$CONFIG" --out "$(mktemp -d)/challenge-check"
```

**Expected result: both commands exit 0.** Exit 0 means integrity and decision reproduction succeeded. It is not a scientific pass.
The P1 check reproduces the 2× PASS. The challenge check reproduces the 2× FAIL for `neural1` and the accuracy FAIL for `neural0`.
A non-zero exit, a traceback or a missing output file is a checker failure.
Each checker writes `verification.json` in its `--out` directory. Read these fields:
- P1: `passed: true`, `continuation_pass: true`, `classical_candidate: "affine3"`.
- Challenge: `passed: true`, `fastest_adequate_classical: "affine2_f64"`, `neural_routes.neural1.continuation_pass: false`, `neural_routes.neural0.matched_accuracy_pass: false`.

`check_package.py` must print `RESULT: PASS`. It checks file hashes only.

**Path-check disclosure.** The checkers refuse an output path inside the Git checkout. Before publication, root ran their path checks:
the real Git-checkout rejection and the outside-checkout acceptance passed. Two synthetic no-Git fixtures were invalid,
because their scratch folders sat inside another Git checkout, and they failed. The remaining synthetic path fixtures were not run.
The real public checker commands above passed.

The exporter `scripts/vector_public_saved/export_bundle.py` made the split parts from the original files. Public users do not need to run it.
The six files in `workers/odmr-edge-ml/scripts/vector_public_saved/` are byte-identical to the reviewed source; each bundle's `PUBLIC-MANIFEST.json` binds their hashes.

## Provenance

| Item | Value |
|---|---|
| P1 frozen source | odmr-edge-ml `c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e` |
| P1 manifest SHA256 | `98429b2dc9cd4cbcc6854a17aed7405dca31e80f550bc4e0f2f3b61667277430` |
| P1 saved verification SHA256 | `1a14a14badb6a29ad8bfb00b37f2b81ade2f9cbe7fb22a1d3e2c1bd844f23c2e` |
| Challenge frozen source | odmr-edge-ml `869ad0f3c7ea881fd462ef1134a4159d5135bee2` |
| Challenge manifest SHA256 | `f3fd66b295bd1dccee38dc65bb7cfb9369f74c1ea2fb61a0d5b0f7cf60df66fc` |
| Challenge saved verification SHA256 | `047b128f6dbca97959f77dd969c6797aeb9fe90d154fbd9aa00ee7748e9af377` |
| Root decision SHA256 | `894e9d47e97824dac76f8c35e2d87c0932c4b3dc71c1bcf22bb33315cbecfcad` |

The source protocols are in `workers/odmr-edge-ml/experiments/vector_initializer_development/protocol.md` and `workers/odmr-edge-ml/experiments/vector_baseline_challenge/protocol.md`.
Only the six resource receipts change for publication. `receipts/PROJECTION.json` lists the rules and, for each receipt, the original SHA256 and size and the public SHA256.
The rules replace private path prefixes with fixed tokens in every string and object key, and redact `environment.HOME` and `environment.USER`. Every other field is unchanged. The raw receipts are kept privately.
All other files in this package are byte-exact copies.

## Limits

- Synthetic computational development on one host with one GPU. No hardware, bandwidth, energy or measured-sensor result.
- One fixed learned initializer. It does not show that every learned initializer must fail.
- The classical routes are a finite tested set, not the fastest classical implementation available. `tied12` timing is this project's PyTorch implementation; native Gpufit speed was not measured.
- External accuracy, failure and workload requirements are unresolved. No confirmation run was authorized.
