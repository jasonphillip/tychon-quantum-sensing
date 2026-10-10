# Phase I Closeout Findings

For the Phase I Final Report and Phase II planning.

The r6_s25 closure numbers (slack, LUT/DFF/Math, power) and the
discriminating gain-fold experiment are not re-derived here — see the
existing DLOG entries and Final Report. This document captures the
audit-and-design layer that landed on top of r6_s25 and its
implications for Phase II scoping.

## Audit gate calibrated for Phase II CI

The synthesis audit gate (`audit_synthesis.sh`) introduced in the r6_s25
closeout was a one-shot checkpoint: grep `.srr` for `@W: CL168`, grep
`compile_netlist_hier_resources.csv` for required instance presence,
abort pre-PLACEROUTE if either fails. That gate is sufficient for the
single-event Phase I closure but unsuitable for Phase II CI in two
respects, both visible when the gate is re-run against the same
`2026-04-29-pid-real` bundle the Final Report cites:

1. **Speculative Synplify message IDs were treated as fail-fast.** The
   Synplify Pro reference manual verbatim-confirms `CL189` → `CL260` →
   `BN362` as the constant-folding cascade for unbound output ports and
   constant-tied inputs; `CL279` (output port not connected at top)
   belongs in the same set per the same reference. `BN115` and `MO129`
   are flagged in Microchip support material as "implementation-
   dependent" / "verify against local log" rather than verbatim-
   confirmed prune indicators. A fail-fast gate that includes the
   speculative IDs raises false alarms on legitimate netlists.

2. **`legup_mult_*` was in the PID coefficient regex.** SmartHLS-
   generated arithmetic primitives (`legup_mult_pipelined_inst`,
   `legup_mult_unsigned_15_17_1_23`, etc.) are arithmetic-primitive
   *alternatives* that Synplify routinely removes when only one variant
   is wired to the live datapath. This is benign optimization, not
   coefficient constant-folding. Including these names in the PID
   coefficient regex produces fail-fast hits on every real-PID-evidence
   bundle.

The new gate (`tools/audit_libero_reports.py`, entry point
`make verify-local`) treats `CL189` / `CL260` / `CL279` / `BN362` as
critical-fail and `BN115` / `MO129` as warnings unless `--strict-mo129`
is opted in; the PID coefficient regex matches only Kp / Ki / Kd /
clamp limits / inner_clamp_setpoint signals. Re-run on
`2026-04-29-pid-real`: zero critical pruning hits, one legitimate
`output_valid` wiring issue (CD279/CD638/CL240) inherent to the
unmodified Beelink Libero project state pending Phase II canvas
refresh. Re-run on the fresh `2026-04-30-claude-r2` closure (same
project state, all stages OK, Timing constraints met): same
classification, real-pid-evidence.

A separate criterion is now explicit: the architectural meaning of
"PID datapath survived synthesis" is not "the instance was preserved
against CL168." Per the AMBA AXI4-Lite specification on read/write
transaction symmetry, the architectural proof is software write-then-
readback through the AXI4-Lite slave. The `--check-readback-contract`
flag verifies that audited slaves expose readback paths for all gain
registers. The DLOG-033 axi_target tap defeats constant-folding (first
criterion); the Phase II two-slot CoreAXI4Interconnect canvas refresh
closes the second.

## New HDL is committed and testbench-validated; netlist validation is Phase II

Phase II carry-forward HDL — `libero/hdl/pid_csr_block.v` (16 KiB
AXI4-Lite slave with coefficient shadows + status CSRs, AXI4-Lite-spec
WSTRB) and `libero/hdl/vbx_pulse_gen.v` (2-FF synchronizer +
rising-edge detector for CoreVectorBlox `output_valid`, per HB0919
§2.4 / §361 / §499 / §784) — is committed and passes
`make hls-test-local` including three new edge-case tests (D.1
repeated completions, D.2 missed-then-recovered, D.3 stuck-high
firmware no-clear). It is **not** in the synthesized netlist that the
fresh closure measured: that closure ran against the existing Beelink
Libero project state, which was not re-imported with the new HDL.

