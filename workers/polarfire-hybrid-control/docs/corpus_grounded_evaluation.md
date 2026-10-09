# Corpus-Grounded Evaluation (Round 2)

Date: 2026-04-30
Branch: `claude/corpus-verification` (independent from `codex/corpus-verification`)
Baseline: `9de366c` (last pre-corpus commit)
Corpus: `~/.corpus/polarfire-control-corpus/`

## Purpose

Evaluate the repo as the **pre-corpus artifact** that existed before
`~/.corpus/polarfire-control-corpus/` was built (2026-04-29). Use the
corpus as ground truth. Layer corpus-grounded fixes that close the gaps
the corpus reveals.

This is Round 2 of the user's three-round experiment:

| Round | Corpus access | Branch |
|---|---|---|
| 0 | none | up to `9de366c` (pre-corpus) |
| 1 | corpus | `codex/corpus-verification` (Codex pass) |
| 2 | corpus | `claude/corpus-verification` (this pass, independent) |

The cross-round comparison is in `docs/frontier_comparison.md`.

## Corpus Anchors Used

| Topic | Corpus reference |
|---|---|
| SmartHLS `axi_target` storage semantics | `raw/microchiptech.github.io/fpga-hls-docs20232userguidehtml.md:2594-2596` (element-aligned WSTRB) |
| AXI tied-down failure mode (constant-folding cascade) | `raw/user-contributed/preventing-synplify-constant-folding-smarthls-pid.md:5, 60-61, 108-113` |
| Architectural fix recommendation | `raw/user-contributed/preserving-real-smarthls-pid-datapath.md:130-148` |
| Survival checklist (which message IDs decisive) | `preserving:74-103` (incl. line 98 for CL279) |
| Speculative IDs (corpus admits not verbatim-confirmed) | `preventing:111` (BN115), `preventing:113` (MO129) |
| CoreVectorBlox `output_valid` is W1C / level-held / interrupt mirror | `raw/download-soc.microsemi.com/...corevectorblox-i.md:361, 499, 784` |
| Output_valid -> watchdog requires edge-detect + CDC sync | `preserving:121-125` |
| CoreVectorBlox WSTRB rule (control slave only) | HB0919:565-635 ("CoreVectorBlox expects all write strobe signals to be all high or all low") |
| Software write-then-readback as architectural proof | `preserving:97` |
| SmartDesign Tcl object names are design-specific | `preserving:105-119` |

## Verification Run

Local:
- `make verify-local` -> pass.
  - `hls-test-local`: g++ shim build + run; all original tests + new D.1/D.2/D.3 output_valid edge cases pass.
  - `audit-reports`: classifies existing bundles; `2026-04-29-pid-real` is `real-pid-evidence`.
  - `audit-citations`: 35 citations resolve in the corpus.

