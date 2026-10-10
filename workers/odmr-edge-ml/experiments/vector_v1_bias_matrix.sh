#!/usr/bin/env bash
set -euo pipefail

# Plan N task N3: known bias (2 mT) plus a small unknown ambient field (<= 200 uT); labels = total field.
# Prior anchors come from the manifest bias and are available at deployment. Training uses GPU, evaluation CPU TFLite.

PY=${PY:-~/miniconda3/envs/tfc2/bin/python}
WT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH=$WT/src:${SHARED_DATA_SRC:-~/projects/tychon-shared-data/src}
export TRITON_CACHE_DIR=${TRITON_CACHE_DIR:-~/projects/odmr-edge-ml/exports/portfolio-c2/triton-cache}
DSR=${DSR:-~/projects/nv-sensor-sim/artifacts/datasets}
DS=${DS:-$DSR/production_50k_v4_bias/dataset.h5}
OUT=${OUT:-~/projects/odmr-edge-ml/exports/portfolio-n/bias}
mkdir -p "$OUT"
cd "$WT"

ev() {
    "$PY" experiments/vector_v1_eval.py --dataset "$DS" --regenerated-dataset "$@"
}

timeout --signal=INT 75m "$PY" experiments/vector_v1_train.py --dataset "$DS" --anchor-source prior --epochs 30 --out "$OUT/models_prior"
timeout --signal=INT 75m "$PY" experiments/vector_v1_train.py --dataset "$DS" --anchor-source oracle --epochs 30 --out "$OUT/models_oracle"

for src in prior spectrum coarse_fit; do
    ev --models "$OUT/models_prior" --anchor-source "$src" --out-json "$OUT/models_prior_${src}.json"
done
for src in oracle prior; do
    ev --models "$OUT/models_oracle" --anchor-source "$src" --out-json "$OUT/models_oracle_${src}.json"
done
