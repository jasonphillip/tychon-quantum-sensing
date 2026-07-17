# Autonomous FPGA Debug Operating Envelope

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

When Jason grants a debug direction in auto mode, keep moving without asking for
permission at every discriminator. Use this envelope unless Jason gives a
narrower one in the live prompt.

Green-zone actions may proceed autonomously:
- Read-only live target inspection: SSH, register dumps, logs, dmesg, sysfs,
  UIO/udmabuf metadata, bounded read-only SmartDebug/FlashPro observations.
- Bounded reproduction probes that use already-proven software paths and time
  out cleanly, including V250 control-page starts via the current Linux runtime.
- Local or bee-side source/artifact inspection, corpus searches, generated RTL
  and report diffs, SDK/reference-design comparisons.
- Building analysis tools, probe binaries, simulation/test utilities, and branch
  bitstreams for inspection, as long as they are not programmed onto hardware.
- Updating repo docs, handoff notes, changelogs, and wiki summaries with dated,
  evidence-labeled findings.

Yellow-zone actions may proceed only if the live prompt explicitly pre-approves
the action class and the implementation is reversible, bounded, and reported:
- Temporary MSS/FIC/MPU diagnostic writes with save/restore, no LOCK bits, trap
  cleanup, raw before/after values, and no unrelated registers touched.
- Runtime overlays or driver/device-tree tweaks that are removable without
  reprogramming the FPGA.

Red-zone actions require stopping for Jason approval:
- Programming FPGA fabric, eNVM, sNVM, SPI flash, HSS, U-Boot, Linux images, or
  any persistent boot artifact unless the live prompt has explicitly approved
  that action class.
- Setting LOCK bits, changing SEG mappings, broad MSS config changes, or writes
  whose blast radius is not proven and reversible.
- Touching the severed PID slave at `0x60001000` unless Jason explicitly
  reauthorizes it for a named experiment.
- Re-synth/reprogram decisions that would replace the trusted seed_7 fallback.
- Destructive git/filesystem operations, cleanup of unknown files, or overwriting
  user/other-agent changes.

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
