"""Central config for the FPGA demo dashboard backend.

Paths are repo-relative so the whole tree copies cleanly to the Mac for the demo.
The kit host/IP is the ONLY environment-specific knob — override with env vars for
the travel-router LAN (e.g. KIT_HOST=192.168.x.x).
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
REPLAY_DIR = DATA_DIR / "replay"
TRACE_CSV = DATA_DIR / "odmr_representative_trace.csv"
DIST_DIR = BASE_DIR.parent / "frontend" / "dist"  # built static UI (Phase 5)

# --- kit connection (override via env on the travel-router LAN) -----------
KIT_HOST = os.environ.get("KIT_HOST", "icicle")          # ssh alias / IP
PID_CTL = os.environ.get("PID_CTL", "/root/bringup/pid_ctl")
BRINGUP = os.environ.get("BRINGUP", "/root/bringup")
V250_MODEL = os.environ.get("V250_MODEL", "fcnn_v2_residual_dataset_a.vnnx")
SSH_TIMEOUT = int(os.environ.get("SSH_TIMEOUT", "40"))   # seconds, for V250 calls

# --- replay sources -------------------------------------------------------
# Default REPLAY plays the real on-silicon capture (honest "recording": real
# liveness, actuator pinned at 0 by M0 gating). The dry-run capture (nonzero
# closed loop) is available via ?file=rung_g_dryrun_2026-06-18.jsonl.
DEFAULT_REPLAY_FILE = "rung_g_silicon_2026-06-18.jsonl"

# --- replay / stream defaults --------------------------------------------
DEFAULT_NN_CONST = -2.9506 / 64.0   # measured V250 out[0], scaled to actuator range
DEFAULT_ROWS = 120
