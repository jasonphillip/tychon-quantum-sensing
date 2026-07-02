"""Unit tests for the learned tracker: shapes, anchors, + the V250/MSS deployability boundary."""

from __future__ import annotations

import pytest
import torch

from odmr_vector_tracking.tracking.learned import (
    AttentionAssociation,
    ExecutionTarget,
    FrameFeatureExtractor,
    GatedKalmanNetCore,
    LearnedTrackerConfig,
    LinearScoreAssociation,
    ReLURecurrentCell,
    build_tracker,
    v250_targeted_modules,
)
from odmr_vector_tracking.validation.ops_guard import check_model_ops

CFG = LearnedTrackerConfig(n_freq=128, n_lines=8)
REAL_CFG = LearnedTrackerConfig(n_freq=951, n_lines=8)  # sequence_sanity_v0 shape


def test_candidate_count_derived_from_downsampling() -> None:
    assert CFG.n_candidates == 8       # ceil(128 / 16)
    assert REAL_CFG.n_candidates == 60  # ceil(951 / 16)
    assert LearnedTrackerConfig(n_freq=400).n_candidates == 25


@pytest.mark.parametrize("motion_prior", [False, True], ids=["plain", "motion-prior"])
def test_forward_output_shapes(motion_prior: bool) -> None:
    cfg = LearnedTrackerConfig(n_freq=128, n_lines=8, motion_prior=motion_prior)
    trk = build_tracker(cfg, core="relu", association="linear")
    B, T, L, K = 2, 12, cfg.n_lines, cfg.n_candidates
    out = trk(torch.rand(B, T, cfg.n_freq))
    assert out.b_est.shape == (B, T, 3)
    assert out.assignment.shape == (B, T, L)
    assert out.covariance.shape == (B, T, 3, 3)
    assert out.scores.shape == (B, T, L, K)
    assert out.projections.shape == (B, T, cfg.n_axes)
    assert out.cand_pos.shape == (B, T, K)
    assert out.track_pos.shape == (B, T, L)
    assert out.tracked_freqs.shape == (B, T, L)
    assert out.assignment.dtype == torch.long


def test_motion_prior_scaffold_is_bounded() -> None:
    """The alpha-beta scaffold is anchored to measurements: positions stay bounded (convex
    combinations of predictions and in-window candidate positions), never running away —
    the failure mode of a free-delta-driven detached scaffold."""
    cfg = LearnedTrackerConfig(n_freq=128, n_lines=8, motion_prior=True)
    trk = build_tracker(cfg)
    out = trk(torch.rand(1, 32, cfg.n_freq))
    assert torch.isfinite(out.track_pos).all()
    assert float(out.track_pos.abs().max()) < 2.0  # window units; generous bound


def test_scheduled_sampling_shapes_and_head() -> None:
    """Lever 3: scheduled_sampling adds an ss_delta head and preserves all output shapes."""
    cfg = LearnedTrackerConfig(n_freq=128, n_lines=8, scheduled_sampling=True)
    trk = build_tracker(cfg)
    assert hasattr(trk, "ss_delta")
    out = trk(torch.rand(2, 10, cfg.n_freq))  # free-running (teacher_pos=None)
    assert out.track_pos.shape == (2, 10, cfg.n_lines)
    assert out.scores.shape == (2, 10, cfg.n_lines, cfg.n_candidates)
    assert torch.isfinite(out.track_pos).all()


def test_scheduled_sampling_free_running_is_deterministic() -> None:
    """teacher_pos=None takes the no-RNG free-running branch → repeatable eval output."""
    cfg = LearnedTrackerConfig(n_freq=128, scheduled_sampling=True)
    trk = build_tracker(cfg).eval()
    x = torch.rand(2, 8, cfg.n_freq)
    with torch.no_grad():
        a, b = trk(x), trk(x)
    assert torch.allclose(a.track_pos, b.track_pos)
    assert torch.allclose(a.scores, b.scores)


