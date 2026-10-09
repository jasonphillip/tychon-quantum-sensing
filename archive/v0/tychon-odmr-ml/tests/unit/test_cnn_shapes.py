"""Shape tests for OdmrCNN1D (Architecture B)."""

import torch
import torch.nn as nn

from tychon_odmr_ml.models.cnn1d import OdmrCNN1D


def test_cnn_output_shape():
    model = OdmrCNN1D()
    x = torch.randn(8, 100)
    out = model(x)
    assert out.shape == (8, 3)


def test_cnn_single_sample():
    model = OdmrCNN1D()
    x = torch.randn(1, 100)
    out = model(x)
    assert out.shape == (1, 3)


def test_cnn_custom_channels():
    model = OdmrCNN1D(channels=[8, 16])
    x = torch.randn(4, 100)
    out = model(x)
    assert out.shape == (4, 3)


def test_cnn_no_nan_on_normalized_input():
    model = OdmrCNN1D()
    x = torch.rand(8, 100)  # [0, 1] range
    out = model(x)
    assert torch.isfinite(out).all()


def test_cnn_uses_2d_conv_not_1d():
    """All conv layers are Conv2d, not Conv1d."""
    model = OdmrCNN1D()
    for name, module in model.named_modules():
        assert not isinstance(module, nn.Conv1d), f"Found Conv1d at {name}"


def test_cnn_parameter_count_under_target():
    """Default CNN should have < 10,000 params (target <1,000 post-pruning)."""
    model = OdmrCNN1D()
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params < 10_000
