# Tychon NV-Sim — Claude Code Context

## Project
Tychon AI Phase I SBIR: NV-diamond magnetometer ODMR simulator and synthetic dataset generator.
Solo founder, 90-day sprint. This is Repo 1 of a planned two-repo architecture.

## Authoritative Documents
- `docs/phase1-context/tychon_phase1_repo_architecture_decisions.md` — **READ THIS FIRST.** Contains all repo architecture decisions, sanitized technical requirements, the dataset manifest contract, and the Repo 2 spec. This document supersedes any conflicting guidance.
- `docs/phase1-context/requirements.md` — Deliverable 1 technical requirements (if created separately; otherwise embedded in the decisions doc Section 3).
- `docs/future/repo2-odmr-ml-spec.md` — Full specification for Repo 2 (ML training). Do not build this code here. Repo 1 must satisfy the data contract defined in that spec.

## What This Repo Does
- Wraps SimOS to generate physics-based NV-diamond ODMR spectra
- Injects coupled stochastic noise (temperature, MW power) at the Hamiltonian level via Ornstein-Uhlenbeck processes
- Generates asymmetric lineshapes (B1 gradient + transverse B_perp)
- Produces versioned dataset manifests with seeds, units, splits, provenance
- Validates synthetic spectra against published reference data

## What This Repo Does NOT Do
- No ML training (that's Repo 2: tychon-odmr-ml)
- No FPGA/hardware code (that's Repo 3, deferred)
- No physics-informed neural networks (PINN) — explicitly excluded
- No surface noise model — removed in v4, irrelevant for bulk diamond ensemble

## Code Patterns
- **Adapters for external deps:** SimOS, QuaCCAToo, CUDA-Q, QDsiM each have an adapter in `src/tychon_nv_sim/adapters/`. Uncertain/unavailable deps use `NotImplementedError` stubs.
- **CPU smoke path required:** Every pipeline must work without CUDA, Julia, or vendor tools.
- **Package code is source of truth.** `experiments/` has Jupyter notebooks for exploration but they are not deliverables.
- Published noise parameters only — do not derive from first principles.

## Style and Conventions
- Python 3.11+
- Use `ruff` for formatting (run manually, no pre-commit hooks)
- Type hints on public APIs
- Docstrings on modules and public functions (numpy style)
- Tests in `tests/smoke/` (CPU-only) and `tests/unit/`
- Config via YAML files in `configs/` when needed; dataclasses for typed config objects

## Dependencies (core)
- simos, qutip>=5.2.3, numpy, scipy, pyyaml, h5py
- Optional: cudaq, cuquantum (GPU paths)
- Dev: pytest, ruff

## Experimental Validation Data
- **Extracted CSVs:** `data/experimental/zenodo_odmr/` — 25 spatially-averaged 1D CW-ODMR spectra (f0–f24), 200 freq points each (2.7–3.0 GHz). Ready for `load_experimental_odmr()`.
- **Raw data:** Stored locally (not in repo). 25 FITS files (4D wide-field: 1280×1024 px × 200 freq × 5 scans, ~2.5 GB each).
- **Extraction script:** `scripts/extract_zenodo_odmr.py` — reproduces CSVs from raw FITS. Supports `--input-dir` for alternate raw data paths.
- **Zenodo DOI:** [zenodo.org/records/7233869](https://zenodo.org/records/7233869) — Sengottuvel et al., "Wide-field magnetometry using nitrogen-vacancy color centers with randomly oriented micro-diamonds," *Scientific Reports* (2022). Uses randomly oriented micro-diamonds (not bulk crystal), 410 diamond spots over 307×245 µm² FOV.
- **Caveat:** Full-frame spatial averages smear ODMR dips due to B-field variation AND random NV axis orientations per microdiamond. For quantitative validation, extract spectra from individual bright diamond spots (ROIs) rather than full-frame averages.
- **Related papers:** Local reference PDFs for CW-ODMR components and low-cost ODMR experiments. Not in repo.

## Do NOT
- Add CI workflows, pre-commit hooks, or Claude skills/agents unless explicitly asked
- Over-scaffold — create files only when there is immediate use for them
- Put business-sensitive material (IP strategy, contacts, competitive intel) in this repo
- Import or depend on any ML training libraries (torch, tensorflow) — those belong in Repo 2

## Cross-Repo Data Flow
Repo 3 (tychon-polarfire-control) is scaffolded and on GitHub. Synthetic ODMR CSVs from this repo go to ~/projects/tychon-shared-data/ for Repo 3 consumption via hls/tb/stimulus/.
