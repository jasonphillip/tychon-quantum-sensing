# Orchestration and publication: conversation selections

These exchanges show protocol checks, corrections, and publication decisions. Quotes retain the source wording and spelling; […] marks cuts. Commentary, context, and outcomes are editorial summaries. Relayed worker reports remain attributed to the worker, not to Jason.

Sources: private export, not published. The Codex export records gpt-6-astra. The quoted Claude Code replies record claude-fable-5-1 in their turn headers. For the relayed Codex worker reports, model version not recorded in the export.

<a id="c1"></a>
## C1. Verify the protocol before the experiments

**Date and context.** October 14, 2026. Codex proposed checking the protocol amendments; Jason told it to act and pasted its sentence.

**Codex — previous reply**

> My immediate priority would be verifying those protocol amendments before the comparison experiments begin. Otherwise, later results could require reruns.

**Jason — instruction followed by Codex's sentence**

> do this My immediate priority would be verifying those protocol amendments before the comparison experiments begin. Otherwise, later results could require reruns.

**Codex**

> **I checked and found a real gap:** the plan contained the amendments, but the active protocol and generator still used the old rules.
>
> I sent the correction directly. **The main session acknowledged it and updated the plan to hold Tasks 4–8** until it verifies:
>
> - Separate development, validation, and final datasets.
> - Symmetric decision rules with confidence intervals.
> - A fresh final dataset after result-driven changes, including v3 if v2 was already used.
> - Committed amendments, hash checks, and the protocol review.
>
> The independent kit work can continue.
>
> **The hold is recorded. The amendments themselves remain pending; they have not passed verification yet.**

**What happened next.** The published [comparison protocol](../../workers/odmr-vector-tracking/docs/comparison_study_protocol_2026-10.md) records separate partitions, symmetric confidence-interval rules, and dataset retirement. Its dated addendum records the review; the protocol requires a fresh final version after result-driven changes.

<a id="c2"></a>
## C2. Codex catches an error in Claude's contract

**Date and context.** October 14, 2026. A worker's source check found an incorrect clamp calculation and unsupported interpretations in Claude's integration contract.

**Codex worker report, relayed by Jason**

> Integration-contract correction from direct source checks: safety_clamps.cpp:105-107 uses range=out_max-out_min. v250_pid_loop.c:597-598 explicitly writes out_min=-1 and out_max=+1, so range=2. […] Please correct the contract and plan with an explicit correction note. Also qualify three unsupported conclusions: (1) clamp binds only for outputs beyond its limit, not 'always'; (2) 'quantization noise dominates' is unmeasured and should await our FP32/INT8 results; (3) clipped/slew-limited actuator output is not automatically a field estimate. […]

**Claude Code session in tychon-verification-workbench**

> Corrected in all three places with explicit notes (contract header note plus ⊘ marks on the four original lines; coordination log 21:05; plan State `7c368c4`): outer clamp 5.76 µT-equivalent, inner may bind tighter; "always" withdrawn; "quantization noise dominates" marked unmeasured; actuator output ≠ field estimate […]

**What happened next.** The published [integration contract](../../workers/odmr-edge-ml/docs/scalar_target_repair_integration_contract_2026-10.md) has an explicit correction note and marked original statements. It separates the 5.76 µT-equivalent outer ceiling from a field estimate and qualifies the unsupported conclusions.

<a id="c3"></a>
## C3. A failed criterion goes into the headline

**Date and context.** October 14, 2026. The frozen scalar stress evaluation failed its registered primary criterion on synthetic data.

**Codex worker report, relayed by Jason**

> […] Final primary criterion FAILED. Clean C INT8 11.09565 vs constant13.04273 and prior-fit10.94069; […] Combined stress C INT8 33.57524 vs constant13.04273/prior-fit25.09654; C float38.46909, so export precision is not the cause by itself. […]

**Claude Code session in tychon-verification-workbench**

> Stress test: the direct estimator's gain does **not** survive realistic conditions — that is the honest result the plan was built to surface, and it goes into the headline. Verifying the summary hash and recomputing the key numbers from the saved predictions before I write any public text.

**What happened next.** The [stress-test report](../../workers/odmr-edge-ml/docs/scalar_stress_test_2026-10.md) and [README results table](../../README.md#representative-results) publish the failed criterion. The report states that saved predictions were recomputed; these were synthetic tests, with no deployment change.

<a id="c4"></a>
## C4. Another LLM's review, checked against the record

**Date and context.** October 12, 2026. Jason pasted another model's review and asked Claude to assess it before addressing the remaining work.

**Jason**

> do the title rename to tychon quantum sensing. before we do the whats left items tell me your thoughts on this llm suggestion

**Claude Code session in tychon-verification-workbench**

> 1. **FPGA README is wrong.** `workers/polarfire-hybrid-control/README.md` line 10 still says the five soak stalls were "all caught + recovered by the 2 ms fabric watchdog". Your own 2026-10-09 fallback test says otherwise. Case C3 failed as predicted: the trip counter rose 20 of 20 times and the controller never fell back. Case A4: a stopped control process gives no fallback at all. The front-page row already has the corrected wording, so the two READMEs contradict each other. One sentence fix in the worker repo plus a link to the test plan. […]

**What happened next.** The [FPGA worker README](../../workers/polarfire-hybrid-control/README.md#where-this-fits) now describes software-mediated fallback and dates each measurement. Its [fallback test record](../../workers/polarfire-hybrid-control/docs/watchdog_fallback_test_plan.md) separates a counted watchdog trip from actual controller recovery.
