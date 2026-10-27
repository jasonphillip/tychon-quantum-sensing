# Next sensing study: less calibration for NV thermometry

The proposed study asks whether an NV thermometer can use half as many reference-temperature calibration settings.
It must preserve temperature accuracy on complete, untouched thermal acquisitions.
The intended user is a laboratory calibrating a fiber-coupled NV thermometer.
This study would use existing computers and public or redistributable measurements.
It requires no FPGA work, live diamond, or new equipment.

Assessment date: October 16, 2026. Status: protocol proposal; numerical work blocked pending the data eligibility gate.
This is one proposed task, not a search across new architectures.
The scientific objective remains unmet.
The existing [measured studies](nv_advantage_search_2026-10.md) and [vector comparison](nv_vector_development_2026-10.md) retain their verdicts.

## Why this task

The [NIST publication](https://www.nist.gov/publications/evaluating-impact-probabilistic-and-data-driven-inference-models-uncertainties-fiber) compares physical inference with peak finding, PCR, and a CNN.
The [primary manuscript](https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=958356) reports drywell-referenced temperatures and transfer between two thermal cycles.
Its physical model is already a strong reference.
Its data statement offers data on request; it does not establish a public deposit.

The possible contribution is a controlled reduction in labelled calibration, with honest transfer limits.
This is a hypothesis, not a novelty claim.
Predicting temperature, using a neural network, or repeating the source's transfer result would not establish a distinct contribution.

## Available candidates and exact blockers

This is a bounded eligibility assessment, not a complete public-data survey.

| Candidate | What is established | Current decision |
| --- | --- | --- |
| NIST fiber-coupled NV thermometry | The manuscript describes measured spectra, a drywell reference, and two thermal cycles. | Selected lead, **not qualified**. Raw files, paired reference logs, uncertainty, redistribution terms, and enough untouched acquisitions remain unverified. |
| [Public NV localisation archive](https://zenodo.org/records/19855773) | The public record supplies a 5.5 GB data/code archive. This project's separate [25-case transfer study](nv_advantage_search_2026-10.md) is complete. | Not a thermometry dataset. Its evaluated acquisition is consumed and cannot become confirmation for another claim. |
| [NV-Center-Analysis temperature examples](https://github.com/MikiDotan/NV-Center-Analysis/tree/b60617095a4a21963aa94d1f27a71d3ed8a7ae31/ODMR/ODMR_vs_T) | A prior source audit found example spectra and notebook-assigned temperature labels. | Not qualified. Independent reference linkage and complete independent thermal cycles were not established. Filename temperatures do not resolve this. |

No candidate currently satisfies the contract below.
More compute cannot supply missing reference measurements or unused acquisitions.
The author-data request remains unsent. Contact requires separate authorization.
A new deposit can reopen metadata qualification; it cannot automatically release experiments.

## Data eligibility gate

A data custodian must produce a public, reviewable inventory before signal access.

- Give immutable file identities, source revision, hashes, license, and redistribution permissions.
- Provide raw frequency axes and ODMR observations, with units and acquisition settings.
- Pair each observation with an independently measured reference temperature.
- Document reference calibration, uncertainty, timestamp alignment, thermal settling, and sensor/reference separation.
- Preserve device, day, thermal-cycle, and repeat identifiers. File formats are not independent acquisitions.
- Record every prior use, exclusion, published split, and existing derived label.
- Exclude temperature labels inferred from the same ODMR spectrum as independent truth.
- Identify complete acquisitions that have not been used for model selection or scoring.

The proposed minimum is six complete acquisitions over at least five acquisition days.
Reserve two acquisitions on different days for calibration and one separate day for development.
Reserve at least three whole acquisitions on at least two later days for confirmation.
No day may cross those partitions.
This is a proposed small transfer study, not evidence of robustness across devices or laboratories.
A sensor reviewer must accept this scope and its reference uncertainty before the freeze.

The exact temperature range must cover at least 40 K within 243–323 K.
Choose it from acquisition metadata before decoding spectra; do not choose it from estimator errors.
Require at least ten distinct, settled reference settings in each calibration acquisition.
Any unexplained time/temperature confounding or calibration drift blocks launch.
Two cycles alone do not meet this contract.

## Proposed acceptance contract

These values are reviewable starting requirements. They are not results or a frozen experiment.
An independent sensor reviewer must accept or reject them before any confirmation access.
Changes must be dated, justified, and frozen prospectively.
If no reviewer accepts the use case, retain BLOCKED rather than invent an application.

| Item | Proposed requirement |
| --- | --- |
| Calibration saving | At least 50% fewer distinct reference settings, counting all labels used to fit or select a method. |
| Primary metric | RMSE in kelvin against the independent reference, calculated separately for each complete confirmation acquisition. |
| Accuracy margin | Each confirmation acquisition must have reduced-budget RMSE no more than 1.05× the selected full-budget classical reference. |
| Absolute usefulness | RMSE no greater than 2 K in every confirmation acquisition. The reviewer must confirm this meets the stated laboratory use case. |
| Tail and coverage checks | 95th-percentile absolute error no more than 1.10× the full-budget reference; no dropped or silently invalid predictions. |
| Uncertainty reporting | Report per-acquisition bias, reference uncertainty, and prediction-interval coverage and width. Do not claim calibrated uncertainty without a separate frozen coverage requirement. |
| Decision | All primary and guard conditions must pass. Otherwise report FAIL or INELIGIBLE, with the specific reason. |

Count each (acquisition, settled reference setting) once, including settings used for method selection.
Let N be full-budget fitting settings and D be common development settings.
A reduced method may fit at most floor((N + D) / 2) − D settings.
If this leaves too few settings for identifiable calibration, the proposed saving is ineligible.
Select those fitting settings by a deterministic, evenly spaced rule over the reference range.
Keep every repeat at a chosen setting together and report both setting and spectrum counts.
Provide identical fitting settings to every same-budget method.
Development labels count toward the saving when they influence the selected estimator.
No confirmation labels, signal statistics, or temperature-derived target features enter preprocessing or fitting.

The minimum study supports a result conditional on its listed acquisitions.
It does not justify a population-level confidence claim.
Report cycle-level results and sensitivity to reference uncertainty; do not treat spectra as independent replicate experiments.
If a reviewer requires stronger statistical evidence, obtain sufficient groups before freezing or stop.

## Strong classical comparison

The finite comparison should start with these methods:

1. The source study's probabilistic physical model, using its public code when available.
2. Joint two-line likelihood fitting with calibrated temperature conversion.
3. Weighted line-center calibration with linear and quadratic alternatives.
4. Principal-component regression and a calibration-mean constant control.

Use each relevant method at full and reduced calibration budgets.
Select the full-budget reference on development acquisitions, with no confirmation access.
Optimize convergence, initialization, scaling, and vectorization before comparing cost.
Declare failures, fallbacks, preprocessing, and all labels used by tuning.
The exact implementations and finite settings require external review and a source freeze.

The first candidate is the best development-qualified reduced-budget classical method.
A learned method is optional and needs a specific remaining error or cost hypothesis.
It receives no extra data or selection budget.
A classical winner is a valid outcome; there is no requirement to train a neural model.

A companion simulator check must use calibration acquisitions only to set line shape, noise, and nuisance parameters.
Freeze those settings before comparing predicted spectra with untouched measured acquisitions.
Report spectral mismatch separately from temperature error.
Do not turn an in-sample fit into a validated simulator claim.
The simulator mismatch metric and tolerance must be accepted and frozen before held-out signals are accessed.

## Owners, dependencies, and limits

| Stage | Owner | Dependency and completion condition | Proposed effort |
| --- | --- | --- | --- |
| Saved-output reproduction | Independent software reviewer | Fresh public checkout reproduces existing decisions using [the evidence guide](reproduce-evidence.md). | 1–2 hours |
| Metadata qualification | Data custodian and maintainer | Eligibility checklist, complete groups, public rights, hashes, and access ledger pass. | At most 1 hour; metadata only, at most 10 MiB |
| Measurement protocol review | Independent NV/thermometry specialist; currently unassigned | Reviews reference validity, useful margins, grouping, baseline strength, and scope. | A bounded 1-hour review; response time unknown |
| Source and fixture preparation | Software contributor | Accepted protocol, grouped split, fixtures, and frozen implementation. | 0.5–1 working day |
| Development and one confirmation | Maintainer authorizes; custodian releases groups | Finite development passes; source, methods, metrics, and budgets freeze before one confirmation read. | 0.5–1 working day |
| Independent verification and publication | Separate reviewer and maintainer | Saved predictions, references, flags, manifests, and decisions reproduce from a public checkout. | 0.5–1 working day |

After data and reviewer dependencies resolve, allow roughly two to three working days.
External data access and reviewer availability have no reliable completion date.
No completion promise starts from this document.

The proposed numerical ceiling is 16 CPU-hours, 1 GPU-hour, and 4 cumulative numerical wall-hours.
Use at most one scientific job, four CPU threads, 8 GiB CPU memory, or 32 GiB GPU memory.
Keep at least 24 GiB host memory free and do not evict services.
These are proposed ceilings, not a resource allocation.
The maintainer must approve the frozen implementation and accounting before launch.
No new numerical budget is active now.

## Stop and publication rules

Stop if reference linkage, redistribution, grouping, or calibration provenance fails.
Stop when metadata inspection reaches its cap without an eligibility decision.
Stop after one finite development choice if no candidate qualifies.
Stop after the single confirmation result; never tune, add groups, or weaken a margin after seeing it.
Stop at any compute or memory cap. Preserve partial evidence and record the reason.
Do not reopen earlier campaigns or reuse consumed tests.

Publish the manifest, grouped split, reference provenance, saved predictions, flags, metrics, and negative results.
A fresh public checkout must recompute every reported metric without private files or inference.
Document any public source dependency and verify its pinned bytes.
Compare the final claim with the source paper and relevant newer prior art before claiming novelty.

External review assesses whether the question and test are useful.
It is not a substitute for independently referenced measurements.
A passed software reproduction check is not a passed sensing experiment.
