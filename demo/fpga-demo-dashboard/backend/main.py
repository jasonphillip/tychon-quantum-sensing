"""FastAPI app for the FPGA demo dashboard.

Run from the repo root:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000

Modes: DRY-RUN (default, no kit), LIVE (ssh to the Icicle kit), REPLAY (saved .jsonl).
All hardware access is M1-only and guarded against M0 (see registers.is_m0).
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from . import config
from .modes import VALID, ModeManager

app = FastAPI(title="FPGA Demo Dashboard", version="0.1.0")

# Dev convenience: the Vite dev server (5173) calls this backend (8000) cross-origin.
# In the packaged demo the UI is served same-origin from dist/, so this is harmless.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173",
                   "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"], allow_headers=["*"],
)

modes = ModeManager(initial="DRY-RUN")


# --- request bodies -------------------------------------------------------
class ModeBody(BaseModel):
    mode: str
    file: str | None = None


class GainBody(BaseModel):
    name: str
    value: float


# --- meta -----------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True, "mode": modes.mode}


@app.get("/api/mode")
def get_mode():
    return {"mode": modes.mode, "replay_file": modes.replay_file, "valid": list(VALID)}


@app.post("/api/mode")
def set_mode(body: ModeBody):
    try:
        modes.set_mode(body.mode, body.file)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return get_status()


# --- live surface ---------------------------------------------------------
@app.get("/api/status")
def get_status():
    ctrl = modes.current()
    try:
        return ctrl.read_status()
    except Exception as e:
        return JSONResponse(
            {"mode": modes.mode, "online": False, "error": str(e),
             "csr_version_ok": False},
            status_code=200,  # report offline rather than 500 (kit may be unplugged)
        )


@app.get("/api/evidence")
def get_evidence():
    return modes.current().evidence()


@app.post("/api/v250/probe")
def v250_probe():
    try:
        return modes.current().v250_check()
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/csr")
def csr_read():
    return modes.current().csr_read_all()


@app.post("/api/csr/write")
def csr_write(body: GainBody):
    try:
        return modes.current().csr_write_gain(body.name, body.value)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/watchdog/demo")
def watchdog_demo():
    """Report the live watchdog state. Active induction (stopping V250 output_valid
    to force a timeout) is an open item (#4) pending firmware confirmation — for now
    this surfaces the real watchdog_csr so the panel is honest."""
    ctrl = modes.current()
    status = ctrl.read_status()
    return {
        "watchdog_timeout": status.get("watchdog_timeout", 0),
        "induced": False,
        "note": "live watchdog_csr readout; on-demand induction TBD (open item #4)",
    }


@app.get("/api/telemetry/stream")
def telemetry_stream(rows: int = config.DEFAULT_ROWS, nn: str = "surrogate",
                     stunt: str = "none", period: float = 0.05):
    ctrl = modes.current()

    def gen():
        try:
            for s in ctrl.stream(rows, nn, stunt, period):
                yield f"data: {json.dumps(s)}\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as e:  # noqa: BLE001 — surface to the client, don't 500
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache",
                                      "X-Accel-Buffering": "no"})


# --- Tier-3 context (snapshots wired in Phase 4) --------------------------
@app.get("/api/model-card")
def model_card():
    return {"phase4": True, "name": "FCNN v2 (residual)", "params": 3300,
            "quant": "INT8", "tflite_kb": 7.5, "vnnx_kb": 12.5,
            "task": "100-pt ODMR window -> scalar dB residual correction",
            "note": "placeholder; full card snapshot wired in Phase 4"}


@app.get("/api/metrics")
def metrics():
    return {"phase4": True, "note": "metrics snapshot (MAE, +8.71%, Allan-dev) wired in Phase 4"}


@app.get("/api/spectrum")
def spectrum():
    return {"phase4": True, "note": "ODMR spectrum + pred-vs-truth wired in Phase 4"}


# --- static UI (Phase 5: built frontend served same-origin) ---------------
if config.DIST_DIR.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=str(config.DIST_DIR), html=True), name="ui")
else:
    @app.get("/")
    def root():
        return {"app": "FPGA Demo Dashboard backend", "mode": modes.mode,
                "ui": "not built yet — run the Vite dev server (Phase 2) or build dist/ (Phase 5)",
                "api": ["/api/status", "/api/evidence", "/api/v250/probe", "/api/csr",
                        "/api/telemetry/stream", "/api/mode"]}
