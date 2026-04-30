# Corpus-Backed Improvement Plan

This is the follow-on plan after `docs/corpus_grounded_evaluation.md`. It does
not change architecture in this branch; it ranks the next implementation work.

## Priority 1: Real AXI4-Lite PID Control Path

Replace the current FIC_0 signal tap experiment with a real address-decoded
AXI4-Lite slave connection for `nv_pid_top`.

Acceptance criteria:

- `Kp`, `Ki`, `Kd`, `out_min`, `out_max`, and `inner_clamp_setpoint` are in a
  documented FIC_0 address window.
- Full write and read channels are connected: AW, W, B, AR, and R.
- Software can write non-default values and read them back.
- Report audit still finds a nontrivial `nv_pid_top` footprint and positive
  slack after removing `patch_smartdesign_axi_target_experiment.py`.

## Priority 2: Observable PID Status

Add readback/status registers that make the control loop semantically
observable, not just structurally present.

Recommended fields:

- coefficient shadows for `Kp`, `Ki`, and `Kd`
- current `error`
- integrator and derivative terms
- pre-clamp and post-clamp outputs
- saturation flag and saturation-event counter
- watchdog timeout and cooldown counters

Acceptance criteria:

- Status changes when software changes coefficients or input stimulus.
- The report audit has no PID-scoped pruning of these status registers.

## Priority 3: CoreVectorBlox Watchdog Source

Replace MSS GPIO heartbeat stimulus with CoreVectorBlox `output_valid`.

Implementation requirement:

- Treat `output_valid` as a level-held completion indication.
- Add edge detection so each completed inference produces one watchdog refresh
  event, unless the intended behavior is deliberately level-held reset.
- Synchronize the pulse if watchdog and CoreVectorBlox clocks differ.

Acceptance criteria:

- Testbench covers repeated completion events, missed completions, and stuck
  high `output_valid`.
- Libero reports preserve `watchdog_timer_0`.

## Priority 4: Verification Gates

Promote the new local checks into the normal workflow.

Acceptance criteria:

- `make verify-local` passes before report archival.
- Beelink runs record `shls sw_run`, synthesis status, report audit output, and
  exact run/seed tag.
- `tools/audit_libero_reports.py` classifies known paper-shell bundles as
  baseline/paper-shell and the real closure as real PID evidence.

## Priority 5: Documentation Tightening

Align docs with the corpus-backed evidence level.

Acceptance criteria:

- README guarantees are scoped to documented assumptions.
- Power numbers are labeled as default-toggle estimates until workload-driven
  SmartPower exists.
- Phase I vs Phase II wiring limitations are visible near build/reproduction
  instructions.
