# The 2025 proposal and the delivered state

This archive records Tychon AI's **not-selected, unfunded SBIR Phase I proposal**, FX255-PCSO2-0044, under topic AFX255-PCSO2.
No award, contract, or government funding resulted from this proposal.
The software and kit work continued independently.

## Origin, team and report chronology

- Jason says he submitted the proposal during the first week of August 2025. This is his recollection. The precise submission day and upload receipt remain unverified.
- The [AFWERX opening bulletin](https://content.govdelivery.com/accounts/USAFAFWERX/bulletins/3e789fe) advertised a close of August 5, 2025 at noon ET. The bulletin is not a submission receipt.
- The solicitation anticipated notifications about 90 calendar days after the August 5 closing. Jason expected about 90 days. The [AFWERX notification FAQ](https://afwerx.com/contact-faq/what-is-the-timeframe-for-select-non-select-notifications/) also states a 90-day timeframe.
- The archived not-selected notice is dated May 12, 2026, roughly nine months later.
- The wait spanned the [federal shutdown](https://piv.opm.gov/chcoc/latest-memos/employee-pay-leave-benefits-and-other-human-resources-programs-affected-by-the-lapse-in-appropriations/) and the [SBIR authorization lapse](https://www.nist.gov/tpo/small-business-innovation-research-program-sbir). These records do not show that either caused this particular delay.
- The proposed team included Jason and three additional engineering specialists: one PhD and two master's-level engineers.
- Without funding for the team, Jason continued with AI agents. He owned architecture, experiments, debugging and evidence review.
- He prepared a full technical report before the decision. Version 3.4 is dated May 3, 2026, with a cover date of May 4. The report is privately retained.
- The [case study](../case-study.md#timeline) places these events in the wider timeline.

The proposal describes intended work. Its performance promises, staffing plans, and product plans are not delivered results.
Use the crosswalk below before reading the historical claims.

## Proposal claims versus delivered state

Each evidence link states its own datasets, hardware, and limits. A result in one setting does not verify another setting.

| Historical claim or objective | Delivered state and remaining limit | Evidence |
| --- | --- | --- |
| Simulate NV spectra and build noise-aware synthetic data (pp. 3, 11-12) | A simulator and stochastic recipes exist. Default spectra differed from measured data; later fitting was in-sample. This does not validate an estimator on measured spectra. | [Data recipe](../synthetic-data.md), [measured-data comparison](../../workers/nv-sensor-sim/docs/external_validation_results.md), [in-sample fit](../../workers/nv-sensor-sim/docs/simulator_fit_results.md) |
| AI noise suppression above 10x and heading-error reduction above 50% versus PID (pp. 11-12) | These proposal targets are not demonstrated. Scalar tests report field error, not a navigation heading benefit. Realistic synthetic stress exposed estimator failures. | [Scalar stress](../../workers/odmr-edge-ml/docs/scalar_stress_test_2026-10.md), [current results](../case-study.md#results-and-limits) |
| A CNN is required because classical methods cannot handle the noise (p. 2) | The work does not support that necessity claim. A constant beats the deployed scalar model on the same kit rows. Classical exact inversion is the realistic vector-study reference, with substantial failures remaining. | [Kit constants](../../workers/odmr-edge-ml/docs/kit_constant_baselines_2026-10.md), [vector verdict](../../workers/odmr-vector-tracking/docs/comparison_study_protocol_2026-10.md) |
| Above 99% state-classification accuracy (p. 12) | The published scalar task estimates magnetic field. Its regression error cannot establish a classification-accuracy target. | [Model contract and errors](../../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md) |
| July 28 draft: loop below 150 microseconds and inference below 2 milliseconds; archived volume: inference below 1 millisecond (pp. 2, 11-12) | Kit model inference reached 0.038 ms per replayed synthetic sample. This excludes acquisition and the complete control path. Demonstrated control is processor-paced with replayed input. | [Kit run](../../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md), [controller limits](../engineering-decisions.md#2-test-actual-fallback-rather-than-count-watchdog-trips) |
| July 28 draft: below 5 W compute; below 12 W for the complete PNT system (pp. 6, 11-12) | FPGA tool reports and a development kit do not establish power for an integrated PNT payload. No complete payload is demonstrated. | [FPGA evidence](../../workers/polarfire-hybrid-control/README.md), [project boundary](../../README.md) |
| Radiation-tolerant RT PolarFire and space-ready operation (pp. 2, 5-6) | The demonstrated board is a commercial PolarFire SoC Icicle Kit, MPFS250T. This is not radiation qualification, flight-hardware validation, or orbital testing. | [Exact kit and toolchain](../model-to-v250.md) |
| Live quantum-state stabilization and robust sensing (pp. 2-3, 5) | No live diamond was connected. Replay parity and simulator fits do not demonstrate sensor sensitivity or live noise cancellation. | [Evidence boundaries](../../AGENTS.md#evidence-boundaries), [engineering decisions](../engineering-decisions.md) |
| Fused navigation with IMU, clock, and star tracker; heading and mission benefits (pp. 3, 6-9, 11) | These remain proposed work. No integrated navigation system, measured navigation improvement, or mission benefit is demonstrated here. | [Scope](../../README.md), [case study](../case-study.md) |
| A proposed team, stakeholder commitments, and follow-on phases (pp. 4, 7, 11-12) | Proposed roles do not establish employment or participation. This archive establishes no funded phase, customer commitment, or follow-on award. | [Independent build history](../case-study.md#timeline) |

The bounded scalar repair completed on October 15, 2026 and stopped at its validation gate.
No repaired method passed both primary conditions, and no final set was generated.
That result does not establish reliable sensing or a useful neural advantage.
The [scalar decision record](../../workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10.md) publishes the validation result and saved-output evidence.
The earlier vector confirmation is already part of the reviewed baseline, not a new improvement from adding this archive.

## Work extended beyond the Phase I feasibility plan

The three items below map to later technical planning labelled Phase II. That label is a planning category. It is not an awarded phase, and it does not show that all proposal targets were met.

| Planned next-phase work | Independently delivered work | Evidence and limit |
| --- | --- | --- |
| On-board inference and runtime measurement | 512 held-out synthetic spectra ran on a commercial PolarFire SoC development kit. CPU INT8, simulator and kit outputs were bit-exact. Median NPU inference was 0.038 ms per sample. | No full sensing-and-control latency and no live diamond. Evidence: [kit run](../../workers/odmr-edge-ml/docs/deployed_model_on_kit_2026-10.md). |
| Board-level controller measurements | 120 measured watchdog trips, median 2.000 ms. | This measures the trigger, not complete recovery. Recovery limits are in [engineering decisions](../engineering-decisions.md#2-test-actual-fallback-rather-than-count-watchdog-trips). The full safety chain is not autonomously validated. Evidence: [watchdog measurement](../../workers/polarfire-hybrid-control/docs/watchdog_trip_measured_2026-07-01.md). |
| Hierarchical two-stage INT8 model | A coarse and fine model composition was implemented and tested. It showed saturation and failed its improvement gate. | A completed experiment with a negative result. It is not an achieved accuracy objective, and no on-board cascade is claimed. Evidence: [cascade saturation finding](../../workers/odmr-edge-ml/docs/phase2/cascade_saturation_finding.md). |

### Historical planning basis

These short excerpts come from private retained source documents. They show the planning category only. They are not current validated performance claims. The full documents remain private.

- Session log dated April 28, 2026 (end of day). Its Decision 3 status reads "Option E (defer to Phase II)". It describes "hierarchical INT8 (coarse + fine)" as "Phase II Priority 1". Its other numerical conclusions are superseded and are not reproduced.
- "Tychon Phase I Final Technical Report", version 3.4, version date May 3, 2026, cover date May 4. Section 9.5 begins: "Three Phase I markers carry a deferred status (Section 8.6 KPP scorecard): on-board AI inference latency, on-board PID classical latency, and total payload power." Section 1.2 includes: "on-board runtime measurement is scoped to Phase II HIL on the Icicle Kit."
- In that report, "Phase I" refers to the unfunded plan. A subset of these measurements was later pursued. Total payload power remains unresolved.
- Original DOCX SHA-256: `4d43e70c9392aba4b94020854d2da829c923e0c39e50acf65cdf7e806be27eea`.

These excerpts do not show that the whole plan was completed.

## Optional historical background

- The redacted technical volume was available on this page from October 15 to October 22, 2026. It was withdrawn on October 22, 2026, pending an export-control review. This note takes no position on whether the material is export-controlled. The volume remains privately retained.
- [File manifest](manifest.json): records the withdrawal and the hashes of the withdrawn file.
- [Eight proposal-development selections](../../planning/excerpts/00-proposal-2025.md): dated prompt/reply evidence and one email excerpt.

The submission date rests on Jason's recollection of the first week of August 2025. These records do not establish the exact day or an upload receipt.
The proposal and topic identifiers above follow privately retained records.
Page references in the crosswalk use the printed page numbers of the privately retained technical volume.

## What this archive adds

The archive connects original promises to later evidence and unresolved objectives.
It shows the starting plan, requests for model critique, corrections, and the decision to retain negative results.
Model praise in an excerpt is historical output, not independent verification.

Back to [project overview](../../README.md), [case study](../case-study.md), or [planning archive](../../planning/README.md).
