# The 2025 proposal and the delivered state

This archive records Tychon AI's **not-selected, unfunded SBIR Phase I proposal**, FX255-PCSO2-0044, under topic AFX255-PCSO2.
The notice is dated May 12, 2026. No award or contract resulted from this proposal.
The software and kit work continued independently.

The proposal describes intended work. Its performance promises, staffing plans, and product plans are not delivered results.
Use the crosswalk below before reading the historical claims.

## Documents and provenance

- [Technical volume](technical-volume-2025-redacted.pdf): a scrubbed, 16-page derivative of a privately retained archived copy.
- [Not-selected notice and feedback](not-selected-letter-2026-05-12-redacted.pdf): the two-page notice, with three officers' names and the military email address removed.
- [File manifest](manifest.json): output hashes, page counts, and archived-source hashes.
- [Eight proposal-development selections](../../planning/excerpts/00-proposal-2025.md): dated prompt/reply evidence and one email excerpt.

The exact submission date is not established by these records. The archived technical copy is not verified as the exact submitted bytes.
The decision letter establishes the proposal and topic identifiers above. The archived volume retains its original identifier typos.
Page references below use printed page numbers; the PDF has an additional contents page.

The cover sheet, budget, and separate certifications are excluded. Within the technical volume, the SBC ID, teammate names, personnel school names, institutional affiliations in the related-work group labels, private contact details, named customer references and discussions, prior customer-work table, commercial strategy and pricing, and certification bodies are omitted. The letter omits three officers’ names and the military email address.
Original pagination is retained. Team roles, original duties, and degree fields remain; Jason stays named.
Public researcher citations and group names are retained. Original metadata, comments, attachments, hidden content, and active links were removed.
The letter uses redacted page images with a newly generated OCR text layer. The visible pages are authoritative.

**Jason’s statement:** all proposal information came from public sources, and his position is that ITAR does not apply.
This is Jason’s position, not an independent legal finding. The archived ITAR declaration remains within the omitted certification body.

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
| A proposed team, stakeholder commitments, and follow-on phases (pp. 4, 7, 11-12) | Proposed roles do not establish employment or participation. This archive establishes no funded phase, customer commitment, or follow-on award. | [Not-selected notice](not-selected-letter-2026-05-12-redacted.pdf), [independent build history](../case-study.md#timeline) |

The bounded scalar repair completed on October 15, 2026 and stopped at its validation gate.
No repaired method passed both primary conditions, and no final set was generated.
That result does not establish reliable sensing or a useful neural advantage.
The [scalar decision record](../../workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10.md) publishes the validation result and saved-output evidence.
The earlier vector confirmation is already part of the reviewed baseline, not a new improvement from adding this archive.

## Reading the feedback

The letter reports Commercialization **Acceptable**, Defense Need **Excellent**, and Technical Merit **Good**.
It also says the feedback uses standardized language and does not reproduce proposal-specific peer-review comments.
These ratings are not a government endorsement, technical validation of the performance claims, or an award.
The notice does not establish a specific reason for non-selection.

## What this archive adds

The archive connects original promises to later evidence and unresolved objectives.
It shows the starting plan, requests for model critique, corrections, and the decision to retain negative results.
Model praise in an excerpt is historical output, not independent verification.

Back to [project overview](../../README.md), [case study](../case-study.md), or [planning archive](../../planning/README.md).
