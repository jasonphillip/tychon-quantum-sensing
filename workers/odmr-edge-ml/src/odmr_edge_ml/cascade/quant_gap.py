"""Measure the float-twin vs deployed-quantized cascade gap.

Wraps ``tychon_shared_data.cascade.compose_quantized_then_dequant`` (the
deployed numerical path — what the FPGA actually computes) and
``compose_float_reference`` (a hypothetical float-precision twin — the
capability ceiling). The difference quantifies how much accuracy the
INT8 quantization is costing the cascade, which the project decision
log tracks.

The float runners are caller-supplied — there is no canonical way to
derive a float twin from a TFLite. Typically you pass closures over the
pre-quantization PyTorch ``OdmrFCNNv2`` instances (or the equivalent
``OdmrFCNN(in_channels=2)`` export-shape model) and the Gaussian-anchor
host preprocessing.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from tychon_shared_data.cascade import (
    CascadeManifest,
    compose_float_reference,
    compose_quantized_then_dequant,
)

RunnerFloat = Callable[[np.ndarray], np.ndarray]


def measure_quantization_gap(
    x: np.ndarray,
    manifest: CascadeManifest,
    *,
    coarse_float_runner: RunnerFloat,
    fine_float_runner: RunnerFloat,
) -> dict[str, np.ndarray]:
    """Return per-sample float, deployed, and gap arrays.

    Parameters
    ----------
    x
        ``(N, ...)`` input batch in the manifest's ``input_dim`` shape.
    manifest
        Already-loaded ``CascadeManifest`` (its
        ``compose_quantized_then_dequant`` call uses the manifest's TFLite
        paths for the deployed runners).
    coarse_float_runner, fine_float_runner
        Float twins for the compose_float_reference call.

    Returns
    -------
    dict
        ``{"deployed": (N,...), "float": (N,...), "gap": float - deployed}``.
    """
    deployed = compose_quantized_then_dequant(x, manifest)
    float_ref = compose_float_reference(
        x, manifest,
        coarse_runner=coarse_float_runner, fine_runner=fine_float_runner,
    )
    return {
        "deployed": deployed,
        "float": float_ref,
        "gap": float_ref - deployed,
    }
