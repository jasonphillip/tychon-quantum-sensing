# Learning and waiting, August 2025–February 2026

After the 2025 proposal and before the March 2026 playbook, Jason learned the PolarFire toolchain and NV physics with chat models. The selection decision was delayed; no award existed. The [proposal archive](../../docs/proposal/README.md) does not establish the exact submission date.

Quotes retain source spelling and punctuation. `[…]` marks cuts. Context and outcomes are editorial summaries, not additional chat messages. Sources are private exports, not published. For these exported chats: model version not recorded in the export. Model recommendations are historical claims, not verified results.

[Conversation record](README.md)

<a id="a1"></a>

## Choosing a grounded tool for vendor manuals

**Date and context.** August 14, 2025. Jason asked how to use vendor documentation while learning FPGA deployment; ChatGPT recommended a Project.

**Jason**

> Specifically the polarfire icicle kit es with soc.
> 
> […]
> 
> i know little about fpgas so i want you to search the web to find the best way to use the docs and guides provided by microchip.
> 
> […]
> 
> should i use something like NOtebook LLM to upload the docs and use that LLM or do something like chatgpt projects where the docs are uploaded

**ChatGPT**

> - **Google NotebookLM**: optimized as a “notebook over your sources,” with generous limits (**up to 50 sources / notebook, ~25M words total**), great for study guides/briefings. Less code-assistant oriented, but excellent for synthesis across many docs.
> 
> […]
> 
> **My recommendation for you:** start a *ChatGPT Project* called “Icicle + VectorBlox Bring-Up” and upload the seven docs above. It’s tighter integration for code snippets, terminal steps, and quick error triage while you’re actually flashing/programming.
> 
> […]

**What happened next.** A month later, Gemini recommended a docs-grounded notebook ([A2](#a2)). The [method record](../../docs/method.md#grounded-qa-over-vendor-manuals) says Jason kept NotebookLM for the manuals.

<a id="a2"></a>

## Thin training data favours grounded answers

**Date and context.** September 26, 2025. Jason compared assistant methods for a vendor ecosystem with limited public training data.

**Jason**

> Can you find out if Claude is better at fpga design and implementation than other methods such as notebook llm with docs(rag), chatgpt 5 pro, chatgpt projects, or gemeni. Keep in mind this is for a smaller manufacturer with smaller training data (microchip polarfire icicle kit with soc and vectorblox for the CNN on a startracker). Please tell me how each method would perform on each step needed.

**Gemini Apps**

> For the specific scenario of a smaller manufacturer working with the Microchip PolarFire Icicle Kit and VectorBlox, Claude is likely not the best standalone option.
> 
> […]
> 
> The critical limiting factor is the specialized nature of the hardware and the scarcity of public training data.
> 
> […]
> 
> The Winner: Notebook LLM with Docs (RAG)
> 
> […]

**What happened next.** The [method record](../../docs/method.md) describes learning from vendor manuals through grounded Q&A. Jason later described this experience as one reason for [local, source-limited critics](../../orchestrator/README.md#why-the-critics-stay-local-and-off-the-web); that account is not a measured comparison of assistants.

<a id="a3"></a>

## Waiting on a delayed decision: build first

**Date and context.** November 18, 2025. Jason said the proposal selection decision was delayed by the government shutdown and program renewal.

**Jason**

> My SBIR has been delayed for a few months due to the renewal of the SBIR program abd the government shutdown down.
> 
> […]
> 
> What should be my biggest priorities while I wait? Network with people or building my prototype MVP?
> 
> […]

**ChatGPT**

> Do both, but not equally. For the next 6 weeks, bias **~70% build / 30% outreach**.
> 
> […]
> 
> Why: your **biggest technical risk is the synthetic‑to‑real gap** for the AI control loop.
> 
> […]

**What happened next.** The [case study](../../docs/case-study.md#how-i-ran-it) records independent work while funding remained unavailable. The repositories were built in sequence: simulator, ML, then FPGA.

<a id="a4"></a>

## A model corrects the control-loop framing

**Date and context.** January 5, 2026. During a proposal-related discussion, Jason asked whether a control-loop visual was accurate.

**Jason**

> would you say this visual is accurate? If not what is wrong with it? Can you give 3 prompts to incoporate any of your changes?

**ChatGPT**

> Partly accurate at the “control-theory” level (fast inner loop + slower supervisory/adaptive loop), but it’s **not accurate enough for an NV-diamond magnetometer** and can be misleading in a few specific ways.
> 
> […]
> 
> 3) **PID is not the core primitive most people associate with NV tracking**
> - The inner loop is commonly a **frequency-tracking loop** (often lock-in-derived error → servo a VCO/NCO), i.e., PLL-like behavior, sometimes with PID elements.
> 
> […]

**What happened next.** Two months later, a Gemini review made the related point that a one-dimensional PID cannot correct heading error ([playbook entry 4](playbook-creation-2026-03.md#p4)). [DLOG-010](../docs/decision-log.md#dlog-010) records the resulting change in the network’s proposed role.

