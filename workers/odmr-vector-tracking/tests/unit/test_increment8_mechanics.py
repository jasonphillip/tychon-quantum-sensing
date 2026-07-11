"""Unit tests for the increment-8 B+C-stack training mechanics.

Covers the training-only levers the dispatch-9 arms add — logit standardization, ensemble
response averaging, prob-target KD, weight-EMA, SAM, and shared-trunk branch/resume — plus the
invariant that the default training path (all levers off) is unchanged.
"""

from __future__ import annotations

import dataclasses

import torch
import torch.nn.functional as F

from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.training import TrainSettings, train
from odmr_vector_tracking.training.loop import SplitTensors, _WeightEMA, set_seed
from odmr_vector_tracking.training.losses import (
    compute_losses,
    ensemble_soft_targets,
    logit_standardize,
    prob_distillation_loss,
)
from odmr_vector_tracking.training.targets import association_targets


# --------------------------------------------------------------------------------------------
# logit standardization + ensemble averaging + prob-target KD (arXiv:2403.01427 / 2601.18909)
# --------------------------------------------------------------------------------------------

def test_logit_standardize_zero_mean_unit_std() -> None:
    x = torch.randn(3, 5, 7) * 4.0 + 2.0  # deliberately off-scale (mimics a wide teacher)
    z = logit_standardize(x)
    assert torch.allclose(z.mean(dim=-1), torch.zeros(3, 5), atol=1e-5)
    assert torch.allclose(z.std(dim=-1), torch.ones(3, 5), atol=1e-3)


def test_logit_standardize_invariant_to_affine_rescale() -> None:
    """Standardization removes exactly the teacher/student affine scale mismatch it targets."""
    x = torch.randn(2, 4, 6)
    assert torch.allclose(logit_standardize(x), logit_standardize(3.7 * x + 1.9), atol=1e-4)


def test_ensemble_single_teacher_equals_plain_softmax() -> None:
    logits = torch.randn(2, 4, 5)
    stacked = logits.unsqueeze(0)  # k=1
    got = ensemble_soft_targets(stacked, temperature=2.0, standardize=True)
    want = F.softmax(logit_standardize(logits) / 2.0, dim=-1)
    assert torch.allclose(got, want, atol=1e-6)


def test_ensemble_soft_targets_is_a_distribution_and_averages() -> None:
    stacked = torch.randn(5, 2, 3, 4)  # 5 teachers
    p = ensemble_soft_targets(stacked, temperature=2.0, standardize=True)
    assert p.shape == (2, 3, 4)
    assert torch.allclose(p.sum(dim=-1), torch.ones(2, 3), atol=1e-6)
    # equals the mean of the per-teacher standardized-softmax responses
    manual = F.softmax(logit_standardize(stacked) / 2.0, dim=-1).mean(dim=0)
    assert torch.allclose(p, manual, atol=1e-6)


def test_prob_distillation_zero_on_self_target() -> None:
    """KL(teacher‖student)=0 when the teacher target IS the student's standardized response."""
    student = torch.randn(2, 4, 6)
    teacher_prob = F.softmax(logit_standardize(student) / 2.0, dim=-1)
    loss = prob_distillation_loss(student, teacher_prob, temperature=2.0, standardize=True)
    assert float(loss) < 1e-6


def test_prob_distillation_nonneg_and_collision_upweighted() -> None:
    # slot 0 (out of collision): flat logits → matches the uniform teacher → KL≈0.
    # slot 1 (in collision): peaky logits → mismatched vs uniform teacher → KL high.
    student = torch.zeros(1, 2, 5)
    student[0, 1, 0] = 10.0
    teacher_prob = torch.full((1, 2, 5), 0.2)  # uniform target
    coll = torch.tensor([[False, True]])
    base = prob_distillation_loss(student, teacher_prob, line_collision=coll, collision_weight=1.0)
    up = prob_distillation_loss(student, teacher_prob, line_collision=coll, collision_weight=5.0)
    assert float(base) >= 0.0
    assert float(up) > float(base)  # upweighting the higher-KL in-collision slot raises the mean


