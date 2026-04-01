"""Architecture B-alt: Fully Convolutional CNN for ODMR spectrum -> 3D B-field vector.

VectorBlox V250 compatible: CONV_2D + RELU only. NO Linear layers anywhere.
The final Conv2d with kernel matching the remaining spatial dimension replaces
the traditional Flatten -> Linear head.

All convolutions use (1, k) kernels on input reshaped to (batch, 1, 1, length),
satisfying VectorBlox's no-CONV_1D constraint.
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor


class OdmrFCNN(nn.Module):
    """Fully convolutional neural network for ODMR inversion.

    No Linear layers. The final Conv2d collapses the remaining spatial
    dimension to produce the output vector directly.

    Parameters
    ----------
    input_dim : int
        Number of frequency points per spectrum (default 100).
    output_dim : int
        Output vector dimension (default 3 for [Bx, By, Bz]).
    channels : list[int]
        Channel sizes for strided conv layers. Default [8, 16, 24].
    kernel_size : int
        Kernel width for (1, k) convolutions. Default 5.
    stride : int
        Stride for strided conv layers. Default 2.
    """

    def __init__(
        self,
        input_dim: int = 100,
        output_dim: int = 3,
        channels: list[int] | None = None,
        kernel_size: int = 5,
        stride: int = 2,
    ) -> None:
        super().__init__()
        if channels is None:
            channels = [8, 16, 24]

        # Build strided conv layers and track spatial dimension
        self.convs = nn.ModuleList()
        self.relus = nn.ModuleList()
        spatial = input_dim
        prev_c = 1
        for c in channels:
            self.convs.append(
                nn.Conv2d(prev_c, c, kernel_size=(1, kernel_size), stride=(1, stride))
            )
            self.relus.append(nn.ReLU())
            spatial = (spatial - kernel_size) // stride + 1
            prev_c = c

        # Head conv: collapse remaining spatial to (1,1), replacing Linear
        self.conv_head = nn.Conv2d(prev_c, output_dim, kernel_size=(1, spatial))

    def forward(self, x: Tensor) -> Tensor:
        """Forward pass.

        Parameters
        ----------
        x : Tensor
            Shape (batch, input_dim).

        Returns
        -------
        Tensor
            Shape (batch, output_dim).
        """
        # (batch, 100) -> (batch, 1, 1, 100) for 2D conv
        x = x.unsqueeze(1).unsqueeze(2)
        for conv, relu in zip(self.convs, self.relus):
            x = relu(conv(x))
        x = self.conv_head(x)  # (batch, output_dim, 1, 1)
        return x.flatten(1)  # (batch, output_dim)
