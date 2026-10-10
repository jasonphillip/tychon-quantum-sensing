# vector_v1 anchor ablation (single-spectrum INT8 pipeline)

Date: 2026-10-10 (fp32 rerun). Code: odmr-edge-ml `9b9b67e` (`experiments/vector_v1_anchor_matrix.sh` with `ORACLE=exports/portfolio-n/v3_oracle_fp32/models` and `TRAIN_FLAGS='--no-compile --no-autocast'`). Dataset: `production_50k_v3_vector/dataset.h5`, md5 `4eb3f0437b1efbfed8bfcacced79a14f`, test split n = 5000, not regenerated (`regenerated_dataset = false`). Oracle-trained models: the fp32 retrain from plan N item N4 (30 epochs, oracle anchors, no autocast, no `torch.compile`; training 444 s); the INT8 export of each channel is within 0.2–14 µT of its recorded validation MAE. Coarse_fit-trained models: trained in this run (30 epochs, fp32, no `torch.compile`; training 3076 s on one GPU shared with an embedding service); the INT8 export of each channel is within 0.1 µT of its recorded validation MAE. Evaluations: 2.3–7.6 s each on CPU (TFLite INT8). Whole run 3162 s. GPU used: about 0.86 h in this run plus 0.12 h for the N4 oracle retrain. Cap: none set (estimate was 0.5 GPU-h).

The first version of this table (2026-10-09, kept below under "Superseded") measured models trained with bfloat16 autocast, whose saved checkpoints did not reproduce their own validation error. The tables and the reading in the first three sections are from the fp32 models.

## What is being tested

Each of the 8 per-channel FCNN-v2 models takes two inputs: the spectrum and an "anchor" channel that marks where the resonance line should be. In the original evaluation the anchor comes from the test labels (`_compute_lock_bins` on the true field), so the models are told the answer's neighbourhood, and the test labels also decide which channels and samples enter the BLUE vector solve. This ablation replaces or removes the anchor:

- **oracle** — anchor from the test labels (the original setting, original label-based channel and sample gate).
- **anchor_only / spectrum_only** — the spectrum channel or the anchor channel set to zero (oracle anchors otherwise).
- **noisy_anchor** — oracle anchor plus integer jitter of σ bins.
- **prior** — anchor from the configured bias field alone. This dataset samples field directions uniformly over the sphere (|B| 0.5–5 mT, no bias field), so the prior is the zero-field position: an uninformative anchor.
- **spectrum** — the dip nearest the prior position within ±25 bins (smoothed, low-prominence dip finder), else the prior.
- **coarse_fit** — a matched filter over a grid of candidate fields (2000 directions × 19 magnitudes): the field whose predicted 8-line pattern best correlates with the spectrum gives all 8 anchors. Median error of that field estimate on the test set: 61° in direction (single spectra cannot tell apart field directions related by the NV tetrahedral symmetry) and 1.2 mT in magnitude.

For every non-oracle row, no test-label information reaches the anchors, the channel validity, the BLUE weights or the sample set: a channel is valid when its predicted line position lies inside its window, BLUE weights come from the per-channel validation error stored with the models, and all 5000 test samples are scored. Labels are used only to compute the error afterwards.

## Results (fp32 models; BLUE 3-D residual, µT; n_blue_used = samples scored)

| Model | Anchor source | Condition | Noise (bins) | Selection | n_blue_used | RMS | p50 | p90 | Label |
|---|---|---|---:|---|---:|---:|---:|---:|---|
| oracle-trained (fp32) | oracle | full | 0 | test labels | 3632 | 548 | 85 | 958 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | anchor_only | 0 | test labels | 3632 | 626 | 71 | 1148 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | spectrum_only | 0 | test labels | 3632 | 2733 | 2354 | 4180 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | noisy_anchor | 1 | test labels | 3632 | 539 | 88 | 974 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | noisy_anchor | 2 | test labels | 3632 | 541 | 87 | 978 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | noisy_anchor | 4 | test labels | 3632 | 566 | 86 | 998 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | oracle | noisy_anchor | 8 | test labels | 3632 | 645 | 95 | 1182 | oracle-conditioned (anchors from test labels) |
| oracle-trained (fp32) | prior | full | 0 | model outputs only | 5000 | 3035 | 2760 | 4531 | deployment-available |
| oracle-trained (fp32) | spectrum | full | 0 | model outputs only | 5000 | 3035 | 2761 | 4530 | deployment-available |
| oracle-trained (fp32) | coarse_fit | full | 0 | model outputs only | 4595 | 3296 | 2826 | 5027 | deployment-available |
| coarse_fit-trained (fp32, 30 epochs) | coarse_fit | full | 0 | model outputs only | 5000 | 3051 | 2744 | 4562 | deployment-available |
| coarse_fit-trained (fp32, 30 epochs) | spectrum | full | 0 | model outputs only | 5000 | 3045 | 2749 | 4555 | deployment-available |
| coarse_fit-trained (fp32, 30 epochs) | prior | full | 0 | model outputs only | 5000 | 3045 | 2748 | 4556 | deployment-available |

Reference floors: the RMS field magnitude of the test set is 3035 µT (the error of estimating a zero field), and predicting zero for every channel gives a per-channel MAE of 1372 µT (mean |B·n| over the four NV axes).

## How to read this

