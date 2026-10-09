"""Shape and compliance tests for OdmrFCNNv2 (learnable-anchor variant)."""

import torch
import torch.nn as nn

from odmr_edge_ml.models.fcnn import OdmrFCNN
from odmr_edge_ml.models.fcnn_v2 import OdmrFCNNv2
from odmr_edge_ml.validation.ops_guard import check_model_ops


def test_fcnn_v2_output_shape():
    model = OdmrFCNNv2()
    x = torch.randn(8, 101)
    out = model(x)
    assert out.shape == (8, 1)


def test_fcnn_v2_single_sample():
    model = OdmrFCNNv2()
    x = torch.randn(1, 101)
    out = model(x)
    assert out.shape == (1, 1)


def test_fcnn_v2_custom_channels():
    model = OdmrFCNNv2(channels=[4, 8])
    x = torch.randn(4, 101)
    out = model(x)
    assert out.shape == (4, 1)


def test_fcnn_v2_no_nan_on_normalized_input():
    model = OdmrFCNNv2()
    x = torch.rand(8, 101)
    out = model(x)
    assert torch.isfinite(out).all()


def test_fcnn_v2_no_linear_layers():
    """Fully convolutional: no nn.Linear anywhere."""
    model = OdmrFCNNv2()
    for name, module in model.named_modules():
        assert not isinstance(module, nn.Linear), f"Found Linear at {name}"


def test_fcnn_v2_uses_2d_conv_not_1d():
    """All conv layers are Conv2d, not Conv1d."""
    model = OdmrFCNNv2()
    for name, module in model.named_modules():
        assert not isinstance(module, nn.Conv1d), f"Found Conv1d at {name}"


def test_fcnn_v2_parameter_count():
    """Default OdmrFCNNv2 should have exactly 2,906 parameters.

    Same conv stack as OdmrFCNN(in_channels=2, output_dim=1), plus the
    learnable sigma scalar. Locking this guards the cascade — both COARSE
    and FINE depend on this count for INT8 budget reasoning.
    """
    model = OdmrFCNNv2()
    n_params = sum(p.numel() for p in model.parameters())
    assert n_params == 2906


def test_fcnn_v2_sigma_is_learnable():
    """The anchor sigma must be a trainable Parameter, not a buffer."""
    model = OdmrFCNNv2()
    assert isinstance(model.sigma, nn.Parameter)
    assert model.sigma.requires_grad


def test_fcnn_v2_bins_buffer_matches_input_dim():
    """bins buffer length must equal input_dim so the anchor covers the spectrum."""
    model = OdmrFCNNv2(input_dim=100)
    assert model.bins.shape == (100,)
    model_smaller = OdmrFCNNv2(input_dim=50, channels=[4])
    assert model_smaller.bins.shape == (50,)


def test_fcnn_v2_export_path_passes_ops_guard():
    """The deployed graph must pass V250 ops whitelist.

    OdmrFCNNv2 itself does NOT pass ops_guard — the inline Gaussian anchor
    uses mul/exp/sub/pow/div, none of which are on the V250 whitelist. This
    is intentional: at deployment the anchor moves to host-side (or to the
    Keras static-batch wrapper at convert_fcnn_to_tflite_int8) and the FPGA
    only sees the conv-only subgraph. The "equivalent export model" is
    OdmrFCNN(in_channels=2) consuming the pre-baked (spectrum || anchor)
    input — that's what we ops-guard, mirroring the production training
    script (experiments/scalar_residual_v2.py:435).
    """
    export_check = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    report = check_model_ops(export_check, input_shape=(1, 200))
    assert report.is_compatible, f"Disallowed ops: {report.disallowed}"


def test_fcnn_v2_anchor_is_preprocessing_not_exported():
    """Sanity check that OdmrFCNNv2 actually contains the host-side ops we
    expect to strip at export time. If this changes (e.g. someone replaces
    the Gaussian with a conv-friendly approximation), the export path's
    weight-transfer step in convert_fcnn_to_tflite_int8 needs revisiting.
    """
    model = OdmrFCNNv2()
    report = check_model_ops(model, input_shape=(1, 101))
    assert "aten.mul" in report.disallowed or "aten.exp" in report.unknown, (
        "Expected the Gaussian-anchor ops to be flagged; if not, the export "
        "path assumption (anchor = host-side preprocessing) is broken."
    )
