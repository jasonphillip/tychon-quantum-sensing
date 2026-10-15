# 00 — The unfunded proposal: origins, a scope change and drafting

- Date: 2025-07-02 to 2025-08-04.
- Context: Jason prepared the SBIR Phase I proposal later identified as FX255-PCSO2-0044. It was not selected.
- Shows: the cryogenic origin, a room-temperature pivot, requests to check claims, and a draft shared before the deadline.

**Attribution.** These eight selections come from Gemini Apps exports, a Claude web conversation export, and one email.
For both AI platforms: **model version not recorded in the export**.
No model version is inferred. Each AI selection pairs Jason’s prompt with selected model reply text.
The email is Jason’s wording, not model output. Private recipients and corpus paths are omitted.

Quotes retain source spelling. Cuts are marked `[…]`.
These excerpts show drafting activity; they do not prove a submitted version or a technical result.
See the [proposal crosswalk and decision letter](../../docs/proposal/README.md).

### 1. Begin with a 20 K superconducting-qubit controller — July 2, 2025

> **Jason, in Gemini Apps:**
>
> Im interested in submitting my first sbir open topic phase 1 proposal for the spaceforce.   I have a sample of what i might want my topic to be. I would like your help on telling me if this soloution already exists, go into detail of what the siloution might involve along with a proposal one month timeline of submitting it and a 3 month timeline of what it would look likdoing the actually phase 1, and also let me know anything i can be overlooking here: This project aligns with the OUSD(R&E) Quantum Science CTA and USSF mission area Space Access, Mobility & Logistics (SAML). We will prototype a radiation-tolerant, re-programmable FPGA controller that operates below 20 mW at 20 K to stabilize superconducting qubits for on-orbit quantum time-transfer experiments. The Phase I objective is a cryostat-validated breadboard achieving <1 µs closed-loop latency and <10⁻⁶ logical error rate, paving the way for a Phase II flight unit that enables sub-nanosecond clock synchronization across proliferated LEO.

> **Gemini Apps — model version not recorded in the export:**
>
> Yes, your proposed solution appears to be novel and addresses a critical need for the Space Force. While individual components of your idea exist, a single device that is a radiation-tolerant, re-programmable FPGA controller operating below 20 mW at 20 K for stabilizing superconducting qubits does not currently exist as a commercial off-the-shelf product. This lack of an existing integrated solution makes it a strong candidate for an SBIR topic.
>
> […]

The novelty assessment and performance targets are historical model output, not independently verified findings.

### 2. Narrow the idea to quantum payloads — July 5, 2025

> **Jason, in Gemini Apps:**
>
> This report is for quantum and rf payloads. What would be different if it was only geared to quantum payloads?

> **Gemini Apps — model version not recorded in the export:**
>
> […]
>
> - A More Urgent Latency Requirement: The need for on-orbit AI would be framed not just as a way to reduce data downlink, but as a non-negotiable physical requirement. Many quantum protocols, especially for error correction and state stabilization, demand a closed-loop feedback time of less than one microsecond—a timescale that is impossible to achieve without a controller physically co-located with the sensor inside the cryostat.
>
> […]

This records the model’s cryogenic-control framing. It does not establish a universal latency or cryostat requirement for quantum sensing.

### 3. Redirect the research to a room-temperature FPGA — July 27, 2025

> **Jason, in Gemini Apps:**
>
> Thanks!  Can you now help me modify a prompt for a LLM deep research? I would llike the following prompt to no longer focus on cryo tempts and instead room tempature fpga with quantum sensors at both room temp and cryo temps which would use the room temp fpga as the classical computer for the quantum sensors for navigation […]

> **Gemini Apps — model version not recorded in the export:**
>
> […]
>
> (3) Research the use of INT8-quantized CNNs on room-temperature FPGAs (specifically PolarFire/RTG4) for tasks relevant to quantum navigation, such as quantum state discrimination or signal processing from atomic interferometers. Collect metrics on inference latency, power, resource use, and accuracy.
>
> […]

A connection between this request and the files supplied on July 28 is an **unverified inference**.
Later work [built and measured INT8 CNN inference on PolarFire](../../docs/model-to-v250.md), using synthetic or replayed inputs. That does not demonstrate reliable live sensing.

