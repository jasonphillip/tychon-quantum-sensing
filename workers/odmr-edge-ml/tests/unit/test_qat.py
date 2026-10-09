"""Tests for QAT (Quantization-Aware Training) utilities."""

import warnings

import torch

from odmr_edge_ml.models.fcnn import OdmrFCNN
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.training.qat import (
    extract_clean_state_dict,
    load_clean_weights,
    make_int8_symmetric_qconfig,
    prepare_model_qat,
)

# FX QAT is deprecated in torch 2.11 but functional; suppress noise
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")


def test_qconfig_weights_are_per_tensor_symmetric():
    """Locked invariant: weights MUST be per-tensor symmetric.

    PolarFire VectorBlox SDK 2.0.x rejects per-channel weights, and
    tychon_shared_data.cascade.CascadeManifest.validate() hard-rejects
    quantization_granularity != "per_tensor". If this test fails, the
    cascade manifest emission in src/odmr_edge_ml/cascade/manifest_emit.py
    will refuse to write a valid manifest.
    """
    qconfig = make_int8_symmetric_qconfig()
    # Both observers go through FakeQuantize.with_args; introspect the kwargs
    # captured on the partial (FakeQuantize doesn't expose qscheme directly
    # until instantiated, so we instantiate and check).
    weight_fq = qconfig.weight()
    assert weight_fq.qscheme == torch.per_tensor_symmetric, (
        f"Weights must be per_tensor_symmetric for VectorBlox V250 + "
        f"CascadeManifest compatibility; got {weight_fq.qscheme}"
    )
    activation_fq = qconfig.activation()
    assert activation_fq.qscheme == torch.per_tensor_symmetric


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


def test_extract_clean_state_dict_strips_compile_prefix():
    """torch.compile-wrapped QAT models still yield clean (unprefixed) keys.

    Regression for KeyError('sigma') seen during Phase B scalar-residual v2
    export: torch.compile(qat_model) wraps the module and prepends
    '_orig_mod.' to every state_dict key. extract_clean_state_dict must
    strip that prefix so the export model's load_state_dict(strict=True)
    finds 'sigma', 'convs.0.weight', etc.
    """
    model = OdmrFCNN()
    original_keys = set(model.state_dict().keys())
    qat = prepare_model_qat(model)
    compiled: torch.nn.Module = torch.compile(qat)  # type: ignore[assignment]
    raw_keys = set(compiled.state_dict().keys())
    assert any(k.startswith("_orig_mod.") for k in raw_keys), (
        "Test precondition failed: torch.compile did not add expected prefix"
    )

    clean = extract_clean_state_dict(compiled)  # type: ignore[arg-type]
    assert set(clean.keys()) == original_keys
    assert not any(k.startswith("_orig_mod.") for k in clean.keys())


def test_extract_clean_state_dict_idempotent_on_unprefixed():
    """Uncompiled checkpoints pass through unchanged (backward compatibility)."""
    model = OdmrFCNN()
    original_keys = set(model.state_dict().keys())
    qat = prepare_model_qat(model)
    first = extract_clean_state_dict(qat)
    second = extract_clean_state_dict(qat)
    assert set(first.keys()) == original_keys
    assert set(second.keys()) == set(first.keys())


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
