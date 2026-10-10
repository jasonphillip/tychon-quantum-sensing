"""CLI compile choice reaches every vector training channel."""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

from experiments import vector_v1_train as trainer


@pytest.mark.parametrize("flag,expected", [(True, False), (False, None)])
def test_compile_flag_reaches_each_channel_and_summary(tmp_path, monkeypatch, flag, expected):
    dataset = tmp_path / "tiny.h5"
    with h5py.File(dataset, "w") as h5:
        for split in ("train", "val"):
            group = h5.create_group(split)
            group.create_dataset("spectra", data=np.tile(np.linspace(0, 1, 64), (3, 1)))
            group.create_dataset("labels", data=np.tile([0.0, 0.0, 0.001], (3, 1)))
            group.create_dataset("frequencies", data=np.linspace(2.82e9, 2.92e9, 64))

    calls = []

    def fake_train_stage(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            val_metrics={"mae_uT": 2.0, "rmse_uT": 3.0},
            export_val_mae_uT={"float": 2.0, "int8": 2.5},
            learned_sigma=1.7,
            n_params=4,
            tflite_path=Path("model.tflite"),
            onnx_path=Path("model.onnx"),
        )

    monkeypatch.setattr(trainer, "train_stage", fake_train_stage)
    monkeypatch.setattr(trainer.torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(trainer.torch.cuda, "get_device_name", lambda _: "test GPU")
    out = tmp_path / "out"
    argv = ["vector_v1_train.py", "--dataset", str(dataset), "--out", str(out),
            "--window-size", "64", "--channels", "0,1;1,-1"]
    if flag:
        argv.append("--no-compile")
    monkeypatch.setattr(sys, "argv", argv)
    trainer.main()

    assert len(calls) == 2
    assert all(call["use_compile"] is expected for call in calls)
    summary = json.loads((out / "training_summary.json").read_text())
    assert summary["use_compile"] is (not flag)
    assert [ch["export_val_mae_uT"] for ch in summary["channels"]] == [
        {"float": 2.0, "int8": 2.5},
    ] * 2
