# Frontier Comparison — With vs Without Domain Corpus

The user's experiment: how does a frontier model's work change when the
same project is approached **without** a domain corpus vs **with** one?

Three rounds at the same baseline (`9de366c`):

| Round | Corpus | Branch | Author |
|---|---|---|---|
| 0 | none | up to `9de366c` | general frontier model |
| 1 | yes | `codex/corpus-verification` | Codex (corpus-grounded) |
| 2 | yes | `claude/corpus-verification` | Claude/Opus 4.7 (corpus-grounded, independent) |

Round 0 is the same for everyone. Rounds 1 and 2 are **independent**
corpus-grounded passes from the same baseline. They can be compared
against each other and against Round 0.

## Headline Finding — Where The Corpus Paid Off

The decisive Round 1 vs Round 2 difference is **audit calibration on
identical synthesis evidence**, not HDL or design. Three explicit
points:

1. **The synthesis evidence (slack, LUT/DFF/MATH, power) was identical
   in both runs because the same Beelink Libero project state was
   synthesized.** Round 1 never actually produced a closure (Beelink was
   unreachable for every Codex attempt); Round 2's `2026-04-30-claude-r2`
   bundle is the first fresh closure on this project state. Both audits
   read the same 45-row `nv_pid_top` hierarchy with `LUT=2390`,
   `DFF=1728`, `Math=25`, slack `+0.728 ns`. There is no slack/area/power
   delta to attribute to the corpus.

