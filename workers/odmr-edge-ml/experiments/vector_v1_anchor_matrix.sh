#!/usr/bin/env bash
set -euo pipefail

# Plan C task C2 anchor ablation: 13 result files; training uses GPU, evaluation uses CPU TFLite.

PY=${PY:-~/miniconda3/envs/tfc2/bin/python}
WT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
export PYTHONPATH=$WT/src:${SHARED_DATA_SRC:-~/projects/tychon-shared-data/src}
export TRITON_CACHE_DIR=${TRITON_CACHE_DIR:-/tmp/triton-cache-$USER}
DS=${DS:-~/projects/nv-sensor-sim/artifacts/datasets/production_50k_v3_vector/dataset.h5}
OUT=${OUT:-~/projects/odmr-edge-ml/exports/portfolio-c2}
mkdir -p "$OUT"
ORACLE=~/projects/odmr-edge-ml/exports/vector_v1
EXTRA=${REGEN:+--regenerated-dataset}

cd "$WT"

ev() {
    "$PY" experiments/vector_v1_eval.py --dataset "$DS" "$@" $EXTRA
}

# A: Evaluate oracle-trained models.
for cond in full spectrum_only anchor_only; do
    ev --models "$ORACLE" --anchor-source oracle --condition "$cond" \
        --out-json "$OUT/oracle_${cond}.json"
done

for s in 1 2 4 8; do
    ev --models "$ORACLE" --anchor-source oracle --condition noisy_anchor \
        --anchor-noise-bins "$s" --out-json "$OUT/oracle_noisy_${s}.json"
done

for src in prior spectrum coarse_fit; do
    ev --models "$ORACLE" --anchor-source "$src" --condition full \
        --out-json "$OUT/oracle_model_${src}_anchor.json"
done

# B: Train coarse-fit models, then evaluate alternate anchor sources.
timeout --signal=INT 75m "$PY" experiments/vector_v1_train.py \
    --anchor-source coarse_fit --epochs 30 --dataset "$DS" --out "$OUT/models_coarse_fit"

for src in coarse_fit spectrum prior; do
    ev --models "$OUT/models_coarse_fit" --anchor-source "$src" \
        --out-json "$OUT/cf_model_${src}_anchor.json"
done
