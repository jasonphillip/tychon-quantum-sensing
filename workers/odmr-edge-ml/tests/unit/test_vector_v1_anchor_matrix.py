"""Accepted training invocation for the C2 anchor matrix."""

from pathlib import Path


def test_retrain_uses_accepted_dataset_epochs_and_timeout():
    script = (Path(__file__).resolve().parents[2] /
              "experiments/vector_v1_anchor_matrix.sh").read_text()
    retrain = script.split("# B: Train coarse-fit models", 1)[1].split("for src", 1)[0]
    assert 'timeout --signal=INT 75m "$PY" experiments/vector_v1_train.py' in retrain
    assert '--anchor-source coarse_fit --epochs 30 --dataset "$DS"' in retrain
