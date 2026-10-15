# Planning and building an AI-on-FPGA quantum-sensing stack, with multi-model review

Between March and October 2026 I planned and built five connected repositories for AI-assisted control of NV-diamond quantum magnetometers: a physics simulator, an edge-ML training and export pipeline, a PID plus neural-network controller on production PolarFire SoC silicon (paced by software on the SoC's processor, with replayed ODMR input), a learned vector tracker (FP32 simulation only), and a workbench that checks written claims against evidence. Claude Code and Codex wrote the code from written specs and data contracts. I ran the planning, the cross-model reviews and the claim checks, and I reviewed what came back.

The scope comes from a technical plan I developed in July and August 2025 for an AFWERX SBIR Phase I proposal ([FX255-PCSO2-0044](proposal/README.md)), which was not selected in May 2026; the work had no contract and no government funding. The government shutdown in autumn 2025 stalled the program and the decision slipped into 2026. Rather than wait for funding to hire the people on the proposal, I built it myself. I turned the plan into a 90-day build plan in March 2026 and kept building into October. Files that say Phase I, KPP (key performance parameter) or deliverable follow the plan and report I wrote for that proposal. The public history holds about 400 commits between 2026-03-26 and 2026-10-08, counting a week of first attempts in three repos I later archived.

Three decisions with their evidence and attribution: [engineering-decisions.md](engineering-decisions.md). Selected conversation evidence: [research and verification](../planning/excerpts/05-research-and-verification.md). Terms: [glossary](glossary.md). Back to the [project overview](../README.md).

## How I ran it

I did the planning in one claude.ai project that held the original technical plan and research reports next to a 90-day execution playbook. The playbook lists five deliverables (a sensor model, a trained INT8 network, an FPGA analysis, Draft ICD and CONOPS, and a final report) sized for one person with two NVIDIA DGX Spark desktops. The Draft ICD and CONOPS deliverable is not in this repository; the playbook specifies it, and the report outline only lists a planned diagram. Major choices went into a decision log with its date, trigger, rationale and the alternative I turned down. Early on I rejected an AI-generated plan to scaffold all three repos on day one and built them in sequence instead, simulator first, then ML, then FPGA, because each stage's output is the next stage's input.

Claude produced the designs and Gemini Deep Think reviewed them as a second model. Claude then sorted the review items into those to act on and those to defer or close, and I logged the outcome in an integration tracker.

The workbench started as a way to check my own work, and only later became the orchestrator. It checks the claims in my own technical report against the project's ground truth. Its critics see only the project's own files, never the web; the reasons are in [orchestrator/README.md](../orchestrator/README.md). It builds searchable corpora from the docs and code, extracts each claim and runs it past an ensemble of critic models on my own machines, with no cloud inference and a stop-gate after each stage. In the first audit on 2026-05-01 a manual structure review of the report found the abstract and body disagreeing on timing slack, an unfinished deliverable section and a missing reference list, all rated critical. All three were closed in the corrected report.

The second audit showed the cost of a closed corpus. A critic marked a correct timing claim CONTRADICTED because the corpus held both an early timing run and the final one, and the critic read the early run. After I archived the early run, the claim came back SUPPORTED. The lesson I recorded was that evidence needs version metadata, such as which run and which design state, before a bigger critic is worth adding.

The ensemble also produced false positives, and at first the two critic models returned identical verdicts 10 times out of 10. I counted that as a failed independence test rather than a pass. I also adopted a stopping rule for verify-and-repair loops. A fix is accepted only when its evidence is stronger than before, and the loop stops after two failed repairs.

The workbench also sends scoped tasks to each repo's own agent session. Each dispatch carries a prediction in hours, sessions and probability, an acknowledgment step and a file-based payload, and workers don't dispatch onward. Atomic ID reservation and lease handling were added to the dispatch tool in September. Until the tool existed in July 2026, I relayed prompts between the planning chat and the repo sessions by hand.

## Tools and roles

| Role | Tool | Where it shows |
|---|---|---|
| Planner and first orchestrator | a claude.ai project | [planning/](../planning/) |
| Grounded Q&A over vendor manuals | Google NotebookLM | [method.md](method.md) |
| Math and physics checks | Gemini Deep Think, on the problems it was strongest at | [second-opinions.md](second-opinions.md) |
| Second reviews of plans and patches | ChatGPT Pro | [second-opinions.md](second-opinions.md) |
| Orchestrator | a Claude Code session with its own rules | [orchestrator/](../orchestrator/) |
| Workers | one Claude Code or Codex session per repository | [workers/](../workers/) |
| Claim critics | qwen3-coder:30b and nemotron-mini, run locally with Ollama | [orchestrator/STAGES.md](../orchestrator/STAGES.md) |

By rule, the orchestrator session sends a written dispatch with a goal and an acceptance check, sometimes with a predicted effort, and the worker session does the work in its own repository. (The orchestrator's rules also let it commit to the implementation repositories for multi-repository bring-up work.) The critic models run only on my own machines. A real dispatch: [dispatch-9-increment8-bc-stack-2026-07-11.md](../orchestrator/tvw/audits/dispatch-9-increment8-bc-stack-2026-07-11.md), sent with [dispatch.sh](../orchestrator/tvw/scripts/dispatch.sh). The agents' own instructions: [orchestrator/AGENTS.md](../orchestrator/AGENTS.md) and `workers/*/AGENTS.md`.

## What the reviews caught

On 2026-04-01 Gemini argued that INT8 quantization would push a small heading signal below one quantization step on raw spectra, and it proposed an INT16 input layer. Claude marked the claim "directionally correct but overstated," noted that "the INT16 input layer mitigation is wrong for TorchAO/XNNPACKQuantizer," and closed with "test empirically, don't take on faith."

The next day Gemini reviewed my draft report. It confirmed the relative figures held at either unit scale and told me to "double-check your report for a 'µT' vs 'nT' typo before submitting."

One catch was in my own tracker program. On 2026-07-01 I ran a design review with three audit agents working in parallel, and two of them reproduced the same finding independently. The classical baseline's peak detector had returned zero peaks in every frame of every sequence, so the tracker never left its starting position and the metrics scored a frozen tracker against moving lines. The headline failure numbers for that baseline were an artifact. I retracted them, fixed the detector so its threshold scales with the data, and added a textbook Kalman tracker with one-to-one assignment as a stronger classical baseline.

## Results and limits

Each row keeps its limit next to it. [HW] marks a measurement on the PolarFire SoC kit; everything else is simulation, synthetic data or software.

| Part | Result | Limit |
|---|---|---|
| FPGA watchdog [HW] | Trip time measured on PolarFire SoC silicon on 2026-07-01: median 2.000 ms over 120 trips | One dev kit |
| FPGA control loop [HW] | 8-hour soak on silicon on 2026-07-02: 95.7 M steps at 3,319 Hz, and the loop never stopped advancing. Five short scheduling delays over 2 ms each tripped the watchdog | Paced by software on the SoC's processor, not in the fabric; replayed ODMR input, no live diamond. A counted trip does not show that the controller fell back (next row) |
| Watchdog fallback [HW] | Board tests on 2026-10-09. When the next controller update saw the timeout, control passed to plain PID within one update (66 to 71 µs), with no jump in the actuator value, 60 of 60. After a software fix that starts the hand-over whenever the timeout is high, the two cases that had failed now fall back as well: a timeout that cleared before the next update, 20 of 20 (was 0 of 20), and a 1 s pause of the control process, 10 of 10 after it resumes (was 0 of 10) | A processor that stays frozen gets no fallback until it resumes. At recovery the actuator still steps by about 0.01, ten times the slew limit |
| Edge ML benchmark | `make bench` trains a 10,689-parameter network on synthetic spectra. Mean field error on 200 test spectra is 10.53 µT, against 12.26 µT for a constant baseline and 25.93 µT for a derivative zero-crossing PID proxy | Synthetic data, FP32 on a CPU; INT8 accuracy on the kit is not in this table |
| Scalar repair cycle | A bounded repair of the scalar estimators (background correction, constrained peak fits; no retraining), frozen before a single read of a fresh sealed validation set. On the realistic synthetic condition it brings the unchanged direct INT8 models' 27–41 µT down to 12.9 µT on the same data, but no repaired method beats the 12.3 µT training constant, so the registered rule stopped the study before a final set ([decision record](../workers/odmr-edge-ml/docs/scalar_repair_cycle_2026-10.md)) | Synthetic, one orientation; the earlier stress cells under-sampled thermal drift and the new sets correct it, so only same-data comparisons count |
| Known-axis bias comparison | With the field known to lie along one NV axis, a +250 µT axial bias lowered a fixed classical fit's error from 2.56 µT to 1.07 µT on 256 sealed synthetic fields (constant 45 µT: 12.82). Design, fit and pass rule were fixed before the single evaluation; the entropy that generated the sealed set was committed by hash before generation and revealed after it ([decision record](../workers/odmr-edge-ml/docs/scalar_bias_design_2026-10.md)) | Synthetic, one orientation, a changed task (not comparable with the arbitrary-direction results); no network; the low-SNR secondary cell misses its thresholds; the [information diagnostic](../workers/odmr-edge-ml/docs/scalar_information_limit_2026-10.md) before it keeps a recorded independent FAIL |
| Vector models | With a known 1 mT bias field, eight small networks estimate the ambient field (up to 200 µT) with 75.5 µT RMS error from label-free anchors. Assuming the bias alone gives 115.2 µT | Simulated spectra. Earlier GPU-trained versions were invalid, because the bfloat16 training path saved models that didn't reproduce their own validation error. I fixed that and retrained them |
| Vector tracker | Follows the field vector through spectral line crossings, reliable to about 30 to 40° off the bias axis. With the association losses taken out of training, field-cone error fell in all three seeds I ran. RMSE dropped by 0.46, 0.17 and 0.17 mT and mean angular error by 10.4, 3.7 and 8.6°, with every 95 % interval below zero. Identity switches on the dwell set went down in all three too | FP32 simulation only, with no INT8 export or on-target run. I've since turned the association losses off in the default training config. Apart from these three seeds, the tracker hasn't been retrained with that setting. The pre-registered comparison below supersedes the "reliable to 30 to 40°" reading: on its sealed sets the tracker as trained loses 96 to 100 % of sequences in every cell |
| Simulator | Against four public ODMR datasets, the default simulated lines are 2 to 11 times narrower than measured. When I fit line width and contrast per spectrum, the simulated widths match the measured ones, 2.3 to 7.3 MHz | The fit is in-sample, since the same rows were used to choose the values. With one shared setting the zero-field lines are still narrower than measured |
| Claim checks | Audits of my technical report on 2026-05-01, up to 114 claims per pass through two local critic models. A manual structure review found three critical errors, all fixed in the corrected report. On a 60-claim test set with 30 deliberately altered claims, I added a stronger local model (DeepSeek-V4-Flash on a second workstation) and required all three critics to agree. False acceptances fell from 27 to 10 | On the first run the two critics agreed 10 times out of 10, which I counted as a failed independence test ([details](../orchestrator/README.md#critic-independence)). The three-critic setup abstained on 58 % of claims, 62.5 % of the claims it accepted weren't supported, and on a rerun of 10 claims the stronger model gave a different verdict on 2 |

### Reference estimator for vector tracking

I fixed the comparison protocol, the decision rule and the sealed test sets before scoring, then scored once on each of two sealed synthetic sets (14 cells × 120 sequences each). The classical side is a per-frame Lorentzian fit followed by exact Hamiltonian inversion, chosen on a separate validation set before either final set was read. The registered rule needed the same result on the second set before any branch could follow, and it got it.

| Cell, set | Classical fit + exact inversion: RMSE / angular p90 / sequences lost | Learned tracker: RMSE / angular p90 / sequences lost |
|---|---|---|
| Realistic, set 1 | 0.91 mT / 70° / 66 % | 5.91 mT / 171° / 100 % |
| Realistic, set 2 | 0.93 mT / 68° / 69 % | 5.81 mT / 170° / 100 % |
| Clean, set 1 | 0.80 mT / 31° / 44 % | 1.38 mT / 26° / 96 % |
| Clean, set 2 | 1.01 mT / 71° / 48 % | 1.35 mT / 24° / 97 % |

The classical estimator is the reference under realistic conditions, where it wins by the registered margins on both sets and on eleven of the twelve stress cells of each set. The learned tracker as trained is not a usable estimator. On clean narrow-line spectra the two split: the classical side has the lower RMSE and loses far fewer sequences, the tracker has the lower angular error. Neither result is good enough to call the problem solved: the classical estimator still loses 44 to 69 % of sequences, and its clean-cell angular p90 moved from 31° to 71° between the two sets. On the two primary cells, the median time per frame on one CPU thread was 4.7 to 6.7 ms for the classical estimator and 1.9 to 2.2 ms for the tracker, with all 14 cell runs sharing one machine; the protocol registered that latency never substitutes for accuracy. Synthetic data only. Protocol and addenda: [protocol](../workers/odmr-vector-tracking/docs/comparison_study_protocol_2026-10.md), decisions for [set 1](../workers/odmr-vector-tracking/docs/comparison_study_decision_2026-10.md) and [set 2](../workers/odmr-vector-tracking/docs/comparison_study_decision_2026-10_v2.md).

Every comparison against the four public ODMR datasets passes the frequency-overlap check ([table](../workers/nv-sensor-sim/docs/external_validation_results.md)), but the default lines are narrower than measured. The vector models and the tracker were trained on data generated with the narrow default lines. After the retrain, the vector models didn't degrade on lines with the measured width: their 3-D RMS error was 523.9 µT, against 526.5 µT on the default lines, with anchors taken from the true field ([sensitivity](../workers/odmr-edge-ml/docs/vector_v1_linewidth_sensitivity.md)). Neither has been retrained on fitted-width data yet.

GitHub Actions runs the tests on CPU runners for every push. In the 2026-10-10 run, 764 passed across the simulator, edge ML, tracker, FPGA tooling, dashboard and orchestrator. Another 63 were skipped because they need datasets that aren't in the repository, optional packages, a private package or the FPGA kit.

Where I'd push back on these results myself: [the weakest claims](../orchestrator/INVENTORY.md#6-weakest-claims--what-would-not-survive-a-sharp-reviewer), my own list. What review caught is in the section above and in [errors in agent output](../orchestrator/README.md#checking-the-agents-as-well-as-the-report).

## The repos

The first three repositories below were the original workers, restarted in clean repositories on 2026-04-03; the vector tracker was added as a fourth on 2026-06-29.

- [`nv-sensor-sim`](../workers/nv-sensor-sim) is the NV-diamond ODMR simulator, with a coupled stochastic noise model, synthetic datasets, frame and trajectory utilities, and loaders for five external ODMR and magnetometry datasets. How its data is made and used: [synthetic-data walkthrough](synthetic-data.md).
- [`odmr-edge-ml`](../workers/odmr-edge-ml) has the training and evaluation suite for ODMR inversion and the INT8 export for the FPGA's neural-network engine.
- [`polarfire-hybrid-control`](../workers/polarfire-hybrid-control) contains the PID plus neural control on PolarFire SoC, the Libero and SmartHLS flows, a run-time-assurance watchdog and the on-kit bring-up. I measured the 2 ms watchdog on production silicon at a median trip time of 2.000 ms over 120 trips.
- [`odmr-vector-tracking`](../workers/odmr-vector-tracking) is an ML tracker for the NV vector through spectral line crossings, supported by FP32 simulation experiments only; no INT8 export or on-target parity run exists. An NV diamond has four crystal orientations, so one sensor can measure the direction of the field as well as its size; the deployed edge model and the FPGA loop use only the scalar field.
- [`orchestrator/`](../orchestrator) (`tychon-verification-workbench`) holds the claim-verification pipeline and the dispatch layer.
- The archived first attempts (`tychon-nv-sim`, `tychon-odmr-ml`, `tychon-polarfire-control`) were replaced by the 2026-04-03 restart.

## Timeline

| Date | Event |
|---|---|
| 2025-07-02 to 08-04 | Proposal origin, scope changes, and research condensed with Claude and Gemini; [eight drafting excerpts](../planning/excerpts/00-proposal-2025.md) |
| 2025, exact submission date unverified | Proposal FX255-PCSO2-0044 submitted under topic AFX255-PCSO2; [archived technical volume and claim crosswalk](proposal/README.md) |
| 2026-03-04 | [Planning starts in a claude.ai project](../planning/excerpts/playbook-creation-2026-03.md); execution playbook v4 is dated 2026-03-09, with a numbered decision log |
| 2026-03-11 | Decision DLOG-017 sets the build order, simulator, then ML, then FPGA |
| 2026-03-26 to 04-02 | First attempts in three repos (38 commits), later archived |
| 2026-04-01 to 04-02 | Gemini Deep Think review of the training-loop and dataset designs, then of the draft report |
| 2026-04-03 | Restart in `nv-sensor-sim`, `odmr-edge-ml` and `polarfire-hybrid-control` |
| 2026-04-04 | Review findings turned into code changes in all three repos |
| 2026-05-01 | Verification workbench started, with a full claim audit of my technical report the same day |
| 2026-05-12 | [Not-selected notice](proposal/not-selected-letter-2026-05-12-redacted.pdf): no contract, no government funding; building continued |
| 2026-06 | Production PolarFire SoC silicon confirmed on the dev kit, then two-slot PID integration; demo dashboard built for a live demo |
| 2026-06-29 | `odmr-vector-tracking` started |
| 2026-07-01 to 07-02 | Per-claim inventory of every repo, plus watchdog trip time and a kit-resident paced loop measured on silicon |
| 2026-07-01 to 07-10 | Dispatches move from pasted prompts to files; the dispatch tool follows on 2026-07-10 |
| 2026-07 | Busiest month, with 56 commits in the tracker repo and 24 each in the simulator and FPGA repos |
| 2026-08 | Loaders for five external ODMR and magnetometry datasets, plus two-sample test code to compare the simulator against them |
| 2026-09 | Dispatch tooling hardened: atomic ID reservation, leases and an 18-group test |
| 2026-10-09 to 10-10 | Simulator compared with four public ODMR datasets, then a line-width and contrast fit (in-sample); watchdog fallback tested on the kit |


Each folder of this repository keeps the original commit history of the repository it came from, with original dates. In `workers/polarfire-hybrid-control` and `orchestrator` some planning documents and vendor tool logs were left out of the history; dates and authors are unchanged. The first attempts are in [`archive/v0`](../archive/v0) and the planning phase is in [`planning/`](../planning).
