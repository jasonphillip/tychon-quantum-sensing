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

## Beelink Environment Setup

Beelink runs two environments — native Windows for FPGA synthesis, WSL for VectorBlox SDK.

### Native Windows: SmartHLS / Libero

**SmartHLS** — `C:\Microchip\Libero_SoC_2025.2\SmartHLS\SmartHLS\bin\shls.bat`

SmartHLS and Libero run natively on Windows. No special environment needed beyond the Microchip install.

### WSL (Ubuntu): VectorBlox SDK

**VectorBlox SDK v2.0.3** — installed at `C:\Microchip\VectorBlox-SDK\` (checked out at tag `release-v2.0.3`). The SDK's compiled `.so` libraries are x86-64 Linux only — `vnnx_compile`, `vnnx_infer`, and all `tflite_*` tools must run inside WSL, not native Windows.

**⚠ The Windows-side `conda vbx` env does not work** — it appears functional but the SDK tools fail without the Linux `.so`. Do not use it.

**⚠ DGX Sparks are ARM64 — the SDK cannot run there either.** Beelink WSL is the only machine that can run VectorBlox tools.

To enter the WSL environment:
```
wsl -d Ubuntu -u jason
source ~/vbx-env/bin/activate
```

**Python and dependency pinning (hard requirements):**

The WSL venv (`~/vbx-env`) must use **Python 3.10** — not 3.11 or 3.12. The SDK's `setup_vars.sh` and compiled `.so` files expect 3.10 ABI. Newer Python versions cause silent binary validation failures in `vnnx_compile` output.

Pinned versions:
```
python3.10 -m venv ~/vbx-env
pip install tensorflow-cpu==2.15.1 numpy==1.23.5
```

**flatc must be v23.5.26** (from [PINTO0309 flatbuffers releases](https://github.com/PINTO0309/flatbuffers/releases)), not the apt default. The apt version produces schema-incompatible FlatBuffer binaries that pass compilation but fail silently at inference time.

**Hidden dependencies:** The SDK's `setup.py` doesn't declare all deps. After `pip install -e .`, you also need:
```
pip install tensorflow-cpu silence_tensorflow natsort
```

**TensorFlow CUDA/oneDNN warnings** appear on every SDK run. They are cosmetic — ignore them.

## Beelink Quick Start Checklist

For 2am synthesis runs — two workflows depending on what you need:

### SmartHLS / Libero (native Windows)
1. Open Git Bash
2. `cd ~\projects\tychon-polarfire-control` (once cloned)
3. `git pull origin master`
4. Run `shls` commands or Libero Tcl scripts
5. Commit reports, push

### VectorBlox SDK (WSL)
1. `wsl -d Ubuntu -u jason`
2. `source ~/vbx-env/bin/activate`
3. `cd /mnt~/projects/tychon-polarfire-control`
4. `git pull origin master`
5. Run `vnnx_compile`, `vnnx_infer`, or `tflite_*` commands
6. Commit reports, push

## Transfer Protocol for Upstream Artifacts
- Repo 1 synthetic ODMR CSVs → copy to `hls/tb/stimulus/` from `~/projects/tychon-shared-data/`
- Repo 2 `.vnnx` models → copy to `models/` from `~/projects/tychon-shared-data/models/`
- Do NOT commit `.vnnx` files to git (large binaries)
- Use simple `cp` — no git submodules
