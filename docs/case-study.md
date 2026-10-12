# Planning and building an AI-on-FPGA quantum-sensing stack, with multi-model review

Between March and October 2026 I planned and built five connected repositories for AI-assisted control of NV-diamond quantum magnetometers: a physics simulator, an edge-ML training and export pipeline, a PID plus neural-network controller on production PolarFire SoC silicon (paced by software on the SoC's processor, with replayed ODMR input), a learned vector tracker (FP32 simulation only), and a workbench that checks written claims against evidence. Claude Code and Codex wrote the code from written specs and data contracts. I ran the planning, the cross-model reviews and the claim checks, and I reviewed what came back.

The scope comes from a technical plan I wrote in August 2025 for an AFWERX SBIR Phase I proposal (FX255-PCS02-0044), which was not selected in May 2026; the work had no contract and no government funding. I turned it into a 90-day build plan in March 2026 and kept building through September. The public history holds about 400 commits between 2026-03-26 and 2026-10-08, counting a week of first attempts in three repos I later archived.

Three decisions with their evidence and attribution: [engineering-decisions.md](engineering-decisions.md). Selected conversation evidence: [research and verification](../planning/excerpts/05-research-and-verification.md).

## How I ran it

I did the planning in one claude.ai project that held the original technical plan and research reports next to a 90-day execution playbook. The playbook lists four deliverables (a sensor model, a trained INT8 network, an FPGA analysis and a final report) sized for one person with two NVIDIA DGX Spark desktops. Major choices went into a decision log with its date, trigger, rationale and the alternative I turned down. Early on I rejected an AI-generated plan to scaffold all three repos on day one and built them in sequence instead, simulator first, then ML, then FPGA, because each stage's output is the next stage's input.

Claude produced the designs and Gemini Deep Think reviewed them as a second model. Claude then sorted the review items into those to act on and those to defer or close, and I logged the outcome in an integration tracker.

The workbench started as a way to check my own work, and only later became the orchestrator. It checks the claims in my own technical report against the project's ground truth. Its critics see only the project's own files, never the web; the reasons are in [orchestrator/README.md](../orchestrator/README.md). It builds searchable corpora from the docs and code, extracts each claim and runs it past an ensemble of critic models on my own machines, with no cloud inference and a stop-gate after each stage. In the first audit on 2026-05-01 a manual structure review of the report found the abstract and body disagreeing on timing slack, an unfinished deliverable section and a missing reference list, all rated critical. All three were closed in the corrected report.

The second audit showed the cost of a closed corpus. A critic marked a correct timing claim CONTRADICTED because the corpus held both an early timing run and the final one, and the critic read the early run. After I archived the early run, the claim came back SUPPORTED. The lesson I recorded was that evidence needs version metadata, such as which run and which design state, before a bigger critic is worth adding.

The ensemble also produced false positives, and at first the two critic models returned identical verdicts 10 times out of 10. I counted that as a failed independence test rather than a pass. I also adopted a stopping rule for verify-and-repair loops. A fix is accepted only when its evidence is stronger than before, and the loop stops after two failed repairs.

The workbench also sends scoped tasks to each repo's own agent session. Each dispatch carries a prediction in hours, sessions and probability, an acknowledgment step and a file-based payload, and workers don't dispatch onward. Atomic ID reservation and lease handling were added to the dispatch tool in September. Until the tool existed in July 2026, I relayed prompts between the planning chat and the repo sessions by hand.

## What the reviews caught

On 2026-04-01 Gemini argued that INT8 quantization would push a small heading signal below one quantization step on raw spectra, and it proposed an INT16 input layer. Claude marked the claim "directionally correct but overstated," noted that "the INT16 input layer mitigation is wrong for TorchAO/XNNPACKQuantizer," and closed with "test empirically, don't take on faith."

The next day Gemini reviewed my draft report. It confirmed the relative figures held at either unit scale and told me to "double-check your report for a 'µT' vs 'nT' typo before submitting."

One catch was in my own tracker program. On 2026-07-01 I ran a design review with three audit agents working in parallel, and two of them reproduced the same finding independently. The classical baseline's peak detector had returned zero peaks in every frame of every sequence, so the tracker never left its starting position and the metrics scored a frozen tracker against moving lines. The headline failure numbers for that baseline were an artifact. I retracted them, fixed the detector so its threshold scales with the data, and added a textbook Kalman tracker with one-to-one assignment as a stronger classical baseline.

## The repos

- [`nv-sensor-sim`](../workers/nv-sensor-sim) is the NV-diamond ODMR simulator, with a coupled stochastic noise model, synthetic datasets, frame and trajectory utilities, and loaders for five external ODMR and magnetometry datasets.
- [`odmr-edge-ml`](../workers/odmr-edge-ml) has the training and evaluation suite for ODMR inversion and the INT8 export for the FPGA's neural-network engine.
- [`polarfire-hybrid-control`](../workers/polarfire-hybrid-control) contains the PID plus neural control on PolarFire SoC, the Libero and SmartHLS flows, a run-time-assurance watchdog and the on-kit bring-up. I measured the 2 ms watchdog on production silicon at a median trip time of 2.000 ms over 120 trips.
- [`odmr-vector-tracking`](../workers/odmr-vector-tracking) is an ML tracker for the NV vector through spectral line crossings, supported by FP32 simulation experiments only; no INT8 export or on-target parity run exists.
- [`orchestrator/`](../orchestrator) (`tychon-verification-workbench`) holds the claim-verification pipeline and the dispatch layer.
- The archived first attempts (`tychon-nv-sim`, `tychon-odmr-ml`, `tychon-polarfire-control`) were replaced by the 2026-04-03 restart.

## Timeline

| Date | Event |
|---|---|
| 2025-08-04 | Research sections of the first technical plan drafted and condensed with Gemini |
| 2026-03-08 to 03-09 | Planning in a claude.ai project, with execution playbook v4 (dated 2026-03-09) and a numbered decision log |
| 2026-03-11 | Decision DLOG-017 sets the build order, simulator, then ML, then FPGA |
| 2026-03-26 to 04-02 | First attempts in three repos (38 commits), later archived |
| 2026-04-01 to 04-02 | Gemini Deep Think review of the training-loop and dataset designs, then of the draft report |
| 2026-04-03 | Restart in `nv-sensor-sim`, `odmr-edge-ml` and `polarfire-hybrid-control` |
| 2026-04-04 | Review findings turned into code changes in all three repos |
| 2026-05-01 | Verification workbench started, with a full claim audit of my technical report the same day |
| 2026-06 | Production PolarFire SoC silicon confirmed on the dev kit, then two-slot PID integration |
| 2026-06-29 | `odmr-vector-tracking` started |
| 2026-07-01 to 07-02 | Per-claim inventory of every repo, plus watchdog trip time and a kit-resident paced loop measured on silicon |
| 2026-07 | Busiest month, with 56 commits in the tracker repo and 24 each in the simulator and FPGA repos |
| 2026-08 | Loaders for five external ODMR and magnetometry datasets, plus two-sample test code to compare the simulator against them (results not yet committed) |
| 2026-09 | Dispatch tooling hardened: atomic ID reservation, leases and an 18-group test |


Each folder of this repository keeps the original commit history of the repository it came from, with original dates. In `workers/polarfire-hybrid-control` and `orchestrator` some planning documents and vendor tool logs were left out of the history; dates and authors are unchanged. The first attempts are in [`archive/v0`](../archive/v0) and the planning phase is in [`planning/`](../planning).
