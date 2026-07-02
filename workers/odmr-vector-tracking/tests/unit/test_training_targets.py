"""Unit tests for supervision-target construction — hand-built inputs, known answers."""

from __future__ import annotations

import numpy as np
import torch

from odmr_vector_tracking.training.targets import (
    association_targets,
    normalize_freqs,
    projection_labels,
    soft_association_targets,
)
from odmr_vector_tracking.vector.geometry import NV_AXES_UNIT


def test_normalize_freqs_maps_window_to_unit_interval() -> None:
    fr = (2.0e9, 3.0e9)
    f = torch.tensor([2.0e9, 2.5e9, 3.0e9])
    out = normalize_freqs(f, fr)
    assert torch.allclose(out, torch.tensor([0.0, 0.5, 1.0]))


def test_association_targets_pick_nearest_anchor() -> None:
    anchors = torch.tensor([0.0, 0.25, 0.5, 0.75])
    res = torch.tensor([[0.02, 0.30, 0.49, 0.74]])  # (1, L=4)
    tgt = association_targets(res, anchors)
    assert tgt.tolist() == [[0, 1, 2, 3]]
    assert tgt.dtype == torch.long


def test_association_targets_share_anchor_when_lines_merge() -> None:
    """Two lines inside one anchor cell (a collision) share the target — the merged regime."""
    anchors = torch.tensor([0.0, 0.5, 1.0])
    res = torch.tensor([[0.49, 0.52]])
    tgt = association_targets(res, anchors)
    assert tgt.tolist() == [[1, 1]]


def test_association_targets_batch_shapes() -> None:
    anchors = torch.linspace(0, 1, 16)
    res = torch.rand(3, 7, 8)  # (N, T, L)
    tgt = association_targets(res, anchors)
    assert tgt.shape == (3, 7, 8)
    assert int(tgt.max()) < 16


def test_soft_targets_isolated_lines_are_one_hot() -> None:
    """Lines far apart (no cluster neighbours) → soft target == the hard one-hot."""
    anchors = torch.tensor([0.0, 0.25, 0.5, 0.75])
    res = torch.tensor([[0.02, 0.30, 0.49, 0.74]])  # spaced >> radius
    soft = soft_association_targets(res, anchors, radius=0.05)
    hard = association_targets(res, anchors)
    assert soft.shape == (1, 4, 4)
    assert torch.allclose(soft, torch.nn.functional.one_hot(hard, 4).float())
    assert torch.allclose(soft.sum(-1), torch.ones(1, 4))


def test_soft_targets_merged_pair_splits_mass() -> None:
    """Two lines within radius but on distinct anchors → 0.5/0.5 for BOTH slots."""
    anchors = torch.tensor([0.0, 0.25, 0.5, 0.75])
    # 0.36 → nearest 0.25 (anchor 1); 0.39 → nearest 0.5 (anchor 2); |Δ| = 0.03 < radius.
    res = torch.tensor([[0.36, 0.39]])
    soft = soft_association_targets(res, anchors, radius=0.05)
    expected = torch.tensor([[[0.0, 0.5, 0.5, 0.0], [0.0, 0.5, 0.5, 0.0]]])
    assert torch.allclose(soft, expected)


def test_soft_targets_fully_merged_cell_is_one_hot() -> None:
    """Clustered lines that share a single nearest anchor → mass 1 on that anchor."""
    anchors = torch.tensor([0.0, 0.5, 1.0])
    res = torch.tensor([[0.49, 0.51]])  # both nearest anchor 1, and within radius
    soft = soft_association_targets(res, anchors, radius=0.05)
    expected = torch.tensor([[[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]]])
    assert torch.allclose(soft, expected)


def test_soft_targets_radius_zero_is_pure_one_hot() -> None:
    """radius=0: no line has a neighbour (strict <), self-membership rescues the diagonal."""
    anchors = torch.tensor([0.0, 0.5, 1.0])
    res = torch.tensor([[0.49, 0.51]])
    soft = soft_association_targets(res, anchors, radius=0.0)
    hard = association_targets(res, anchors)
    assert torch.allclose(soft, torch.nn.functional.one_hot(hard, 3).float())
    assert torch.allclose(soft.sum(-1), torch.ones(1, 2))


def test_soft_targets_always_sum_to_one() -> None:
    anchors = torch.linspace(0, 1, 16)
    res = torch.rand(3, 7, 8)
    soft = soft_association_targets(res, anchors, radius=0.1)
    assert soft.shape == (3, 7, 8, 16)
    assert torch.allclose(soft.sum(-1), torch.ones(3, 7, 8), atol=1e-6)


def test_soft_targets_triple_cluster_splits_thirds() -> None:
    """Three mutually-close lines on distinct anchors → 1/3 mass each."""
    anchors = torch.tensor([0.0, 0.1, 0.2, 0.3, 0.9])
    res = torch.tensor([[0.10, 0.12, 0.19]])  # nearest anchors 1,1,2 ... check split
    # nearest: 0.10→1, 0.12→1, 0.19→2. pairwise all within 0.1 → one cluster of 3.
    # anchors hit: {1,1,2} → mass 2/3 on anchor 1, 1/3 on anchor 2 for every slot.
    soft = soft_association_targets(res, anchors, radius=0.1)
    expected_row = torch.tensor([0.0, 2.0 / 3.0, 1.0 / 3.0, 0.0, 0.0])
    assert torch.allclose(soft[0], expected_row.expand(3, 5), atol=1e-6)


def test_projection_labels_along_axis0() -> None:
    """B along n_0: projections are |B|·(n_0·n_i) = |B|·[1, -1/3, -1/3, -1/3], scaled."""
    scale = 1.0e-2
    b_mag = 5.0e-3
    B = torch.tensor(NV_AXES_UNIT[0], dtype=torch.float64) * b_mag
    lab = projection_labels(B.unsqueeze(0), scale)  # (1, 4)
    expected = torch.tensor([[1.0, -1.0 / 3.0, -1.0 / 3.0, -1.0 / 3.0]], dtype=torch.float64)
    expected = expected * (b_mag / scale)
    assert torch.allclose(lab, expected, atol=1e-12)


def test_projection_labels_sum_to_zero() -> None:
    """The four ⟨111⟩ projections satisfy Σ = 0 identically (Σ n_i = 0)."""
    rng = np.random.default_rng(0)
    B = torch.tensor(rng.normal(0, 5e-3, size=(4, 6, 3)), dtype=torch.float64)
    lab = projection_labels(B, 1.0e-2)
    assert lab.shape == (4, 6, 4)
    assert torch.allclose(lab.sum(dim=-1), torch.zeros(4, 6, dtype=torch.float64), atol=1e-14)


def test_projection_labels_match_loader_convention() -> None:
    """Cross-check against numpy: labels equal (B_true @ N^T)/scale elementwise."""
    rng = np.random.default_rng(1)
    B_np = rng.normal(0, 5e-3, size=(2, 3, 3)).astype(np.float32)
    lab = projection_labels(torch.from_numpy(B_np), 1.0e-2)
    ref = B_np @ NV_AXES_UNIT.T.astype(np.float32) / 1.0e-2
    assert np.allclose(lab.numpy(), ref, atol=1e-6)
