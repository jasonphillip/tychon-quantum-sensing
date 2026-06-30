"""Unit tests for the V250 ops-guard (PyTorch-graph stage)."""

from __future__ import annotations

import torch
import torch.nn as nn

from odmr_vector_tracking.validation.ops_guard import (
    OpsGuardError,
    assert_v250_compatible,
    check_model_ops,
)


def test_relu_mlp_is_compatible() -> None:
    mlp = nn.Sequential(nn.Linear(100, 32), nn.ReLU(), nn.Linear(32, 3))
    report = check_model_ops(mlp, input_shape=(1, 100))
    assert report.is_compatible
    assert "aten.linear" in report.allowed


def test_conv2d_1k_is_compatible() -> None:
    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.c = nn.Conv2d(1, 8, (1, 5))
            self.act = nn.ReLU()
            self.fc = nn.Linear(8 * 96, 3)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.fc(self.act(self.c(x)).flatten(1))

    report = check_model_ops(Net(), input_shape=(1, 1, 1, 100))
    assert report.is_compatible


def test_conv1d_is_flagged() -> None:
    class Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.c = nn.Conv1d(1, 4, 5)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.c(x)

    report = check_model_ops(Net(), input_shape=(1, 1, 100))
    assert not report.is_compatible


def test_batchnorm_module_is_flagged() -> None:
    model = nn.Sequential(nn.Linear(16, 16), nn.BatchNorm1d(16), nn.ReLU())
    report = check_model_ops(model, input_shape=(4, 16))
    assert not report.is_compatible
    assert any("BatchNorm1d" in d for d in report.disallowed)


def test_softmax_and_matmul_are_flagged() -> None:
    class Attn(nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            s = torch.softmax(x @ x.transpose(-1, -2), dim=-1)
            return s @ x

    report = check_model_ops(Attn(), input_shape=(1, 8, 16))
    assert not report.is_compatible
    assert "aten.softmax" in report.disallowed
    assert "aten.matmul" in report.disallowed


def test_assert_raises_on_incompatible() -> None:
    bad = nn.Sequential(nn.Linear(16, 16), nn.Tanh())
    try:
        assert_v250_compatible(bad, input_shape=(1, 16))
    except OpsGuardError:
        return
    raise AssertionError("expected OpsGuardError for a tanh model")


def test_assert_returns_report_on_compatible() -> None:
    good = nn.Sequential(nn.Linear(16, 8), nn.ReLU())
    report = assert_v250_compatible(good, input_shape=(1, 16))
    assert report.is_compatible