def test_scheduled_sampling_zero_init_is_constant_position() -> None:
    """ss_delta zero-init → free-running query is a constant-position prior: with no motion
    delta, every frame's track_pos equals the t=0 acquisition readout."""
    cfg = LearnedTrackerConfig(n_freq=128, scheduled_sampling=True)
    trk = build_tracker(cfg).eval()
    with torch.no_grad():
        out = trk(torch.rand(1, 6, cfg.n_freq))
    first = out.track_pos[:, :1, :]
    assert torch.allclose(out.track_pos, first.expand_as(out.track_pos), atol=1e-6)


def test_scheduled_sampling_teacher_forcing_runs() -> None:
    """Teacher-forced forward (ss_prob=0 → always GT prev) produces valid finite output."""
    cfg = LearnedTrackerConfig(n_freq=128, n_lines=8, scheduled_sampling=True)
    trk = build_tracker(cfg)
    teacher = torch.rand(2, 9, cfg.n_lines)
    out = trk(torch.rand(2, 9, cfg.n_freq), teacher_pos=teacher, ss_prob=0.0)
    assert out.track_pos.shape == (2, 9, cfg.n_lines)
    assert torch.isfinite(out.track_pos).all()


def test_scheduled_sampling_gradients_reach_ss_delta() -> None:
    from odmr_vector_tracking.training.losses import compute_losses
    from odmr_vector_tracking.training.targets import association_targets

    cfg = LearnedTrackerConfig(n_freq=64, scheduled_sampling=True)
    trk = build_tracker(cfg)
    teacher = torch.rand(2, 6, cfg.n_lines)
    out = trk(torch.rand(2, 6, cfg.n_freq), teacher_pos=teacher, ss_prob=0.3)
    anchors = trk.extractor.get_buffer("anchors")
    res = torch.rand(2, 6, cfg.n_lines)
    tgt = association_targets(res, anchors)
    labels = torch.randn(2, 6, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 6, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)
    compute_losses(out, tgt, res, labels, coll, anchor_spacing=spacing)["total"].backward()
    assert trk.ss_delta.weight.grad is not None
    assert float(trk.ss_delta.weight.grad.abs().sum()) > 0


def test_scheduled_sampling_and_motion_prior_are_mutually_exclusive() -> None:
    with pytest.raises(ValueError):
        build_tracker(
            LearnedTrackerConfig(n_freq=128, motion_prior=True, scheduled_sampling=True)
        )


def test_plain_model_ignores_teacher_pos() -> None:
    """Without scheduled_sampling the teacher_pos/ss_prob args are inert (baseline unchanged)."""
    cfg = LearnedTrackerConfig(n_freq=128, scheduled_sampling=False)
    trk = build_tracker(cfg).eval()
    assert not hasattr(trk, "ss_delta")
    x = torch.rand(1, 5, cfg.n_freq)
    with torch.no_grad():
        base = trk(x)
        with_teacher = trk(x, teacher_pos=torch.rand(1, 5, cfg.n_lines), ss_prob=0.0)
    assert torch.allclose(base.track_pos, with_teacher.track_pos)


def test_tracked_freqs_are_the_state_posterior() -> None:
    """Claimed line centers = the state readout (MOT scores tracks, not raw detections)."""
    trk = build_tracker(CFG)
    out = trk(torch.rand(1, 3, CFG.n_freq))
    assert torch.allclose(out.tracked_freqs, out.track_pos)


