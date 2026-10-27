# FPGA Demo Dashboard

This offline Mac/Linux dashboard controls the PolarFire SoC Icicle Kit (MPFS250T + CoreVectorBlox V250) over SSH. LIVE mode shows the kit controller with replayed synthetic input; DRY-RUN mode generates values from a software model. Jason directed coding agents and checked written claims with local critics. The [FPGA controller](../../workers/polarfire-hybrid-control/README.md) and [project overview](../../README.md) link the measurements and build path.

The default DRY-RUN mode produces every displayed value, including PASS and LIVE badges, from a software model. Design notes and the implementation plan are retained in a private planning folder.

## Dry-run recording

**Software dry-run.** Every value in this recording, including the PASS and LIVE badges, comes from the dashboard's software model. The three scripted scenarios show a clamp event, watchdog fallback and a clean run.

![Software dry-run dashboard with simulated controller traces and status badges](../../docs/media/dashboard-demo.gif)

## Quick start
Needs Python 3 and Node.js with npm. The first run builds a virtual environment and the frontend.
`run_demo.sh` finds its own folder, so `demo/fpga-demo-dashboard/run_demo.sh` also works from the
repository root.
```bash
./run_demo.sh                                                # http://localhost:8077
KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh         # LIVE idfix2 actuator path
```
Open http://localhost:8077.

## Modes (top-right toggle)
- **DRY-RUN** — software model, no board needed
- **LIVE** — hardware datapath over ssh. Host-paced replay writes allowlisted idfix2 M0 gain/start
  registers, injects error through M1, and reads the real actuator from M1 `post_clamp_out`.
  `NN: V250 loop` starts the on-kit helper so V250 output feeds M1 `u_ai` and pulses the PID loop.
- **REPLAY** — plays a saved capture from `backend/data/replay/*.jsonl`

## What it shows
- **Tier 1** — connection/identity (live heartbeat), evidence badges, V250 inference, M1 CSR
  read + gain write/readback, safety watchdog
- **Tier 2** — telemetry plot (uPlot, streamed over SSE) with clamp/watchdog flags; V250 loop mode
  polls the daemon state continuously while the kit loop is running
- **Tier 3** — model card, deployed-model accuracy metrics (about 5% AIC-test reduction),
  ODMR spectrum viewer (real simulated input + ground-truth |B|)

## Architecture
- `backend/` FastAPI: `KitLink` (`ssh <host> pid_ctl repl`) / `FakeKit` / `ReplayController` + SSE.
  M0 reads are always blocked. M0 writes are allowlisted for idfix2 only and require
  `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`.
- `frontend/` React + Vite + TS + uPlot; built to `dist/`, served **same-origin** by FastAPI.
- All assets bundled locally — **no CDN / external fonts** — so it works on an isolated LAN.

## Dev
```bash
cd frontend && npm run dev      # Vite :5173, proxies /api -> :8077
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --port 8077
```
The Tier-3 snapshots in `backend/data/` were made by a one-off script (`/tmp/extract_context.py`,
needs h5py and the odmr eval JSONs) that is not in this repository, so they cannot be regenerated
from it.

## Offline checklist (before the demo)
- [ ] `./run_demo.sh` launches with **Wi-Fi OFF**
- [ ] LIVE: run with `KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1`
- [ ] LIVE: `csr_version=0x00010000`, `axi_write_count` climbs, V250 `out[0]=-2.9506`
- [ ] LIVE stream: idfix2 M0 smoke passes and M1 `post_clamp_out` shows nonzero actuator values
- [ ] `grep -rEi 'googleapis|cdn|unpkg|jsdelivr' frontend/dist` → empty
- [ ] `KIT_HOST` points at the reachable kit route; `ssh $KIT_HOST` works
- [ ] REPLAY mode works with the network unplugged (fallback)
- [ ] after any reprogram, run V250 probe; cold power-cycle only if the V250 does not reinitialize
