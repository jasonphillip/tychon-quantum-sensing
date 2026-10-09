"""Shape and compliance tests for OdmrFCNN (fully convolutional architecture)."""

import torch
import torch.nn as nn

from tychon_odmr_ml.models.fcnn import OdmrFCNN
from tychon_odmr_ml.validation.ops_guard import check_model_ops


def test_fcnn_output_shape():
    model = OdmrFCNN()
    x = torch.randn(8, 100)
    out = model(x)
    assert out.shape == (8, 3)


def test_fcnn_single_sample():
    model = OdmrFCNN()
    x = torch.randn(1, 100)
    out = model(x)
    assert out.shape == (1, 3)


def test_fcnn_custom_channels():
    model = OdmrFCNN(channels=[4, 8])
    x = torch.randn(4, 100)
    out = model(x)
    assert out.shape == (4, 3)


def test_fcnn_no_nan_on_normalized_input():
    model = OdmrFCNN()
    x = torch.rand(8, 100)  # [0, 1] range
    out = model(x)
    assert torch.isfinite(out).all()


def test_fcnn_no_linear_layers():
    """Fully convolutional: no nn.Linear anywhere."""
    model = OdmrFCNN()
    for name, module in model.named_modules():
        assert not isinstance(module, nn.Linear), f"Found Linear at {name}"


def test_fcnn_uses_2d_conv_not_1d():
    """All conv layers are Conv2d, not Conv1d."""
    model = OdmrFCNN()
    for name, module in model.named_modules():
        assert not isinstance(module, nn.Conv1d), f"Found Conv1d at {name}"


def test_fcnn_parameter_count():
    """Default FCNN should have exactly 3,299 parameters."""
    model = OdmrFCNN()
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params == 3299


def test_fcnn_intermediate_shapes():
    """Verify the exact spatial dimension flow through conv layers."""
    model = OdmrFCNN()
    x = torch.randn(1, 100)
    x = x.unsqueeze(1).unsqueeze(2)  # (1, 1, 1, 100)

    x = model.relus[0](model.convs[0](x))
    assert x.shape == (1, 8, 1, 48)

    x = model.relus[1](model.convs[1](x))
    assert x.shape == (1, 16, 1, 22)

    x = model.relus[2](model.convs[2](x))
    assert x.shape == (1, 24, 1, 9)

    x = model.conv_head(x)
    assert x.shape == (1, 3, 1, 1)


def test_fcnn_passes_ops_guard():
    """Must pass VectorBlox V250 ops whitelist check."""
    model = OdmrFCNN()
    report = check_model_ops(model, input_shape=(1, 100))
    assert report.is_compatible, f"Disallowed ops: {report.disallowed}"
