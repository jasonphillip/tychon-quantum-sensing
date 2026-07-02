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
import torch.nn.functional as F

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


def soft_association_targets(
    res_norm: torch.Tensor,
    anchors: torch.Tensor,
    radius: float,
    hard_targets: torch.Tensor | None = None,
) -> torch.Tensor:
    """Soft/merged CE targets for attribution-ambiguous in-collision frames (2c lever 1).

    Inside an *ambiguity cluster* — a set of lines mutually within ``radius`` (normalized
    window units) — the one-hot target is replaced by target mass split uniformly across the
    cluster members' nearest anchors; outside any cluster (an isolated line) the target stays
    one-hot at the line's own nearest anchor. Rationale (dispatch 2c): hard one-hot targets
    teach a confident answer exactly where the attribution is physically unearned — within
    ``k·Γ`` of a merge the lines are not distinguishable from the spectrum — and that
    over-confident wrong lock is what B3's motion gate amplified. Splitting the mass makes the
    unearned confidence un-learnable.

    The cluster is built from pairwise center proximity, which is the same rule the contract
    uses for ``line_collision`` (``|f_i − f_j| < k·Γ``), so no separate collision flag is
    needed: an isolated line's cluster is just itself and the target reduces to the hard
    one-hot. When two clustered lines share a single nearest anchor (a fully merged cell) the
    split mass lands on that one anchor, i.e. the "merged target class" — recovered as a
    special case, not a separate code path.

    Parameters
    ----------
    res_norm
        ``(..., L)`` ground-truth line centers in normalized window units.
    anchors
        ``(K,)`` extractor anchor positions (normalized units).
    radius
        Ambiguity radius in normalized window units (e.g. ``k·Γ`` mapped through
        :func:`normalize_freqs`' scale, ``k·Γ_Hz / (f1 − f0)``).
    hard_targets
        Optional precomputed ``(..., L)`` nearest-anchor indices (from
        :func:`association_targets`); recomputed when omitted.

    Returns
    -------
    torch.Tensor
        ``(..., L, K)`` target distributions summing to 1 over the anchor axis. Equals the
        one-hot of :func:`association_targets` wherever a line has no cluster neighbours.
    """
    if radius < 0.0:
        raise ValueError(f"radius must be non-negative, got {radius}")
    if hard_targets is None:
        hard_targets = association_targets(res_norm, anchors)  # (..., L)
    n_anchors = int(anchors.shape[0])
    n_lines = int(res_norm.shape[-1])
    onehot = F.one_hot(hard_targets, num_classes=n_anchors).to(res_norm.dtype)  # (..., L, K)
    # Mutual-proximity adjacency over line pairs. Self-membership is forced (a line is always
    # in its own cluster) so the target is well-defined even at radius=0 (→ pure one-hot),
    # where the strict ``< radius`` test would otherwise exclude the zero-distance diagonal.
    d = torch.abs(res_norm.unsqueeze(-1) - res_norm.unsqueeze(-2))  # (..., L, L)
    eye = torch.eye(n_lines, dtype=torch.bool, device=res_norm.device)
    adj = ((d < float(radius)) | eye).to(res_norm.dtype)           # (..., L, L)
    # Cluster target for slot l = mean of its cluster members' one-hot anchor targets.
    summed = adj @ onehot                                          # (..., L, K)
    counts = adj.sum(dim=-1, keepdim=True)                         # (..., L, 1) >= 1 (diagonal)
    return summed / counts


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
