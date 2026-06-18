# FPGA Demo Dashboard

Live demo control panel for the **PolarFire SoC Icicle Kit** (MPFS250T + CoreVectorBlox V250).
Runs fully offline on a Mac/Linux laptop; talks to the kit over SSH (M1-only, M0-guarded).

Design + plan: `~/Desktop/Shared/fpga_demo/` (README index, `06_implementation_plan.md`,
`07_m0_actuator_fix_investigation.md`).

## Quick start
```bash
./run_demo.sh                        # http://localhost:8077  (ssh alias 'icicle')
KIT_HOST=192.168.x.x ./run_demo.sh  # travel-router LAN (reserved kit IP)
```
Open http://localhost:8077.

## Modes (top-right toggle)
- **DRY-RUN** — software model, no board needed (default; full nonzero closed loop)
- **LIVE** — reads the kit over ssh (csr_version, axi_write_count, V250 inference, watchdog).
  The actuator value is **M0-gated → 0 on silicon**; error/liveness/inference are real.
- **REPLAY** — plays a saved capture from `backend/data/replay/*.jsonl`

## What it shows
- **Tier 1** — connection/identity (live heartbeat), evidence badges, V250 inference, M1 CSR
  read + gain write/readback, safety watchdog
- **Tier 2** — closed-loop telemetry plot (uPlot, streamed over SSE) with clamp/watchdog flags
- **Tier 3** — model card, accuracy metrics (8.71% vs PID, bit-exact INT8, Allan-deviation),
  ODMR spectrum viewer (real simulated input + ground-truth |B|)

## Architecture
- `backend/` FastAPI: `KitLink` (`ssh <host> pid_ctl repl`) / `FakeKit` / `ReplayController` + SSE.
  M1-only by construction — `registers.is_m0()` refuses the M0 gains slave (its reads wedge a hart).
- `frontend/` React + Vite + TS + uPlot; built to `dist/`, served **same-origin** by FastAPI.
- All assets bundled locally — **no CDN / external fonts** — so it works on an isolated LAN.

## Dev
```bash
cd frontend && npm run dev      # Vite :5173, proxies /api -> :8077
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --port 8077
```
Regenerate Tier-3 snapshots (needs h5py + the odmr eval JSONs): `python /tmp/extract_context.py`.

## Offline checklist (before the demo)
- [ ] `./run_demo.sh` launches with **Wi-Fi OFF**
- [ ] LIVE: `csr_version=0x00010000`, `axi_write_count` climbs, V250 `out[0]=-2.9506`
- [ ] `grep -rEi 'googleapis|cdn|unpkg|jsdelivr' frontend/dist` → empty
- [ ] kit on the travel-router LAN; `KIT_HOST` = its reserved IP; `ssh $KIT_HOST` works
- [ ] REPLAY mode works with the network unplugged (fallback)
- [ ] cold power-cycle the kit after any reprogram (V250 needs it)
