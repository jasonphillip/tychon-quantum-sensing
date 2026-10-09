# vector_v1 anchor ablation (single-spectrum INT8 pipeline)

Date: 2026-10-09. Code: odmr-edge-ml `c437024` (branch `portfolio/c2-anchor-ablation`). Dataset: `production_50k_v3_vector/dataset.h5`, md5 `4eb3f0437b1efbfed8bfcacced79a14f`, test split n = 5000; restored from a 2026-05-17 backup, not regenerated (`regenerated_dataset = false`). The oracle row reproduces the recorded result (2216 µT against 2215.9 µT), which confirms it is the same dataset. Wall time: evaluations about 75 s each on CPU (TFLite INT8); retraining 26 min on one GPU shared with another job. Cap: 2 GPU-hours; used about 0.45.

## What is being tested

Each of the 8 per-channel FCNN-v2 models takes two inputs: the spectrum and an "anchor" channel that marks where the resonance line should be. In the original evaluation the anchor comes from the test labels (`_compute_lock_bins` on the true field), so the models are told the answer's neighbourhood. This ablation replaces or removes that anchor:

- **oracle** — anchor from the test labels (the original setting).
- **anchor_only / spectrum_only** — the spectrum channel or the anchor channel set to zero.
- **noisy_anchor** — oracle anchor plus integer jitter of σ bins.
- **prior** — anchor from the configured bias field alone. This dataset samples field directions uniformly over the sphere (|B| 0.5–5 mT, no bias field), so the prior is the zero-field position: an uninformative anchor.
- **spectrum** — the dip nearest the prior position within ±25 bins (smoothed, low-prominence dip finder), else the prior.
- **coarse_fit** — a matched filter over a grid of candidate fields (2000 directions × 19 magnitudes): the field whose predicted 8-line pattern best correlates with the spectrum gives all 8 anchors. Median error of that field estimate on the test set: 61° in direction (single spectra cannot tell apart field directions related by the NV tetrahedral symmetry) and 1.2 mT in magnitude.

## Results (BLUE 3-D residual, µT; n_blue_used = samples that pass the BLUE gate)

| Model | Anchor source | Condition | Noise (bins) | n_blue_used | RMS | p50 | p90 | Label |
|---|---|---|---:|---:|---:|---:|---:|---|
| oracle-trained (existing) | oracle | full | 0 | 3632 | 2216 | 1717 | 3566 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | anchor_only | 0 | 3632 | 2199 | 1736 | 3534 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | spectrum_only | 0 | 3632 | 2550 | 2097 | 3984 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 1 | 3632 | 2125 | 1647 | 3432 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 2 | 3632 | 2033 | 1567 | 3283 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 4 | 3632 | 2043 | 1538 | 3286 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | oracle | noisy_anchor | 8 | 3632 | 2141 | 1609 | 3469 | oracle-conditioned (anchors from test labels) |
| oracle-trained (existing) | prior | full | 0 | 3632 | 2549 | 2101 | 3987 | deployment-available |
| oracle-trained (existing) | spectrum | full | 0 | 3632 | 2549 | 2101 | 3987 | deployment-available |
| oracle-trained (existing) | coarse_fit | full | 0 | 3632 | 2576 | 2124 | 4056 | deployment-available |
| coarse_fit-trained (30 epochs) | coarse_fit | full | 0 | 3632 | 2563 | 2115 | 4018 | deployment-available |
| coarse_fit-trained (30 epochs) | spectrum | full | 0 | 3632 | 2560 | 2118 | 4008 | deployment-available |
| coarse_fit-trained (30 epochs) | prior | full | 0 | 3632 | 2560 | 2117 | 4007 | deployment-available |

Reference floors: the RMS field magnitude of the test set is 3035 µT, and predicting zero for every channel gives a per-channel MAE of 1372 µT (mean |B·n| over the four NV axes).

## How to read this

- The models read almost everything from the anchor. With the oracle anchor and a zeroed spectrum the error (2199 µT) equals the full-input error (2216 µT). With the spectrum and a zeroed anchor it rises to 2550 µT.
- Oracle anchors with up to 8 bins of jitter stay at 2033–2141 µT, slightly better than the exact oracle anchor.
- Every anchor available at deployment (prior, spectrum, coarse_fit) gives 2549–2576 µT, the same as the zeroed-anchor condition. None of them carries usable information about the line positions.
- Retraining with coarse_fit anchors does not change this. The retrained models reach a per-channel validation MAE of 1357–1374 µT, the same as predicting zero (1372 µT), and the BLUE error stays at 2560–2563 µT.
- The oracle-conditioned rows are therefore an upper bound that depends on knowing the field in advance. They are not a measure of field estimation from the spectrum.

No readiness or deployment statement is made here.
