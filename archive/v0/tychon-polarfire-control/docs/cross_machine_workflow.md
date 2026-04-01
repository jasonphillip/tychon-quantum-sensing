# Cross-Machine Workflow: DGX Spark ↔ Beelink

Repo 3 source lives on DGX Spark (where Claude Code CLI operates).
Synthesis runs on Beelink (where Libero/SmartHLS are installed).

```
DGX Spark (source of truth):
  ~/projects/tychon-polarfire-control/
  - Edit C++ source, write testbenches, commit, push to GitHub
  - Run ops_guard checks on model architectures

    ↓ git push / git pull ↓

Beelink (synthesis machine):
  C:\Users\...\tychon-polarfire-control\
  - git pull from GitHub
  - shls sw_run (C++ testbench — verifies on x86)
  - shls hw (RTL generation)
  - Run Libero Tcl scripts for synthesis, P&R
  - Extract SmartTime / SmartPower reports
  - Push reports back to GitHub

    ↓ git push / git pull ↓

DGX Spark:
  - git pull to get synthesis reports
  - Analyze, document, iterate
```

## Rules
- Never edit source on Beelink — it's a build machine only
- Synthesis outputs (.job, reports) committed to `libero/reports/` and pushed
- `.gitignore` excludes Libero work directories, IP caches, intermediate synthesis files
- All Libero operations are Tcl-scripted — no GUI state to lose

## Transfer Protocol for Upstream Artifacts
- Repo 1 synthetic ODMR CSVs → copy to `hls/tb/stimulus/` from `~/projects/tychon-shared-data/`
- Repo 2 `.vnnx` models → copy to `models/` from `~/projects/tychon-shared-data/models/`
- Do NOT commit `.vnnx` files to git (large binaries)
- Use simple `cp` — no git submodules
