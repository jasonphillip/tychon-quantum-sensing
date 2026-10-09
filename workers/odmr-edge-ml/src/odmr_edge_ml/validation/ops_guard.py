"""VectorBlox SDK 3.0 ops whitelist checker.

Exports a PyTorch model via torch.export and verifies all operations
are in the VectorBlox-supported op set. Run this BEFORE training at scale.

Uses torch.export.export() — the same entry point as TorchAO QAT pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn


# Ops that map to VectorBlox TFLite operators.
# Keys are the base aten op name (without variant suffix).
# torch.export emits targets like aten.linear.default, aten.conv2d.default, etc.
VECTORBLOX_ALLOWED_OPS: set[str] = {
    # Compute ops
    "aten.linear",
    "aten.conv2d",
    "aten.relu",
    "aten.relu6",
    "aten.hardtanh",        # relu6 lowers to hardtanh(0, 6)
    "aten.add",
    "aten.mean",
    "aten.adaptive_avg_pool2d",
    # Layout ops (no compute, free in TFLite)
    "aten.reshape",
    "aten.view",
    "aten.flatten",
    "aten.permute",
    "aten.contiguous",
    "aten.t",
    "aten.unsqueeze",
    "aten.squeeze",
}

# Ops explicitly banned by VectorBlox constraints
VECTORBLOX_BANNED_OPS: set[str] = {
    "aten.conv1d",
    "aten.batch_norm",
    "aten.layer_norm",
    "aten.instance_norm",
    "aten.group_norm",
    "aten.sigmoid",
    "aten.tanh",
    "aten.gelu",
    "aten.silu",
    "aten.softmax",
    "aten.log_softmax",
    "aten.max_pool1d",
    "aten.max_pool2d",
    "aten.dropout",
    "aten.mul",
    "aten.matmul",
}

# Module types banned at the PyTorch module level.
# Conv1d and Conv2d both lower to aten.conv2d in some export paths,
# so we check module types directly as a safety net.
VECTORBLOX_BANNED_MODULES: set[type] = {
    nn.Conv1d,
    nn.BatchNorm1d,
    nn.BatchNorm2d,
    nn.LayerNorm,
    nn.InstanceNorm1d,
    nn.InstanceNorm2d,
    nn.GroupNorm,
    nn.Dropout,
    nn.GELU,
    nn.SiLU,
    nn.Sigmoid,
    nn.Tanh,
    nn.Softmax,
    nn.MaxPool1d,
    nn.MaxPool2d,
}


@dataclass
class OpsReport:
    """Result of checking a model's ops against VectorBlox whitelist."""

    allowed: list[str] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        """True only if every operation is known and allowed."""
        return not self.disallowed and not self.unknown


def _base_op_name(target: object) -> str:
    """Extract 'aten.op_name' from a torch.export target.

    Targets look like: aten.linear.default, aten.conv2d.default, etc.
    We strip the variant suffix to match against our whitelist.
    """
    s = str(target)
    parts = s.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return s


def check_model_ops(
    model: nn.Module,
    input_shape: tuple[int, ...] = (1, 100),
) -> OpsReport:
    """Export a model and check its ops against the VectorBlox whitelist.

    Parameters
    ----------
    model : nn.Module
        PyTorch model to check.
    input_shape : tuple[int, ...]
        Shape of dummy input tensor for export tracing.

    Returns
    -------
    OpsReport
        Report with allowed, disallowed, and unknown ops.
    """
    model.eval()
    report = OpsReport()

    # Phase 1: Module-level check (catches Conv1d vs Conv2d ambiguity)
    for name, module in model.named_modules():
        if type(module) in VECTORBLOX_BANNED_MODULES:
            report.disallowed.append(f"{type(module).__name__} at {name}")

    # Phase 2: torch.export graph op-level check
    dummy = torch.randn(*input_shape)
    exported = torch.export.export(model, (dummy,))

    op_names: set[str] = set()
    for node in exported.graph.nodes:
        if node.op == "call_function":
            op_names.add(_base_op_name(node.target))

    for op in sorted(op_names):
        if op in VECTORBLOX_ALLOWED_OPS:
            report.allowed.append(op)
        elif op in VECTORBLOX_BANNED_OPS:
            report.disallowed.append(op)
        else:
            report.unknown.append(op)

    return report
