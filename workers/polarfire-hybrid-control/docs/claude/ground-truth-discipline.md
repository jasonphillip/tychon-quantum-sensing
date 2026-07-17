# FPGA Ground-Truth Discipline

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

Durable repo copy: `docs/agent_ground_truth_contract.md`.

Treat prior notes, project docs, memories, and previous assistant conclusions as **orientation only** until reconciled against primary artifacts. This project has stale and contradictory local notes from multiple bring-up phases; generated seed_7 artifacts, live silicon, SDK source, and primary Microchip docs win.

Every significant FPGA/VectorBlox/Libero claim must be labeled:
- **HYPOTHESIS** — plausible, not yet verified.
- **CONFIRMED** — backed by live silicon, generated seed_7 RTL/config/reports, SDK source, or a primary Microchip document.
- **FALSIFIED** — directly contradicted by one of those ground-truth sources.
- **STALE/RISKY** — inherited from memory, old docs, previous plans, or prior chat transcripts.

Ground-truth priority, highest first:
1. Live silicon reads, SmartDebug/FlashPro observations, raw target logs, raw register dumps.
2. Generated seed_7 Libero artifacts on bee (`component/work/**`, `designer/**`, MSS cfg XML, timing reports, probe DB output).
3. Version-matched SDK source and primary Microchip docs in the corpus (MSS TRM, MSS Configurator UG, CoreVectorBlox handbook, SDK `vbx_cnn_api.c`).
4. Canonical Microchip reference design under the installed Libero/SmartHLS tree.
5. Project docs, runbooks, memories, and previous assistant transcripts.
6. Inference.

Conclusion gates:
- Do **not** say "ruled out", "confirmed", or "root cause" unless the exact evidence is cited: filepath+line/grep, command output, register address+raw value, SmartDebug probe name+value, or primary-doc section/table.
- Before carrying forward a prior conclusion, search for contradictions in the corpus and generated seed_7 artifacts using concept synonyms. If local docs disagree with generated RTL/config or a primary document, call that out explicitly and follow the primary/generated artifact.
- For every root-cause claim, record: observed symptom, hypothesis, prediction if true, test performed, raw result, confidence, and next falsifier.
- Do not update memory or durable docs with a root cause until the claim has survived the conclusion gate.

Current cautionary example: do not treat "FIC2 MPU is open" as true unless the actual TRM-defined FIC2 MPU block is read and decoded. A prior 16-region "FIC2 MPU" read was suspect because FIC2/MPU3 is documented as a different block than FIC0/FIC1. Always reconcile MPU/FIC/SEG claims against the MSS TRM register map and live register values.
