# Parallel Libero P&R sweep on Beelink

Default workflow for any audit / variance study that needs N independent
placement runs against the same RTL+netlist baseline. Use this **instead of**
sequential `pnr_verify_only.tcl` invocations with different seeds.

End-to-end time on Beelink for N=4: ~50 min total (one ~25 min Synplify
re-synth + N parallel ~25 min P&R runs), versus ~3 hr if each seed runs full
synth+P&R sequentially.

## Beelink resource ceiling (verified 2026-05-03)

| Resource | Value |
|---|---|
| Total RAM | 64 GB (≥56 GB free pre-launch) |
| Free disk on `C:` | 774 GB |
| Synplify Pro seats | uncounted (unlimited concurrent) |
| Libero / SmartHLS / ACTEL_BASESOC | uncounted |
| Project size (Icicle MPFS_ICICLE_Vectorblox) | 583 MB; clones add 2-3 GB total for N=4 |
| Per-Libero RAM during P&R | ~2-8 GB resident |

Headroom calculation: 4 concurrent Liberos × 8 GB peak = 32 GB. Beelink has
2× that headroom.

## The pattern in 6 steps

```
1. Clone project to N+1 directories (1 master + N seed clones)
2. Rewrite each clone's prjx self-path (rewrite_prjx_path.pl)
3. Run SYNTHESIZE once in the master clone (audit_master_synth.tcl)
4. Propagate master's synthesis/ + component/ state to each seed clone
5. Launch N parallel Libero processes, each running PLACEROUTE+VERIFYTIMING
   on its clone with configure_tool RANDOM_SEED:N
6. Parse worst-slack from each clone's timing rpt
```

Files in this directory:

- `parallel_sweep_pnr.tcl.tmpl` — Tcl template for the per-clone P&R job.
  Generate per-seed copies via sed substitution of `__SEED__` and `__CLONE_DIR__`.
- `master_synth.tcl` — Tcl for the one-shot master Synplify re-synth.
- `rewrite_prjx_path.pl` — Perl script that rewrites the absolute project-self-path
  in a cloned `.prjx` file.
- `parallel_launch.sh` — End-to-end orchestrator. Clones, rewrites, kicks off the
  master synth, then launches N parallel P&R processes. Captures DONE/FAILED markers.
- `parse_seed_slacks.sh` — Extracts worst-slack + clock-domain attribution from each
  clone's timing rpt and prints a table.

## ⚠️ Critical caveat — seed control does NOT work in batch Tcl

Audit-006 (2026-05-03) verified across 3 independent clones that `configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:N"]` from a Tcl script **does not vary placement**. SEEDs 7 / 13 / 23 all produced bit-identical Path 1/2/3 register endpoints, delays, and slacks to 3 decimal places.

**Root cause found in the run logs**: Libero's batch PLACEROUTE invokes the built-in **Multi-Pass / Iterate Seeds** feature, *not* `configure_tool`'s RANDOM_SEED setting. The log line `Multi-Pass: Iteration 1, Seed Index 27, Worst Slack = 0.274 / Multi-Pass: Have met stopping criterion (all timing constraints have been met), so ceasing iterations.` shows what's actually happening: the placer auto-increments the seed index from the project's prior highest-numbered rpt (`r7_s26` → starts at index 27) and **stops after iteration 1 if timing closes**. Three clones with three different `configure_tool` seed values still all placed at Seed Index 27 and exited successfully on the first pass.

**This means `parallel_sweep_pnr.tcl.tmpl` produces N independent clones running the same effective seed.** Useful as:
- ✅ A cross-clone determinism check (positive finding from audit-006: Libero PLACEROUTE IS bit-identical for fixed inputs)
- ✅ A way to amortize the "single P&R takes ~28 min" cost when you actually want N copies of the same answer (probably never)
- ❌ A seed-variance characterization tool — does NOT work as documented

