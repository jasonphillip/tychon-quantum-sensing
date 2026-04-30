# Phase I Closeout Findings

For the Phase I Final Report and Phase II planning.

The r6_s25 closure numbers (slack, LUT/DFF/Math, power) and the
discriminating gain-fold experiment are not re-derived here — see the
existing DLOG entries and Final Report. This document is the
corpus-grounded audit-and-design layer that landed on top of r6_s25, and
its implications for Phase II scoping.

## Audit calibration is the headline corpus contribution

On the same `2026-04-29-pid-real` bundle that the Final Report cites
(45-row `nv_pid_top` hierarchy, `LUT=2390 / DFF=1728 / Math=25`, slack
`+0.728 ns`), two corpus-grounded audits disagree by 4 critical-pruning
hits and a strict-mode pass/fail. The disagreement is not about the
synthesis evidence — both audits read identical numbers. It is about
which Synplify message IDs constitute coefficient constant-folding.
Codex's audit treats BN115 as fail-fast and includes `legup_mult` in the
PID coefficient regex; mine demotes BN115 to a warning and excludes
`legup_mult`. The corpus itself supports the latter calibration:
`preventing-synplify-constant-folding-smarthls-pid.md:111` flags BN115
as "Not located verbatim in the public OEM reference ... verify against
local log," and the verbatim-confirmed cascade is CL189 → CL260 →
BN362, with CL279 named in the survival checklist
(`preserving-real-smarthls-pid-datapath.md:98`). Codex's gate would
declare a healthy r6_s25 closure pruned-paper-shell on a sealed-and-
forwarded report bundle; mine wouldn't. For Phase II this means the
strict-mode gates baked into the Beelink overnight runner can be relied
on without manually re-vetting BN115/`legup_mult_*` hits each iteration.

## New HDL is committed and testbench-validated; netlist validation is Phase II

The Phase B HDL — `libero/hdl/pid_csr_block.v` (16 KiB AXI4-Lite slave
with coefficient shadows + status CSRs, AXI4-Lite-spec-compliant WSTRB
cited to `fpga-hls-docs:2594-2596`) and `libero/hdl/vbx_pulse_gen.v`
(2-FF synchronizer + rising-edge detector for CoreVectorBlox
`output_valid`, cited to `HB0919:361/499/784` and `preserving:121-125`)
— is committed and passes `make hls-test-local` including three new
edge-case tests (D.1 repeated completions, D.2 missed-then-recovered,
D.3 stuck-high firmware no-clear). It is **not** in the synthesized
netlist that the Round 2 closure measured: that closure ran against the
existing Beelink Libero project state, which was not re-imported with
the new HDL. The path to closing this gap is documented in
`docs/smartdesign_two_slot_canvas_runbook.md` as a GUI/Tcl exercise
that the corpus says cannot be reliably regex-patched
(`preserving:105-119`). The runbook prescribes instantiating
`CoreAXI4Interconnect` with two distinct slave slots for `nv_pid_top`'s
`axi_target` and the new `pid_csr_block`, and acceptance is software
write-then-readback through both slaves — which is the corpus's named
architectural proof of survival (`preserving:97`) and the gate that
Codex's "production replacement" labeling glossed over. The Phase I
tap-style patch (`patch_smartdesign_pid_csr.py`) is committed as a
bring-up shortcut, clearly labeled Phase I in its docstring.

## Phase II scope: the Residual Proof Obligations table

`docs/safety_architecture.md` now carries the residual obligations the
Phase I "sector-bounded by design" claim is conditioned on. The README's
prior "AI cannot destabilize" wording was replaced with "sector-bounded
by design within the Phase I assumptions" and a pointer to this list.
For Phase II planning, these are the six items:

1. **Plant model identification** — Khalil §7. The Circle Criterion
   needs a sector-bounded plant; Phase I assumes "any positive gain."
2. **Quantitative phase margin under ZOH** — Khalil §11; Astrom-Hagglund
   Ch.6. Sampled-data closure changes the Nyquist contour.
3. **Bounded transport delay verification** — corpus ODMR closed-loop
   bundle. The 1 ms watchdog is the worst case; nominal delay must be
   measured.
4. **Derivative filter system identification** — Astrom-Hagglund Ch.4.
   Unfiltered first-difference amplifies high-frequency noise at the
   expanded ±30% authority.
5. **ReLU sector verification (NN-in-loop)** — recent arxiv 2025 on
   sector-bounded NN feedback (corpus). Trained-weight sector bound
   must be discharged before "sector-bounded NN" claim is admissible.
6. **Workload-driven SmartPower** — Microchip SmartPower UG 2025.2.
   Default-toggle is an upper bound, not an operational measurement;
   the README's "57% margin" stands as preliminary.

These are now part of the project's honest framing rather than implicit.
Phase II should pick these up in priority order: plant ID → ZOH/phase
margin → transport delay → derivative filter SI → ReLU sector → power.
The first four are loop-stability obligations and can be discharged from
existing instrumented bench data plus standard tools; the ReLU sector
and workload-driven power require new artifacts (trained weights with
proven sector bound, representative-trace VCD).

## Verification harness landed for Phase II reuse

A side benefit: the `Makefile` now exposes `verify-local`,
`verify-strict`, and `beelink-verify TAG=...`. The first two are
local g++ shim runs plus the corpus-grounded report audit and the
corpus-citation linter; the third pushes the current branch through
`shls sw_run` + Libero closure on Beelink and captures the bundle into
`libero/reports/<tag>/`. The Beelink runner's spark1-remote fallback
removes the GitHub-SSH-on-Beelink dependency that blocked every Codex
attempt. For Phase II, this lets a single command produce reproducible
closure bundles per iteration.
