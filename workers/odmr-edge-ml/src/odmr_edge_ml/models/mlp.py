"""Architecture A: MLP for ODMR spectrum → 3D B-field vector.

VectorBlox-compatible: FULLY_CONNECTED + RELU only. No BatchNorm,
no Dropout, no activations outside {ReLU, ReLU6}.
"""

from __future__ import annotations

import torch.nn as nn
from torch import Tensor

from odmr_edge_ml.training.loop import init_weights_kaiming_he


class OdmrMLP(nn.Module):
    """Multi-layer perceptron for ODMR inversion.

    Parameters
    ----------
    input_dim : int
        Number of frequency points per spectrum (default 100).
    output_dim : int
        Output vector dimension (default 3 for [Bx, By, Bz]).
    hidden_dims : list[int]
        Sizes of hidden layers.
    activation : str
        "relu" or "relu6" (both VectorBlox-compatible).
    init_weights : bool
        If True (default), apply Kaiming He Normal initialization.
        Set to False when loading pretrained weights.
    """

    def __init__(
        self,
        input_dim: int = 100,
        output_dim: int = 3,
        hidden_dims: list[int] | None = None,
        activation: str = "relu",
        init_weights: bool = True,
    ) -> None:
        super().__init__()
        if hidden_dims is None:
            hidden_dims = [256, 128, 64]

        act_fn: type[nn.Module] = nn.ReLU if activation == "relu" else nn.ReLU6

        layers: list[nn.Module] = []
        prev_dim = input_dim
        for h in hidden_dims:
            layers.append(nn.Linear(prev_dim, h))
            layers.append(act_fn())
            prev_dim = h

        # Output layer — no activation (regression)
        layers.append(nn.Linear(prev_dim, output_dim))
        self.net = nn.Sequential(*layers)

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
        return self.net(x)