def test_compute_losses_ensemble_path_precedence_and_blend() -> None:
    """teacher_prob takes precedence and blends as (1-alpha)*CE + alpha*KD; gradients flow."""
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg, core="gated", association="linear")
    spectra = torch.rand(2, 5, cfg.n_freq)
    out = trk(spectra)
    anchors = trk.extractor.get_buffer("anchors")
    res_norm = torch.rand(2, 5, cfg.n_lines)
    targets = association_targets(res_norm, anchors)
    labels = torch.randn(2, 5, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 5, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)
    tp = torch.full((2, 5, cfg.n_lines, cfg.n_candidates), 1.0 / cfg.n_candidates)

    base = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing)
    kd = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing,
                        teacher_prob=tp, ensemble_standardize=True, kd_alpha=0.5, kd_temp=2.0)
    # KD blend moved the association term off the pure-CE value
    assert not torch.allclose(base["association"], kd["association"], atol=1e-6)
    assert torch.isfinite(kd["total"])
    kd["total"].backward()
    assert trk.association.score.weight.grad is not None


def test_compute_losses_default_unchanged_by_new_kwargs() -> None:
    """No teacher_prob / kd_alpha=0 → association term identical to the pre-increment-8 call."""
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg)
    out = trk(torch.rand(2, 4, cfg.n_freq))
    anchors = trk.extractor.get_buffer("anchors")
    res_norm = torch.rand(2, 4, cfg.n_lines)
    targets = association_targets(res_norm, anchors)
    labels = torch.randn(2, 4, cfg.n_axes) * 0.3
    coll = torch.zeros(2, 4, cfg.n_lines, dtype=torch.bool)
    spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)
    a = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing)
    b = compute_losses(out, targets, res_norm, labels, coll, anchor_spacing=spacing,
                       teacher_prob=None, ensemble_standardize=True, kd_alpha=0.0)
    assert torch.allclose(a["total"], b["total"], atol=0.0)


# --------------------------------------------------------------------------------------------
# weight-EMA
# --------------------------------------------------------------------------------------------

def test_weight_ema_tracks_and_copies_buffers_exactly() -> None:
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg)
    ema = _WeightEMA(trk, decay=0.9)
    key = "state_to_proj.weight"
    before = ema.shadow[key].clone()
    with torch.no_grad():
        for p in trk.parameters():
            p.add_(torch.randn_like(p))  # move the live weights
    ema.update(trk)
    after = ema.shadow[key]
    live = trk.state_dict()[key]
    # float weight moved a fraction (1-decay) toward the live value
    assert not torch.allclose(after, before)
    assert torch.norm(after - before) < torch.norm(live - before)
    # non-float buffer (fixed anchor grid) copied exactly
    anc = "extractor.anchors"
    if anc in ema.shadow:
        assert torch.equal(ema.shadow[anc], trk.state_dict()[anc])
    # snapshot is a loadable state_dict
    trk.load_state_dict(ema.state_dict())


# --------------------------------------------------------------------------------------------
# training-loop smoke: every arm's code path runs and stays deployment-neutral
# --------------------------------------------------------------------------------------------

def _tiny_split(n: int, T: int, cfg: LearnedTrackerConfig, seed: int = 0) -> SplitTensors:
    g = torch.Generator().manual_seed(seed)
    K = cfg.n_candidates
    return SplitTensors(
        spectra=torch.rand(n, T, cfg.n_freq, generator=g),
        res_norm=torch.rand(n, T, cfg.n_lines, generator=g),
        assoc_targets=torch.randint(0, K, (n, T, cfg.n_lines), generator=g),
        proj_labels=torch.randn(n, T, cfg.n_axes, generator=g) * 0.2,
        line_collision=torch.zeros(n, T, cfg.n_lines, dtype=torch.bool),
    )


def _settings(**over) -> TrainSettings:
    base = dict(epochs=3, batch_size=2, patience=100, val_every=1, device="cpu",
                seed=0, noise_photons=None, log_every=100)
    base.update(over)
    return TrainSettings(**base)


