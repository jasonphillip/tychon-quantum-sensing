> Original: claude.ai project document, created 2026-04-04. Edited for publication: names of other people and business details removed.

# Tychon AI — Repository Migration Record (Updated)

**Original date:** April 3, 2026
**Last updated:** April 4, 2026
**Author:** Jason Phillip
**Status:** COMPLETE — all repos migrated, Beelink updated, remote synthesis enabled

---

## CRITICAL: Read This First

**As of April 3, 2026, the active code repositories have new names.** All older project knowledge files reference the OLD repo names. Those files are still valid for their technical content, but repo names, package names, and file paths must be mapped using the table below.

**CLAUDE.md files exist locally in each repo but are NOT tracked by git.** They are excluded via global gitignore on both Spark and Beelink. They will never appear on GitHub or in commit history.

---

## Repo Name Mapping

| Role | Old Repo (archived, private) | New Repo (active, private) | Python/C Package | Branch |
|------|------------------------------|---------------------------|-----------------|--------|
| Repo 1: NV physics sim | `tychon-nv-sim` | `nv-sensor-sim` | `nv_sensor_sim` | `main` |
| Repo 2: ML training/export | `tychon-odmr-ml` | `odmr-edge-ml` | `odmr_edge_ml` | `main` |
| Repo 3: FPGA control | `tychon-polarfire-control` | `polarfire-hybrid-control` | N/A (C/C++) | `main` |

**GitHub:** All repos under `github.com/jasonphillip/` (personal account). Old repos kept private, untouched.

---

## Current Machine State (April 4, 2026)

### A local DGX Spark node (DGX Spark, ARM64 — source of truth for all code)
```
~/projects/nv-sensor-sim/              ← Active Repo 1
~/projects/odmr-edge-ml/               ← Active Repo 2
~/projects/polarfire-hybrid-control/   ← Active Repo 3

~/projects/tychon-nv-sim/              ← Archived Repo 1 (untouched)
~/projects/tychon-odmr-ml/             ← Archived Repo 2 (untouched)
~/projects/tychon-polarfire-control/   ← Archived Repo 3 (untouched)

~/projects/tychon-shared-data/         ← Dataset storage (unchanged)
  golden/                              ← 140 spectra validation set
  production_50k/                      ← 50K production dataset

Global gitignore: ~/.gitignore_global (CLAUDE.md, CLAUDE.local.md, .claude/)
```

### Repo 2 Data Symlinks (Spark)
```
~/projects/odmr-edge-ml/data/golden → ~/projects/tychon-shared-data/golden
~/projects/odmr-edge-ml/data/production_50k → ~/projects/tychon-shared-data/production_50k
```

### Beelink "Bee" (Windows 11, x86 — synthesis machine)
```
~/dev/projects/polarfire-hybrid-control/   ← Active Repo 3 clone (NEW, cloned April 4)
~/dev/projects/tychon-polarfire-control/   ← Old Repo 3 clone (keep until new Libero .prjx verified)

SSH: Spark can SSH into Beelink (lands in Git Bash / MINGW64)
SmartHLS: accessible via ~/bin/shls wrapper → shls.bat
Libero: accessible via ~/bin/libero wrapper → libero.exe
VectorBlox SDK: WSL only (~/VectorBlox-SDK, Python 3.10 venv ~/vbx-env)

Global gitignore: ~/.gitignore_global (CLAUDE.md, CLAUDE.local.md, .claude/)
Claude Code: v2.1.80 installed in Git Bash
```

### NAS (local network storage)
```
/volume1/projects/tychon-artifacts/models/ — TFLite, .vnnx, ONNX files
```

---

## Cross-Machine Workflow (Updated April 4, 2026)

```
DGX Spark (source of truth):
  ~/projects/polarfire-hybrid-control/
  - Edit C++ source, write testbenches, commit, push to GitHub
  - Can trigger remote builds via SSH

    ↓ git push ↓

GitHub (github.com/jasonphillip/polarfire-hybrid-control)

    ↓ git pull (on Beelink, via SSH from Spark or locally) ↓

Beelink (synthesis machine, x86):
  ~/dev/projects/polarfire-hybrid-control/
  - git pull from GitHub
  - shls sw_run (C++ testbench via ~/bin/shls wrapper)
  - shls hw (RTL generation)
  - Libero Tcl scripts for synthesis, P&R (via ~/bin/libero wrapper)
  - SmartTime/SmartPower report extraction
  - Commit reports to libero/reports/ and push

    ↓ git push ↓

GitHub → git pull on Spark

Remote trigger from Spark (NEW):
  ssh bee "cd ~/dev/projects/polarfire-hybrid-control && git pull && shls sw_run"
  ssh bee "cd ~/dev/projects/polarfire-hybrid-control && libero SCRIPT:libero/scripts/04_synth_pnr.tcl"
```

**Rules:**
- Spark is source of truth for code — never edit source on Beelink
- Beelink pushes synthesis reports only (libero/reports/)
- SSH into Beelink lands in Git Bash (MINGW64) with direct access to Windows tools
- VectorBlox SDK operations require WSL session

---

## CLAUDE.md Management

CLAUDE.md files are present locally in all three repos on Spark and in polarfire-hybrid-control on Beelink. They are **not tracked by git** — excluded via global gitignore on both machines.

- Spark: ~/.gitignore_global contains CLAUDE.md, CLAUDE.local.md, .claude/
- Beelink: ~/.gitignore_global contains CLAUDE.md, CLAUDE.local.md, .claude/
- GitHub: No CLAUDE.md in any repo, no trace in commit history
- Claude Code reads CLAUDE.md automatically from disk regardless of git tracking

**Commit message convention (all repos):** Never reference specific development tools, assistants, or AI in commit messages. Describe what changed technically.

---

## What Was Done (Summary)

### April 3, 2026 — Repo Migration
- Created clean copies of all 3 repos under new names
- Scrubbed all LLM/internal process references
- Renamed all packages, imports, project names, cross-repo references
- Fresh git init with single clean initial commit per repo
- Pushed to GitHub (private)
- Created clean CLAUDE.md files from old repo knowledge, committed, then removed from git history via reset + force push
- Set up global gitignore on Spark

### April 4, 2026 — Beelink Setup
- Set up global gitignore on Beelink
- Cloned polarfire-hybrid-control to Beelink
- Created ~/bin/shls and ~/bin/libero wrapper scripts for remote access
- Verified SmartHLS reachable via SSH from Spark
- Remote synthesis capability confirmed operational

---

## Verification Results

### Repos (April 3)
| Check | Repo 1 | Repo 2 | Repo 3 |
|-------|--------|--------|--------|
| Tests passing | 49/49 | 87/87 | N/A (x86) |
| Sensitive term grep | 0 hits | 0 hits | 0 hits |
| Package install + import | OK | OK | N/A |
| CLAUDE.md on GitHub | No | No | No |
| LICENSE on GitHub | No | No | No |
| Single commit | Yes | Yes | Yes |

### Beelink (April 4)
| Check | Status |
|-------|--------|
| Global gitignore configured | Yes |
| polarfire-hybrid-control cloned | Yes |
| shls wrapper working | Yes (SmartHLS 2025.2) |
| libero wrapper on PATH | Yes |
| Old repo preserved | Yes (tychon-polarfire-control) |

