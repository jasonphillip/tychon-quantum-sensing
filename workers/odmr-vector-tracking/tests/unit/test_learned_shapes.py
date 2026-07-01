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


def test_forward_output_shapes() -> None:
    trk = build_tracker(CFG, core="relu", association="linear")
    B, T, L, K = 2, 12, CFG.n_lines, CFG.n_candidates
    out = trk(torch.rand(B, T, CFG.n_freq))
    assert out.b_est.shape == (B, T, 3)
    assert out.assignment.shape == (B, T, L)
    assert out.covariance.shape == (B, T, 3, 3)
    assert out.scores.shape == (B, T, L, K)
    assert out.projections.shape == (B, T, CFG.n_axes)
    assert out.cand_pos.shape == (B, T, K)
    assert out.track_pos.shape == (B, T, L)
    assert out.tracked_freqs.shape == (B, T, L)
    assert out.assignment.dtype == torch.long


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
    state = torch.randn(1, CFG.state_dim)
    obs = torch.randn(1, CFG.state_dim)
    rc = check_model_ops(ReLURecurrentCell(CFG), example_inputs=(state, obs))
    assert rc.is_compatible

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    tpos = torch.rand(1, CFG.n_lines)
    cpos = torch.rand(1, CFG.n_candidates)
    la = check_model_ops(
        LinearScoreAssociation(CFG), example_inputs=(track, cand, tpos, cpos)
    )
    assert la.is_compatible


def test_research_blocks_are_flagged_off_npu() -> None:
    """Gated core + attention head must be flagged — they run on the host, not the V250."""
    state = torch.randn(1, CFG.state_dim)
    obs = torch.randn(1, CFG.state_dim)
    gk = check_model_ops(GatedKalmanNetCore(CFG), example_inputs=(state, obs))
    assert not gk.is_compatible
    assert "aten.sigmoid" in gk.disallowed and "aten.tanh" in gk.disallowed

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    tpos = torch.rand(1, CFG.n_lines)
    cpos = torch.rand(1, CFG.n_candidates)
    at = check_model_ops(AttentionAssociation(CFG), example_inputs=(track, cand, tpos, cpos))
    assert not at.is_compatible
    assert "aten.matmul" in at.disallowed and "aten.softmax" in at.disallowed
