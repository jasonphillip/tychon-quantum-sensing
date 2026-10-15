# Scalar repair cycle protocol

Status: implementation candidate, awaiting independent review and Freeze 1.
Scope: synthetic single-NV-orientation magnitude prediction on the original 100-point grid.
No training, calibration, hardware deployment, or consumed-final scoring is permitted.

## Frozen candidate mapping

Identity is an unchanged-input neural control. It is not eligible for repair selection.
Edge OLS fits bins 0–19 and 80–99, subtracts slope only, and uses the unchanged PID lock.
Joint fit subtracts its fitted slope and uses the nearest bin to the fitted pair midpoint.
Each policy applies identically to seeds 42, 20261014, and 20261015, in FP32 and existing INT8.
All repaired predictors share joint-fit quality and ambiguity flags. Hard invalid inputs use the training median.
An ambiguous but otherwise valid estimate may remain a prior-aided prediction. It never counts as reliable sensing.

The classical candidates are the bounded joint fit with the declared-prior median, and a 64-point conditional likelihood estimate.
Both assume uniform magnitude on [20,70] microtesla and isotropic direction.
The likelihood grid fixes center and width at the robust-fit estimates.
It refits the affine baseline and nonnegative dip depths at each splitting.
It integrates likelihood over axial projection, then applies the magnitude/direction prior.
It does not marginalize center/width uncertainty. Its intervals are uncalibrated and support no coverage claim.

## Exact fit and rejection choices

Coordinates are MHz relative to the sweep midpoint. The forward model uses two shared-width Lorentzian dips.
Parameters: baseline [0.5,1.5], slope [-0.002,0.002] per MHz, midpoint [-10,10] MHz,
splitting [0,4.20] MHz, each dip depth [0,0.10], and HWHM [0.30,6.00] MHz.
The projection conversion uses gamma = 0.028035 MHz per microtesla.
The 4.20 MHz optimizer bound permits detection of estimates outside the declared 70 microtesla support.

Four deterministic starts use prominence-based centers plus midpoint/splitting/width alternatives.
Each start has at most 200 least-squares function evaluations.
The loss is soft-L1, scaled by input-only edge-difference MAD noise.
The noise floor is 0.00001 normalized fluorescence.
Optimizer ftol, xtol and gtol are all 1e-8.

Hard rejection conditions:
- Invalid shape/grid or nonfinite spectrum.
- Detrended peak-to-peak <= max(1e-9, three noise standard deviations).
- No finite fit, or the selected optimizer reports failure.
- Baseline, slope, midpoint or width lies within 0.01% of an optimizer bound.
- A component depth reaches 99.99% of its upper bound.
- Axial projection lies outside [0,70] microtesla.
- RMS residual exceeds max(three noise standard deviations, 15% of fitted dip depth).
- Fitted dip depth is less than five noise standard deviations.

Ambiguity conditions:
- Splitting is below max(one frequency-bin spacing, fitted HWHM).
- Either fitted component depth is below three noise standard deviations.

Ambiguity alone does not trigger fallback.
Nonfinite or out-of-support [20,70] neural magnitude predictions trigger fallback.
The fixed fallback is the original training median, 44.90404360960018 microtesla.
Raw estimates and reason flags are retained. Every fallback remains in all-row metrics.
The original two-line comparator retains its optimizer but uses the same declared-support rejection and median fallback.
Unchanged PID and direct-model controls remain descriptive; they cannot win repair selection.

## Data and custody

Dev: 256 independent fields. Validation: 512. Final: 1,024.
Each partition has the same seven original stress conditions, paired by field and nuisance-group identity.
Consumed target-repair and stress final sets remain retired.
All data paths are explicit command arguments. Payload hashes, seal permissions, grid, field identities,
sample seeds and paired truth identities are checked.
Analysis seed 202610152001 belongs to the reserved analysis namespace; the custodian checks data non-overlap.

