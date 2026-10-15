# The 90-day plan, March 4–11, 2026

Versions 1 through 3 were developed on March 4–5 in one claude.ai project chat. A version 3.1 physics addendum followed Gemini reviews on March 5; [version 4](../docs/90-day-execution-playbook-v4.md) is dated March 9. The version 3 stakeholder section is not quoted because it names a person. These were plans for a [not-selected proposal](../../docs/proposal/README.md), with no award or contract.

Quotes retain source spelling and punctuation. `[…]` marks cuts. Context and outcomes are editorial summaries, not additional chat messages. Sources are private exports, not published. For these exported chats: model version not recorded in the export. Model recommendations are historical claims, not verified results.

[Conversation record](README.md)

<a id="p1"></a>

## Version 1 to version 2: a scope cut

**Date and context.** March 4, 2026. Jason asked whether another research report justified revising the plan.

**Jason**

> does this ad any added value> if so please refactor the phase 1 playbok

**Claude (claude.ai project)**

> Yes, it added real value. Here's what changed between v1 and v2 of the playbook:
> 
> […]
> 
> 2. **The "don't do PINN" warning** saves you from a tempting rabbit hole.
> 
> […]

**What happened next.** The [playbook](../docs/90-day-execution-playbook-v4.md) begins its What NOT to Build section with this cut: no physics-informed network for ODMR.

<a id="p2"></a>

## The simulator’s physics is too clean

**Date and context.** March 5, 2026. Jason submitted a structured physics-review prompt to Gemini; the selection omits its unsupported contract framing.

**Jason — structured review prompt**

> You are reviewing the technical physics and mathematics of a 90-day SBIR Phase I execution plan for an AI-controlled NV-diamond magnetometer system.
> 
> […]

**Gemini Apps**

> Direct answer: The simulation assumes idealized, perfectly symmetric ODMR lineshapes, but real continuous-wave bulk ensembles suffer from severe asymmetric distortions.
> 
> […]
> 
> Recommended action: Deliberately corrupt the synthetic data generator.
> 
> […]

