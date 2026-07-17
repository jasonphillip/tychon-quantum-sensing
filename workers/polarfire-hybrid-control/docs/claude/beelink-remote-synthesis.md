# Remote Synthesis (Beelink)

> Moved verbatim from CLAUDE.md during the 2026-07-17 progressive-disclosure restructure.

SSH from Spark lands in Git Bash (MINGW64) on the Beelink. SmartHLS and Libero are accessible via wrapper scripts.
```bash
# Test SmartHLS from Spark:
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull && cd hls && shls sw_run"

# Trigger full Libero synthesis from Spark:
ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull && libero SCRIPT:libero/scripts/04_synth_pnr.tcl"

# VectorBlox SDK (requires WSL):
ssh bee "wsl -d Ubuntu -u jason -- bash -c 'source ~/vbx-env/bin/activate && vnnx_compile -c V250 -t model.tflite -o model.vnnx'"
```

Beelink paths:
- Repo: ~/dev/projects/polarfire-hybrid-control/
- shls wrapper: ~/bin/shls → C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\bin\shls.bat
- libero wrapper: ~/bin/libero → C:\Microchip\Libero_SoC_2025.2\Libero_SoC\Designer\bin\libero

Rules:
- Never edit source on Beelink — Spark is source of truth
- Always git pull on Beelink before building
- Beelink pushes synthesis reports only (libero/reports/)

## Parallel synthesis / seed-sweep on Beelink

For multi-seed P&R sweeps, variance studies, or any audit that needs N independent placement runs against the same RTL+netlist baseline, **default to parallel execution on Beelink** and **never run them sequentially unless you've already proven parallel doesn't fit**. Beelink resource ceiling and a working pattern are documented at `libero/scripts/parallel/README.md`. Headlines:

- **Beelink resources** (verified 2026-05-03): 64 GB RAM (≥56 GB free pre-launch), 774 GB free disk on `C:`. Supports ≥4 concurrent Libero processes (~2 GB each in synth, peaks ~8 GB during P&R).
- **Synplify Pro license** is `INCREMENT synplifypro_actel ... uncounted` in `C:\FlexLM\License.dat` — unlimited concurrent seats. Same for `ACTEL_BASESOC` and `SmartHLS`.
- **One Libero project = one prjx lock**. To run N P&Rs in parallel you must clone the project to N independent directories. The project root is **583 MB** (Vectorblox+Icicle base design); 4 clones = ~2.4 GB.
- **The clone gotcha**: `MPFS_ICICLE_Vectorblox.prjx` hardcodes its absolute self-path (`KEY ProjectLocation "C:\Microchip\...\MPFS_ICICLE_Vectorblox"`) at line 35. Clones must rewrite this. Synth-stage report files (e.g. `synthesis/synlog/*_compiler.srr`) also embed absolute paths to the original install tree — re-running SYNTHESIZE in a clone doesn't always cleanly overwrite them, which can cause parallel Synplify launches from N clones to fail with `Error: Synthesis failed.` even with uncounted licenses.
- **Reliable parallel pattern (proven 2026-05-03 audit-006 §2)**: do ONE Synplify re-synth in a "master" clone, then `cp -r master/synthesis/* seed_N/synthesis/` and `cp -r master/component/* seed_N/component/` to each P&R clone (their `.prjx` self-path stays as the rewritten clone path), then run **PLACEROUTE + VERIFYTIMING only** in each P&R clone with `configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:N"]`. This isolates the ~25 min Synplify step (1×) from the ~25 min P&R step (parallel ×N).
- **Tcl path syntax**: Libero in MSYS Git Bash needs Windows-style script paths — `libero "SCRIPT:~/foo.tcl"` works; `SCRIPT:~/foo.tcl` fails with `Parameter 'file' is missing or has invalid value`.
- **Seed knob — BROKEN IN BATCH TCL (audit-006 root-cause 2026-05-03)**: `configure_tool -name {PLACEROUTE} -params [list "RANDOM_SEED:N"]` from a Tcl script does **not** vary placement. The actual mechanism: Libero's batch PLACEROUTE invokes the built-in **Multi-Pass / Iterate Seeds** feature with auto-incremented seed index (next number after the project's existing `r{N}_s{M}.rpt` highest), and **terminates at iteration 1 if timing closes** (`Multi-Pass: Have met stopping criterion`). So all 3 clones with SEED 7/13/23 actually placed at "Seed Index 27" and stopped after the first iteration that met timing. The configure_tool seed value never reached the placer. Verified across 3 independent clones — all produced **bit-identical placement** (path 1/2/3 endpoints, delays, slacks match to 3 decimal places).
- **To actually get N seeds via Multi-Pass**: disable the early-stopping criterion. The relevant Tcl knob is `configure_tool -name {PLACEROUTE} -params [list "EFFORT_LEVEL:high" "MULTIPASS_RUNS:N" "STOP_ON_FIRST_PASS:false"]` (parameter names assumed — needs validation against Microchip Libero 2025.2 reference). Each iteration writes a separate timing rpt; collect them after PLACEROUTE returns. This is **deferred research** — none of those exact param names tested yet.
- **What is reliably variable across clones**: synth output (Synplify Pro is non-deterministic across days even with identical RTL+SDC+tool — the audit-006 re-synth produced sha256 `44917cd6` while the Apr-30 on-disk netlist was `ae51d60d`), tool effort levels, constraint variations. Use those as the variance dimension if you need a meaningful sweep.
- **What IS deterministic** (audit-006 confirmed positive finding): Libero Designer's PLACEROUTE is bit-identical across independent clones for fixed `(netlist, prjx-state, effective-seed)`. So clone-based replication is good for cross-clone audits and reproducibility checks even though the seed knob doesn't work.
- **`run_tool -name {SYNTHESIZE} -script {REPORT}`** is **invalid Tcl** — `-script` expects a Tcl filepath, not a built-in. The construct in legacy `04_synth_pnr.tcl` line 39 / `pnr_verify_only.tcl` is dead code; use plain `run_tool -name {SYNTHESIZE}`.
- **For variance sweeps, skip POWERANALYSIS and GENERATEPROGRAMMINGDATA** — only PLACEROUTE+VERIFYTIMING are needed for slack characterization. Saves ~5 min per clone.
- **Don't re-run SYNTHESIZE in each clone in parallel.** Synplify's startup races and the synth-stage absolute-path entanglement above will make some of them fail. Use the "1 master synth, N parallel P&Rs" pattern.

Reusable templates and a launcher under `libero/scripts/parallel/`. End-to-end wall time for a 4-clone sweep: synth ~25 min + parallel P&R ~25 min ≈ **~50 min total** (versus ~3 hr if run sequentially with re-synth per seed).
