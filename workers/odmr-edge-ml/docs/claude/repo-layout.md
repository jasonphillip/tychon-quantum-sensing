# odmr-edge-ml — repo layout, data, commands, dependencies

Companion to `CLAUDE.md` (the map). Moved here verbatim from `CLAUDE.md` on 2026-09-04.

## Layout

- `src/odmr_edge_ml/` — package source (src layout)
- `tests/unit/` — self-contained unit tests (no external data needed)
- `tests/contract/` — contract tests against golden dataset
- `tests/smoke/` — end-to-end CPU-only smoke tests
- `experiments/` — standalone experiment scripts (training, evaluation, figures)
- `scripts/` — utility scripts (first training pass, FCNN export fix)
- `configs/` — YAML configuration files

## Data

Golden dataset: `./data/golden/` (dataset.h5 + manifest.json).
Production dataset: `./data/production_50k/` (50K spectra for full experiments).

Both are symlinks to the shared data directory and are gitignored. The golden dataset was generated with master_seed=12345: 100 train / 20 val / 20 test, 100-point spectra.

## Commands

```bash
pip install -e ".[dev]"       # install in dev mode
make test                     # all tests
make test-unit                # unit tests only
make test-contract            # contract tests (need golden dataset)
make test-smoke               # smoke tests (need golden dataset)
```

## Dependencies

Runtime: torch>=2.2, numpy>=1.26, h5py>=3.10, pyyaml>=6.0
Dev: pytest>=8.0
Python: >=3.11
