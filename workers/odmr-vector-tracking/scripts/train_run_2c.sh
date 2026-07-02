#!/usr/bin/env bash
# Launch one 2c training run (frozen reference recipe) as a detached nohup job.
#
# Usage: scripts/train_run_2c.sh <run-name> <seed> [extra increment2a_train.py flags...]
#
# Recipe is the v1-scale reference (v1_gated_linear_snr10): gated+linear, shot-noise aug
# SNR10, epochs 800 / batch 32 / patience 100 / val_every 5. Logs are timestamped and
# unbuffered; pidfile written next to the log. Everything local — no NAS paths.
set -euo pipefail
cd "$(dirname "$0")/.."
name="$1"; seed="$2"; shift 2
PY="$HOME/miniconda3/bin/python3"
[ -x "$PY" ] || PY=python3
mkdir -p artifacts/increment2c
nohup bash -c "PYTHONUNBUFFERED=1 $PY -u experiments/increment2a_train.py \
  --dataset data/sequence_train_v2 --core gated --assoc linear --noise-snr 10 \
  --epochs 800 --patience 100 --val-every 5 --batch-size 32 --seed $seed \
  --out artifacts/increment2c --run-name $name $* 2>&1 \
  | awk '{ print strftime(\"[%H:%M:%S]\"), \$0; fflush() }'" \
  > "artifacts/increment2c/${name}.log" 2>&1 &
echo $! > "artifacts/increment2c/${name}.pid"
disown
echo "launched $name (seed $seed) wrapper-pid $(cat "artifacts/increment2c/${name}.pid")"
