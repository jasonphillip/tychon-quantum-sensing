#!/usr/bin/env bash
set -euo pipefail

PY=~/miniconda3/bin/python3
DS=~/projects/odmr-vector-tracking/data/sequence_train_v2
A=~/projects/odmr-vector-tracking/artifacts/portfolio-n
COMMON="--dataset $DS --core gated --assoc linear --noise-snr 10 --epochs 800 --stop-epoch 330 --batch-size 32 --patience 100 --val-every 5 --out $A"

timeout --signal=INT 240m $PY experiments/increment2a_train.py $COMMON --seed 20260703 --w-assoc 1.0 --run-name assoc_s20260703
timeout --signal=INT 240m $PY experiments/increment2a_train.py $COMMON --seed 20260702 --w-assoc 0.0 --run-name noassoc_s20260702
timeout --signal=INT 240m $PY experiments/increment2a_train.py $COMMON --seed 20260703 --w-assoc 0.0 --run-name noassoc_s20260703
