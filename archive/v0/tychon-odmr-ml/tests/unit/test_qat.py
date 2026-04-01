"""Tests for QAT (Quantization-Aware Training) utilities."""

import warnings

import torch

from tychon_odmr_ml.models.fcnn import OdmrFCNN
from tychon_odmr_ml.models.mlp import OdmrMLP
from tychon_odmr_ml.training.qat import (
    extract_clean_state_dict,
    load_clean_weights,
    prepare_model_qat,
)

# FX QAT is deprecated in torch 2.11 but functional; suppress noise
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")


def test_prepare_mlp_qat():
    """QAT preparation inserts FakeQuantize into MLP and forward still works."""
    model = OdmrMLP(hidden_dims=[64, 32])
    qat = prepare_model_qat(model)
    out = qat(torch.randn(4, 100))
    assert out.shape == (4, 3)


def test_prepare_fcnn_qat():
    """QAT preparation inserts FakeQuantize into FCNN and forward still works."""
    model = OdmrFCNN()
    qat = prepare_model_qat(model)
    out = qat(torch.randn(4, 100))
    assert out.shape == (4, 3)


def test_extract_clean_state_dict_mlp():
    """Extracted clean keys match the original MLP state dict keys."""
    model = OdmrMLP(hidden_dims=[64, 32])
    original_keys = set(model.state_dict().keys())
    qat = prepare_model_qat(model)
    clean = extract_clean_state_dict(qat)
    assert set(clean.keys()) == original_keys


def test_extract_clean_state_dict_fcnn():
    """Extracted clean keys match the original FCNN state dict keys."""
    model = OdmrFCNN()
    original_keys = set(model.state_dict().keys())
    qat = prepare_model_qat(model)
    clean = extract_clean_state_dict(qat)
    assert set(clean.keys()) == original_keys


def test_load_clean_weights_roundtrip():
    """Weights survive QAT prepare -> extract -> load into clean model."""
    model = OdmrMLP(hidden_dims=[64, 32])
    original_sd = {k: v.clone() for k, v in model.state_dict().items()}

    qat = prepare_model_qat(model)
    clean = OdmrMLP(hidden_dims=[64, 32])
    load_clean_weights(clean, qat)

    for key in original_sd:
        assert torch.equal(original_sd[key], clean.state_dict()[key]), f"Mismatch: {key}"


def test_qat_model_trains_mlp():
    """Gradients flow through FakeQuantize — loss decreases over a few steps."""
    model = OdmrMLP(hidden_dims=[64, 32])
    qat = prepare_model_qat(model)
    qat.train()

    optimizer = torch.optim.Adam(qat.parameters(), lr=1e-3)
    x = torch.randn(16, 100)
    y = torch.randn(16, 3)

    losses = []
    for _ in range(10):
        optimizer.zero_grad()
        loss = torch.nn.functional.mse_loss(qat(x), y)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())

    assert losses[-1] < losses[0], "Loss did not decrease through FakeQuantize"


def test_qat_model_trains_fcnn():
    """Gradients flow through FakeQuantize on FCNN — loss decreases."""
    model = OdmrFCNN()
    qat = prepare_model_qat(model)
    qat.train()

    optimizer = torch.optim.Adam(qat.parameters(), lr=1e-3)
    x = torch.randn(16, 100)
    y = torch.randn(16, 3)

    losses = []
    for _ in range(10):
        optimizer.zero_grad()
        loss = torch.nn.functional.mse_loss(qat(x), y)
        loss.backward()
        optimizer.step()
        losses.append(loss.item())

    assert losses[-1] < losses[0], "Loss did not decrease through FakeQuantize"
