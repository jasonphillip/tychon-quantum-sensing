"""Tests for VectorBlox ops guard."""

import torch.nn as nn

from odmr_edge_ml.models.cnn1d import OdmrCNN1D
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.validation.ops_guard import check_model_ops


def test_mlp_passes_ops_guard():
    """Default MLP uses only VectorBlox-allowed ops."""
    model = OdmrMLP()
    report = check_model_ops(model)
    assert report.is_compatible, f"Disallowed ops: {report.disallowed}"


def test_cnn_passes_ops_guard():
    """Default CNN uses only VectorBlox-allowed ops."""
    model = OdmrCNN1D()
    report = check_model_ops(model)
    assert report.is_compatible, f"Disallowed ops: {report.disallowed}"


def test_model_with_batchnorm_fails():
    """A model containing BatchNorm is flagged as incompatible."""
    model = nn.Sequential(
        nn.Linear(100, 64),
        nn.BatchNorm1d(64),
        nn.ReLU(),
        nn.Linear(64, 3),
    )
    report = check_model_ops(model)
    assert not report.is_compatible
    assert any("batch_norm" in op for op in report.disallowed)


def test_model_with_conv1d_fails():
    """A model using Conv1d is flagged."""
    model = nn.Sequential(
        nn.Unflatten(1, (1, 100)),
        nn.Conv1d(1, 8, kernel_size=5, padding=2),
        nn.ReLU(),
        nn.Flatten(),
        nn.Linear(800, 3),
    )
    report = check_model_ops(model)
    assert not report.is_compatible
    assert any("Conv1d" in op for op in report.disallowed)


def test_ops_report_structure():
    """OpsReport correctly partitions ops."""
    model = OdmrMLP()
    report = check_model_ops(model)
    assert isinstance(report.allowed, list)
    assert isinstance(report.disallowed, list)
    assert isinstance(report.unknown, list)
    assert len(report.allowed) > 0  # MLP must use some allowed ops
