# Integration contract: arms B and C into the deployed scalar path (read-only analysis, 2026-10-14)

> **Correction note (2026-10-14 21:05 EDT, orchestrating session, after a direct source check relayed by Jason's Codex session).** The fabric clamp magnitude is `range * outer_q` with `range = out_max - out_min` (`safety_clamps.cpp:105-107`); the loop writes `out_min = -1`, `out_max = +1` (`v250_pid_loop.c:597-598`), so range = 2 and the OUTER ceiling is 0.045 x 2 x 64 = **5.76 uT-equivalent** with `u_scale = 1/64`, not 2.88 as first written below; the inner clamp may bind tighter. Three statements below are qualified: the clamp binds only for outputs beyond its limit (not "always"); "dominated by quantization noise" is unmeasured until the FP32/INT8 results; a clipped, slew-limited actuator output is not a field estimate, and a replay of shuffled independent spectra tests interface arithmetic under a stated ordering only — closed-loop tracking or stability needs an explicit plant/time-series model. Direct estimation (arm C) can still be useful as a reported measurement without being a drop-in residual controller. The original text is kept and marked.


Paths: ML = <path> (experiments/...);
MONO = <path> PHC = <path> = <path> Evidence grade: file reads only; no run was made.

## 1. Deployed contract today
- Input: NHWC [1,1,100,2]. Channel 0 = spectrum min-max scaled to [-1,1]. Channel 1 = Gaussian anchor at the PID lock bin
  (MONO/workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md:19; ML/experiments/fcnn_v2_int8_float_equivalence.py:62-73, `preprocess`, `flat_to_nhwc`).
  Kit payload is the same array in NCHW element order, int8 (deployed_model_on_kit_2026-10.md:36; KIT/docs/contracts.md:12,42).
- Input quantization: scale 0.007843, zero point -1 (deployed_model_on_kit_2026-10.md:23).
- Output: one value, dB = |B_true| - B_PID in uT. INT8 scale 0.022875, zero point 1 (deployed_model_on_kit_2026-10.md:20,23).
  INT8 range is therefore (-128-1)*0.022875 = -2.95 uT to (127-1)*0.022875 = +2.88 uT (arithmetic from the stored scale; the kit run
  saw outputs "within about -2.95 to +2.88 uT", deployed_model_on_kit_2026-10.md:68). The output tensor cannot represent a larger value.
- No fixed `target_scale` exists in the deployed path: grep found `target_scale` only in KIT/pfkit/pipeline.py:100-126,401,425 and
  KIT skill text, not in ML/src or ML/experiments. Deployed targets are raw uT; the output scale comes from the TFLite converter
  calibration (ML/experiments/scalar_residual_v2.py:216-236). (Absence claim: grep of ML/src and ML/experiments only.)
- Controller use on the kit: v250_pid_loop.c dequantizes `(q - zp) * scale_fix16/65536` (PHC/firmware/linux/v250_pid_loop.c:256-265),
  then `u_ai = nn_out * u_scale` with `DEFAULT_U_SCALE = 1/64` (:62, :672-673), writes u_ai to R_U_AI (:678), pulses the PID core (:679ff).
  Same dequantization formula in MONO/docs/model-to-v250.md:215. Rationale for 1/64: not located.
- Where the limits live (three different places, three different units):
  1. +/-2.25 uT clip: HOST EVALUATION SOFTWARE only. `np.clip(prediction, -DEFAULT_CLAMP_UT, DEFAULT_CLAMP_UT)`
     (MONO/workers/odmr-edge-ml/experiments/deployed_model_on_kit.py:167; ML/experiments/fcnn_v2_int8_float_equivalence.py:31,147-148).
     Not in v250_pid_loop.c (:672-678 applies no clip). Origin: training clip, scalar_residual_v2.py:66,98-108 ("+/-4.5% of 50 uT", :60-66).
  2. Fabric sector clamp: fraction of actuator range, `OUTER_SECTOR_CLAMP_FRACTION = 0.045`, hardcoded constexpr
     (PHC/hls/include/rta_config.hpp:19; PHC/hls/src/safety_clamps.cpp:18-40, :74-120). AXI can only tighten it (safety_clamps.cpp:27-30).
     Applied before the slew limiter and the PID sum (PHC/hls/src/nv_pid.cpp:85-92, :98).
  3. Slew limit: fabric, `MAX_SLEW_PER_CYCLE = 0.001` per PID compute (rta_config.hpp:25; safety_clamps.cpp:126-134; nv_pid.cpp:91).
     (Header comments disagree on clock: 200 MHz in safety_clamps.cpp:7, 125 MHz in rta_config.hpp:22-24. Not needed here.)
- FINDING (⊘ corrected above: range = 2, so 0.045*2*64 = 5.76 uT-equivalent outer ceiling): with u_scale 1/64 the fabric clamp binds at |dB| = 0.045*64 = 2.88 uT (arithmetic), not 2.25 uT. The 2.25 uT figure is the
  host/training clip; the fabric figure equals the INT8 maximum (+2.88) by arithmetic, not by a recorded design link (rationale not located).
- Dashboard/replay expectation: `rung_g_replay.py` writes per-row `nn_u_ai`, `actuator_out`, `clamp_active`, `watchdog_timeout`
  (PHC/tools/rung_g_replay.py:17-23). `clamp_active` is host-derived as `abs(u_ai) > 0.045` (:233).

## 2. Arm B (full residual, unclipped targets)
- Output range: true corrections have median 20.6 uT and 95 % exceed 2.25 uT (deployed_model_on_kit_2026-10.md:68). To hold +/-20 uT in
  INT8 the output scale must rise to about 20/127 = 0.16 uT/level (about 7x coarser than 0.0229; arithmetic). The repo's own note gives
  17.6 nT/level at +/-2.25 and 117.6 nT/level at +/-15 uT (scalar_residual_v2.py:62-65). The scale is set by converter calibration
  (scalar_residual_v2.py:216-236), so a retrained model gets a new output scale automatically; nothing is pinned. Expect clipping risk at
  the INT8 ends if calibration data under-covers the tails: measure it (check b below).
- Does the controller clamp still bind? Only for outputs beyond its limit (⊘ "always" withdrawn; limit = 0.09 in actuator units = 5.76 uT-equivalent, see the correction note). A 20 uT correction gives u_ai = 20/64 = 0.31, above 0.09, so the fabric clamp
  (rta_config.hpp:19) cuts it to 0.045 (= 2.88 uT-equivalent) and the slew limiter then bounds the step (nv_pid.cpp:85-92).
  Arm B's extra range is therefore discarded by the deployed safety chain unless a limit changes. Under the host eval path it is cut to 2.25 (deployed_model_on_kit.py:167).
- Untouched by design: CLAMP_UT 2.25 (scalar_residual_v2.py:66), OUTER_SECTOR_CLAMP_FRACTION (rta_config.hpp:19), MAX_SLEW_PER_CYCLE
  (rta_config.hpp:25), watchdog (rta_config.hpp:29, nv_pid.cpp:69), u_scale (v250_pid_loop.c:62).
- Smallest change set if only the model artifact is swapped: new `.tflite` (export per scalar_residual_v2.py:178-236, ops check
  included) -> new `.vnnx` (MONO/docs/model-to-v250.md:100 flow). No source constant changes. Compare still runs through
  deployed_model_on_kit.py (reads output scale from the model; fcnn_v2_int8_float_equivalence.py:95-96,115). The deployed score of B is
  then B_PID + clip(dB_B, +/-2.25): its value is bounded by the clamp-oracle ceiling (9.35 % on 5,000 rows, 14.23 % on the 512-row subset,
  deployed_model_on_kit_2026-10.md:68). Success of B on the unclipped holdout does not by itself imply improvement under the clip.

## 3. Arm C (direct |B| regression)
- Different interface: the controller consumes a correction (deployed_model_on_kit_2026-10.md:20-21; v250_pid_loop.c:672 feeds
  `nn_out` straight into u_ai). C outputs a magnitude of about 20-70 uT; fed unchanged it would saturate the clamp every row.
- Adapter: dB_hat = B_hat - B_PID, then the existing clip. B_PID is already computed on the host for the anchor channel
  (fcnn_v2_int8_float_equivalence.py:62-69 uses `lock_bins`; `b_pid` is a dataset array, :147-148). The adapter belongs HOST-SIDE, in
  the software between dequantization (v250_pid_loop.c:256-265) and the u_ai write (:672-678), and in the evaluation harness
  `_accuracy` (deployed_model_on_kit.py:164-172) for simulation. It must not live in the NN graph (V250 op whitelist,
  scalar_residual_v2.py:178-185) or in fabric (hardcoded clamp). Neither adapter exists today.
- Blockers: (i) v250_pid_loop.c has no access to B_PID; its `error` is a synthetic ramp or CSV column (:511-514, :665), so a host change
  is needed there (new work, not a constant swap). (ii) INT8 resolution for a 0-70 uT output is about 0.27 uT/level (70/255, arithmetic),
  and the subtraction B_hat - B_PID may then be affected by quantization (⊘ "dominated" withdrawn: unmeasured until the FP32/INT8 results) against a 2.25 uT clip. (iii) The constant predictor at 45.06 uT
  already scores 12.56 uT on the 512 rows (deployed_model_on_kit_2026-10.md:70); C must beat that, not only PID. (iv) C duplicates
  information PID already carries; its useful content is the correction after subtraction, which is arm B's target.

## 4. Simulation-only checks (software; no hardware)
| Check | Exists today? | Where |
|---|---|---|
| (a) float vs INT8 TFLite vs VectorBlox simulator, held-out rows, per-stage MAE and clipped count | Exists | `deployed_model_on_kit.py --prepare/--evaluate` (MONO/workers/odmr-edge-ml/experiments/deployed_model_on_kit.py:68, 180, 299-315); `--prepare` is already run; `--evaluate` reads a run dir. Needs the new `.tflite` and `.vnnx` as stage inputs. Pass bar: INT8 vs simulator 0 LSB (deployed_model_on_kit_2026-10.md:48). Kit stage not run. |
| (b) output saturation count at the new INT8 scale | Partly | `run_tflite` already returns output_at_min/at_max and saturation fraction (fcnn_v2_int8_float_equivalence.py:117-130). Add a gate: saturation fraction below a preset value on holdout and on rows with |dB|>10 uT. Pre-register the threshold. |
| (c) replay stored spectra through host loop with clamp and slew, count clamp binds, field error | NONE | `rung_g_replay.py` replays an error trace; its "hardware" NN mode is a placeholder (:220), and `FakeKit` models the sector clamp but no slew limiter (:126-156). `_accuracy` applies only the 2.25 clip. New script needed: per row, dequantize, `u_ai = dB/64`, clamp at 0.045, slew at 0.001 per compute, count binds, convert back to uT, report field MAE vs PID and vs constant 45.06. Slew caveat: one PID compute per row allows at most 0.001/row (about 0.064 uT-equivalent), so the replay must state its compute-per-row assumption. |
| (d) watchdog and fallback unaffected | By construction | Watchdog gates `ai_active` independent of NN content (nv_pid.cpp:69; rta_config.hpp:29); model swap changes only u_ai values. Cheap test: existing clamp stunt in rung_g_replay (:224-226) with the new model's range (dry-run `--dry-run`, FakeKit). Does not test the real RTL. |

## 5. Blockers and next checks, ranked
1. B can only help inside the clamp. Compute, on holdout, B's final-field MAE after clip(+/-2.25), versus the clamp oracle (9.35 %); if B's clipped MAE does not beat A's, integration is moot.
2. Fabric clamp (5.76 uT-equivalent outer ceiling via range 2 and u_scale 1/64; ⊘ 2.88 corrected) differs from the host clip (2.25 uT). Decide which defines "the deployed limit" before the replay in 4(c); replay both.
3. INT8 output resolution/saturation at the new scale (4b).
4. C needs a host adapter and B_PID access in the loop (section 3); not a model swap.
5. Slew limit makes per-row correction authority tiny at host pacing; 4(c) must model it or say it does not.
6. Write the sim-only replay script (4c) before any kit run.

No change to CLAMP_UT, the slew limit, the kit image or the deployed artifact is part of this contract; a success on the holdout is a prerequisite, not a result of this document.
