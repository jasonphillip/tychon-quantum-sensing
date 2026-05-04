# Bringup Handoff — 2026-05-04

> **Handed off from a TVW session to a polarfire-hybrid-control session.**
> TVW (`~/projects/tychon-verification-workbench`) was driving the demo
> bring-up but the work is implementation iteration on this repo's Libero
> Tcl flow + RISC-V firmware — that belongs here, where the CLAUDE.md,
> reference corpus, and commit conventions all live. TVW remains live for
> orchestration / audit / cross-repo coordination.

## Mission

Get a programmed PolarFire SoC Icicle Kit doing something visible and credible to reviewers. The fabric design (PolarFire hybrid PID controller) is place-and-route complete with positive timing slack on the corrected MPFS250T-FCVG484E silicon. Missing pieces:
1. Bitstream `.job` artifact persisted to disk (HW-04d)
2. Kit programmed via FlashPro
3. MSS firmware to drive the PID block over FIC1 AXI (currently `firmware/` is a placeholder)

The work is **not** scoped to any SBIR phase. It's "make the board do a credible thing this week so we can demo it." Three demo modes are defined in the plan as Options A → B → C.

## Authoritative plan

Read this first:

```
~/.claude/plans/i-plugged-in-j11-optimized-quilt.md
```

It defines six Parts (0–5) with stop-gate boundaries, dependency ordering, branch strategy (`bringup/part-N-*`), and verification artifacts. Each Part is sized to stop and resume cleanly. **Don't re-plan; execute.** If something material changes, update the plan in place — don't fork.

## Where we are right now (state at handoff)

### Branches and commits

- **Current branch:** `bringup/part-1-bitstream` (this branch — same on spark1 and Beelink)
- **5 commits ahead of `main`** (oldest → newest):
  - `36b79bd` docs: refresh track0 runbook (HW-01/02/03 RESOLVED, HW-04b OBSOLETED)
  - `5da3943` docs: SoftConsole binary name correction (`riscv64-unknown-elf-gcc`, not `riscv-none-elf-gcc`)
  - `37e17e7` feat: populate pinout.pdc + dated-subdir bitstream export with sha256
  - `55fefb4` fix: `-io_pdc` not `-pdc` in `import_files` (Libero 2025.2 API)
  - `6f4daaf` fix: delete stale `libero/work/` before `new_project` (no `-overwrite` flag in 2025.2)
- **Beelink** (`~/dev/projects/polarfire-hybrid-control/`) is fast-forward synced to this branch
- **`claude/corpus-verification`** branch on Beelink contains earlier corpus-grounded work, fully merged with main as of `3c981f0`; do not lose

### Last failing state

