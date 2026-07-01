"""Supervision-target construction for the learned tracker — pure tensor functions.

Builds the three label sets the Increment-2 losses consume, straight from v1-contract arrays:

- **association targets** — for each (frame, line-slot), the index of the extractor anchor
  nearest the ground-truth line center. Slot ``l`` carries the canonical identity (axis
  ``l // 2``) by the contract's line ordering, so ``resonance_freqs[..., l]`` *is* the
  ``line_axis`` association ground truth expressed as a position.
- **projection labels** — exact per-axis projections ``B_true · n_i`` (contract rule: training
  labels come from ``B_true``, never from the observed splitting), in ``proj_scale_T`` units.
- **normalized frequencies** — window units ``(f - f0) / (f1 - f0)`` matching the model's
  internal position convention.

Anchors are fixed buffers (not learned), so all targets are precomputed once per split.
"""

from __future__ import annotations

import torch

from odmr_vector_tracking.vector.geometry import NV_AXES_UNIT


def normalize_freqs(
    freqs_hz: torch.Tensor, freq_range_hz: tuple[float, float]
) -> torch.Tensor:
    """Map absolute frequencies (Hz) to normalized window units ``[0, 1]``.

    ``freq_range_hz`` is the manifest's ``(start, stop)`` MW window; bin ``i`` of an F-point
    sweep sits at ``i / (F - 1)`` in these units (the extractor's anchor convention).
    """
    f0, f1 = float(freq_range_hz[0]), float(freq_range_hz[1])
    return (freqs_hz - f0) / (f1 - f0)


def association_targets(res_norm: torch.Tensor, anchors: torch.Tensor) -> torch.Tensor:
    """Nearest-anchor index for each ground-truth line center.

    Parameters
    ----------
    res_norm
        ``(..., L)`` ground-truth line centers in normalized window units.
    anchors
        ``(K,)`` extractor anchor positions (normalized units).

    Returns
    -------
    torch.Tensor
        ``(..., L)`` long — the anchor each line-slot's association head should select. Two
        lines inside the same anchor cell share a target (the physically merged regime).
    """
    d = torch.abs(res_norm.unsqueeze(-1) - anchors)  # (..., L, K)
    return torch.argmin(d, dim=-1)


def projection_labels(B_true: torch.Tensor, proj_scale_T: float) -> torch.Tensor:
    """Exact axis-projection labels ``(B_true · n_i) / proj_scale_T``.

    ``B_true`` is ``(..., 3)`` Tesla; returns ``(..., 4)`` in the model's regression units.
    The four ⟨111⟩ axis projections satisfy Σ = 0 identically (Σ n_i = 0), so the labels live
    on the BLUE-realizable subspace by construction.
    """
    axes = torch.as_tensor(
        NV_AXES_UNIT, dtype=B_true.dtype, device=B_true.device
    )  # (4, 3)
    return (B_true @ axes.T) / float(proj_scale_T)
