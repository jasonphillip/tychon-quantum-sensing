"""PyTorch → ONNX export with VectorBlox ops_guard pre-check.

Validates all model operations against the VectorBlox V250 whitelist
before exporting, preventing wasted time on an ONNX→TFLite→VNNX chain
that would fail at the vnnx_compile step.

Usage::

    from odmr_edge_ml.export import export_onnx

    export_onnx(model, Path("model.onnx"), input_shape=(1, 200))
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch
import torch.nn as nn

from odmr_edge_ml.validation.ops_guard import check_model_ops

log = logging.getLogger(__name__)


class OpsGuardError(RuntimeError):
    """Raised when a model contains VectorBlox-incompatible ops."""


def export_onnx(
    model: nn.Module,
    output_path: Path | str,
    input_shape: tuple[int, ...] = (1, 100),
    *,
    opset_version: int = 17,
    skip_ops_check: bool = False,
) -> Path:
    """Export a PyTorch model to ONNX with optional ops_guard pre-check.

    Parameters
    ----------
    model : nn.Module
        Model to export. Must be in eval mode or will be set to eval.
    output_path : Path or str
        Destination .onnx file path.
    input_shape : tuple[int, ...]
        Shape of dummy input tensor for tracing (default ``(1, 100)``).
    opset_version : int
        ONNX opset version (default 17).
    skip_ops_check : bool
        If True, skip the VectorBlox compatibility pre-check and mark the
        exported ONNX model as unverified.
        Default False — always validate before export.

    Returns
    -------
    Path
        The output path of the exported ONNX model. Its metadata contains
        ``ops_certified`` and ``ops_certification_reason``.

    Raises
    ------
    OpsGuardError
        If the model contains disallowed or unknown VectorBlox ops and
        ``skip_ops_check`` is False.
    """
    output_path = Path(output_path)
    model.eval()

    # Pre-flight: VectorBlox compatibility check
    if skip_ops_check:
        ops_certified = False
        certification_reason = "ops check skipped by skip_ops_check=True"
        log.warning("ONNX ops unverified: %s", certification_reason)
    else:
        report = check_model_ops(model, input_shape=input_shape)
        if not report.is_compatible:
            raise OpsGuardError(
                "Model contains VectorBlox-incompatible ops: "
                f"disallowed={report.disallowed}, unknown={report.unknown}. "
                "Fix the model architecture or pass skip_ops_check=True to bypass."
            )
        ops_certified = True
        certification_reason = "ops check passed: no disallowed or unknown ops"
        log.info(
            "ops_guard passed: %d allowed ops",
            len(report.allowed),
        )

    # Export
    dummy = torch.randn(*input_shape)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        (dummy,),
        str(output_path),
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        opset_version=opset_version,
    )

    # Validate the exported ONNX model
    import onnx

    onnx_model = onnx.load(str(output_path))
    for key, value in (
        ("ops_certified", str(ops_certified).lower()),
        ("ops_certification_reason", certification_reason),
    ):
        metadata = onnx_model.metadata_props.add()
        metadata.key = key
        metadata.value = value
    onnx.checker.check_model(onnx_model)
    onnx.save(onnx_model, str(output_path))

    size_kb = output_path.stat().st_size / 1024
    log.info("ONNX exported: %s (%.1f KB)", output_path, size_kb)

    return output_path
