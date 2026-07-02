"""VectorBlox V250 ops whitelist checker (PyTorch-graph stage).

Exports a PyTorch model via ``torch.export`` and verifies every operation is in the
VectorBlox-supported op set. **Run this BEFORE training at scale** so the eventual model
stays deployable to the V250 NPU via ``polarfire-hybrid-control``.

Mirrors ``odmr_edge_ml.validation.ops_guard`` (the canonical whitelist referenced by the
project CLAUDE.md). The complementary post-conversion flatbuffer stage lives in
``tflite_ops.py``.

MEASURED REBASELINE (2026-07-02, vnnx_compile -c V250 + VNNX simulator on the SDK host;
evidence: polarfire-hybrid-control ``docs/vnnx_ops_support_probe_2026-07-02.md`` +
``libero/reports/2026-07-02-vnnx-ops-probe/``):

- ``aten.sigmoid`` / ``aten.tanh`` / ``aten.softmax`` are **ALLOWED** — they compile and
  simulate correctly in single-graph-input feedforward graphs (LOGISTIC/TANH LUT-grade,
  <=11 int8 LSB vs TFLite; an 8x60 SOFTMAX head matched float to 0.029 max abs err).
  The old ban on these ops was launch-collateral folklore, falsified by measurement.
- The **real, measured constraint is topology: exactly ONE graph input.** Two-graph-input
  models compile but the VNNX simulator returns garbage on distinct inputs (input order and
  operand broadcast ruled out), and the one-step GRU-style cell (state as a second graph
  input) additionally CRASHES vnnx_compile in both rank-2 and rank-4 forms. This — not the
  gate activations — is why recurrence stays on the MSS host: state-as-graph-input cells
  cannot target the V250 on SDK 2.0.x.
- ``aten.mul`` stays banned with measured provenance: the two-input MUL probe compiled but
  sim-corrupted, and internal-mul compositions crashed the compiler. ``aten.matmul`` stays
  banned as UNTESTED (attention-style MATMUL is not FULLY_CONNECTED; no measurement yet).

Execution partition consequence: single-input feedforward blocks (feature extractors AND
softmax association heads) may target the V250; recurrence and anything needing a second
graph input runs on the MSS RISC-V host, which has no op whitelist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import torch
import torch.nn as nn

# Ops that map to VectorBlox TFLite operators. Keys are the base aten op name (no variant
# suffix); torch.export emits targets like ``aten.linear.default``.
VECTORBLOX_ALLOWED_OPS: set[str] = {
    # Compute ops
    "aten.linear",
    "aten.conv2d",
    "aten.relu",
    "aten.relu6",
    "aten.hardtanh",  # relu6 lowers to hardtanh(0, 6)
    "aten.add",
    "aten.mean",
    "aten.adaptive_avg_pool2d",
    # Gate/head activations — MEASURED SUPPORTED 2026-07-02 (vnnx_compile + VNNX sim,
    # single-graph-input graphs; see module docstring). SOFTMAX per OPS.md needs dim in
    # {-3,-2,-1}; sigmoid/tanh are int8 LUTs (<=11 LSB vs TFLite) — budget for that in eval.
    "aten.sigmoid",
    "aten.tanh",
    "aten.softmax",
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

# Ops explicitly banned by VectorBlox constraints.
VECTORBLOX_BANNED_OPS: set[str] = {
    "aten.conv1d",
    "aten.batch_norm",
    "aten.layer_norm",
    "aten.instance_norm",
    "aten.group_norm",
    "aten.gelu",
    "aten.silu",
    "aten.log_softmax",  # untested (only plain softmax measured)
    "aten.max_pool1d",
    "aten.max_pool2d",
    "aten.dropout",
    # MEASURED 2026-07-02: two-input MUL compiles but the VNNX sim corrupts it; internal-mul
    # compositions (GRU cell) crash vnnx_compile. Keep banned until the SDK flow is fixed.
    "aten.mul",
    # UNTESTED: attention-style MATMUL is not FULLY_CONNECTED; no measurement yet.
    "aten.matmul",
}

# MEASURED 2026-07-02: multi-graph-input models are broken in the SDK 2.0.x flow (sim
# corruption when they compile; compiler crash for state-as-graph-input cells). The V250
# target therefore accepts exactly one graph input.
MAX_GRAPH_INPUTS: int = 1

# Module types banned at the PyTorch module level. Conv1d/Conv2d can both lower to
# aten.conv2d in some export paths, so we check module types directly as a safety net.
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
    # nn.Sigmoid / nn.Tanh / nn.Softmax removed 2026-07-02 — measured supported (see docstring).
    nn.MaxPool1d,
    nn.MaxPool2d,
}


class OpsGuardError(RuntimeError):
    """Raised when a model contains ops/modules banned on the V250."""


@dataclass
class OpsReport:
    """Result of checking a model's ops against the VectorBlox whitelist."""

    allowed: list[str] = field(default_factory=list)
    disallowed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def is_compatible(self) -> bool:
        """True only if no disallowed ops were found."""
        return len(self.disallowed) == 0

    def summary(self) -> str:
        """Human-readable one-line summary."""
        return (
            f"compatible={self.is_compatible} "
            f"allowed={len(self.allowed)} disallowed={self.disallowed} "
            f"unknown={self.unknown}"
        )


