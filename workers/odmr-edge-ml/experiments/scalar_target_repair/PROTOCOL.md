# Scalar target repair: controlled synthetic experiment

Opened: 2026-10-14. This protocol is written before training.

## Question and ownership

Does replacing clipped training targets improve total magnetic-field magnitude estimates?
Codex owns training and evaluation. The coordinating Spark2 session owns the fresh holdout and integration.
This is a synthetic estimator experiment. It does not change an actuator or deployed artifact.
The runner uses Python, NumPy, h5py, and PyTorch. Paths are arguments; CUDA is optional.
The recorded experiment runs on Spark2, using existing packages and no cloud spend.

## Data access

- Training: original production_50k_v2_aic train, 40,000 rows.
- Model selection: original validation, 5,000 rows.
- Original test: 5,000 previously seen rows, exploratory evaluation only after checkpoint freeze.
- Fresh holdout: generated and sealed independently by the coordinating session.
- No fresh holdout access until all checkpoint hashes and choices are sent to the coordinator.
- No vector comparison validation or final data access.
- Train and validation labels must match the HDF5 vector norms and residual identities.

## Fixed arms

1. A_clipped: target = clip(true magnitude - PID estimate, -2.25, +2.25) microtesla.
2. B_full_residual: target = true magnitude - PID estimate, without clipping.
3. C_direct: target = true magnitude, without clipping. This uses the same spectral and anchor inputs.

All arms use canonical OdmrFCNNv2, channels [8,16,24], learnable anchor sigma initialized at 1.5.
Inputs use the original per-spectrum [-1,1] normalization and PID lock bin.
All arms retain canonical symmetric per-tensor INT8 quantization-aware training, with FP32 arithmetic.
No autocast, torch.compile, TF32, or hyperparameter search.
Seeds: 42, 20261014, 20261015. Each arm resets initialization and batch order to the same seed.
AdamW: learning rate 0.001, weight decay 0.001, betas (0.9,0.999).
Huber delta: 10 microtesla. Gradient norm cap: 10. Batch size: 64.
Cosine schedule over the fixed epoch count, minimum learning rate 0.00001.

## Compute and stopping

Global training wall-clock cap: 3,600 seconds, including the timing pilot.
Before any validation result, run 200 training batches for timing only. Discard that model.
Choose the largest common epoch count from [10,20,40,60,100] predicted to fit nine runs within 3,000 seconds.
Estimate from the last 100 timing batches, multiplied by 1.3 for validation and serialization overhead.
If ten epochs for all nine runs exceed that allowance, stop and report the compute limitation.
Write the resulting epoch count and estimate before training the experiment arms.
Run seeds in order and arms A,B,C within each seed. Do not adapt based on accuracy.
If the global cap is hit, retain partial artifacts and mark the primary study incomplete.
No data-dependent early stopping and no extra tuning after seeing test results.

## Selection and reproducibility

Evaluate every max(1, epochs // 10) epochs and at the final epoch.
For each arm and seed, select the checkpoint with lowest validation total-field MAE.
Use unbounded clean FP32 predictions extracted from the QAT weights for this selection.
Break exact ties in favor of the earlier epoch.
Residual arms add the predicted correction to PID; the direct arm predicts magnitude directly.
Selection is identical across arms. A is a matched control, not an exact replay of historical training.
Shared changes from the historical recipe are FP32, explicit pre-initialization seeding,
validation against full magnitude, and the timing-selected common epoch count.
Save every epoch's training loss, validation metrics, selected checkpoints, source hashes,
initialization and batch-order hashes, input hashes, software versions, and elapsed time.
Reload each saved clean checkpoint and reproduce its saved validation predictions and MAE.
Freeze all nine choices and hashes before any test or holdout evaluation.

## Metrics and decision

Primary metric: total-field MAE, averaged over the three fixed training seeds for each arm.
Report each seed too; do not select the best seed on test data.
For residual arms, residual error against the full residual equals final magnitude error.
Report RMSE, median and p90 absolute error, signed bias, and magnitude-bin MAE.
Report unbounded predictions and PID + clip(predicted field - PID, +/-2.25 microtesla) separately.
For the direct arm the latter is a hypothetical bounded correction, not its direct output.
Include PID, training mean, and training median constant baselines on every cohort.
Constants use training labels only.

On the fresh holdout, compute paired row-bootstrap 95% intervals (10,000 resamples,
seed 20261014) for mean per-row absolute-error differences B-A, B-mean, C-B, and C-mean.
Average each row's absolute errors across training seeds before bootstrapping.
These intervals quantify sampled-row uncertainty, not simulator validity or training-seed uncertainty.
Report seed variation separately.
B demonstrates an improvement if its MAE beats A and the training-mean constant,
and both upper confidence bounds are below zero. Report effect sizes regardless of the outcome.
C has the analogous secondary comparison against B and the training-mean constant.

Optional INT8 CPU conversion uses the fixed canonical export path and the first 1,000 training rows.
Do not change a candidate or calibration after holdout results. FP32 and INT8 results remain separate.
No claim of real-sensor accuracy, safe wider control authority, or state-of-the-art performance follows.

## Deliverables

Protocol, runner source, frozen choices, checkpoints, per-row predictions, machine-readable metrics,
source/data hashes, reload verification, and a short report. Integration belongs to the coordinating session.
