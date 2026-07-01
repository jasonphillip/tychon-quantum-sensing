"""Unit tests for the training losses — hand-built known answers + end-to-end gradient flow."""

from __future__ import annotations

import torch

from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.training.losses import (
    association_loss,
    compute_losses,
    position_loss,
    projection_loss,
)
from odmr_vector_tracking.training.targets import association_targets


def test_association_loss_zero_when_confident_and_correct() -> None:
    targets = torch.tensor([[0, 2]])
    scores = torch.full((1, 2, 3), -50.0)
    scores[0, 0, 0] = 50.0
    scores[0, 1, 2] = 50.0
    loss = association_loss(scores, targets)
    assert float(loss) < 1e-6


def test_association_loss_uniform_logits_is_log_k() -> None:
    k = 8
    scores = torch.zeros((1, 4, k))
    targets = torch.zeros((1, 4), dtype=torch.long)
    loss = association_loss(scores, targets)
    assert abs(float(loss) - torch.log(torch.tensor(float(k))).item()) < 1e-6


def test_association_loss_collision_upweighting() -> None:
    """Wrong only on the in-collision entry: weighted loss must exceed unweighted."""
    targets = torch.tensor([[0, 1]])
    scores = torch.full((1, 2, 3), -50.0)
    scores[0, 0, 0] = 50.0   # slot 0 correct (out of collision)
    scores[0, 1, 0] = 50.0   # slot 1 WRONG (in collision; target 1)
    coll = torch.tensor([[False, True]])
    base = association_loss(scores, targets, line_collision=coll, collision_weight=1.0)
    up = association_loss(scores, targets, line_collision=coll, collision_weight=5.0)
    assert float(up) > float(base) * 1.5


def test_association_loss_probs_path() -> None:
    """Attention-head variant: probabilities in, same zero-loss-when-correct behavior."""
    probs = torch.tensor([[[0.98, 0.01, 0.01], [0.01, 0.98, 0.01]]])
    targets = torch.tensor([[0, 1]])
    loss = association_loss(probs, targets, scores_are_probs=True)
    assert float(loss) < 0.03


def test_position_loss_known_value() -> None:
    """Error of half an anchor cell → scaled residual 0.5 → Huber = 0.5²/2 = 0.125."""
    spacing = 0.1
    cand_pos = torch.tensor([[0.0, 0.10, 0.20]])
    targets = torch.tensor([[1]])
    res = torch.tensor([[0.15]])  # true center 0.05 from anchor-1 position
    loss = position_loss(cand_pos, targets, res, anchor_spacing=spacing)
    assert abs(float(loss) - 0.125) < 1e-6


def test_position_loss_zero_when_exact() -> None:
    cand_pos = torch.tensor([[0.0, 0.5, 1.0]])
    targets = torch.tensor([[1, 2]])
    res = torch.tensor([[0.5, 1.0]])
    assert float(position_loss(cand_pos, targets, res, anchor_spacing=0.5)) == 0.0


def test_projection_loss_is_mse() -> None:
    p = torch.tensor([[1.0, 0.0, -1.0, 0.0]])
    lab = torch.tensor([[0.0, 0.0, -1.0, 0.0]])
    assert abs(float(projection_loss(p, lab)) - 0.25) < 1e-7


def test_compute_losses_total_is_weighted_sum() -> None:
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg)
    spectra = torch.rand(2, 5, cfg.n_freq)
    out = trk(spectra)
    anchors = trk.extractor.get_buffer("anchors")
    res_norm = torch.rand(2, 5, cfg.n_lines)
    targets = association_targets(res_norm, anchors)
    labels = torch.randn(2, 5, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 5, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)

    d = compute_losses(
        out, targets, res_norm, labels, coll,
        anchor_spacing=spacing, w_assoc=2.0, w_pos=3.0, w_proj=0.5,
    )
    expected = 2.0 * d["association"] + 3.0 * d["position"] + 0.5 * d["projection"]
    assert torch.allclose(d["total"], expected)


def test_gradients_reach_every_trainable_block() -> None:
    """End-to-end: one loss backward must produce nonzero grads in extractor (convs + both
    heads), core, association head, and the host glue — proves the training graph is wired."""
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg, core="relu", association="linear")
    spectra = torch.rand(2, 6, cfg.n_freq)
    out = trk(spectra)
    anchors = trk.extractor.get_buffer("anchors")
    res_norm = torch.rand(2, 6, cfg.n_lines)
    targets = association_targets(res_norm, anchors)
    labels = torch.randn(2, 6, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 6, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)

    d = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing)
    d["total"].backward()

    def grad_ok(mod: torch.nn.Module) -> bool:
        gs = [p.grad for p in mod.parameters() if p.requires_grad]
        return len(gs) > 0 and all(g is not None for g in gs) and any(
            float(g.abs().sum()) > 0 for g in gs if g is not None
        )

    assert grad_ok(trk.extractor.convs)
    assert grad_ok(trk.extractor.feat_head)
    assert grad_ok(trk.extractor.offset_head)   # via the position loss
    assert grad_ok(trk.core)
    assert grad_ok(trk.association)
    assert grad_ok(trk.obs_embed)
    assert grad_ok(trk.state_to_proj)
    assert grad_ok(trk.state_to_tracks)
    # The BLUE decode stays frozen — geometry is not learned.
    assert trk.decoder.decode.weight.grad is None
    assert not trk.decoder.decode.weight.requires_grad
