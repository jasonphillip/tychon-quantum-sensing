"""Central config for the FPGA demo dashboard backend.

Paths are repo-relative so the whole tree copies cleanly to the Mac for the demo.
The kit host/IP is environment-specific; idfix2 M0 writes require explicit env
opt-in so older bitstreams cannot be touched by accident.
"""
from __future__ import annotations

import os
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPLAY_DIR = DATA_DIR / "replay"
TRACE_CSV = DATA_DIR / "odmr_representative_trace.csv"
DIST_DIR = BASE_DIR.parent / "frontend" / "dist"  # built static UI (Phase 5)

# --- kit connection -------------------------------------------------------
KIT_HOST = os.environ.get("KIT_HOST", "icicle")          # ssh alias / IP
PID_CTL = os.environ.get("PID_CTL", "/root/bringup/pid_ctl")
V250_PID_LOOP = os.environ.get("V250_PID_LOOP", "/root/bringup/v250_pid_loop")
V250_INPUT_CSV = os.environ.get("V250_INPUT_CSV", "/root/bringup/odmr_v250_rows.csv")
V250_LOOP_STATE = os.environ.get("V250_LOOP_STATE", "/tmp/v250_pid_loop_state.json")
V250_LOOP_PID = os.environ.get("V250_LOOP_PID", "/tmp/v250_pid_loop.pid")
V250_LOOP_LOG = os.environ.get("V250_LOOP_LOG", "/tmp/v250_pid_loop_daemon.log")
# The 2 ms fabric watchdog needs the helper to run as fast as the V250/PID path allows.
V250_LOOP_SLEEP_US = int(os.environ.get("V250_LOOP_SLEEP_US", "0"))
V250_U_SCALE = float(os.environ.get("V250_U_SCALE", "0.015625"))
BRINGUP = os.environ.get("BRINGUP", "/root/bringup")
V250_MODEL = os.environ.get("V250_MODEL", "fcnn_v2_residual_dataset_a.vnnx")
SSH_TIMEOUT = int(os.environ.get("SSH_TIMEOUT", "40"))   # seconds, for V250 calls
KIT_BITSTREAM = os.environ.get("KIT_BITSTREAM", "").strip().lower()
ALLOW_IDFIX2_M0 = _env_bool("ALLOW_IDFIX2_M0", False)

# Live idfix2 host-paced demo gains. Ki/Kd stay zero because host injection is
# not at the 125 MHz fabric rate; this mirrors polarfire-hybrid-control/tools/rung_g_replay.py.
PID_KP = float(os.environ.get("PID_KP", "0.8"))
PID_KI = float(os.environ.get("PID_KI", "0.0"))
PID_KD = float(os.environ.get("PID_KD", "0.0"))
PID_OUT_MIN = float(os.environ.get("PID_OUT_MIN", "-1.0"))
PID_OUT_MAX = float(os.environ.get("PID_OUT_MAX", "1.0"))

# --- replay sources -------------------------------------------------------
# Default REPLAY plays the saved on-silicon capture. New LIVE streams use the
# idfix2 M0-safe actuator path when explicitly enabled.
DEFAULT_REPLAY_FILE = "rung_g_silicon_2026-06-18.jsonl"

# --- replay / stream defaults --------------------------------------------
DEFAULT_NN_CONST = -2.9506 / 64.0   # measured V250 out[0], scaled to actuator range
DEFAULT_ROWS = 120
