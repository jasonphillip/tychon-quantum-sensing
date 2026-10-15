> Original: claude.ai project document, created 2026-04-30. Edited for publication: names of other people and business details removed.

# Tychon AI — STATUS

**Last updated:** 2026-04-30
**Status:** technical work (post-r6_s25 closure, all KPPs met in simulation)
**Plan:** 90-day build plan

---

## ⚠️ Read This First — File Lifecycle Rule

**This is the single live state file for the Tychon project.** It is overwritten in place every session. **Do not create new pickup guides, session summaries, snapshot files, or state files.** They produced a 38-file mess that took a full cleanup session to triage. The pattern is now banned.

**At the end of every session:** update this file in place. Bump the "Last updated" date. Adjust the relevant sections. Re-upload to project knowledge. Done.

**For decisions made in a session:** append to `tychon_phase1_decision_log.md` (DLOG-NNN format). Decisions are append-only and immutable.


---

## Current State (One Paragraph)

All technical demonstrations are complete. The April 29, 2026 r6_s25 closure on the `polarfire-hybrid-control` repo (`decision-2-option-c` branch, commit `9de366c`) is the first post-place-and-route closure with the synthesized PID datapath actually present in the placed netlist — all prior closures (April 2 baseline, April 28 overlay, April 29 r3_s22) closed on a paper-shell where Synplify CL168 had pruned `nv_pid_top_0`. Headline numbers from r6_s25: +0.728 ns worst slack on FIC_0 PLL OUT0, 25.90% LUT, 2,693 mW fabric power, 5 KPPs met. The `claude/corpus-verification` branch was merged into `main` on April 30 (merge commit `ce71ca5`), adding a calibrated audit gate (`make verify-local`) and follow-on canvas-refresh HDL prototypes (`pid_csr_block.v`, `vbx_pulse_gen.v`). The Final technical report reflects the post-r6_s25 numbers.

---

## KPP Scorecard (r6_s25)