def _params(trk) -> int:
    return sum(p.numel() for p in trk.parameters() if p.requires_grad)


def test_train_default_path_runs_and_is_deployment_neutral(tmp_path) -> None:
    cfg = LearnedTrackerConfig(n_freq=64)
    set_seed(0)
    trk = build_tracker(cfg, core="gated", association="linear")
    n0 = _params(trk)
    res = train(trk, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg), _settings(),
                out_dir=tmp_path / "base")
    assert res.epochs_run == 3
    assert (tmp_path / "base" / "best.pt").exists()
    assert not (tmp_path / "base" / "last.pt").exists()  # last.pt only for the trunk
    assert _params(trk) == n0  # shape untouched


def test_train_ensemble_kd_ema_runs(tmp_path) -> None:
    """bc arm: ensemble KD (2 teachers) + logit-std + EMA — runs and checkpoints EMA weights."""
    cfg = LearnedTrackerConfig(n_freq=64)
    set_seed(1)
    teachers = [build_tracker(cfg, core="gated", association="linear") for _ in range(2)]
    trk = build_tracker(cfg, core="gated", association="linear")
    s = _settings(ensemble_kd=True, logit_standardize=True, ema_decay=0.9,
                  kd_alpha=0.5, kd_temp=2.0)
    res = train(trk, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg), s,
                teachers=teachers, out_dir=tmp_path / "bc")
    assert res.epochs_run == 3 and (tmp_path / "bc" / "best.pt").exists()
    assert torch.isfinite(torch.tensor(res.best_val_total))


def test_train_sam_runs(tmp_path) -> None:
    cfg = LearnedTrackerConfig(n_freq=64)
    set_seed(2)
    teachers = [build_tracker(cfg, core="gated", association="linear") for _ in range(2)]
    trk = build_tracker(cfg, core="gated", association="linear")
    s = _settings(ensemble_kd=True, logit_standardize=True, ema_decay=0.9,
                  sam_rho=0.05, kd_alpha=0.5, kd_temp=2.0)
    res = train(trk, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg), s,
                teachers=teachers, out_dir=tmp_path / "sam")
    assert res.epochs_run == 3


def test_train_ensemble_kd_requires_teachers() -> None:
    cfg = LearnedTrackerConfig(n_freq=64)
    trk = build_tracker(cfg, core="gated", association="linear")
    try:
        train(trk, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg),
              _settings(ensemble_kd=True, kd_alpha=0.5))
    except ValueError:
        pass
    else:
        raise AssertionError("ensemble_kd without teachers must raise")


def test_trunk_writes_last_and_branch_resumes(tmp_path) -> None:
    """Trunk stops at stop_epoch and writes last.pt; a branch warm-started from it resumes on
    the same schedule and runs epochs start_epoch+1..epochs."""
    cfg = LearnedTrackerConfig(n_freq=64)
    set_seed(3)
    trk = build_tracker(cfg, core="gated", association="linear")
    # full-length schedule is 6 epochs; trunk stops at 2
    trunk_res = train(trk, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg),
                      _settings(epochs=6, stop_epoch=2), out_dir=tmp_path / "trunk")
    assert trunk_res.epochs_run == 2
    last = tmp_path / "trunk" / "last.pt"
    assert last.exists()

    # branch: warm-start from the trunk's last iterate, resume at epoch 3
    ck = torch.load(last, weights_only=False)
    set_seed(30)
    branch = build_tracker(cfg, core="gated", association="linear")
    branch.load_state_dict(ck["model_state"])
    br_res = train(branch, _tiny_split(4, 3, cfg), _tiny_split(2, 3, cfg),
                   _settings(epochs=6, start_epoch=2), out_dir=tmp_path / "branch")
    assert br_res.epochs_run == 6  # ran epochs 3..6


def test_default_settings_are_all_off() -> None:
    """The increment-8 knobs default to the neutral/off values (default path unchanged)."""
    s = TrainSettings()
    assert s.ensemble_kd is False and s.logit_standardize is False
    assert s.ema_decay == 0.0 and s.sam_rho == 0.0
    assert s.start_epoch == 0 and s.stop_epoch == 0
