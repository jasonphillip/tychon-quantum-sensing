"""Tests for VectorBlox ops guard."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch.nn as nn

from odmr_edge_ml.models.cnn1d import OdmrCNN1D
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.validation.ops_guard import OpsReport, check_model_ops


onnx_export = importlib.import_module("odmr_edge_ml.export.onnx_export")


def test_ops_report_certification_requires_known_allowed_ops():
    assert not OpsReport(unknown=["aten.new_op"]).is_compatible
    assert not OpsReport(disallowed=["aten.mul"]).is_compatible
    assert OpsReport(allowed=["aten.linear"]).is_compatible


def test_onnx_export_refuses_unknown_ops_without_override(tmp_path, monkeypatch):
    monkeypatch.setattr(
        onnx_export,
        "check_model_ops",
        lambda *args, **kwargs: OpsReport(unknown=["aten.new_op"]),
    )
    monkeypatch.setattr(
        onnx_export.torch.onnx,
        "export",
        lambda *args, **kwargs: pytest.fail("ONNX export must not run"),
    )

    with pytest.raises(onnx_export.OpsGuardError, match="unknown=.*aten.new_op"):
        onnx_export.export_onnx(nn.Identity(), tmp_path / "model.onnx")


def test_onnx_export_override_records_unverified(tmp_path, monkeypatch, caplog):
    class MetadataProps(list):
        def add(self):
            entry = SimpleNamespace(key="", value="")
            self.append(entry)
            return entry

    model_proto = SimpleNamespace(metadata_props=MetadataProps())
    saved = []
    fake_onnx = SimpleNamespace(
        load=lambda path: model_proto,
        save=lambda model, path: saved.append((model, path)),
        checker=SimpleNamespace(check_model=lambda model: None),
    )
    monkeypatch.setitem(sys.modules, "onnx", fake_onnx)
    monkeypatch.setattr(
        onnx_export,
        "check_model_ops",
        lambda *args, **kwargs: pytest.fail("ops check must be skipped"),
    )
    monkeypatch.setattr(
        onnx_export.torch.onnx,
        "export",
        lambda model, inputs, path, **kwargs: Path(path).write_bytes(b"ONNX"),
    )

    output_path = tmp_path / "model.onnx"
    result = onnx_export.export_onnx(
        nn.Identity(), output_path, skip_ops_check=True,
    )

    metadata = {entry.key: entry.value for entry in model_proto.metadata_props}
    assert result == output_path
    assert saved == [(model_proto, str(output_path))]
    assert metadata["ops_certified"] == "false"
    assert "skip_ops_check=True" in metadata["ops_certification_reason"]
    assert "unverified" in caplog.text


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