def test_extractor_anchor_grid() -> None:
    """Anchors sit on conv receptive-field centers k*2^d/(F-1); zero-init offsets start there."""
    fe = FrameFeatureExtractor(REAL_CFG)
    anchors = fe.get_buffer("anchors")
    assert anchors.shape == (REAL_CFG.n_candidates,)
    expected = torch.arange(60, dtype=torch.float32) * 16.0 / 950.0
    assert torch.allclose(anchors, expected)
    assert float(anchors.min()) >= 0.0 and float(anchors.max()) <= 1.0

    feat, pos = fe(torch.rand(2, REAL_CFG.n_freq))
    assert feat.shape == (2, 60, REAL_CFG.feat_dim)
    assert pos.shape == (2, 60)
    # Offset head is zero-initialized: positions == anchors before training.
    assert torch.allclose(pos, anchors.expand(2, -1))


def test_research_variant_runs() -> None:
    trk = build_tracker(CFG, core="gated", association="attention")
    out = trk(torch.rand(2, 8, CFG.n_freq))
    assert out.b_est.shape == (2, 8, 3)
    # Attention head returns soft assignments summing to 1 over candidates.
    assert torch.allclose(out.scores.sum(dim=-1), torch.ones(2, 8, CFG.n_lines))


def test_build_tracker_validates_choices() -> None:
    with pytest.raises(ValueError):
        build_tracker(CFG, core="bogus")
    with pytest.raises(ValueError):
        build_tracker(CFG, association="bogus")


def test_only_extractor_is_v250_targeted() -> None:
    trk = build_tracker(CFG)
    v250 = v250_targeted_modules(trk)
    assert len(v250) == 1
    assert isinstance(v250[0], FrameFeatureExtractor)
    assert v250[0].EXECUTION_TARGET is ExecutionTarget.V250


@pytest.mark.parametrize("cfg", [CFG, REAL_CFG], ids=["f128", "f951-real"])
def test_extractor_passes_ops_guard(cfg: LearnedTrackerConfig) -> None:
    """The deployability contract: the V250-targeted extractor must be ops-compatible."""
    fe = FrameFeatureExtractor(cfg)
    report = check_model_ops(fe, input_shape=(1, cfg.n_freq))
    assert report.is_compatible, report.summary()


def test_deployable_host_blocks_are_ops_clean() -> None:
    """Host blocks carry no banned COMPUTE ops; their multi-input signatures are (correctly)
    flagged by the measured 2026-07-02 topology gate — they cannot be promoted to the V250
    as-is, which is exactly why they run on the host."""
    state = torch.randn(1, CFG.state_dim)
    obs = torch.randn(1, CFG.state_dim)
    rc = check_model_ops(ReLURecurrentCell(CFG), example_inputs=(state, obs))
    assert all("multi_graph_input" in d for d in rc.disallowed), rc.summary()

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    tpos = torch.rand(1, CFG.n_lines)
    cpos = torch.rand(1, CFG.n_candidates)
    la = check_model_ops(
        LinearScoreAssociation(CFG), example_inputs=(track, cand, tpos, cpos)
    )
    assert all("multi_graph_input" in d for d in la.disallowed), la.summary()


def test_research_blocks_are_flagged_off_npu() -> None:
    """Gated core + attention head must be flagged — they run on the host, not the V250.

    Measured rebaseline 2026-07-02: the gated core is flagged for its multi-input topology
    and internal mul (NOT sigmoid/tanh, which are supported); the attention head for matmul
    (softmax itself is supported)."""
    state = torch.randn(1, CFG.state_dim)
    obs = torch.randn(1, CFG.state_dim)
    gk = check_model_ops(GatedKalmanNetCore(CFG), example_inputs=(state, obs))
    assert not gk.is_compatible
    assert any("multi_graph_input" in d for d in gk.disallowed)
    assert "aten.mul" in gk.disallowed
    assert "aten.sigmoid" in gk.allowed and "aten.tanh" in gk.allowed

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    tpos = torch.rand(1, CFG.n_lines)
    cpos = torch.rand(1, CFG.n_candidates)
    at = check_model_ops(AttentionAssociation(CFG), example_inputs=(track, cand, tpos, cpos))
    assert not at.is_compatible
    assert "aten.matmul" in at.disallowed
    assert "aten.softmax" in at.allowed
