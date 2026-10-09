"""Unit tests for the training losses — hand-built known answers + end-to-end gradient flow."""

from __future__ import annotations

import torch
import torch.nn.functional as F

from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.training.losses import (
    association_loss,
    compute_losses,
    log_sinkhorn,
    position_loss,
    projection_loss,
    sinkhorn_assignment_loss,
    soft_association_loss,
    track_position_loss,
)
from odmr_vector_tracking.training.targets import (
    association_targets,
    soft_association_targets,
)


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


def test_soft_association_loss_matches_hard_on_one_hot() -> None:
    """Soft CE on a one-hot target is bit-for-bit the hard cross-entropy (2c lever 1)."""
    scores = torch.randn(2, 4, 5)
    targets = torch.randint(0, 5, (2, 4))
    onehot = F.one_hot(targets, 5).float()
    assert torch.allclose(
        soft_association_loss(scores, onehot), association_loss(scores, targets), atol=1e-6
    )


def test_soft_association_loss_split_target_known_value() -> None:
    """Uniform 3-way logits, target mass split 0.5/0.5 → soft CE = −log(1/3) = log 3."""
    scores = torch.zeros(1, 1, 3)  # log_softmax → log(1/3) each
    target = torch.tensor([[[0.5, 0.5, 0.0]]])
    loss = soft_association_loss(scores, target)
    assert abs(float(loss) - torch.log(torch.tensor(3.0)).item()) < 1e-6


def test_soft_association_loss_collision_upweighting() -> None:
    """Split (unearned-confidence) target on the in-collision slot → weighting raises loss."""
    scores = torch.full((1, 2, 3), -50.0)
    scores[0, 0, 0] = 50.0            # slot 0 confident + correct (out of collision)
    scores[0, 1, 0] = 50.0            # slot 1 confident on anchor 0 (in collision)
    target = torch.tensor([[[1.0, 0.0, 0.0], [0.5, 0.5, 0.0]]])  # slot 1 should be split
    coll = torch.tensor([[False, True]])
    base = soft_association_loss(scores, target, line_collision=coll, collision_weight=1.0)
    up = soft_association_loss(scores, target, line_collision=coll, collision_weight=5.0)
    assert float(up) > float(base) * 1.5


def test_soft_association_loss_probs_path() -> None:
    """Attention-head variant: probabilities in, one-hot target → matches hard probs path."""
    probs = torch.tensor([[[0.98, 0.01, 0.01], [0.01, 0.98, 0.01]]])
    targets = torch.tensor([[0, 1]])
    onehot = F.one_hot(targets, 3).float()
    assert torch.allclose(
        soft_association_loss(probs, onehot, scores_are_probs=True),
        association_loss(probs, targets, scores_are_probs=True),
        atol=1e-6,
    )


def test_soft_association_loss_gradients_flow() -> None:
    scores = torch.randn(2, 4, 6, requires_grad=True)
    res = torch.rand(2, 4)
    anchors = torch.linspace(0, 1, 6)
    soft = soft_association_targets(res, anchors, radius=0.1)
    soft_association_loss(scores, soft).backward()
    assert scores.grad is not None and float(scores.grad.abs().sum()) > 0


def test_compute_losses_routes_soft_targets() -> None:
    """compute_losses with assoc_soft_targets uses the soft CE; one-hot soft == hard total."""
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
    onehot = F.one_hot(targets, cfg.n_candidates).float()
    hard = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing)
    soft = compute_losses(
        out, targets, res_norm, labels, coll,
        anchor_spacing=spacing, assoc_soft_targets=onehot,
    )
    assert torch.allclose(hard["association"], soft["association"], atol=1e-6)
    assert torch.allclose(hard["total"], soft["total"], atol=1e-6)


def test_log_sinkhorn_recovers_transport_marginals() -> None:
    """Log-Sinkhorn converges to the SuperGlue marginals μ=[1]*L⊕K, ν=[1]*K⊕L (total L+K)."""
    scores = torch.randn(2, 3, 5)
    p = log_sinkhorn(scores, n_iters=150).exp()
    assert p.shape == (2, 4, 6)
    assert torch.allclose(p.sum(dim=(1, 2)), torch.ones(2), atol=1e-4)  # total mass 1
    L, K = 3, 5
    mu = torch.tensor([1.0, 1.0, 1.0, K]) / (L + K)
    nu = torch.tensor([1.0, 1.0, 1.0, 1.0, 1.0, L]) / (L + K)
    assert torch.allclose(p.sum(dim=2), mu.expand(2, -1), atol=1e-3)  # row marginals
    assert torch.allclose(p.sum(dim=1), nu.expand(2, -1), atol=1e-3)  # col marginals