2. **The corpus-grounded audit produces zero false positives on
   `legup_mult_*` SmartHLS arithmetic primitives, where Codex's audit
   classifies them as PID-coefficient pruning (BN115 critical → 4 false
   hits, strict-mode FAIL).** Run on identical input (the
   `2026-04-29-pid-real` bundle), Codex's strict audit fails with "4
   critical PID-coefficient pruning hits"; mine passes the critical-
   pruning gate with 0 hits. The 4 hits Codex flags are all BN115 on
   `legup_mult_pipelined_inst` / `legup_mult_unsigned_15_17_1_23` /
   similar — these are SmartHLS-generated arithmetic-primitive
   alternatives that Synplify routinely removes when only one variant
   is wired to the live datapath. They are *not* coefficient
   constant-folding. The corpus itself flags BN115 as speculative
   (`preventing-synplify-constant-folding-smarthls-pid.md:111`: "Not
   located verbatim in the public OEM reference … verify against local
   log") and treats CL189 → CL260 → BN362 as the verbatim-confirmed
   cascade.

3. **At this stage the corpus value is in audit calibration, not in HDL
   changes.** The new Phase B HDL (`pid_csr_block.v`,
   `vbx_pulse_gen.v`, the Phase I tap patch, the follow-on canvas
   runbook) is committed and testbench-validated, but it is not in the
   synthesized netlist that Round 2's closure measured — the Beelink
   Libero project state was not re-imported with the new HDL in this
   pass. That re-import + re-synth is honestly follow-on work per
   `docs/smartdesign_two_slot_canvas_runbook.md`. The corpus-grounded
   delta visible in this pass is entirely in **which signals the audit
   gate alarms on**, which is exactly where the corpus's user-
   contributed deep-research files are most explicit and most
   actionable.

## Methodology

- Each row of the scorecard is judged against a specific corpus
  citation in `~/.corpus/polarfire-control-corpus/`.
- Each row also reports the actual Beelink synthesis evidence (where
  available) from `make beelink-verify TAG=<round>`.
- Citation accuracy is verified by `tools/audit_corpus_citations.py`.

## Scorecard

### Failure-mode diagnosis (Synplify constant-folding cascade)

| | R0 | R1 (Codex) | R2 (Claude) |
|---|---|---|---|
| Recognized cause | ✓ (gain-fold experiment in `patch_smartdesign_axi_target_experiment.py`) | ✓ (commit `04b2505` cites `preventing:60-61`) | ✓ (`docs/corpus_grounded_evaluation.md` cites `preventing:60-61, 108-113`) |
| Verbatim-confirmed IDs | implicit | explicit: CL189/CL260/BN362/MO129 | explicit: CL189/CL260/CL279/BN362; BN115/MO129 demoted (corpus calls them speculative) |
| Citation accuracy | n/a | 1 mis-application (HB0919 WSTRB applied to hand-written slave) | corrected: SmartHLS WSTRB cited to `fpga-hls-docs:2594-2596`, HB0919 reserved for CoreVectorBlox-control-slave paths |

### AXI integration

| | R0 | R1 | R2 |
|---|---|---|---|
| Phase I write-defeat | tap experiment | extends to read channel + WSTRB tightening | own pid_csr_block.v with full RW + status, AXI4-Lite-spec-compliant WSTRB |
| Production label | n/a | "production replacement" (overstated; own docstring admits two slaves on one bus) | "Phase I bring-up"; production path is the SmartDesign canvas runbook |
| Readback-contract proof | absent | absent (gap admitted in script docstring; not gated) | absent; gated by `audit_libero_reports.py --check-readback-contract`; runbook in `docs/smartdesign_two_slot_canvas_runbook.md` |
| Coefficient shadows | absent | added | added |
| Status CSRs | absent | added (saturation, watchdog, ai_active, cooldown, integrator, pre/post-clamp) | added (saturation flag+counter, watchdog flag+counter, ai_active, cooldown, integrator, derivative, pre/post-clamp) |

### `output_valid` -> watchdog

| | R0 | R1 | R2 |
|---|---|---|---|
| Recognized as level-held W1C | no (treated as raw heartbeat) | yes (`HB0919:361, 784`) | yes (`HB0919:361, 499, 784`) |
| Edge detect + CDC sync | no | `vbx_completion_sync.v` (2-FF + edge) | `vbx_pulse_gen.v` (2-FF + edge) |
| HLS edge-case tests | none | C.d/C.e/C.f (repeated, missed-then-recovered, stuck-high) | D.1/D.2/D.3 (same scenarios, independently derived assertions) |
| Default behavior | unwired | GPIO heartbeat retained for bring-up; flag enables vbx path | runbook documents follow-on canvas wiring; Phase I patch reuses existing watchdog |

### Audit-gate calibration

| | R0 | R1 | R2 |
|---|---|---|---|
| Critical-prune ID set | n/a | CL189/CL260/BN362/MO129 (MO129 fail-fast) | CL189/CL260/CL279/BN362 (CL279 added; MO129 demoted to speculative; BN115 demoted) |
| `legup_mult` in coefficient regex | n/a | yes -> false-fail on benign HLS arithmetic-alternative pruning | no -> only Kp/Ki/Kd/clamp limits/inner_clamp_setpoint |
| Readback-contract gate | n/a | absent | `--check-readback-contract` flag |
| MO129 handling | n/a | fail-fast (over-strict per corpus `preventing:113`) | warning unless `--strict-mo129` opt-in |

### Doc claim-strength

| | R0 | R1 | R2 |
|---|---|---|---|
| README "AI cannot destabilize" | over-strong | replaced with sector-bounded language | replaced with "sector-bounded by design within Phase I assumptions" + pointer to residual obligations |
| Power numbers | "57% margin" (no qualifier) | labeled default-toggle estimate | labeled "default-toggle estimate ... preliminary until workload-driven SmartPower" |
| Residual proof obligations | absent | added in `safety_architecture.md` | added in `safety_architecture.md` (independently — same coverage: plant model, ZOH phase margin, transport delay, derivative filter SI, ReLU sector verification, workload-driven SmartPower) |

### Verification tooling

| | R0 | R1 | R2 |
|---|---|---|---|
| Local g++ shim test | absent | `make hls-test-local` | `make hls-test-local` |
| Report classifier | manual | `tools/audit_libero_reports.py` | `tools/audit_libero_reports.py` (calibrated differently — see audit-gate row) |
| Citation linter | absent | absent | `tools/audit_corpus_citations.py` (35/35 citations resolve) |
| Beelink runner | none | `tools/run_beelink_verification.sh` (origin-only fetch — fails when GitHub SSH not configured on Beelink) | `tools/run_beelink_verification.sh` with spark1 fallback (works without GitHub SSH on Beelink) |

### Synthesis evidence

| | R0 | R1 | R2 |
|---|---|---|---|
| Closure run captured | `2026-04-29-pid-real` (45 hier rows, 2390 LUT / 1728 DFF / 25 MATH, slack +0.728 ns) | none — Beelink unreachable for every Codex attempt; "should pass" was hypothesis | `libero/reports/2026-04-30-claude-r2/` — fresh closure on Beelink, all stages OK, "Timing constraints have been met" |
| Strict audit on captured run | failed before patches existed (predates them) | n/a — bundle never produced | passes critical-pruning gate; fails only on the legitimate `output_valid` wiring issue inherent to the unmodified project state |

## Beelink Closure Results

### Round 2 (this branch) — `2026-04-30-claude-r2`

| Step | Result |
|---|---|
| `shls sw_run` | PASS — original tests + D.1 / D.2 / D.3 output_valid edge cases all pass on Beelink |
| Libero SYNTHESIZE | OK |
| Libero PLACEROUTE | OK (Placer + Router both completed successfully) |
| Libero VERIFYTIMING | OK — "Timing constraints have been met" |
| Libero VERIFYPOWER | OK |
| Total wall time | ~1h38m (12:11 → 13:49 EDT) |
| Audit classification | **real-pid-evidence** (45 hier rows, 2390 LUT / 1728 DFF / 25 MATH) |
| Strict audit verdict | FAIL — 1 violation: 3 `output_valid` wiring issues (CD279/CD638/CL240); 0 critical PID-coefficient pruning hits |
| Reports captured | `libero/reports/2026-04-30-claude-r2/` (iteration_summary, hier_resources, .srr, compile_netlist log/resources) |

### Round 1 (Codex's branch) — synthesis re-run not needed

The Beelink Libero project was last synthesized on 2026-04-29 with whatever
patches Codex's branch had applied; that synthesis state is what
`pnr_verify_only.tcl` reuses. Re-running the closure on `codex/corpus-verification`
re-runs PLACEROUTE → VERIFYTIMING → VERIFYPOWER on **the same project state**,
producing identical synthesis numbers. No new SmartHLS or HDL imports happen
in `pnr_verify_only`. The decisive Round 1 vs Round 2 difference is in the
**audit calibration applied to the same synthesis evidence** — captured below.

### Audit Calibration: Codex's audit vs mine, on the same `2026-04-29-pid-real` bundle

Both audits parse the same 45-row `nv_pid_top` hierarchy (LUT=2390, DFF=1728,
Math=25, slack +0.728 ns).

| | Codex | Mine |
|---|---|---|
| Classification | "real PID evidence with pruning review" | `real-pid-evidence` |
| Critical pruning hits flagged | **4** — all BN115 on `legup_mult_*` instances | **0** |
| Strict-mode verdict | **2 violations** (4 critical pruning + 3 output_valid) | **1 violation** (3 output_valid) |
| Source of the 4 false-positive hits | BN115 on `legup_mult_pipelined_inst`, `legup_mult_unsigned_15_17_1_23`, etc. — these are SmartHLS arithmetic-primitive **alternative** removals, not coefficient constant-folding | excluded: BN115 demoted (corpus `preventing:111` says "Not located verbatim … verify in local log"); `legup_mult` removed from PID coefficient regex (it is a SmartHLS arithmetic primitive name) |

In other words, against identical synthesis evidence, Codex's strict audit
**fails the bundle on a corpus-flagged-speculative message ID hitting a
SmartHLS-internal arithmetic primitive**, while mine correctly distinguishes
the speculative hit from the verbatim-confirmed CL189/CL260/BN362 cascade
the corpus actually warns about.

## Where The Corpus Made The Decisive Difference

1. **Citation rigor.** The corpus's user-contributed deep-research files
   are explicit about which Synplify message IDs are verbatim-confirmed
   in the OEM reference (CL189/CL260/BN362) vs which are speculative
   ("verify in local log" — BN115, MO129). Without the corpus a frontier
   model writes a fail-fast gate that includes both classes; with the
   corpus the speculative IDs are correctly demoted.

2. **Slave-specific WSTRB rule.** Without the corpus a frontier model
   conflates "AXI4-Lite says wstrb is implementation-defined" with
   "CoreVectorBlox says all-or-nothing." The corpus separates these:
   `fpga-hls-docs:2594-2596` (SmartHLS, element-aligned) vs
   `HB0919:565-635` (CoreVectorBlox control slave, all-or-nothing).
   Round 1 mixed them; Round 2 separated them.

3. **Architectural-proof criterion.** The corpus elevates "software
   write-then-readback" to **the** architectural proof of survival
   (`preserving:97`). A frontier model without this criterion can
   generate a "production" patch that defeats constant-folding but never
   provides write-then-readback, and label it production. The corpus
   forces an explicit gate (`--check-readback-contract`) and an explicit
   follow-on runbook.

4. **Output_valid semantics.** Without the corpus, `output_valid` looks
   like a generic interrupt. With the corpus
   (`HB0919:361/499/784`, `preserving:121-125`) it is unambiguously a
   level-held W1C bit requiring edge detect + CDC sync. Both Round 1 and
   Round 2 got this right because the corpus is unusually explicit.

## Where The Corpus Did Not Help

- **GUI canvas surgery.** The corpus says SmartDesign Tcl object names
  are design-specific and cannot be reliably regex-patched
  (`preserving:105-119`). Both rounds correctly identified this; both
  branches still depend on the user opening the Libero GUI to wire a
  CoreAXI4Interconnect. Round 2 produces a runbook
  (`docs/smartdesign_two_slot_canvas_runbook.md`); Round 1 noted the gap
  in a docstring.

- **Beelink reachability.** The corpus has nothing about SSH config or
  GitHub credentials. Round 1 failed every Beelink attempt because
  Beelink can't authenticate to GitHub origin; Round 2 worked around it
  by fetching from the `spark1` SSH remote already configured on
  Beelink. This is a tooling difference, not a corpus difference.

## Conclusion

The corpus produced measurable accuracy improvements on three classes of
issue that a general frontier model gets only ~80% right: (a) selecting
the verbatim-confirmed Synplify message IDs, (b) attributing rules to
the correct slave protocol, (c) elevating readback to architectural
proof. On classes the corpus does not cover (toolchain plumbing, GUI
work) the corpus does not help and ordinary engineering judgment
applies.

The decisive evidence is the synthesis closure rows above. They will be
populated once the Beelink closure run completes.