- The oracle rows are scored only on the 3632 samples that the label-based gate accepts, so they are optimistic twice: in the anchor and in the sample selection. They are an upper bound that depends on knowing the field in advance, not a measure of field estimation from the spectrum.
- With oracle anchors the fp32 models reach 548 µT RMS (p50 85 µT), against 2216 µT for the bf16 artifacts of the first run. Most of that still comes from the anchor: with a zeroed spectrum the error is 626 µT, and with a zeroed anchor it rises to 2733 µT. Oracle anchors with up to 8 bins of jitter give 539–645 µT.
- Every anchor available at deployment gives no better than estimating a zero field (3035 µT). With the oracle-trained models, prior and spectrum anchors give 3035 µT on all 5000 samples, and coarse_fit anchors give 3296 µT on the 4595 samples where the models put enough lines inside their windows. Models retrained with coarse_fit anchors give 3045–3051 µT on all 5000 samples; their per-channel validation MAE is 1357–1374 µT, the same as predicting zero (1372 µT).
- In this single-spectrum pipeline, then, the field estimate still comes from the oracle anchor, not from the spectrum. The fp32 retrain changes the size of the oracle rows, not this conclusion.

No readiness or deployment statement is made here.

## Superseded: first run with bf16-trained artifacts (2026-10-09)

⊘ superseded 2026-10-10 by the fp32 rerun above. Kept for the record, with its original header, table and reading.

Date: 2026-10-10. Code: odmr-edge-ml `825f401` (branch `portfolio/c2-anchor-ablation`). Dataset: `production_50k_v3_vector/dataset.h5`, md5 `4eb3f0437b1efbfed8bfcacced79a14f`, test split n = 5000; restored from a 2026-05-17 backup, not regenerated (`regenerated_dataset = false`). The oracle row reproduces the recorded result (2216 µT against 2215.9 µT), which confirms it is the same dataset. Wall time: evaluations about 75 s each on CPU (TFLite INT8); retraining 26 min on one GPU shared with another job. Cap: 2 GPU-hours; used about 0.45.


| Model | Anchor source | Condition | Noise (bins) | Selection | n_blue_used | RMS | p50 | p90 | Label |
|---|---|---|---:|---|---:|---:|---:|---:|---|
| oracle-trained (existing) | oracle | full | 0 | test labels | 3632 | 2216 | 1717 | 3566 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | anchor_only | 0 | test labels | 3632 | 2199 | 1736 | 3534 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | spectrum_only | 0 | test labels | 3632 | 2550 | 2097 | 3984 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 1 | test labels | 3632 | 2125 | 1647 | 3432 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 2 | test labels | 3632 | 2033 | 1567 | 3283 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 4 | test labels | 3632 | 2043 | 1538 | 3286 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 8 | test labels | 3632 | 2141 | 1609 | 3469 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | prior | full | 0 | model outputs only | 5000 | 3036 | 2754 | 4541 | deployment-available |
| oracle-trained (existing) | spectrum | full | 0 | model outputs only | 5000 | 3036 | 2756 | 4539 | deployment-available |
| oracle-trained (existing) | coarse_fit | full | 0 | model outputs only | 5000 | 3060 | 2771 | 4537 | deployment-available |
| coarse_fit-trained (30 epochs) | coarse_fit | full | 0 | model outputs only | 5000 | 3048 | 2745 | 4556 | deployment-available |
| coarse_fit-trained (30 epochs) | spectrum | full | 0 | model outputs only | 5000 | 3045 | 2746 | 4561 | deployment-available |
| coarse_fit-trained (30 epochs) | prior | full | 0 | model outputs only | 5000 | 3045 | 2746 | 4561 | deployment-available |

Reading of the first run (bf16 artifacts):


- The oracle rows are scored only on the 3632 samples that the label-based gate accepts, so they are optimistic twice: in the anchor and in the sample selection. They are an upper bound that depends on knowing the field in advance, not a measure of field estimation from the spectrum.
- Within the oracle rows, the models read almost everything from the anchor: with a zeroed spectrum the error (2199 µT) equals the full-input error (2216 µT), and with a zeroed anchor it rises to 2550 µT. Oracle anchors with up to 8 bins of jitter stay at 2033–2141 µT.
- Every anchor available at deployment (prior, spectrum, coarse_fit) gives 3036–3060 µT on all 5000 samples — the same as estimating a zero field (3035 µT). Retraining with coarse_fit anchors does not change this (3045–3048 µT); those models reach a per-channel validation MAE of 1357–1374 µT, the same as predicting zero (1372 µT).
- In this single-spectrum pipeline, then, the field estimate comes from the oracle anchor, not from the spectrum.

### Caveat added 2026-10-10 (plan N, item N3)

The models in this table were trained on the GPU with `torch.compile` and bfloat16 autocast. Their saved checkpoints do not reproduce the validation error recorded during training: reloaded and run on the validation split, the four channels checked give 510–2959 µT against 266–287 µT recorded. The same gap appears in new models trained with the same path (1.7 µT recorded, 883 µT on reload). The cause is the bfloat16 autocast used for GPU training, not `torch.compile`: in a short A/B on the GPU without `torch.compile`, training with autocast recorded 62.4 µT and its checkpoint gave 178.2 µT, while training without autocast recorded and reproduced 58.44 µT. The rows above therefore measure the exported artifacts of that training path, not the network that training reported. Training now has `--no-autocast` (fp32) and `--no-compile` switches and records the exported artifacts' own validation error (`export_val_mae_uT`); see `docs/vector_v1_bias_field.md`.
