# vector_v1 with a known bias field (plan N, item N3)

Date: 2026-10-10. Code: nv-sensor-sim `05f7df9` (field sampling `bias_plus_ambient`) and `e88f409` (1 mT config); odmr-edge-ml branch `portfolio/n3-bias-field` (matrix `experiments/vector_v1_bias_matrix.sh`; training fixes `fa6c679`, `6a846e3`; evaluation `ac9baa7`). Datasets regenerated (`regenerated_dataset: true`): `production_50k_v4_bias` (2 mT, md5 `c7ca8ab7b6bcb16b5d0490ffa325876c`, generation 734 s) and `production_50k_v4_bias1mT` (1 mT, md5 `f1a953949bea9d74f291117f69a49c68`, 736 s), each 40000 / 5000 / 5000, seed 4218, 800 points over 2.83–2.91 GHz. GPU job time for the whole item: about 1.2 GPU-hours against a cap of 2. No row is fitted to the test data.

## What the data are

Labels are the total field: B = B0 + ambient, with the known bias B0 along unit(0.2, 0.1, 1.0) and an unknown ambient field drawn uniformly on the sphere with |ambient| ≤ 200 µT. The ambient part is what a sensor has to find: its error equals the total-field error, because B0 is known. Two trivial predictors set the floors on the 5000 test spectra:

| Predictor | RMS (µT) | p50 | p90 |
|---|---:|---:|---:|
| B = 0 (2 mT set / 1 mT set) | 2002.8 / 1006.1 | 2000.1 / 1001.1 | 2089.9 / 1092.5 |
| B = B0, the known bias (both sets; this is the ambient field itself) | 115.2 | 100.3 | 179.3 |

A model is useful only if it beats the second row.

## Two findings that change how the earlier tables read

1. **At 2 mT the lines leave the usable window.** A vector_v1 channel can use a line only within ±35 MHz of 2.87 GHz (|B·n| ≤ 1.25 mT). With B0 = 2 mT along this direction, the four NV axes see 1.47, 1.01, 1.24 and 0.79 mT, so one axis is always outside and one mostly outside, and the 3-D field is underdetermined. The 1 mT set keeps every axis inside (worst case 0.93 mT with ambient). The 2 mT run is reported below as specified.
2. **GPU training with bfloat16 autocast saved checkpoints that did not reproduce their own validation error.** The 2 mT and first 1 mT runs used the default GPU path (`torch.compile`, bfloat16 autocast). Their training logs recorded per-channel validation errors of 1–30 µT, but the saved models gave hundreds of µT on the same validation rows. A short A/B on the GPU isolated the cause: with autocast, 62.4 µT recorded against 178.2 µT from the checkpoint; without autocast, 58.44 µT for both. `torch.compile` alone is not the cause (a no-compile run with autocast still failed). Training now has `--no-autocast` and records the exported float and INT8 models' own validation error (`export_val_mae_uT`); the fp32 rows below agree with it per channel (1.0–2.6 µT recorded against 1.6–4.1 µT exported for the oracle models). The plan C anchor ablation used models from the same path; its table now carries a caveat.

## Results (BLUE 3-D residual on the 5000 test spectra, µT)

Non-oracle rows use no labels for anchors, channel selection, BLUE weights or the sample set (`selection_uses_labels: false`).

| Set | Training | Model | Anchor source | Selection | n_blue_used | RMS | p50 | p90 | Saved model matches its validation |
|---|---|---|---|---|---:|---:|---:|---:|---|
| 1 mT | fp32 | prior-trained | prior (from the known bias) | model outputs only | 5000 | 75.5 | 44.5 | 127.3 | yes |
| 1 mT | fp32 | prior-trained | spectrum | model outputs only | 5000 | 76.4 | 45.1 | 130.1 | yes |
| 1 mT | fp32 | prior-trained | coarse_fit | model outputs only | 5000 | 76.6 | 44.5 | 129.5 | yes |
| 1 mT | fp32 | oracle-trained | oracle (from test labels) | test labels | 5000 | 5.5 | 4.2 | 8.1 | yes |
| 1 mT | fp32 | oracle-trained | prior | model outputs only | 5000 | 115.3 | 100.1 | 179.2 | yes |
| 1 mT | bf16 autocast | prior-trained | prior | model outputs only | 5000 | 406.1 | 398.0 | 467.1 | no |
| 1 mT | bf16 autocast | oracle-trained | oracle | test labels | 5000 | 978.3 | 979.8 | 1000.0 | no |
| 2 mT | bf16 autocast | prior-trained | prior | model outputs only | 4887 | 511.7 | 515.2 | 584.7 | no |
| 2 mT | bf16 autocast | oracle-trained | prior | model outputs only | 0 | — | — | — | no |

Training wall time for the fp32 models: 410 s (prior) and 403 s (oracle) for eight channels at 30 epochs; matrix total 839 s. Result files: `exports/portfolio-n/bias1mT_fp32/`, `bias1mT/` and `bias/` in the odmr-edge-ml working copy.

## Reading

With a known bias, the deployment-available prior anchor works: the prior-trained models estimate the field to 75.5 µT RMS (p50 44.5 µT) from label-free anchors, against 115.2 µT for simply assuming the bias, so they recover about 57 % of the ambient field's variance (error RMS ratio 0.66). The spectrum and coarse-fit anchors give the same result within 1 µT. The label-conditioned oracle row (5.5 µT) is an upper bound, not a deployment number, and an oracle-trained model fed the prior anchor only reproduces the bias (115.3 µT). The ambient error is still large relative to a 200 µT ambient field, the data are simulated with the narrow default line width (see `docs/vector_v1_linewidth_sensitivity.md`), and no INT8 run on the FPGA is part of this table.
