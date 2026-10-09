"""Shape tests for OdmrMLP (Architecture A)."""

import torch

from odmr_edge_ml.models.mlp import OdmrMLP


def test_mlp_output_shape():
    model = OdmrMLP()
    x = torch.randn(8, 100)
    out = model(x)
    assert out.shape == (8, 3)


def test_mlp_single_sample():
    model = OdmrMLP()
    x = torch.randn(1, 100)
    out = model(x)
    assert out.shape == (1, 3)


def test_mlp_custom_hidden_dims():
    model = OdmrMLP(hidden_dims=[128, 64])
    x = torch.randn(4, 100)
    out = model(x)
    assert out.shape == (4, 3)


def test_mlp_no_nan_on_normalized_input():
    model = OdmrMLP()
    x = torch.rand(8, 100)  # [0, 1] range
    out = model(x)
    assert torch.isfinite(out).all()


def test_mlp_parameter_count():
    model = OdmrMLP()  # 100→256→128→64→3
    n_params = sum(p.numel() for p in model.parameters())
    # 100*256+256 + 256*128+128 + 128*64+64 + 64*3+3 = 59,587
    assert 50_000 < n_params < 70_000


def test_mlp_relu6_activation():
    model = OdmrMLP(activation="relu6")
    x = torch.randn(4, 100)
    out = model(x)
    assert out.shape == (4, 3)