**What happened next.** Version 4 added asymmetric lineshape generation ([DLOG-009](../docs/decision-log.md#dlog-009)). Months later, [comparison with four public measured datasets](../../workers/nv-sensor-sim/docs/external_validation_results.md) found default simulated lines 2 to 11 times too narrow where linewidth estimates were meaningful.

<a id="p3"></a>

## One model triages another’s review

**Date and context.** March 5, 2026. Jason asked Claude to respond to Gemini’s high-risk findings and draft a follow-up.

**Jason**

> draft the follow up prompt. Seperatly it seems like i have a lot of high risk components?

**Claude (claude.ai project)**

> […]
> 
> None of the HIGH findings say "your approach is fundamentally wrong" or "this can't work." They say "if you present it the way the playbook currently frames it, a physics-literate reviewer will catch the problems." That's exactly the kind of thing you want to find at Day 0, not Day 85.
> 
> […]

**What happened next.** Claude sorted the findings into presentation fixes and data-generator fixes, then drafted a follow-up prompt. The [next selection](#p4) records Gemini’s response to a closely matching prompt; the connection is inferred from their dates and wording.

<a id="p4"></a>

## The proposal’s noise claim is narrowed

**Date and context.** March 5, 2026. Task 2 of the [2025 technical volume](../../docs/proposal/README.md) promised noise suppression above 10×. The prompt was probably drafted in [entry 3](#p3), inferred from dates and wording.

**Jason — probably the prompt drafted in entry 3 (inferred)**

> […]
> 
> I now want you to rigorously analyze WHERE the neural network adds value over PID in this specific NV-diamond magnetometer architecture. The goal is to reframe the project's performance claims around physics-grounded advantages rather than an indefensible blanket "10× noise suppression."
> 
> […]

**Gemini Apps**

> […]
> 
> Direct answer: No. A linear PID controller mathematically cannot correct heading error because it is a 1D tracking loop that is blind to the underlying multivariable quantum physics.
> 
> […]

**What happened next.** The network was reframed as a nonlinear inverter for errors a PID cannot remove ([DLOG-010](../docs/decision-log.md#dlog-010)). The above-10× claim was narrowed to the slow-drift band, not dropped ([DLOG-014](../docs/decision-log.md#dlog-014)); this planning change did not demonstrate the target.

<a id="p5"></a>

## Phase I was planned as analysis only

**Date and context.** March 8, 2026. Jason asked whether an older development kit limited work under the unfunded Phase I plan.

**Jason**

> […]
> 
> My understanding is that it is old and has less support for items such as the new vectorblox 3.0 etc.
> 
> […]
> 
> So does this matter at all for phase 1?
> 
> […]

**Claude (claude.ai project)**

> Your playbook is pretty clear: **Phase 1 is an analysis deliverable, not a hardware demo.** You produce timing reports and power estimates from Libero SoC v2025.2 vendor tools targeting the RTPF500ZT device. The actual FPGA programming and on-board execution is Phase 2.
> 
> […]

**What happened next.** The build went past that plan: the controller [ran on PolarFire SoC silicon](../../README.md) with replayed synthetic spectra. That result did not involve a connected diamond sensor.

<a id="p6"></a>

## Asking for limits, not praise

**Date and context.** March 8, 2026. Jason asked where the proposed architecture would fail to transfer to other quantum sensors.

**Jason**

> […]
> 
> I want to broaden this architecture to serve as a general-purpose quantum sensor error mitigation platform.
> 
> […]
> 
> not marketing optimism, but honest signal-processing-level analysis of where the analogy holds, where it breaks, and what architectural modifications would be required.
> 
> […]

**Gemini Apps**

> […]
> 
> Fundamentally Different Architectures: Cold-atom interferometry strictly requires time-series sequence modeling to map continuous classical accelerometer histories to a discrete atomic phase. This demands recurrent networks (RNNs/LSTMs) or dilated 1D-CNNs, which are fundamentally incompatible with your current 1D spatial MLP/CNN topology.
> 
> […]

**What happened next.** The cross-sensor idea stayed a short future-work subsection in the [playbook](../docs/90-day-execution-playbook-v4.md). Phase I execution remained NV-diamond only.

<a id="p7"></a>

## The safety design

**Date and context.** March 9, 2026. Gemini’s follow-up review proposed bounds on the neural correction and a classical fallback.

**Gemini Apps**

> […]
> 
> the system must implement a Simplex Run-Time Assurance (RTA) Architecture with bumpless transfer.
> 
> […]
> 
> The AI’s output is treated strictly as an additive exogenous feedforward term ($u_{AI}$). Before being summed with the classical PID output, $u_{AI}$ passes through a hard digital limiter
> 
> […]

**What happened next.** Version 4 adopted the bounded safety design ([DLOG-011](../docs/decision-log.md#dlog-011)). The [FPGA worker](../../workers/polarfire-hybrid-control/README.md) later measured a median watchdog trip time of 2.000 ms over 120 trips; actual fallback remains software-mediated.

<a id="p8"></a>

## Version 4, against the model’s recommendation

**Date and context.** March 9, 2026. Claude recommended another addendum; Jason instead requested a consolidated version 4.

**Claude (claude.ai project)**

> […]
> 
> **My recommendation: Don't create a new playbook version. Create a new addendum (v3.2).**
> 
> […]

**Jason**

> how about you make all recomended changs in both the latestest fastrack version and the adendum and then include everything ( the changes and everything that remained the same  and i stil need to know from previous versions) in a new version 4 and version 4 adendum?
> 
> […]

**Claude (claude.ai project)**

> […]
> 
> **V4 Playbook** — the complete 90-day execution guide.
> 
> […]
> 
> One document, read top to bottom, execute.
> 
> […]

**What happened next.** The consolidation is reflected in [version 4](../docs/90-day-execution-playbook-v4.md), now in the planning documents. The retained chat sets the consolidation request; it does not contain the complete build of the final document.

<a id="p9"></a>

## Claude reviews ChatGPT’s repository plan

**Date and context.** March 11, 2026. Jason brought a ChatGPT-generated repository plan to Claude and explained his limited repository experience.

**Jason**

> I give the most advanced chatgpt model, pro5.4 The v4 plus addedum and this was teh plan on how to create the repos needed to start woking on it. Im used to using jupyternotebooks and am only a little familier with repos.
> 
> […]

**Claude (claude.ai project)**

> […]
> 
> **The file trees are too deep.** Repo 1 has ~50+ files scaffolded.
> 
> […]
> 
> My recommendation: scaffold the top-level structure and the 5-8 files you'll actually touch in the first two weeks, then grow organically.
> 
> […]

**What happened next.** The repositories were built one at a time, simulator first, as the [case study](../../docs/case-study.md#how-i-ran-it) records.

