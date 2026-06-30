"""Unit tests for the learned-tracker skeleton: shapes + the V250/MSS deployability boundary."""

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


def test_forward_output_shapes() -> None:
    trk = build_tracker(CFG, core="relu", association="linear")
    B, T = 2, 12
    out = trk(torch.randn(B, T, CFG.n_freq))
    assert out.b_est.shape == (B, T, 3)
    assert out.assignment.shape == (B, T, CFG.n_lines)
    assert out.covariance.shape == (B, T, 3, 3)
    assert out.assignment.dtype == torch.long


def test_research_variant_runs() -> None:
    trk = build_tracker(CFG, core="gated", association="attention")
    out = trk(torch.randn(2, 8, CFG.n_freq))
    assert out.b_est.shape == (2, 8, 3)


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


def test_extractor_passes_ops_guard() -> None:
    """The deployability contract: the V250-targeted extractor must be ops-compatible."""
    fe = FrameFeatureExtractor(CFG)
    report = check_model_ops(fe, input_shape=(1, CFG.n_freq))
    assert report.is_compatible, report.summary()


def test_deployable_host_blocks_are_ops_clean() -> None:
    state = torch.randn(1, CFG.state_dim)
    feat = torch.randn(1, CFG.feat_dim)
    rc = check_model_ops(ReLURecurrentCell(CFG), example_inputs=(state, feat))
    assert rc.is_compatible

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    la = check_model_ops(LinearScoreAssociation(CFG), example_inputs=(track, cand))
    assert la.is_compatible


def test_research_blocks_are_flagged_off_npu() -> None:
    """Gated core + attention head must be flagged — they run on the host, not the V250."""
    state = torch.randn(1, CFG.state_dim)
    feat = torch.randn(1, CFG.feat_dim)
    gk = check_model_ops(GatedKalmanNetCore(CFG), example_inputs=(state, feat))
    assert not gk.is_compatible
    assert "aten.sigmoid" in gk.disallowed and "aten.tanh" in gk.disallowed

    track = torch.randn(1, CFG.n_lines, CFG.feat_dim)
    cand = torch.randn(1, CFG.n_candidates, CFG.feat_dim)
    at = check_model_ops(AttentionAssociation(CFG), example_inputs=(track, cand))
    assert not at.is_compatible
    assert "aten.matmul" in at.disallowed and "aten.softmax" in at.disallowed