**For genuine variance characterization, deferred research is needed** to identify a batch-mode seed-injection mechanism that Libero actually honors. Candidates not yet tested:
- Libero GUI "Multi-Pass" / "Iterate Seeds" feature, scripted via its own Tcl entry points (different code path from `configure_tool`)
- Editing a prjx KEY entry directly before `open_project` (something like `KEY PLACEROUTE_RANDOM_SEED "7"` — needs validation that such a KEY exists and isn't overridden)
- `set_design_state -tool {PLACEROUTE}` family — may not exist
- Pre-launching with environment variables Synplify/Libero honor

What IS reliably variable across runs (and is the actual variance source): the synthesized netlist itself. Synplify Pro produced `ae51d60d` on Apr-30 and `44917cd6` on May-3 from identical RTL+SDC+tool version, indicating non-determinism in synthesis (likely environmental: build paths, timestamps, license-server interaction). Use *that* as the variance dimension if you need a meaningful sweep.

## Critical gotchas (lessons earned from audit-006, 2026-05-03)

1. **Tcl script path must be Windows-style.** Libero in MSYS Git Bash:
   - ✅ `libero "SCRIPT:~/foo.tcl"` works
   - ❌ `libero "SCRIPT:~/foo.tcl"` fails: `Parameter 'file' is missing or has invalid value`

2. **`run_tool -name {SYNTHESIZE} -script {REPORT}` is invalid Tcl.** `-script`
   expects a Tcl filepath, not a built-in keyword. The legacy in-repo
   `04_synth_pnr.tcl` line 39 has this and silently fails (Tcl `set synth_status
   [...]` swallows the error). Use plain `run_tool -name {SYNTHESIZE}`.

3. **Don't run N parallel SYNTHESIZE invocations from N clones.** Even with
   uncounted licenses, Synplify Pro's startup has a race condition (or absolute
   paths in the cloned `synthesis/synlog/*.srr` files cause the parallel runs to
   collide). 3 concurrent synth attempts from cloned dirs failed cleanly with
   `Error: Synthesis failed.` in audit-006 testing — a single master synth + N
   parallel P&Rs is the proven path.

4. **The cloned `.vm` netlist passes Libero's mtime freshness check** (touch the
   clone's `synthesis/MPFS_ICICLE_KIT_BASE_DESIGN.vm` so its mtime > RTL source mtime),
   but Libero's deeper synth-state tracking (used by PLACEROUTE) checks more than
   mtimes. PLACEROUTE on a touch-only clone fails with `Error: SYNTHESIZE Tool
   inputs are out of date`. The `cp -r master/synthesis/* clone/synthesis/` step
   in the parallel pattern is what fixes this — the master's recently-completed
   synth state propagates as fresh.

5. **Skip POWERANALYSIS and GENERATEPROGRAMMINGDATA** for variance sweeps. Only
   worst-slack matters; those add ~5 min per clone and aren't audit-relevant.

6. **`configure_tool` seed config**:
   ```tcl
   configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:7"]
   ```
   Belt-and-suspenders also write the seed to:
   - `designer/<TOP>/<TOP>_iterate_seed.txt`
   - `designer/<TOP>/<TOP>_iterate_seedindex.txt`

7. **Windows MSYS path conversion** in bash: when sshing to Beelink and writing
   absolute Windows paths in scripts, prefer forward-slash `~/...`
   form. Backslash forms work but require careful escape handling through
   bash + ssh + Tcl interpreter chains.

8. **Process orchestration on Git Bash**: `nohup ... &` + `disown` is the
   reliable way to launch background Libero processes that survive SSH
   disconnect. Use `tasklist | grep libero` to confirm count; use a `.DONE`
   marker file pattern for completion signaling rather than polling logs.

## Reproducing audit-006 §2 (4-seed slack sweep)

```bash
# On Spark:
ssh bee 'bash ~/libero_seedsweep/parallel_launch.sh seed_7 seed_13 seed_23'
# Total wall time ~50 min; logs at ~/libero_seedsweep/<job>_run.log
# Markers at ~/libero_seedsweep/<job>.DONE / .FAILED
ssh bee 'bash ~/libero_seedsweep/parse_seed_slacks.sh'
```

See also: `~/projects/tychon-verification-workbench/tvw/audits/audit-006-fpga-timing-claim-revalidation.md` for the audit deliverable that consumed these results.

## When NOT to use this pattern

- Single-seed bring-up: just use `04_synth_pnr.tcl` or `closure_pipeline.tcl`.
- Smoke test that you only need to run once: not worth the clone overhead.
- POWERANALYSIS-driven workload sweeps: those need the full flow including
  power, so the time savings from skipping it don't apply.
