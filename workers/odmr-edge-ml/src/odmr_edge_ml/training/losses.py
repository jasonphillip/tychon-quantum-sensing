"""Physics-informed composite loss for ODMR → B-field inversion.

Standard MSE fails because Fano bias (~1500 nT) is ~40x larger than
heading error (~37 nT). MSE optimizes away Fano but treats heading error
as noise. Cosine similarity explicitly penalizes angular error regardless
of magnitude — the navigation-critical metric. Huber loss prevents Fano
outliers from exploding gradients.

IMPORTANT: All inputs MUST be in micro-Tesla (µT). Do NOT pass Tesla
or nanoTesla — the caller is responsible for unit conversion.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from torch import Tensor


class CompositeAngularHuberLoss(nn.Module):
    """Weighted combination of cosine angular loss and Huber regression loss.

    Parameters
    ----------
    alpha : float
        Weight for angular loss. (1 - alpha) weights the Huber loss.
        Default 0.7 emphasizes direction over magnitude.
    huber_delta : float
        Huber delta threshold in µT units. Residuals beyond this are
        penalized linearly rather than quadratically.
    """

    def __init__(self, alpha: float = 0.7, huber_delta: float = 1.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.huber_loss = nn.HuberLoss(reduction="mean", delta=huber_delta)

    def forward(self, B_pred_uT: Tensor, B_true_uT: Tensor) -> dict[str, Tensor]:
        """Compute composite loss.

        Parameters
        ----------
        B_pred_uT : Tensor
            Predicted B-field, shape (N, 3) in µT.
        B_true_uT : Tensor
            Ground truth B-field, shape (N, 3) in µT.

        Returns
        -------
        dict[str, Tensor]
            Keys: "loss" (scalar), "angular" (scalar), "huber" (scalar).
        """
        # Angular loss: 1 - mean(cosine_similarity)
        cos_sim = nn.functional.cosine_similarity(B_pred_uT, B_true_uT, dim=1)
        cos_sim = cos_sim.clamp(-1.0, 1.0)
        angular = 1.0 - cos_sim.mean()

        # Huber regression loss on components
        huber = self.huber_loss(B_pred_uT, B_true_uT)

        loss = self.alpha * angular + (1.0 - self.alpha) * huber

        return {"loss": loss, "angular": angular, "huber": huber}


def angular_error_deg(B_pred_uT: Tensor, B_true_uT: Tensor) -> Tensor:
    """Per-sample angular error in degrees.

    Parameters
    ----------
    B_pred_uT : Tensor
        Predicted B-field, shape (N, 3) in µT.
    B_true_uT : Tensor
        Ground truth B-field, shape (N, 3) in µT.

    Returns
    -------
    Tensor
        Shape (N,) — angular error per sample in degrees.
    """
    cos_sim = nn.functional.cosine_similarity(B_pred_uT, B_true_uT, dim=1)
    cos_sim = cos_sim.clamp(-1.0, 1.0)
    return torch.acos(cos_sim) * (180.0 / torch.pi)


def component_error_nT(B_pred_uT: Tensor, B_true_uT: Tensor) -> Tensor:
    """Per-sample per-component absolute error in nanoTesla.

    Parameters
    ----------
    B_pred_uT : Tensor
        Predicted B-field, shape (N, 3) in µT.
    B_true_uT : Tensor
        Ground truth B-field, shape (N, 3) in µT.

    Returns
    -------
    Tensor
        Shape (N, 3) — absolute error per component in nT (µT * 1000).
    """
    return (B_pred_uT - B_true_uT).abs() * 1000.0