Libero pipeline (`00_full_pipeline.tcl`) launched on Beelink in background (nohup'd). Got past scaffold + constraint import. **Failed at `01_scaffold_proj.tcl:78` with:**

```
Error:  Cannot find module named polarfire_hybrid_control::work.
```

**Root cause:** `01_scaffold_proj.tcl` calls `organize_tool_files -module "${PROJECT_NAME}::work"` (lines 72–89) **before** any HDL is imported. The constraint-to-tool binding requires a module to exist; the module is created later by `02_import_ip.tcl` via `build_design_hierarchy`.

**Behind that:** `02_import_ip.tcl` requires SmartHLS-generated RTL in `hls/hls_output/` (the `.cxf` and Verilog netlist). That dir was gitignored on Beelink in commit `a8f979f` because it's regenerable. Need to either (a) restore it from a previous SmartHLS run, or (b) re-run `make hls-hw` (or whatever the SmartHLS hardware-flow target is).

### Hardware connectivity (verified earlier this session)

- **J11 + J33 both plugged into Beelink** (USB)
- **FlashPro embedded programmer:** enumerates as `VID_1514 PID_200B`, status OK
- **CP2108 quad UART bridge:** enumerates as **COM3 / COM4 / COM5 / COM6** (Interface 3 / 2 / 1 / 0 respectively)
- **MMUART0 → which COM port:** unverified until a programmed kit prints something. Plan Part 2 step 4 covers this (open all 4 simultaneously, reset kit, see which prints).

### Tooling installed on Beelink

- **Libero SoC 2025.2 + SmartHLS:** `C:\Microchip\Libero_SoC_2025.2\` — Designer, Synplify Pro, FPExpress on PATH
- **SoftConsole 2022.2 build 747:** `C:\Microchip\SoftConsole-v2022.2-RISC-V-747\`
  - GCC: `…/riscv-unknown-elf-gcc/bin/riscv64-unknown-elf-gcc.exe` (xPack 8.3.0, newlib bare-metal target)
  - GDB 9.1, OpenOCD, Eclipse, MSYS make
  - Smoke-tested with a CSR write at `0xE0000000` — compiles cleanly to RISC-V machine code
  - Note: `extras/mpfs/` is empty — MPFS HAL needs separate clone from `polarfire-soc/polarfire-soc-bare-metal-library` for Part 3
- **License:** Libero Silver + CoreVectorBlox feature both visible to FlexLM (HW-02 done 2026-05-02)
- **CP210x VCP driver:** installed (HW-03 done 2026-05-02)

### Reference resources you should use BEFORE editing more Tcl

**Local corpus** (polarfire-control-corpus, 7,543 chunks across 320 sources):

```
/search-corpus polarfire-control-corpus "<query>"
```

Confirmed contents include:
- **Libero SoC v2025.2 User Guide** — `libero-ecf-ug-2025-2.pdf`
- **Libero SoC v2025.1 Tcl Command Reference Guide** — `libero-soc-tcl-cmd-ref-ug-2025-1.pdf` (this is the authoritative source for `import_files`, `organize_tool_files`, `new_project`, `set_root`, `export_prog_job`, etc.)
- SmartHLS pragmas, `ap_fixpt`, PDC `io.pdc`/`fp.pdc` split docs
- PolarFire SoC Reference Manual (FIC0/1/2/3 capabilities, MSS memory map)
- CoreVectorBlox v2.0.1 IP docs
- Synplify Pro Message Reference
- Khalil / Aström / circle-criterion / Lur'e theory
- arXiv: neural Lyapunov, CBF, safe-RL, FPGA NN accelerators for space, certifiable AI for aerospace
- Zenodo: VectorBlox SDK + RT PolarFire reference

**Do not guess Libero APIs from training data.** The 2025.x flow has materially different flags (`-pdc` removed, `-io_pdc`/`-fp_pdc` split, no `-overwrite` on `new_project`, etc.). Search the corpus first.

### Pre-existing seed-sweep prjx files on Beelink

```
~/libero_seedsweep/{resynth_check,seed_7,seed_13,seed_23}/MPFS_ICICLE_Vectorblox.prjx
```

These are from audit-006's parallel synthesis sweep. They have HDL imported and synth+P&R done — almost certainly what generated r6_s25's +0.728 ns slack. These are the basis for Path B below.

## Three forward paths — your call

| Path | What it is | When it wins | Risk |
|---|---|---|---|
| **A — Fix the Tcl pipeline properly** | Move `organize_tool_files` out of `01` (defer until after `02` imports HDL); restore `hls/hls_output/`; ensure 2025.2 API throughout (corpus-grounded). Future re-runs are clean Tcl-driven. | You want a clean reproducible flow long-term. | Open-ended; each fix may surface another. Estimated 1–3 hr. |
| **B — Repurpose seed_7 prjx for bitstream-only export (RECOMMENDED)** | Write `04b_export_only.tcl`: open `libero_seedsweep/seed_7/MPFS_ICICLE_Vectorblox.prjx`, run `GENERATEPROGRAMMINGDATA`, `export_prog_job`, copy `.job` to dated subdir + sha256. Sidesteps the broken `01-03` chain entirely. | You want a `.job` tonight to enable Part 2 (program kit). | Project name mismatch (`MPFS_ICICLE_Vectorblox` vs `polarfire_hybrid_control`); pin assignments may diverge from our `pinout.pdc` (need to inspect/swap). |
| **C — Libero GUI, one-time bring-up** | Open Libero GUI on Beelink, build/load project step-by-step, save `.prjx`, then script just the export against the saved `.prjx`. Most reliable. | A or B both blow up further. | 30–60 min interactive user time. |

**TVW's recommendation was B.** You decide.

The plan's Part 1 stop-gate is: **`.job` exists in `libero/reports/<dated>/` with sha256 + FIC1 PID base address documented.** Once that lands, Part 2 (program kit) unblocks.

## Critical hard rules (carry over from CLAUDE.md and TVW)

1. **Do not auto-tag work as Phase I or Phase II.** The user pushed back hard on this twice. Default framing: "what's done, what's missing, effort to close." See `~/.claude/projects/-home-badwillhunt-projects-tychon-verification-workbench/memory/feedback_no_auto_phase_tagging.md` for the why (the user-facing version of the same rule applies in this session too).
2. **Specific-path `git add`** always — never `git add .` or `-A` per global CLAUDE.md security rules.
3. **No force-push, no `--no-verify`, no public GitHub push without explicit approval.** Internal mirrors (spark1, NAS) are fine.
4. **Beelink branch state is a recurring trap** — always check `git status` and `git log --oneline -3` over `ssh bee` before launching Libero. Beelink had been on a stale branch with uncommitted artifacts at the start of this session; reconciled in commits `a8f979f` and `3c981f0`.
5. **Search the local corpus before guessing Libero APIs** — `/search-corpus polarfire-control-corpus "<query>"`.

## Open items the next session inherits

- **Part 1:** finish bitstream generation (Path A/B/C choice above) → capture FIC1 PID base address from synth log → commit `.job` artifact location to plan file
- **Part 2:** program kit via FPExpress, identify which COM port (3/4/5/6) carries MMUART0
- **Part 3:** Option A firmware — UART register loopback against the 18 PID CSRs at offsets `0x000–0x05C` (full register map in `libero/hdl/pid_csr_block.v:28-62`, all 32-bit Q16.16). Build with `riscv64-unknown-elf-gcc` from SoftConsole. Will need MPFS HAL (`polarfire-soc/polarfire-soc-bare-metal-library` from GitHub).
- **Part 4 / Part 5:** synthetic stimulus + LED PWM (per plan)

## TVW's standing offer

If something in this work surfaces a fix-list-relevant finding (audit follow-up, doc inconsistency, cross-repo dependency), kick it back to a TVW session — that's TVW's lane. Otherwise this session owns the demo bring-up end-to-end.

## Verification command (smoke-check the handoff worked)

From a fresh polarfire-hybrid-control session:

```bash
git branch --show-current        # → bringup/part-1-bitstream
git log --oneline -6              # → top is 6f4daaf
ls docs/bringup_handoff_2026-05-04.md   # → present
ssh bee 'git -C ~/dev/projects/polarfire-hybrid-control branch --show-current'  # → bringup/part-1-bitstream
ssh bee '/c/Microchip/SoftConsole-v2022.2-RISC-V-747/riscv-unknown-elf-gcc/bin/riscv64-unknown-elf-gcc.exe --version | head -1'   # → xPack 8.3.0
```

If all five pass, you're ready to drive Part 1 to a `.job` artifact.