Freeze 1 records every experiment source, relevant imported source, protocol, numerical dependency version,
frozen model identity, accepted generator/distribution contract, and the one authorized evaluation-output root.
Validation needs a pinned JSON release and its pinned Freeze 1 receipt.
Freeze 2 additionally binds the passing validation summary and selected policies.
Final needs a pinned JSON release, Freeze 2, and the custodian's data-root exclusive-access-receipt.json.
The evaluator creates a separate exclusive local access receipt before its first payload hash.
Outputs must use the frozen evaluation root. A second campaign is refused, including with a different output argument.
Accessed invalid campaigns retire their partition; no automatic rerun is permitted.

Custodian release JSON schema:
```json
{
  "schema": 1,
  "partition": "val",
  "approved": true,
  "data_manifest_sha256": "SHA256",
  "freeze_receipt_sha256": "SHA256",
  "gate_document_sha256": "SHA256",
  "exclusive_access_receipt_sha256": "SHA256"
}
```
The access receipt repeats schema, partition, data_manifest_sha256 and freeze_receipt_sha256.
Its status is authorized or in_progress. The gate document is the custodian's FREEZE1.md or FREEZE2.md.
CLI arguments pin both the release and freeze hashes. Filename existence alone grants no access.

## Selection and acceptance

Primary neural implementation: INT8. Primary claim route: accuracy.
FP32, speed and quantization results remain secondary.
Only clean and realistic_anchor are primary. Secondary conditions cannot rescue failure.

Prediction gate: upper paired 95% MAE-difference bound below -0.5 microtesla versus each original training constant,
and p90 absolute error <=25 microtesla, in both primary conditions.
Reliability additionally requires >=95% unambiguous, nonfallback valid estimates in both.
For a blanket three-seed reliability claim, every seed must also pass the prediction gate.

Classical selection uses lowest all-row realistic-anchor MAE among both complete frozen classical candidates.
Neural selection uses lowest all-row realistic-anchor mean seed MAE among the two repaired INT8 policies.
Differences below 0.1 microtesla are ties: prefer lower fallback fraction, then lower complete-pipeline median latency,
then lexical method name. Selection does not require a classical win.
Proceed to final only if at least one selected repaired method passes the prediction gate in both primary conditions.
If only an unselected method passes, select among passing methods first. Preserve all candidate results.

Final neural accuracy advantage requires the selected neural policy to pass the prediction gate,
and its upper paired MAE-difference bound versus the selected classical reference below -0.5 microtesla in both.
INT8 preservation uses the paired upper bound versus corresponding FP32 <=0.5 microtesla, reported per seed.
If neither selected method passes, stop. If estimates improve but ambiguity remains, report prior-aided prediction only.
No final-size increase or post-validation tuning is permitted.

Bootstrap 10,000 draws with seed 202610152001. Resample independent nuisance groups, retaining their paired rows.
For model-family errors, average the three seed losses per field; do not ensemble predictions.
Report per-seed gates and mean-loss gates separately.
Intervals condition on this generator and these fixed checkpoints.

## Timing and compute

Use one thread and batch size one. Pause competing numerical workers before validation/final timing.
Per condition, time the first 16 retained inputs, with the first four as warm-up.
Time the complete path, including common quality fit, preprocessing, inference/conversion and fallback.
Record median and p95, count, thread setting and fallback behavior.
This is CPU timing; it supports no FPGA timing claim.

Cycle cap: four CPU-hours, two cumulative numerical job wall-hours, four workers maximum, 8 GiB actual memory.
Reserve two CPU-hours for final, capped at thirty minutes wall.
Every numerical job appends a compute receipt with command, wall/CPU time, peak memory and status.
This initial implementation deliverable uses at most 0.5 CPU-hours and fifteen numerical wall-minutes.
Stop on hash drift, leakage, overlap, missing rows, cap exhaustion or a failed scientific gate.
A failed operation gets one changed-approach retry; accessed final data are never reused.
