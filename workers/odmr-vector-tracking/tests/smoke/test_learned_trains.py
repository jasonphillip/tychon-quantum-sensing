"""Smoke: the training harness reduces loss end-to-end on a tiny synthetic fixture (CPU).

Not a convergence test — just proof that data → targets → forward → losses → backward → step
is wired: the total loss must drop substantially within a few dozen epochs. The real sanity
gate (overfit one sequence to ~perfect association) runs in
``experiments/increment2a_train.py --overfit-one`` against the real dataset.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.training import TrainSettings, build_split_tensors, set_seed, train
from tests.fixtures.synthetic import write_synthetic_h5


@pytest.fixture(scope="module")
def tiny_dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("tiny_seq")
    # Small T/F keep the CPU run fast; the fixture guard still requires an inter-axis crossing.
    write_synthetic_h5(out, {"train": 2, "val": 1, "test": 1}, n_timesteps=48, n_freq=160)
    return out


def test_training_reduces_loss(tiny_dataset: Path) -> None:
    loader = SequenceDatasetLoader(tiny_dataset)
    m = loader.manifest
    freq_range = (float(m["freq_range_Hz"][0]), float(m["freq_range_Hz"][1]))

    cfg = LearnedTrackerConfig(n_freq=int(m["n_freq_points"]), n_lines=int(m["n_lines"]))
    set_seed(0)
    tracker = build_tracker(cfg, core="relu", association="linear")

    train_t = build_split_tensors(
        loader.load_split("train"),
        tracker.extractor.get_buffer("anchors"),
        freq_range,
        cfg.proj_scale_T,
        "cpu",
    )
    settings = TrainSettings(
        epochs=40, batch_size=2, patience=10_000, lr=3e-3, device="cpu", log_every=10_000
    )
    result = train(
        tracker, train_t, train_t, settings, out_dir=None, log=lambda _msg: None
    )

    first = result.history[0]["train_total"]
    last = result.history[-1]["train_total"]
    assert last < 0.5 * first, f"loss did not drop: {first:.4f} -> {last:.4f}"
    # Association CE specifically must move (the thesis loss, not just the easy MSE).
    assert result.history[-1]["train_association"] < result.history[0]["train_association"]