The path to closing this gap is documented in
`docs/smartdesign_two_slot_canvas_runbook.md` as a GUI/Tcl exercise
that the Microchip SmartDesign User Guide indicates cannot be reliably
regex-patched against design-specific object names. The runbook
prescribes instantiating `CoreAXI4Interconnect` with two distinct
slave slots for `nv_pid_top`'s `axi_target` and the new
`pid_csr_block`. Acceptance is software write-then-readback through
both slaves, which is the AMBA AXI4-Lite-grounded architectural proof
of survival enforced by the `--check-readback-contract` audit gate.
The Phase I tap-style patch (`patch_smartdesign_pid_csr.py`) is
committed as a bring-up shortcut, clearly labeled Phase I in its
docstring; the production path is the Phase II canvas refresh.

A separate WSTRB attribution discipline matters here. The AMBA AXI4-
Lite specification governs the hand-written `pid_csr_block` slave
behavior. The SmartHLS User Guide governs `axi_target`-port WSTRB
rules on HLS-generated slaves (element-aligned). The CoreVectorBlox
HB0919 control-slave specification governs WSTRB on a different signal
path (all-or-nothing). Conflating these three rule sets produces
over-strict hand-written CSR slaves that return SLVERR on legitimate
AXI4-Lite-spec-compliant byte writes. The Phase B HDL keeps the rules
separate by source.

## Phase II scope: the Residual Proof Obligations table

`docs/safety_architecture.md` now carries the residual obligations the
Phase I "sector-bounded by design" claim is conditioned on. The
README's prior "AI cannot destabilize" wording was replaced with
"sector-bounded by design within the Phase I assumptions" and a
pointer to this list. For Phase II planning, these are the six items:

1. **Plant model identification** — Khalil §7. The Circle Criterion
   needs a sector-bounded plant; Phase I assumes "any positive gain."
2. **Quantitative phase margin under ZOH** — Khalil §11; Astrom-
   Hagglund Ch.6. Sampled-data closure changes the Nyquist contour.
3. **Bounded transport delay verification** — ODMR closed-loop FPGA-
   PID architecture references. The revised sub-2 ms watchdog target is the near-term worst case;
   nominal delay must be measured.
4. **Derivative filter system identification** — Astrom-Hagglund Ch.4.
   Unfiltered first-difference amplifies high-frequency noise at the
   expanded ±30% authority.
5. **ReLU sector verification (NN-in-loop)** — recent literature on
   sector-bounded NN feedback (2025). Trained-weight sector bound
   must be discharged before "sector-bounded NN" claim is admissible.
6. **Workload-driven SmartPower** — Microchip SmartPower User Guide
   2025.2. Default-toggle is an upper bound, not an operational
   measurement; the README's "57% margin" stands as preliminary.

These are now part of the project's honest framing rather than
implicit. Phase II should pick these up in priority order: plant ID →
ZOH/phase margin → transport delay → derivative filter SI → ReLU
sector → power. The first four are loop-stability obligations and can
be discharged from existing instrumented bench data plus standard
tools; the ReLU sector and workload-driven power require new
artifacts (trained weights with proven sector bound, representative-
trace VCD).

## Verification harness landed for Phase II reuse

The `Makefile` exposes `verify-local`, `verify-strict`, and
`beelink-verify TAG=...`. The first two are local g++ shim runs plus
the report audit and the citation linter; the third pushes the
current branch through `shls sw_run` + Libero closure on Beelink and
captures the bundle into `libero/reports/<tag>/`. The Beelink runner
fetches via the `ws1` SSH remote already configured on Beelink,
removing a GitHub-SSH-on-Beelink dependency that previously blocked
remote synthesis attempts. For Phase II, this lets a single command
produce reproducible closure bundles per iteration.
