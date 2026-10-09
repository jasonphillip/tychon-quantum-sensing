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


def test_matmul_flagged_softmax_allowed() -> None:
    """Measured rebaseline 2026-07-02: softmax is supported; attention matmul stays banned."""

    class Attn(nn.Module):
        def forward(self, x: torch.Tensor) -> torch.Tensor:
            s = torch.softmax(x @ x.transpose(-1, -2), dim=-1)
            return s @ x

    report = check_model_ops(Attn(), input_shape=(1, 8, 16))
    assert not report.is_compatible
    assert "aten.softmax" in report.allowed
    assert "aten.matmul" in report.disallowed


def test_sigmoid_tanh_single_input_now_compatible() -> None:
    """Measured 2026-07-02: gate activations compile + simulate in single-input graphs."""
    gates = nn.Sequential(nn.Linear(16, 16), nn.Sigmoid(), nn.Linear(16, 16), nn.Tanh())
    report = check_model_ops(gates, input_shape=(1, 16))
    assert report.is_compatible
    assert "aten.sigmoid" in report.allowed
    assert "aten.tanh" in report.allowed


def test_multi_graph_input_is_flagged() -> None:
    """Measured 2026-07-02: >1 graph input breaks the SDK 2.0.x flow (sim corruption /
    compiler crash) — the topology gate, not the op list, keeps recurrence off the NPU."""

    class TwoInput(nn.Module):
        def forward(self, x: torch.Tensor, h: torch.Tensor) -> torch.Tensor:
            return x + h

    report = check_model_ops(
        TwoInput(), example_inputs=(torch.randn(1, 16), torch.randn(1, 16))
    )
    assert not report.is_compatible
    assert any("multi_graph_input" in d for d in report.disallowed)


def test_assert_raises_on_incompatible() -> None:
    class Bad(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.c = nn.Conv1d(1, 4, 5)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.c(x)

    try:
        assert_v250_compatible(Bad(), input_shape=(1, 1, 16))
    except OpsGuardError:
        return
    raise AssertionError("expected OpsGuardError for a Conv1d model")


def test_assert_returns_report_on_compatible() -> None:
    good = nn.Sequential(nn.Linear(16, 8), nn.ReLU())
    report = assert_v250_compatible(good, input_shape=(1, 16))
    assert report.is_compatible
