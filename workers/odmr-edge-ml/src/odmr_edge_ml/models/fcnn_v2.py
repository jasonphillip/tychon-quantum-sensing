"""Architecture B-alt + learnable anchor: OdmrFCNNv2.

Promoted from experiments/scalar_residual_v2.py so multiple downstream
consumers (the production training script and the upcoming hierarchical
INT8 cascade) share one canonical implementation.

Identical conv pipeline to OdmrFCNN(input_dim=100, in_channels=2). The
difference is that the second channel — a Gaussian "anchor" centered on
the lock bin — is computed *inside* the network using a learnable sigma
parameter rather than precomputed in the dataset.

Input contract: (batch, input_dim + 1) — spectrum followed by the lock
bin index. Default 101 floats. Output: (batch, output_dim).

VectorBlox V250 compatible: CONV_2D + RELU only, static spatial shape.
See the forward-pass docstring for the dynamic-batch TFLite footgun.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor


class OdmrFCNNv2(nn.Module):
    """FCNN with learnable anchor sigma.

    Takes (batch, input_dim + 1) input: [spectrum(input_dim), lock_bin(1)].
    Computes a Gaussian anchor with learnable sigma, then runs an identical
    conv pipeline to OdmrFCNN(input_dim=input_dim, in_channels=2).

    Attribute names (convs, relus, conv_head) match OdmrFCNN for weight
    transfer during export.
    """

    def __init__(
        self,
        input_dim: int = 100,
        output_dim: int = 1,
        channels: list[int] | None = None,
        kernel_size: int = 5,
        stride: int = 2,
    ) -> None:
        super().__init__()
        if channels is None:
            channels = [8, 16, 24]

        self.input_dim = input_dim
        self.in_channels = 2
        self.sigma = nn.Parameter(torch.tensor(1.5))
        self.register_buffer("bins", torch.arange(input_dim, dtype=torch.float32))

        # Conv layers — identical to OdmrFCNN(in_channels=2)
        self.convs = nn.ModuleList()
        self.relus = nn.ModuleList()
        spatial = input_dim
        prev_c = 2
        for c in channels:
            self.convs.append(
                nn.Conv2d(prev_c, c, kernel_size=(1, kernel_size), stride=(1, stride))
            )
            self.relus.append(nn.ReLU())
            spatial = (spatial - kernel_size) // stride + 1
            prev_c = c

        self.conv_head = nn.Conv2d(prev_c, output_dim, kernel_size=(1, spatial))

    def forward(self, x: Tensor) -> Tensor:
        """Forward pass.

        Footgun (TFLite / vnnx_compile): the ``x.view(x.size(0), 2, 1, ...)``
        below queries the batch dim at runtime. PyTorch eager and
        ``torch.export`` both happily handle this with a symbolic batch axis,
        but the downstream Keras→TFLite converter — when given a dynamic batch
        — emits SHAPE / STRIDED_SLICE / PACK ops to reconstruct the runtime
        shape. ``vnnx_compile -c V250`` then rejects the TFLite (those three
        ops are outside the V250 whitelist; see CLAUDE.md → "Known Gotchas").

        Symptom: TFLite conversion succeeds, then ``vnnx_compile`` fails with
        a "VECTORBLOX ERROR: unsupported op SHAPE/STRIDED_SLICE/PACK" message
        on the .tflite produced from this model. The same trap caught v1 and
        is what ``scripts/fix_fcnn_export.py`` was written to undo.

        Fix when exporting:
          * Do not export this module directly to TFLite via the dynamic-batch
            Keras path. Either: (a) build the Keras model with a *fixed* batch
            dim (``Input(batch_shape=(1, 1, 100, 2))``) and skip the inline
            ``view``, as ``convert_fcnn_to_tflite_int8`` and the recovery
            script ``scalar_residual_v2_export_recovery.py`` now do; or
          * (b) trace with ``torch.jit.trace`` against a representative input
            so the batch dim is baked to a concrete value before conversion.
          * Always run ``odmr_edge_ml.validation.verify_tflite_ops`` on the
            converted bytes to catch any leak-through before the artifact
            ships to Beelink for ``vnnx_compile``.
        """
        spectrum = x[:, :self.input_dim]   # (batch, input_dim)
        lock_bin = x[:, self.input_dim:]   # (batch, 1)

        sigma = self.sigma.clamp(min=0.1)
        anchor = torch.exp(
            -0.5 * ((self.bins[None, :] - lock_bin) / sigma) ** 2
        )  # (batch, input_dim)

        combined = torch.cat([spectrum, anchor], dim=1)  # (batch, 2 * input_dim)
        x = combined.view(x.size(0), 2, 1, self.input_dim)

        for conv, relu in zip(self.convs, self.relus):
            x = relu(conv(x))
        x = self.conv_head(x)  # (batch, output_dim, 1, 1)
        return x.flatten(1)