def test_sinkhorn_loss_small_when_confident_and_distinct() -> None:
    """Scores confident on distinct GT anchors → one-to-one transport matches → low loss."""
    scores = torch.full((1, 3, 6), -20.0)
    for li, k in enumerate([0, 2, 4]):
        scores[0, li, k] = 20.0
    targets = torch.tensor([[0, 2, 4]])
    loss = sinkhorn_assignment_loss(scores, targets=targets, n_iters=50)
    assert float(loss) < 0.05


def test_sinkhorn_penalizes_two_lines_on_one_candidate() -> None:
    """Exclusivity: piling both lines on candidate 0 costs more than distinct correct scores —
    the transport cannot give one candidate column to two line rows."""
    targets = torch.tensor([[0, 1]])
    distinct = torch.full((1, 2, 4), -20.0)
    distinct[0, 0, 0] = 20.0
    distinct[0, 1, 1] = 20.0
    collide = torch.full((1, 2, 4), -20.0)
    collide[0, 0, 0] = 20.0
    collide[0, 1, 0] = 20.0  # both want candidate 0 — one-to-one impossible
    lo = sinkhorn_assignment_loss(distinct, targets=targets, n_iters=50)
    hi = sinkhorn_assignment_loss(collide, targets=targets, n_iters=50)
    assert float(hi) > float(lo) + 1.0


def test_sinkhorn_loss_accepts_soft_targets() -> None:
    """Composes with lever 1: a soft target_dist is matched against the transport conditional."""
    scores = torch.randn(2, 4, 6, requires_grad=True)
    dist = torch.full((2, 4, 6), 0.0)
    dist[:, :, 0] = 1.0  # one-hot on candidate 0 (valid distribution)
    loss = sinkhorn_assignment_loss(scores, target_dist=dist, n_iters=20)
    loss.backward()
    assert scores.grad is not None and float(scores.grad.abs().sum()) > 0


def test_sinkhorn_requires_exactly_one_target() -> None:
    scores = torch.randn(1, 2, 3)
    try:
        sinkhorn_assignment_loss(scores)  # neither targets nor target_dist
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError when no target is supplied")


def test_compute_losses_routes_sinkhorn() -> None:
    """compute_losses(sinkhorn=True) uses the transport loss and backprops through the tracker."""
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
        out, targets, res_norm, labels, coll, anchor_spacing=spacing, sinkhorn=True,
    )
    assert torch.isfinite(d["total"])
    d["total"].backward()
    assert trk.association.score.weight.grad is not None


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


def test_track_position_loss_known_value() -> None:
    """Same scaling as the candidate-position loss: half-cell error → Huber 0.125."""
    track_pos = torch.tensor([[0.20]])
    res = torch.tensor([[0.15]])
    loss = track_position_loss(track_pos, res, anchor_spacing=0.1)
    assert abs(float(loss) - 0.125) < 1e-6


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
        anchor_spacing=spacing, w_assoc=2.0, w_pos=3.0, w_track=1.5, w_proj=0.5,
    )
    expected = (
        2.0 * d["association"] + 3.0 * d["position"]
        + 1.5 * d["track_position"] + 0.5 * d["projection"]
    )
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
    assert grad_ok(trk.association.dist_proj)   # the relational (distance) branch
    assert grad_ok(trk.obs_embed)
    assert grad_ok(trk.state_to_proj)
    assert grad_ok(trk.state_to_tracks)
    assert grad_ok(trk.state_to_track_pos)      # via the track-position loss
    # The BLUE decode stays frozen — geometry is not learned.
    assert trk.decoder.decode.weight.grad is None
    assert not trk.decoder.decode.weight.requires_grad


def test_gradients_flow_through_motion_prior() -> None:
    """With the CV scaffold on, the innovation head, velocity gain, and t=0 readout all
    receive gradient through the kinematic chain (BPTT through pos/vel recurrences)."""
    cfg = LearnedTrackerConfig(n_freq=64, motion_prior=True)
    trk = build_tracker(cfg)
    out = trk(torch.rand(2, 6, cfg.n_freq))
    anchors = trk.extractor.get_buffer("anchors")
    res_norm = torch.rand(2, 6, cfg.n_lines)
    targets = association_targets(res_norm, anchors)
    labels = torch.randn(2, 6, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 6, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)
    d = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing)
    d["total"].backward()
    assert trk.state_to_track_delta.weight.grad is not None
    assert float(trk.state_to_track_delta.weight.grad.abs().sum()) > 0
    assert trk.gain_head.weight.grad is not None           # learned alpha-beta gain
    assert float(trk.gain_head.weight.grad.abs().sum()) > 0
    assert trk.state_to_track_pos.weight.grad is not None  # t=0 acquisition head
