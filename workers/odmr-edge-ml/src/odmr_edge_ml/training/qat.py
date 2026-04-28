"""Quantization-Aware Training utilities for VectorBlox V250 INT8 deployment.

Uses FX-graph mode QAT (torch.ao.quantization.quantize_fx) which automatically
fuses Conv2d+ReLU and Linear+ReLU pairs and inserts FakeQuantize nodes.

Symmetric INT8 quantization matches VectorBlox TFLite runtime requirements:
- Activations: per_tensor_symmetric (zero_point = 0)
- Weights: per_channel_symmetric (separate scale per output channel)
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor
from torch.ao.quantization import (
    FakeQuantize,
    MovingAverageMinMaxObserver,
    MovingAveragePerChannelMinMaxObserver,
    QConfig,
    QConfigMapping,
)
from torch.ao.quantization.quantize_fx import prepare_qat_fx
from torch.fx import GraphModule


def make_int8_symmetric_qconfig() -> QConfig:
    """Create symmetric INT8 QConfig for VectorBlox V250.

    Returns
    -------
    QConfig
        Activations: per_tensor_symmetric INT8 [-128, 127].
        Weights: per_channel_symmetric INT8 [-128, 127].
    """
    act_fq = FakeQuantize.with_args(
        observer=MovingAverageMinMaxObserver,
        quant_min=-128,
        quant_max=127,
        dtype=torch.qint8,
        qscheme=torch.per_tensor_symmetric,
    )
    wt_fq = FakeQuantize.with_args(
        observer=MovingAveragePerChannelMinMaxObserver,
        quant_min=-128,
        quant_max=127,
        dtype=torch.qint8,
        qscheme=torch.per_channel_symmetric,
        ch_axis=0,
    )
    return QConfig(activation=act_fq, weight=wt_fq)


def prepare_model_qat(
    model: nn.Module,
    example_input: Tensor | None = None,
) -> GraphModule:
    """Prepare a model for QAT by inserting FakeQuantize via FX graph mode.

    Automatically fuses Conv2d+ReLU and Linear+ReLU pairs.

    Parameters
    ----------
    model : nn.Module
        Model to prepare. Must be in train mode.
    example_input : Tensor or None
        Example input for tracing. Default: (1, 100) random tensor.

    Returns
    -------
    GraphModule
        Model with FakeQuantize nodes inserted, ready for QAT training.
    """
    if example_input is None:
        example_input = torch.randn(1, 100)

    qconfig = make_int8_symmetric_qconfig()
    qconfig_mapping = QConfigMapping().set_global(qconfig)

    model.train()
    prepared = prepare_qat_fx(model, qconfig_mapping, example_inputs=(example_input,))
    return prepared


_COMPILE_PREFIX = "_orig_mod."


def extract_clean_state_dict(
    qat_model: GraphModule,
) -> dict[str, Tensor]:
    """Extract weight/bias tensors from a QAT model, stripping FakeQuantize keys.

    Also strips the ``_orig_mod.`` prefix that ``torch.compile`` prepends to
    every state_dict key when the module has been wrapped by Dynamo. Keys
    without the prefix (uncompiled checkpoints) pass through untouched, so
    this is idempotent and backward-compatible with pre-compile checkpoints.

    Parameters
    ----------
    qat_model : GraphModule
        QAT-prepared model after training, optionally torch.compile-wrapped.

    Returns
    -------
    dict[str, Tensor]
        State dict with only weight/bias parameters (no FakeQuantize or
        observer state, and no ``_orig_mod.`` prefix).
    """
    skip_patterns = ("fake_quant", "activation_post_process", "observer")
    cleaned: dict[str, Tensor] = {}
    for k, v in qat_model.state_dict().items():
        if any(pat in k for pat in skip_patterns):
            continue
        if k.startswith(_COMPILE_PREFIX):
            k = k[len(_COMPILE_PREFIX):]
        cleaned[k] = v
    return cleaned


def load_clean_weights(
    clean_model: nn.Module,
    qat_model: GraphModule,
) -> nn.Module:
    """Load QAT-trained weights into a clean (non-QAT) model for export.

    Parameters
    ----------
    clean_model : nn.Module
        Fresh model instance matching the QAT model's architecture.
    qat_model : GraphModule
        QAT model after training.

    Returns
    -------
    nn.Module
        Clean model with QAT-trained weights loaded.
    """
    clean_sd = extract_clean_state_dict(qat_model)
    clean_model.load_state_dict(clean_sd, strict=True)
    return clean_model
