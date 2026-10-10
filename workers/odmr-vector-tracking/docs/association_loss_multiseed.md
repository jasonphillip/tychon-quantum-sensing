# Association losses across three seeds (plan N, item N1)

Date: 2026-10-10. Code: odmr-vector-tracking `dfde915` (branch `portfolio/n1-noassoc-multiseed`; the ablation driver now fails on a missing run). Training data: `data/sequence_train_v2` (dataset config hash `3341810ccda0`), not regenerated. Evaluation data: field-cone `data/sequence_eval_fieldcone_v1` (manifest config hash `a39dca58de54`, data_md5 `92dc06692d1975f6fcd101e70cc02d99`; 120 sequences) and dwell `data/sequence_dwell_v1` (config hash `1abb3b21e1f8`, data_md5 `f84d40ea98d173ec135c360909788a2a`; 288 sequences). No row is fitted to the evaluation data.

Recipe for all six runs (matched, as in plan C task C3): gated core, linear association head, shot noise at SNR 10, batch 32, lr 1e-3, `--epochs 800 --stop-epoch 330`, patience 100, validation every 5 epochs. The only difference between arms is the association loss weight: `w_assoc` 1.0 (assoc) or 0.0 (noassoc). Three runs existed (assoc seeds 20260701 and 20260702, noassoc seed 20260701); three are new (assoc 20260703, noassoc 20260702 and 20260703), one per GPU on three workstations. New-run job-hours: 2.69 + 2.64 + 2.65 = 7.98 against a cap of 10 GPU-hours; none was truncated by its timeout. Training commands: `experiments/noassoc_multiseed.sh`. Data behind every number: `docs/association_loss_multiseed_table.json` and `docs/association_loss_multiseed_verdicts.json`.

## Six runs

Field-cone metrics come from `experiments/full_vector_eval.py` (clean rung); dwell metrics are means over the 288 dwell sequences from `experiments/increment8_ablation_eval.py` (clean rung, baseline decode). Identity switches (`idsw_opp_rate`) and collision misassociation (`misassoc_in_coll`) are computed from tracked positions, not from the association head.

| Seed | Arm | Epochs run (best) | Wall (h) | Field-cone RMSE mean / p90 (mT) | Field-cone angular error mean / p90 (°) | Field-cone lock fraction | Field-cone lost (of 120) | Dwell lost rate | Dwell angular p90 (°) | Dwell lock fraction | Dwell identity switches | Dwell collision misassociation |
|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 20260701 | assoc | 330 (230) | 3.17 | 2.565 / 4.331 | 44.8 / 83.4 | 0.100 | 108 | 0.500 | 23.6 | 0.500 | 0.245 | 0.723 |
| 20260701 | noassoc | 330 (310) | 2.87 | 2.110 / 3.702 | 34.4 / 65.2 | 0.100 | 108 | 0.410 | 13.8 | 0.572 | 0.178 | 0.728 |
| 20260702 | assoc | 240 (140) | 1.92 | 2.510 / 3.754 | 44.0 / 72.3 | 0.100 | 108 | 0.510 | 24.8 | 0.480 | 0.356 | 0.754 |
| 20260702 | noassoc | 330 (325) | 2.64 | 2.343 / 3.739 | 40.3 / 66.7 | 0.100 | 108 | 0.500 | 19.4 | 0.497 | 0.123 | 0.726 |
| 20260703 | assoc | 325 (225) | 2.69 | 2.464 / 3.695 | 47.5 / 83.2 | 0.100 | 108 | 0.500 | 28.8 | 0.500 | 0.238 | 0.750 |
| 20260703 | noassoc | 330 (305) | 2.65 | 2.291 / 3.721 | 38.9 / 63.8 | 0.100 | 108 | 0.500 | 19.2 | 0.496 | 0.079 | 0.750 |

## Paired differences within each seed (noassoc minus assoc)

Field-cone, per-sequence paired, 95 % CI from the C3 driver. Dwell, paired over the same 288 sequences with `evaluation/noninferiority.py`: Tango score interval for the binary lost rate, sequence-blocked bootstrap (10,000 resamples) for the other metrics. Negative is better except for lock fraction.

| Seed | Field-cone RMSE (mT) | Field-cone angular error (°) | Dwell angular p90 (°) | Dwell identity switches | Dwell collision misassociation | Dwell lost rate | Dwell lock fraction |
|---|---|---|---|---|---|---|---|
| 20260701 | −0.456 [−0.650, −0.276] | −10.4 [−14.9, −6.2] | −9.8 [−12.5, −7.1] | −0.064 [−0.095, −0.032] | +0.005 [−0.001, +0.011] | −0.090 [−0.129, −0.062] | +0.072 [+0.054, +0.091] |
| 20260702 | −0.167 [−0.276, −0.065] | −3.7 [−6.0, −1.6] | −5.3 [−7.4, −3.4] | −0.235 [−0.275, −0.197] | −0.029 [−0.036, −0.021] | −0.010 [−0.030, +0.003] | +0.017 [+0.006, +0.029] |
| 20260703 | −0.172 [−0.271, −0.078] | −8.6 [−12.1, −5.4] | −9.6 [−12.2, −7.1] | −0.159 [−0.193, −0.127] | +0.000 [−0.000, +0.001] | +0.000 [−0.013, +0.013] | −0.004 [−0.010, +0.000] |
| mean of three | −0.265 | −7.6 | | | | | |

The ablation driver's verdicts against the single baseline run (assoc, seed 20260701), with the proposed margins (not approved by Jason), are in `docs/association_loss_multiseed_verdicts.json`. They mix the arm effect with seed-to-seed spread: the two other assoc seeds are themselves "inferior" to the baseline on dwell angular p90 (+1.2° and +5.2°), so the within-seed pairs above are the cleaner comparison.

## Reading

Removing the association losses improves field accuracy in every seed: all three paired RMSE intervals and all three angular-error intervals lie below zero, so the plan C finding holds across seeds, at a smaller size than seed 20260701 alone suggested (mean −0.27 mT and −7.6° against −0.46 mT and −10.4°). On dwell it does not cost identity: identity switches fall in every seed, collision misassociation changes by +0.005, −0.029 and +0.000 (no consistent cost), and dwell angular p90 improves by 5–10°. The dwell lost rate improves for seed 20260701; for the other two seeds its interval includes zero and crosses the proposed 1 % margin, so neither harm nor non-inferiority is shown there. One caveat on training length: with the matched recipe the assoc runs stop improving earlier (best epochs 230, 140 and 225, and seed 20260702 stopped by patience at 240), while the noassoc runs keep improving to 305–325; the comparison is at the same recipe, not at the same number of useful epochs. The association head itself stays in the model: its output (`assignment`) is computed off the NPU and never feeds the field estimate, so removing the losses changes only an output that no deployed consumer reads; removing the head is an architecture change and out of scope.

## Adoption

Flipping `w_assoc` to 0.0 in `configs/train_increment2a.yaml` is a separate ruling (the repo norm: no default flip inside an increment). Nothing in this item changes the default.