**Note added 2026-10-15:** This scorecard is the April 30 snapshot. The 96.1 % ADEV figure holds only at tau = 2,700 s. The 5.2 W estimate covers FPGA and MSS only, excluding the rest of the payload; see the [later qualifications](../excerpts/building-additional-selections-2026.md#b3).

| # | Metric | Target | Achieved | Status |
|---|---|---|---|---|
| 1 | Heading Error Reduction | >50% | 54.3% (val) / 96.1% ADEV at τ=2700s | **PASS** |
| 2 | Classical Loop Latency | <150 µs | ~48 ns (II=1, 125 MHz) | **PASS** |
| 3 | AI Inference Latency | <1 ms | Timing closure at 200 MHz | **PASS*** |
| 4 | Total Power | <12 W | ~5.2 W (FPGA + MSS subsystem) | **PASS** |
| 5 | FPGA Resource Fit | Fits MPFS250T | 25.90% LUT (post-P&R, integrated PID) | **PASS** |

*Metric 3: Runtime measurement requires board boot (Gold license + RT PolarFire dev kit). Timing closure provides high confidence.

---

## Authoritative Files (Project Knowledge)

| File | What It Is |
|---|---|
| `Tychon_Phase_I_Final_Report.docx` | Working Final Report (April 29 clean version, r6_s25 numbers) |
| `Tychon_AI_Phase_I_Execution_Playbook_v4.docx` | Authoritative requirements + 90-day timeline |
| `Tychon_AI_Platform_Addendum_v4.docx` | Authoritative platform specs + safety architecture |
| `tychon_phase1_decision_log.md` | DLOG-001 through DLOG-036 (high-water mark: DLOG-036, dated 2026-04-30) |
| `tychon_phase1_repo_architecture_decisions.md` | Repo strategy and exclusion rules |
| `tychon_repo3_scaffold_spec.md` | Repo 3 scaffold authority |
| `tychon_microchip_toolchain_reference.md` | Toolchain versions and commands |
| `repo_migration_record_2026-04-03.md` | Old → new repo name mapping (CRITICAL — older files reference old names) |
| `Tychon_Fast_trak_Claude.md` | Foundational research (Feb-Mar 2026) |
| `STATUS.md` | This file (overwrite in place) |

**Stale files referenced by older project knowledge** (older files may reference these — they are correct for the time they were written, not currently authoritative):
- "+0.165 ns worst slack" / "24.72% LUT" / "84.2% ADEV" — these are paper-shell numbers from pre-r6_s25 closures. Current numbers are +0.728 ns / 25.90% / 96.1%.
- Repo names `tychon-nv-sim`, `tychon-odmr-ml`, `tychon-polarfire-control` — renamed April 3, 2026 to `nv-sensor-sim`, `odmr-edge-ml`, `polarfire-hybrid-control`.

---

## Repo State

| Repo | Active Name (GitHub) | Branch | Last Significant Commit | State |
|---|---|---|---|---|
| Repo 1: NV physics sim | `nv-sensor-sim` | `main` | (anti-inverse-crime fixes, see DLOG / integration tracker) | Production-ready for data gen; 55/55 tests pass |
| Repo 2: ML training/export | `odmr-edge-ml` | `main` | (R2-3,4,5,7,8 fixes complete) | 87/87 tests pass; FCNN v1 final model |
| Repo 3: FPGA control | `polarfire-hybrid-control` | `main` | `ce71ca5` (merge of `claude/corpus-verification`) | closure complete; follow-on HDL prototypes in `main` |

All three under `github.com/jasonphillip/`. Old repos archived (untouched).

---

## Machine State

**A local DGX Spark node (ARM64) — source of truth for code:**
- All three active repos at `~/projects/<repo>/`
- Old archived repos at `~/projects/tychon-<repo>/`
- Shared dataset storage at `~/projects/tychon-shared-data/` (140-spectrum golden set + 50K production dataset)
- Global gitignore configured (CLAUDE.md, CLAUDE.local.md, .claude/)

**Beelink (Windows 11, x86) — synthesis machine:**
- WSL2 + VectorBlox SDK v2.0.3 (Python 3.10, TF 2.15.1, numpy 1.23.5)
- SmartHLS / Libero on native Windows; accessible from the Spark node via SSH wrappers (`shls`, `libero`)
- `polarfire-hybrid-control` cloned at `~/dev/projects/polarfire-hybrid-control/`
- SSH remote to the DGX Spark node configured on Beelink (avoids GitHub-SSH-on-Beelink dependency)
- Make targets: `verify-local`, `verify-strict`, `beelink-verify TAG=...`

**NAS (local network storage):**
- `/volume1/projects/tychon-artifacts/` — TFLite, .vnnx, ONNX models; Libero report bundles

---

## Decision Log High-Water Mark

**DLOG-036** (2026-04-30) — follow-on canvas-refresh HDL prototyped (`pid_csr_block.v`, `vbx_pulse_gen.v`)

Next DLOG entry should be numbered **DLOG-037**.

---

## Open Items

### Closeout
1. Final technical report — frozen at the April 29 version. Re-read once more.

### Follow-on Carry-Forwards (in repo as TODO)
1. Real AXI4-Lite interconnect routing for `nv_pid_top_0` gain registers (replaces FIC_0 master tap).
2. CoreVectorBlox `output_valid` wired to `watchdog_timer_0.ai_heartbeat` (canvas refresh).
3. Workload-driven SmartPower run with VCD-based switching activity.
4. Six Residual Follow-on Proof Obligations (DLOG-035): plant model ID, ZOH phase margin, transport delay, derivative filter SI, ReLU sector, workload-driven power.
5. Canvas refresh per `docs/smartdesign_two_slot_canvas_runbook.md` to import `pid_csr_block.v` + `vbx_pulse_gen.v`.

### Should-Do (Not Blocking)
1. Update `gemini_integration_tracker_2026-04-04.md` status — most FR-* items have been incorporated into the new Final Report; the tracker is mostly historical now.
2. Rename `gemini_deep_think_combined_all.md` → `gemini_post_report_review_2026-04-02.md` (the current name is misleading — it is the April 2-3 post-report review batch, not a master file).

---

## What Changed Since Last Session

(For each session, summarize here. Replace this section each update.)

**2026-04-30 session:**
- Project knowledge cleaned: ~38 files → 23 files. Pickup-guide / session-summary sprawl pattern eliminated.
- Decision log appended with DLOG-033 through DLOG-036 (r6_s25 closure, audit gate calibration, safety claim retraction, follow-on HDL prototypes).
- `claude/corpus-verification` branch merged to `main` on `polarfire-hybrid-control` (merge commit `ce71ca5`).
- `STATUS.md` created.

---

## How to Update This File

1. Bump `Last updated` to today's date.
2. Update `Phase` and `Next milestone` if status changed.
3. Update `Current State` paragraph (rewrite, don't append).
4. Update `KPP Scorecard` only if numbers change (rare after closeout).
5. Update `Repo State` if a branch lands or a significant commit is merged.
6. Update `Machine State` only if hardware/toolchain changes.
7. Update `Decision Log High-Water Mark` after appending to the DLOG.
8. Update `Open Items` — move completed items out, add newly discovered ones.
9. Replace `What Changed Since Last Session` with a fresh summary.
10. Re-upload to project knowledge (overwrite the existing `STATUS.md`).

That's it. Do not create new files. Do not version this file. Overwrite.

