# FPGA Demo Dashboard — Claude context

Live demo dashboard for the PolarFire SoC Icicle Kit (MPFS250T + CoreVectorBlox V250).
Developed on the Spark fleet (originally spark1, decommissioned 2026-07-05; now maintained on spark2); runs **offline** on the Mac for a live demo. Plan/design live in
`~/Desktop/Shared/fpga_demo/` (06 = implementation plan, 07 = M0 fix investigation).

## Stack
- `backend/` Python FastAPI + SSE. `KitLink` wraps `ssh icicle pid_ctl repl`; `FakeKit` is the
  software PID (DRY-RUN); `ReplayController` plays `backend/data/replay/*.jsonl`. `ModeManager`
  switches LIVE / DRY-RUN / REPLAY. Run from repo root: `uvicorn backend.main:app` (needs
  `PYTHONPATH=<repo root>`; `run_demo.sh` handles it).
- `frontend/` React + Vite + TS + uPlot; build to `dist/`, served same-origin by FastAPI.

## Hard rules
- **NEVER read the M0 gains slave** (`0x60040000–0x600407FF`). In idfix2, M0 writes are allowed
  only when both gates are set: `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`.
- LIVE M0 write allowlist is only `R_OUT_MIN`, `R_OUT_MAX`, `R_KP`, `R_KI`, `R_KD`,
  `R_INNER_CLAMP`, and `R_ACC_START`. All actuator reads must come from M1 `R_POST_CLAMP`.
- **Offline demo**: no CDN / Google-Fonts / external `url()` — bundle everything locally; use
  relative `/api` paths only.
- Honest labeling: LIVE replay is a host-paced hardware datapath with injected error. The selectable
  V250 loop mode uses the on-kit helper to run V250 -> M1 `u_ai` -> M0 `acc_start` -> M1
  `post_clamp_out`; FPGA-resident/live-sensor autonomous wiring is still pending. Use about 5%
  deployed `fcnn_v2_residual_dataset_a` reduction; do not headline `8.71%` or "bit-exact INT8" as
  deployed accuracy.
- Watchdog labeling: report raw state and the programmed `250000`-cycle / 2 ms fabric watchdog.
- Cold power-cycle remains recommended after reprogramming; if V250 probe passes, continue with the
  captured post-program checks.

## Data provenance
- `backend/data/replay/*.jsonl` ← polarfire-hybrid-control `sim/rung_g/`
- `backend/data/{spectra,metrics}.json` + `figures/adev.png` ← `/tmp/extract_context.py`
  (reads nv-sensor-sim HDF5 + odmr-edge-ml eval JSONs; needs h5py).
- Current remediation evidence and roadmap status live in
  `~/projects/polarfire-hybrid-control/docs/remediation_status_2026-06-21.md`.

## Commit authority
New standalone repo (not one of the 4 impl repos). Internal mirrors OK; **no public GitHub
push without approval** (same posture as the other Tychon repos).
