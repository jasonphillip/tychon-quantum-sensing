#!/usr/bin/env bash
# Launch increment-3 (lever B: appearance-fingerprint) training runs as one detached nohup
# chain. Multiple (name, seed) pairs run SERIALLY in the chain — this is how a single GB10 hosts
# two runs without the 2-parallel contention that pushed wave-2 past its 53 s/epoch threshold.
#
# Usage: scripts/train_run_3.sh <chain-tag> <name1> <seed1> [<name2> <seed2> ...]
#
# Recipe = the wave-2 reference (gated+linear, shot-noise aug SNR10, epochs 800 / batch 32 /
# patience 100 / val 5) on the v2 dataset. The appearance branch is unconditional in the model
# (zero-init, learned in), so no extra flag is needed. Everything local — no NAS paths.
set -euo pipefail
cd "$(dirname "$0")/.."
tag="$1"; shift
PY="$HOME/miniconda3/bin/python3"
[ -x "$PY" ] || PY=python3
mkdir -p artifacts/increment3
chain=""
while [ $# -ge 2 ]; do
  name="$1"; seed="$2"; shift 2
  step="PYTHONUNBUFFERED=1 $PY -u experiments/increment2a_train.py \
--dataset data/sequence_train_v2 --core gated --assoc linear --noise-snr 10 \
--epochs 800 --patience 100 --val-every 5 --batch-size 32 --seed $seed \
--out artifacts/increment3 --run-name $name 2>&1 \
| awk '{ print strftime(\"[%H:%M:%S]\"), \$0; fflush() }' > artifacts/increment3/${name}.log 2>&1"
  chain="${chain:+$chain && }$step"
done
nohup bash -c "$chain" > "artifacts/increment3/chain_${tag}.log" 2>&1 &
echo $! > "artifacts/increment3/chain_${tag}.pid"
disown
echo "launched chain $tag (pid $(cat "artifacts/increment3/chain_${tag}.pid"))"