def _base_op_name(target: object) -> str:
    """Extract ``aten.op_name`` from a torch.export target (strip variant suffix)."""
    s = str(target)
    parts = s.split(".")
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return s


def check_model_ops(
    model: nn.Module,
    input_shape: tuple[int, ...] = (1, 100),
    example_inputs: tuple[torch.Tensor, ...] | None = None,
) -> OpsReport:
    """Export a model and check its ops against the VectorBlox whitelist.

    Parameters
    ----------
    model : nn.Module
        PyTorch model to check.
    input_shape : tuple[int, ...]
        Shape of the dummy input tensor for export tracing (used when ``example_inputs`` is
        ``None``).
    example_inputs : tuple of Tensor, optional
        Explicit positional example inputs for ``torch.export`` — use for multi-input modules
        (e.g. a recurrent cell taking ``(state, features)``). Overrides ``input_shape``.

    Returns
    -------
    OpsReport
        Report with allowed, disallowed, and unknown ops.
    """
    model.eval()
    report = OpsReport()

    # Phase 1: module-level check (catches Conv1d vs Conv2d ambiguity).
    for name, module in model.named_modules():
        if type(module) in VECTORBLOX_BANNED_MODULES:
            report.disallowed.append(f"{type(module).__name__} at {name}")

    # Phase 2: topology gate — MEASURED 2026-07-02: the V250 flow only works with exactly
    # one graph input (multi-input graphs sim-corrupt; state-as-graph-input cells crash
    # vnnx_compile). See module docstring for evidence pointers.
    if example_inputs is None:
        example_inputs = (torch.randn(*input_shape),)
    if len(example_inputs) > MAX_GRAPH_INPUTS:
        report.disallowed.append(
            f"multi_graph_input({len(example_inputs)} inputs; max {MAX_GRAPH_INPUTS} — "
            f"measured broken on SDK 2.0.x, 2026-07-02)"
        )

    # Phase 3: torch.export graph op-level check.
    exported = torch.export.export(model, example_inputs)

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


def assert_v250_compatible(
    model: nn.Module,
    input_shape: tuple[int, ...] = (1, 100),
    example_inputs: tuple[torch.Tensor, ...] | None = None,
) -> OpsReport:
    """Check a model and raise :class:`OpsGuardError` if it is not V250-compatible.

    Use as the pre-train / pre-export gate for any block tagged V250-targeted.
    """
    report = check_model_ops(model, input_shape=input_shape, example_inputs=example_inputs)
    if not report.is_compatible:
        raise OpsGuardError(
            f"Model is not V250-compatible: disallowed ops/modules {report.disallowed}. "
            f"vnnx_compile -c V250 (in polarfire-hybrid-control) would reject it."
        )
    return report
