# Three engineering decisions and their evidence

This project used coding agents for implementation, review and experiment execution. The records below separate the original problem, the correction, the measured result and the human contribution actually documented. The scalar controller runs on a PolarFire development kit with replayed input; the vector tracker is FP32 simulation work.

## 1. Withdraw a comparison after discovering a broken baseline

**Problem.** A learned tracker appeared to outperform a classical tracker through spectral-line crossings. A July 1, 2026 design review found that the classical detector's fixed threshold, 0.03, exceeded the data's approximately 0.0035–0.0076 line depths. It returned zero peaks, so the benchmark compared a frozen tracker with moving lines.

**Decision and correction.** The headline comparison was withdrawn. Detection thresholds were made data-dependent; pre-crossing lock became an explicit sanity check; undefined angular errors ceased to count as perfect estimates; and a constant-velocity Kalman tracker with Hungarian assignment was added. The corrected results no longer claim that the learned tracker beats competent classical tracking on this sanity set.

**Agent contribution.** The design-review record reports three audit agents, two independently reproducing the key defect. The correction was dispatched to the tracker repository's agent session, and the implementation commit contains the detector, baseline, metric and test changes. That commit carries Jason's git identity and no agent co-author trailer, so the code's authorship rests on the dispatch record, not on the commit metadata.

**Human contribution documented.** The project's case study records Jason commissioning the review and retracting the invalid headline. A private session record, checked on 2026-10-12 and not published, shows his request on 2026-07-01 as a broad instruction to critique all aspects of the tracker work and look for mistakes. The review that found the defect and the dispatch that withdrew the headline are agent-written. The public documents do not provide his firsthand reasoning for the retraction.

**Measured outcome.** On the corrected 16-sequence sanity set, the Kalman baseline had 0/16 lock losses, 1.000 post-crossing association and 0.978 in-collision association. The corrected PID baseline lost lock on 11/16. The learned gated tracker also had 0/16 losses and 1.000 post-crossing association from cold acquisition, but its in-collision association was 0.781. The table states the classical ground-truth initialization versus learned cold acquisition.

**Scope.** Synthetic, easy-crossing benchmark; no demonstrated hardware benefit or dynamic-range extension follows from this comparison.

Evidence: [review](../orchestrator/tvw/audits/design-review-odmr-vector-2026-07-01.md), [correction dispatch](../orchestrator/tvw/audits/dispatch-2a-rebaseline-2026-07-01.md), [corrected results](../workers/odmr-vector-tracking/docs/increment2a_results.md), [human-role account](case-study.md#what-the-reviews-caught), [implementation commit](https://github.com/jasonphillip/tychon-quantum-sensing/commit/154f2c9b502f5a63d87377b51aa766d39b78fec0).

## 2. Test actual fallback rather than count watchdog trips

**Problem.** A measured watchdog trip did not establish that the controller produced a PID-only value. October 9, 2026 board tests distinguished a timeout visible at a controller start from a timeout that cleared before the next start. The short-timeout case fell back 0/20 times; the control-process pause case had 0/10 successful fallbacks after resume.

**Decision and correction.** The test report records Jason choosing a software correction. Before inference and during inference polling, the firmware checks the timeout; when armed and high, it writes the current inputs and forces one controller start before inference can clear the signal. It re-arms after a low reading.

**Agent contribution.** The firmware, test tooling and evidence-capture changes are in a commit co-authored by Claude. The shared trip-start helper and a host unit test are present. The board evidence includes commands, binary hashes, control logs and the corrected raw-check summaries.

**Human contribution documented.** The report explicitly attributes the software choice to Jason. A private session record, checked on 2026-10-12 and not published, shows him selecting the software fix from the options the agent listed, without a stated reason. No published excerpt shows his comparison of a software rule with a sticky hardware trip bit.

**Measured outcome.** With the correction, the short-timeout case fell back 20/20 times, with 908–998 recorded PID-only updates. After a one-second process pause, 10/10 cases were PID-only after resume; nine had a forced start after resume and one was already PID-only before the pause.

**Scope.** This is register-level observation on one development kit. No physical actuator or live diamond sensor is demonstrated by these tests. A processor that remains frozen still receives no fallback output until it resumes. Recovery steps of 0.010–0.013 (medians; the raw check records maxima up to 0.065) remain above the 0.001 slew limit; 11 of 104 forced starts also showed discontinuities in limiting or repeated-trip conditions. The correction closes the observed short-timeout hole, not every safety obligation.

Evidence: [test plan and before/after results](../workers/polarfire-hybrid-control/docs/watchdog_fallback_test_plan.md), [before summary](../workers/polarfire-hybrid-control/libero/reports/2026-10-09-watchdog-fallback/rawcheck_summary.txt), [after summary](../workers/polarfire-hybrid-control/libero/reports/2026-10-09-trip-start-fix/rawcheck_summary.txt), [helper](../workers/polarfire-hybrid-control/firmware/linux/wd_trip_start.h), [implementation commit](https://github.com/jasonphillip/tychon-quantum-sensing/commit/b9e424aa1fafaea4cf3376dabafb2c4f8d9269e3).

## 3. Remove an objective that hurt the outcome it was meant to support

**Problem.** Association losses were intended to help a vector tracker preserve line identity. The first ablation found better field estimates when those losses were removed, but one run did not establish robustness across training seeds.

**Decision and correction.** Six matched runs compared association-loss weights of 1.0 and 0.0 across three seeds. The repository subsequently set `w_assoc: 0.0` in its training configuration. The association head remains in the architecture; this change removes its loss terms rather than removing the head or replacing deployed checkpoints.

**Agent contribution.** The records contain the experiment driver, training commands, per-run results and paired comparisons. Three new runs used 7.98 GPU-hours against a ten-hour cap. The later configuration-change commit is co-authored by Claude.

**Human contribution documented.** Adoption is visible in the configuration and commit. A private session record, checked on 2026-10-12 and not published, shows the ablation and the three-seed rerun proposed within the agent-run planning workflow, and Jason approving the default change on 2026-10-10 by accepting a plan whose first item turned the association losses off. The public logs do not record who chose the acceptance criteria. His own reasons require his firsthand account.

**Measured outcome.** In each within-seed comparison, field-cone RMSE fell: −0.456, −0.167 and −0.172 mT. Mean angular error fell by 10.4°, 3.7° and 8.6°. All six corresponding 95% sequence-bootstrap intervals were below zero. Dwell identity-switch rates also fell in all three seeds.

**Scope.** FP32 synthetic evaluation only. Field-cone lock remained about 0.10, with 108/120 sequences lost in every arm. The intervals describe sequence variation conditional on each trained run, not an exhaustive distribution over training seeds. Validation-based checkpoint selection and training lengths differ between arms. No INT8 export or on-target execution is shown for this tracker, and the default change does not retrain existing checkpoints.

Evidence: [initial ablation](../workers/odmr-vector-tracking/docs/full_vector_metric_and_association_ablation.md), [three-seed study](../workers/odmr-vector-tracking/docs/association_loss_multiseed.md), [result table](../workers/odmr-vector-tracking/docs/association_loss_multiseed_table.json), [training commands](../workers/odmr-vector-tracking/experiments/noassoc_multiseed.sh), [current configuration](../workers/odmr-vector-tracking/configs/train_increment2a.yaml), [adoption commit](https://github.com/jasonphillip/tychon-quantum-sensing/commit/755c49e09c47f1d92c47199d46302d5ee40bb11d).
