"""Architecture B: 1D-CNN for ODMR spectrum → 3D B-field vector.

VectorBlox constraint: no CONV_1D op. All 1D convolutions implemented
as CONV_2D with (1, k) kernels on input reshaped to (batch, channels, 1, length).

Uses depthwise-separable convolutions, residual connections (ADD),
and global average pooling (MEAN).
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor

from odmr_edge_ml.training.loop import init_weights_kaiming_he


class DepthwiseSeparableConv2d(nn.Module):
    """Depthwise-separable convolution via Conv2d with (1, k) kernels."""

    def __init__(self, in_channels: int, out_channels: int, kernel_size: int) -> None:
        super().__init__()
        # Depthwise: groups=in_channels, (1, k) kernel
        self.depthwise = nn.Conv2d(
            in_channels,
            in_channels,
            kernel_size=(1, kernel_size),
            padding=(0, kernel_size // 2),
            groups=in_channels,
            bias=False,
        )
        # Pointwise: 1x1 conv
        self.pointwise = nn.Conv2d(in_channels, out_channels, kernel_size=1, bias=True)

    def forward(self, x: Tensor) -> Tensor:
        return self.pointwise(self.depthwise(x))


class ResidualBlock(nn.Module):
    """Residual block with depthwise-separable conv + ReLU + ADD."""

    def __init__(self, channels: int, kernel_size: int) -> None:
        super().__init__()
        self.conv1 = DepthwiseSeparableConv2d(channels, channels, kernel_size)
        self.relu1 = nn.ReLU()
        self.conv2 = DepthwiseSeparableConv2d(channels, channels, kernel_size)
        self.relu2 = nn.ReLU()

    def forward(self, x: Tensor) -> Tensor:
        residual = x
        out = self.relu1(self.conv1(x))
        out = self.conv2(out)
        out = out + residual  # ADD op
        return self.relu2(out)


class OdmrCNN1D(nn.Module):
    """1D-CNN for ODMR inversion, implemented as 2D conv per VectorBlox.

    Parameters
    ----------
    input_dim : int
        Number of frequency points per spectrum (default 100).
    output_dim : int
        Output vector dimension (default 3 for [Bx, By, Bz]).
    channels : list[int]
        Channel sizes for conv layers. First element is the stem output channels,
        subsequent elements add residual blocks with channel projection.
    kernel_size : int
        Kernel width for (1, k) convolutions.
    init_weights : bool
        If True (default), apply Kaiming He Normal initialization.
        Set to False when loading pretrained weights.
    """

    def __init__(
        self,
        input_dim: int = 100,
        output_dim: int = 3,
        channels: list[int] | None = None,
        kernel_size: int = 5,
        init_weights: bool = True,
    ) -> None:
        super().__init__()
        if channels is None:
            channels = [16, 32, 32]

        # Stem: project 1-channel input to first channel count
        self.stem = nn.Sequential(
            nn.Conv2d(1, channels[0], kernel_size=(1, kernel_size), padding=(0, kernel_size // 2)),
            nn.ReLU(),
        )

        # Build conv blocks with channel transitions + residual blocks
        blocks: list[nn.Module] = []
        for i in range(1, len(channels)):
            if channels[i] != channels[i - 1]:
                # Channel projection via pointwise conv
                blocks.append(nn.Conv2d(channels[i - 1], channels[i], kernel_size=1))
                blocks.append(nn.ReLU())
            blocks.append(ResidualBlock(channels[i], kernel_size))
        self.conv_blocks = nn.Sequential(*blocks)

        # Global average pooling → MEAN op
        self.pool = nn.AdaptiveAvgPool2d((1, 1))

        # FC head
        self.head = nn.Linear(channels[-1], output_dim)

        if init_weights:
            init_weights_kaiming_he(self)

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
        # (batch, 100) → (batch, 1, 1, 100) for 2D conv
        x = x.unsqueeze(1).unsqueeze(2)
        x = self.stem(x)
        x = self.conv_blocks(x)
        x = self.pool(x)  # (batch, C, 1, 1)
        x = x.flatten(1)  # (batch, C)
        return self.head(x)
