"""Canonical B-field targets for training and validation."""

from __future__ import annotations

import torch


def fold_bz_sign(b_field: torch.Tensor) -> torch.Tensor:
    """Fold vector rows with negative Bz into the positive hemisphere.

    Scalar residual labels (fewer than three columns) are returned unchanged.
    """
    if b_field.shape[1] < 3:
        return b_field
    neg_mask = b_field[:, 2] < 0
    if neg_mask.any():
        b_field = b_field.clone()
        b_field[neg_mask] *= -1.0
    return b_field


def canonical_vector_target(b_true: torch.Tensor, fold_bz: bool) -> torch.Tensor:
    """Apply the configured Bz convention to vector targets only."""
    if not fold_bz or b_true.shape[1] < 3:
        return b_true
    return fold_bz_sign(b_true)
