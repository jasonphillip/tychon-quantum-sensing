# Vector inversion speed, 2026-10-15: a 2× pass, then a stronger classical baseline removed it


Status: **the registered 2× continuation gate FAILED against the stronger baseline.** The learned initializer stops here.
No practical adoption, no novel algorithm, and no hardware result is claimed. The overall goal is not met.
Both comparisons below were fixed before their results. Both are synthetic computational development on one machine.

## Result in one table

| Comparison | Fastest adequate classical route | Neural route | Speed at batch 4096 | Accuracy gate | 2× gate |
|---|---|---|---:|---|---|
| P1, original development comparison | `affine3` (affine start, three float64 LM steps) | `neural1` | 2.228945× | pass | **PASS** |
| Baseline challenge, fresh data | `affine2_f64` (affine start, two float64 LM steps) | `neural1` (unchanged P1 weights) | 1.591126× | pass | **FAIL** |
| Baseline challenge, fresh data | `affine2_f64` | `neural0` (no refinement step) | 0.063387× | **FAIL** (810 fallbacks) | **FAIL** |

The P1 pass is kept as recorded. P1's classical routes did not include the fastest adequate route that the challenge later found.
**Same-data control:** the challenge also reran `affine3` and `neural1` on its own 4,096 fresh cases. That gave 2.223868×, close to P1's 2.228945×.
So the drop to 1.591126× comes from the stronger classical route (`affine2_f64`), not from the new random sample.
P1 had omitted two-step and mixed-precision classical refinement. The challenge added those routes and changed nothing else.

## Question

Can one compact learned initializer cut the time to invert eight-line NV spectra to a vector field, at matched accuracy?
Can a simpler classical refinement give the same benefit?
Neural inversion speedup in general is prior art. This work tests one matched-device comparison with physical refinement and counted fallback.
The motivating workload is offline processing of large current maps. No instrument deadline is asserted.

## P1: original development comparison (PASS, preserved)

- **Data:** 32,768 fresh training spectra and 2,048 fresh validation spectra, one Poisson observation each. Eight-line Hamiltonian, 512 bins, known orientation and bias, 2 million photons per bin.
- **Model:** one MLP, 512→256→128→64→8 (173,000 parameters), float32, exactly 20 epochs. No architecture search, checkpoint selection or seed sweep.
- **Routes:** full multistart LM; affine start plus 1, 3 or 5 LM steps; the tied-line comparator `tied12`; and the learned start plus one LM step (`neural1`).
- **Guard:** every route passes the same float64 observed-data guard. Every rejected estimate gets the full LM fallback, and its time is counted.
- **Accuracy:** a classical route is adequate when its mean and p95 vector error are each ≤ 1.05× full LM, with no more rejections. The neural route must be ≤ 1.05× the best adequate classical value on each.
- **Speed gate:** ≥ 2× the fastest adequate classical route, host-to-host median at batch 4096, with a finite setup break-even.

| Route (2,048 validation spectra) | Mean error (µT) | p95 error (µT) | Fallbacks |
|---|---:|---:|---:|
| Full LM | 1.92708 | 4.58096 | 2048 (every case is a full-LM solve) |
| `affine3` | 1.92876 | 4.58259 | 0 |
| `affine5` | 1.92693 | 4.58490 | 0 |
| `tied12` | 1.94151 | 4.64192 | 13 |
| `neural1` | 1.94739 | 4.60925 | 0 |


**Speed at batch 4096:** `affine3` 0.267792 s, `neural1` 0.120143 s, speedup 2.228945×. Saved 36.05 s per million spectra; break-even after 439,901 spectra.
Batch 1 (1.866×) and batch 64 (1.845×) were diagnostics only. They could not change the frozen batch-4096 gate.

**The larger gain was classical.** `affine3` was 34.80× faster than full LM and 20.49× faster than `tied12`, at matched accuracy.
That is a classical engineering result, not a neural win. P1 records `neural_win: false` and `algorithmic_novelty_claim: false` for it.

## Baseline challenge: stronger classical routes, fresh data (FAIL)

P1's margin over 2× was small (about 2.23×). The challenge asked whether it survives cheaper classical refinement.
- **New routes:** `affine2_f64`, `affine2_f32`, `affine3_f32` (two or three LM steps, float64 or float32), and `neural0` (the P1 network with no refinement step).
- **Unchanged:** the P1 weights, input scaling, guard, fallback, accuracy rules and the 2× gate. No training, retuning, threshold change or weight selection.
- **Data:** 4,096 fresh spectra with root-issued seeds never used before. No P0 or P1 data was read.
- **Timing:** one warmup, then three repetitions per route, in a fixed route order. Batch 4096, chunk 1024, one process.