### 4. Refactor the proposal for room temperature — July 28, 2025

> **Jason, in Claude web:**
>
> Can you refactor my proposal draft to room temp instead of 77k? I included 3 deep research outputs from my drive that should have the info you need to refactor.

> **Jason, in Claude web, after supplying research files:**
>
> Here they are!

The export lists these three research files:

- `CHATGPT JULY27 2nd Agent Spacebased quantum sensors research.pdf`
- `july 27 GEMENI ROOOM TEMP deep research  FPGA Quantum Sensor Control Research.docx`
- `JULY 27 No.2 Warm temp GEMENI Quantum Navigation FPGA Control Dossier deep research.docx`

> **Claude web — model version not recorded in the export:**
>
> […]
>
> ### 2. **Power Specifications Updated**
> - Compute power: <15 mW → <5W (based on PolarFire benchmarks)
> - Total system: ~30 mW → <12W
> - Aligned with research showing 3-4W for CNN inference on PolarFire
>
> […]
>
> ### 5. **Performance Metrics**
> - Maintained <150 μs closed-loop latency (validated by research)
> - CNN inference <2 ms (supported by VectorBlox benchmarks)
> - Throughput ≥300 fps for sensor processing
>
> […]

These are proposal targets and model assertions about research. Compare the [proposed power and latency with measured evidence](../../docs/proposal/README.md#proposal-claims-versus-delivered-state).

### 5. Ask for flaws and number checks — August 1, 2025

> **Jason, in Gemini Apps:**
>
> Can you look at my sbir proposal and help me improve it? Look for any flaws in it and also verify my numbers are correct especially for what im promising to deliever.
>
> […]

> **Gemini Apps — model version not recorded in the export:**
>
> This is an exceptionally strong and well-structured SBIR proposal.
>
> […]

The praise is preserved as model output. It is not evidence that the proposal’s numbers were correct.
The later [engineering decisions](../../docs/engineering-decisions.md) and [proposal crosswalk](../../docs/proposal/README.md) show why that distinction matters.

### 6. Ask how difficult the complete system would be — August 2, 2025

> **Jason, in Gemini Apps:**
>
> On a scale on 1 to 10 how hard is it to build a novel PNT system quantum based sensor for space systems

> **Gemini Apps — model version not recorded in the export:**
>
> On a scale of 1 to 10, building a novel PNT system using quantum-based sensors for space systems is a 10/10 in difficulty. 🤯
>
> This task represents one of the most formidable scientific and engineering challenges available today, pushing the absolute limits of physics, engineering, and materials science. It combines the extreme difficulty of developing cutting-edge quantum technology with the unforgiving constraints of space deployment.
>
> […]

This is the model’s qualitative difficulty assessment, not a measured result or a feasibility finding.

### 7. Condense two research outputs — August 4, 2025

> **Jason, in Gemini Apps:**
>
> I need help with my sbir proposal.  I have two seperate deep research outputs for the RELATED WORK (DUAL-USE) section […]
>
> I need you to go through both llm deep research outputs to create a much shorter version that i can put into my proposal.
>
> […]

> **Gemini Apps — model version not recorded in the export:**
>
> […]
>
> Jason Phillip (Principal Investigator)
>
> Designed and field-tested a Convolutional Neural Network (CNN)-based star-tracker on a Microchip RT PolarFire System-on-Chip (SoC). This effort involved generating a 200,000-image synthetic dataset for model training and achieving 0.12-pixel centroid accuracy. This work demonstrates complete mastery of the toolchain […]

This is historical model wording about prior work. It does not validate the proposed quantum sensor or establish an SBIR award.

### 8. Share the draft before the stated deadline — August 4, 2025

> **Jason, email to a colleague:**
>
> […]
>
> I attached the proposal if you wanted to take a look at it.  It is due
> tomorrow at noon and Ill probably add some pictures to it as well.

The exported message is dated August 4 at 23:06; its displayed timezone is not recorded.
It supports a draft-sharing event. It does not establish when the proposal was uploaded or submitted.

[Excerpt index](README.md) · [Conversation index](../conversations-index.md) · [Proposal crosswalk](../../docs/proposal/README.md)
