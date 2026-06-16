# Agent Ground-Truth Contract

This project mixes live FPGA state, generated Libero artifacts, primary Microchip
documents, project runbooks, and prior assistant transcripts. Those sources are
not equally authoritative. Use this contract before declaring anything confirmed
or ruled out.

## Claim Labels

- **HYPOTHESIS** — plausible, not yet verified.
- **CONFIRMED** — backed by live silicon, generated seed_7 artifacts, SDK source,
  or primary Microchip documentation.
- **FALSIFIED** — directly contradicted by one of those ground-truth sources.
- **STALE/RISKY** — inherited from memory, old docs, previous plans, or transcripts.

## Source Priority

1. Live silicon reads, SmartDebug/FlashPro observations, raw target logs, raw
   register dumps.
2. Generated seed_7 Libero artifacts on bee: `component/work/**`, `designer/**`,
   MSS cfg XML, timing reports, probe DB output.
3. Version-matched SDK source and primary Microchip docs in the corpus: MSS TRM,
   MSS Configurator UG, CoreVectorBlox handbook, SDK `vbx_cnn_api.c`.
4. Canonical Microchip reference design under the installed Libero/SmartHLS tree.
5. Project docs, runbooks, memories, and previous assistant transcripts.
6. Inference.

## Conclusion Gate

Do not say "ruled out", "confirmed", or "root cause" unless the exact evidence is
cited: filepath plus line/grep, command output, register address plus raw value,
SmartDebug probe name plus value, or primary-doc section/table.

Before carrying forward a prior conclusion, search for contradictions in the
corpus and generated seed_7 artifacts using concept synonyms. If local docs
disagree with generated RTL/config or a primary document, call that out explicitly
and follow the primary/generated artifact.

For every root-cause claim, record:

- observed symptom
- hypothesis
- prediction if true
- test performed
- raw result
- confidence
- next falsifier

Do not update memory or durable docs with a root cause until the claim has
survived this gate.

## Autonomous Debug Operating Envelope

When Jason grants a debug direction in auto mode, the agent should continue
through the next cheapest evidence-producing steps without asking for approval at
every discriminator. Use the source priority and conclusion gate above while
moving.

Green-zone actions may proceed autonomously:

- read-only live target inspection: SSH, register dumps, logs, dmesg, sysfs,
  UIO/udmabuf metadata, bounded read-only SmartDebug/FlashPro observations
- bounded reproduction probes through already-proven software paths, with clean
  timeouts and raw logs
- local or bee-side source/artifact inspection, corpus searches, generated RTL
  and report diffs, SDK/reference-design comparisons
- building analysis tools, probe binaries, simulation/test utilities, and branch
  bitstreams for inspection, as long as they are not programmed onto hardware
- updating repo docs, handoff notes, changelogs, and wiki summaries with dated,
  evidence-labeled findings

Yellow-zone actions may proceed only if the live prompt explicitly pre-approves
the action class and the implementation is reversible, bounded, and reported:

- temporary MSS/FIC/MPU diagnostic writes with save/restore, no LOCK bits, trap
  cleanup, raw before/after values, and no unrelated registers touched
- runtime overlays or driver/device-tree tweaks that are removable without
  reprogramming the FPGA

Red-zone actions require stopping for Jason approval:

- programming FPGA fabric, eNVM, sNVM, SPI flash, HSS, U-Boot, Linux images, or
  any persistent boot artifact unless the live prompt has explicitly approved
  that action class
- setting LOCK bits, changing SEG mappings, broad MSS config changes, or writes
  whose blast radius is not proven and reversible
- touching the severed PID slave at `0x60001000` unless Jason explicitly
  reauthorizes it for a named experiment
- re-synth/reprogram decisions that would replace the trusted seed_7 fallback
- destructive git/filesystem operations, cleanup of unknown files, or overwriting
  user/other-agent changes

Escalate automatically through the next cheapest discriminator when the current
test falsifies a hypothesis. Stop only when a red-zone action is needed, the
hardware appears unstable, evidence contradicts the operating envelope, or a
root-cause/fix claim is ready for Jason review.

Changing hardware state is allowed when it is a purposeful, logged,
rollback-safe experiment. Do not avoid hardware work merely because it changes
state. Avoid unlogged, irreversible, or non-discriminating changes. Before any
persistent or broad hardware-state change, capture the current artifact identity
and hash, exact rollback artifact/path/command, current relevant register/config
baseline, exact change command/script, expected discriminator, and stop
condition.

## Current Cautionary Example

Do not treat "FIC2 MPU is open" as true unless the actual TRM-defined FIC2 MPU
block is read and decoded. A prior 16-region "FIC2 MPU" read was suspect because
FIC2/MPU3 is documented as a different block than FIC0/FIC1. Always reconcile
MPU/FIC/SEG claims against the MSS TRM register map and live register values.