| Route (4,096 fresh spectra) | Mean error (µT) | p95 error (µT) | Fallbacks | Adequate or matched |
|---|---:|---:|---:|---|
| Full LM | 1.94439 | 4.92362 | 4096 (every case is a full-LM solve) | reference |
| `affine3` | 1.94339 | 4.90390 | 0 | adequate |
| `affine2_f64` | 1.95420 | 4.91446 | 0 | adequate, **fastest** |
| `affine2_f32` | 1.95397 | 4.92984 | 26 | adequate |
| `affine3_f32` | 1.94400 | 4.91294 | 20 | adequate |
| `tied12` | 1.95370 | 4.94107 | 34 | adequate |
| `neural1` | 1.94979 | 4.95527 | 0 | accuracy matched |
| `neural0` | 2.66322 | 6.54592 | 810 | **accuracy failed** |

**Speed:** `affine2_f64` took 46.38 s per million spectra and `neural1` 29.15 s. The speedup is 1.591126×, below the registered 2×.

| Same 4,096 challenge cases, batch 4096 | Median host-to-host time (s) | `neural1` speedup over it |
|---|---:|---:|
| `affine3` (P1's selected classical route) | 0.265512 | 2.223868× |
| `affine2_f64` (fastest adequate route in the challenge) | 0.189968 | 1.591126× |
| `neural1` | 0.119392 | — |

Against `affine3`, `neural1` keeps about the same margin as in P1. The two-step route `affine2_f64` removes most of it.
`neural1` saves 17.23 s per million spectra. Counting P1's generation, training and setup, it breaks even only after 920,704 spectra.
`neural0` was 0.063387× (about 16× slower), because 810 of its 4,096 estimates were rejected and fell back to full LM.

**Decision:** `FAIL_REGISTERED_NEURAL_CONTINUATION_GATE`. No retuning, retraining, new variants or confirmation run follows for this candidate.

## What this shows

- A learned initializer can match accuracy here, but a two-step classical refinement removes most of its speed margin.
- The P1 2× pass depended on the classical routes P1 included. It does not survive the stronger baseline.
- Short classical refinement from an affine start is the strongest result in this lane. It is a classical engineering result with no novelty claim.
- No hardware, bandwidth, energy, measured-sensor or population claim. External accuracy and workload requirements stay unresolved.

## Evidence and checks

The [evidence package](nv_vector_development_2026-10/README.md) holds both runs' saved arrays, model bytes, manifests, receipts and the root decision.
Files larger than 10 MiB are split into hashed parts of at most 10 MiB. The package explains how to rebuild them byte-exactly.

Two public checkers recompute both decisions from the saved arrays. They need Python with NumPy and SciPy only: no Torch, CUDA or private files.
They never load the model, run inference, call the forward model or retime anything.
**Exit 0 means the bytes and the recorded decisions reproduce. It does not mean the gate passed:** the challenge checker exits 0 when it reproduces the 2× FAIL.
Commands and expected output are in the [package README](nv_vector_development_2026-10/README.md#public-saved-only-checks).

## Provenance

- P1 source frozen at odmr-edge-ml commit `c4c59ad97b78b43c6e4c936e9ff89e45b8efaf2e`; manifest SHA256 `98429b2dc9cd4cbcc6854a17aed7405dca31e80f550bc4e0f2f3b61667277430`.
- Challenge source frozen at `869ad0f3c7ea881fd462ef1134a4159d5135bee2`; manifest SHA256 `f3fd66b295bd1dccee38dc65bb7cfb9369f74c1ea2fb61a0d5b0f7cf60df66fc`.
- Saved verification SHA256: P1 `1a14a14badb6a29ad8bfb00b37f2b81ade2f9cbe7fb22a1d3e2c1bd844f23c2e`; challenge `047b128f6dbca97959f77dd969c6797aeb9fe90d154fbd9aa00ee7748e9af377`.
- Root decision SHA256 `894e9d47e97824dac76f8c35e2d87c0932c4b3dc71c1bcf22bb33315cbecfcad`.
- The consumed seed certificates, both original verification reports, the root decision and public projections of the six resource receipts are in the [evidence package](nv_vector_development_2026-10/README.md#layout).

Earlier results are unchanged: the [advantage search](nv_advantage_search_2026-10.md), the [measured-data pilots](../workers/odmr-edge-ml/docs/measured_pilots_2026-10.md) and the [NV contribution screen](../workers/odmr-edge-ml/docs/nv_contribution_screen_2026-10.md).
