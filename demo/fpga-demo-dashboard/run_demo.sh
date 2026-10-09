#!/usr/bin/env bash
# One-command launcher for the FPGA demo dashboard.
# Serves the built UI + API on http://localhost:8077 (same-origin, offline-capable).
#
#   ./run_demo.sh                          # ssh alias 'icicle'
#   KIT_BITSTREAM=idfix2 ALLOW_IDFIX2_M0=1 ./run_demo.sh
#   KIT_HOST=icicle ./run_demo.sh          # override ssh alias/IP
#   PORT=9000 ./run_demo.sh                # custom port
#
# DRY-RUN mode (default in the UI) needs no kit at all.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PORT="${PORT:-8077}"

# 1) python venv + backend deps
if [ ! -x "$ROOT/.venv/bin/uvicorn" ]; then
  echo "[setup] creating venv + installing backend deps…"
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install -q -r "$ROOT/backend/requirements.txt"
fi

# 2) build the frontend if dist/ is missing
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "[setup] building frontend (one-time)…"
  ( cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build )
fi

# 3) serve (built UI + API, same origin)
echo "[run] dashboard -> http://localhost:${PORT}   (KIT_HOST=${KIT_HOST:-icicle})"
exec env PYTHONPATH="$ROOT" "$ROOT/.venv/bin/uvicorn" backend.main:app --host 0.0.0.0 --port "$PORT"
