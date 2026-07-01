"""Training losses for the learned tracker — pure tensor functions.

Three terms, all O(1)-normalized so unit weights are a sane starting point:

- :func:`association_loss` — per-slot K-way cross-entropy on the association scores, with
  ``line_collision``-flagged entries upweighted (the hard regime the thesis targets). Works on
  both head variants: raw logits (linear head → ``log_softmax``) and soft probabilities
  (attention head → ``log``). The softmax lives *here*, in loss machinery — it never joins the
  deployed graph, and the deployed hard assignment (argmax) is unchanged by it.
- :func:`position_loss` — Huber on the target-anchor candidate positions vs the true line
  centers, in units of the anchor spacing (so an error of one anchor cell ≈ 1.0).
- :func:`projection_loss` — MSE on the regressed axis projections vs the exact
  ``B_true · n_i`` labels (already in ``proj_scale_T`` units from
  :mod:`~odmr_vector_tracking.training.targets`).

:func:`compute_losses` aggregates the three into a weighted total.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from odmr_vector_tracking.tracking.learned import LearnedTrackerOutput

_EPS = 1e-9


def association_loss(
    scores: torch.Tensor,
    targets: torch.Tensor,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    scores_are_probs: bool = False,
) -> torch.Tensor:
    """Weighted cross-entropy between association scores and nearest-anchor targets.

    Parameters
    ----------
    scores
        ``(..., L, K)`` association-head output (logits, or probabilities summing to 1 over
        the last dim when ``scores_are_probs``).
    targets
        ``(..., L)`` long — target anchor index per line-slot.
    line_collision
        Optional ``(..., L)`` bool; flagged entries get ``collision_weight``, others 1.
    """
    if scores_are_probs:
        logp = torch.log(scores + _EPS)
    else:
        logp = F.log_softmax(scores, dim=-1)
    nll = -torch.gather(logp, -1, targets.unsqueeze(-1)).squeeze(-1)  # (..., L)
    if line_collision is None:
        return nll.mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(nll.dtype)
    return (nll * w).sum() / w.sum()


def position_loss(
    cand_pos: torch.Tensor,
    targets: torch.Tensor,
    res_norm: torch.Tensor,
    anchor_spacing: float,
) -> torch.Tensor:
    """Huber loss on target-anchor candidate positions vs true line centers.

    Gathers each line's *target* anchor position from ``cand_pos`` (differentiable through the
    offset head) and penalizes its distance to the true center, scaled by ``anchor_spacing`` so
    the residual is in anchor-cell units (Huber ``delta = 1`` → quadratic within one cell).

    Parameters
    ----------
    cand_pos
        ``(..., K)`` candidate positions (normalized window units).
    targets
        ``(..., L)`` long — target anchor per line (from :func:`association_targets`).
    res_norm
        ``(..., L)`` true line centers (normalized window units).
    anchor_spacing
        Anchor pitch in normalized units: ``2**n_downsample / (n_freq - 1)``.
    """
    pred = torch.gather(cand_pos, -1, targets)  # (..., L)
    residual = (pred - res_norm) / float(anchor_spacing)
    return F.smooth_l1_loss(residual, torch.zeros_like(residual))


def projection_loss(projections: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """MSE between regressed projections and exact ``B_true · n_i`` labels (scaled units)."""
    return F.mse_loss(projections, labels)


def compute_losses(
    output: LearnedTrackerOutput,
    assoc_targets: torch.Tensor,
    res_norm: torch.Tensor,
    proj_labels: torch.Tensor,
    line_collision: torch.Tensor | None,
    *,
    anchor_spacing: float,
    collision_weight: float = 5.0,
    w_assoc: float = 1.0,
    w_pos: float = 1.0,
    w_proj: float = 1.0,
    scores_are_probs: bool = False,
) -> dict[str, torch.Tensor]:
    """All three losses + weighted total for one forward pass over ``(B, T, ...)`` batches.

    Returns ``{"association", "position", "projection", "total"}`` scalar tensors.
    """
    assoc = association_loss(
        output.scores,
        assoc_targets,
        line_collision=line_collision,
        collision_weight=collision_weight,
        scores_are_probs=scores_are_probs,
    )
    pos = position_loss(output.cand_pos, assoc_targets, res_norm, anchor_spacing)
    proj = projection_loss(output.projections, proj_labels)
    total = w_assoc * assoc + w_pos * pos + w_proj * proj
    return {"association": assoc, "position": pos, "projection": proj, "total": total}