Remote (Beelink):
- `make beelink-verify TAG=2026-04-30-claude-r2` (this branch's HEAD).
  Records `shls sw_run`, full Libero closure, report extraction, and
  strict audit into `libero/reports/2026-04-30-claude-r2/`.
- `make beelink-verify TAG=2026-04-30-codex-r1` (Codex's branch HEAD)
  for matched comparison.

## Scorecard

| Area | Pre-corpus (Round 0) | This pass (Round 2) | Evidence |
|---|---|---|---|
| HLS behavior | covered: bumpless / clamp / SEU / chatter | + D.1/D.2/D.3 output_valid edge cases | `hls/tb/tb_bumpless.cpp` |
| SmartHLS type | correct (`hls::ap_fixpt`) | unchanged | `hls/include/fp_types.hpp` |
| Constant-folding diagnosis | `patch_smartdesign_axi_target_experiment.py` correctly identified gain-fold | unchanged; corpus confirms diagnosis | `preventing:60-61` |
| WSTRB enforcement | not addressed | AXI4-Lite-spec compliant; correct citation pinned | `libero/hdl/pid_csr_block.v`, `preserving-real-smarthls-pid-datapath.md` line 27-46 |
| Real PID closure evidence | `2026-04-29-pid-real`: 45 hier rows, 2390 LUT / 1728 DFF / 25 MATH, slack +0.728 ns | preserved as historical baseline; superseded by two-slot closures r10_s29 (+0.977 ns) and r13_s32 (+1.006 ns, programmed 2 ms image) | `libero/reports/2026-04-29-pid-real/` |
| Production AXI integration | experimental tap only | Phase I patch + follow-on canvas runbook; readback contract gated by audit | `docs/smartdesign_two_slot_canvas_runbook.md` |
| Watchdog source | MSS GPIO heartbeat (test stimulus) | `vbx_pulse_gen.v` 2-FF sync + edge detect; HB0919-cited | `libero/hdl/vbx_pulse_gen.v` |
| Synplify pruning audit | not gated | corpus-calibrated strict gate (CL189/CL260/CL279/BN362; BN115/MO129 demoted) | `tools/audit_libero_reports.py` |
| Citation rigor | no automated check | `audit_corpus_citations.py` resolves every cited file/line | `tools/audit_corpus_citations.py` |
| Safety claims | "AI cannot destabilize" (over-strong) | replaced with "sector-bounded by design within Phase I assumptions" + residual obligations | `README.md`, `docs/safety_architecture.md` |
| Power claim | "57% margin" (default-toggle) | labeled "preliminary; awaiting workload-driven SmartPower" | `README.md` |
| Status observability | none | full CSR bank: pre/post-clamp, integrator, derivative, sat flag+counter, watchdog flag+counter, cooldown, ai_active | `libero/hdl/pid_csr_block.v` |
| Readback contract | unverified | `--check-readback-contract` gate fails when two slaves share one FIC master without `CoreAXI4Interconnect` | `tools/audit_libero_reports.py` |

## What The Corpus Changed (vs Round 0)

- The general-knowledge model correctly diagnosed the gain-fold failure
  mode but did not have a citable rule set for which Synplify message
  IDs are decisive evidence vs speculative. The corpus disambiguates:
  CL189 -> CL260 -> BN362 is the verbatim-confirmed cascade; CL279 is in
  the survival checklist; BN115 and MO129 are explicitly flagged "verify
  in local log" by the corpus author.
- Round 0 had no rule to distinguish the SmartHLS WSTRB rule (per-element
  alignment) from the CoreVectorBlox WSTRB rule (control-slave-specific
  "all high or all low"). The corpus makes the distinction explicit.
- Round 0 treated `output_valid` as a generic interrupt. The corpus is
  emphatic that it is a level-held W1C bit requiring edge detection plus
  CDC synchronization before driving a watchdog.
- The corpus elevates "software write-then-readback" from nice-to-have
  to architectural proof of survival, which means a single-slave
  eavesdropping integration is necessary but not sufficient.

## Round 2 vs Round 1 Highlights

(See `docs/frontier_comparison.md` for the full row-by-row comparison.)

Where Round 1 (Codex) and Round 2 (this pass) agree:
- Add a real CSR bank with shadows + status registers.
- Edge-detect + CDC-sync `output_valid` before the watchdog.
- Replace "cannot destabilize" with sector-bounded language.
- Add 3 HLS edge-case tests for output_valid.

Where Round 2 differs by closer corpus reading:
- WSTRB cited correctly to `fpga-hls-docs:2594-2596` for the SmartHLS
  case; HB0919:565-635 invoked only for CoreVectorBlox control-slave
  paths. Round 1 applied HB0919 to the hand-written slave.
- Round 2 strict gate excludes BN115 and MO129 by default (corpus calls
  them speculative). Round 1 treated MO129 as fail-fast.
- Round 2 gate adds CL279 (named in the corpus survival checklist).
  Round 1 omitted it.
- Round 2 labels the regex patch as "Phase I bring-up" not "production
  replacement"; Round 1 used the latter label even though the script's
  own docstring admitted the readback-contract gap.
- Round 2 adds an automated citation linter
  (`tools/audit_corpus_citations.py`) and a readback-contract gate
  (`--check-readback-contract`) that catches the multi-slave-on-one-bus
  pattern.

## Bottom Line

Round 0 (pre-corpus) hit the central failure mode by intuition. Round 2
(corpus-grounded) confirms the diagnosis, sharpens the citations, adds
the architectural proof gate (readback contract), and ships the follow-on deployment path
runbook the corpus says cannot be regex-patched. The next decisive
evidence is the Beelink closure runs on both branches, captured in
`docs/frontier_comparison.md`.
