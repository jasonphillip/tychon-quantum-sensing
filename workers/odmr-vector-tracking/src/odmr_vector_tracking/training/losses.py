"""Training losses for the learned tracker — pure tensor functions.

Three terms, all O(1)-normalized so unit weights are a sane starting point:

- :func:`association_loss` — per-slot K-way cross-entropy on the association scores, with
  ``line_collision``-flagged entries upweighted (the hard regime the thesis targets). Works on
  both head variants: raw logits (linear head → ``log_softmax``) and soft probabilities
  (attention head → ``log``). The softmax lives *here*, in loss machinery — it never joins the
  deployed graph, and the deployed hard assignment (argmax) is unchanged by it.
- :func:`position_loss` — Huber on the target-anchor candidate positions vs the true line
  centers, in units of the anchor spacing (so an error of one anchor cell ≈ 1.0).
- :func:`projection_loss` — MSE on the regressed axis projections vs the exact
  ``B_true · n_i`` labels (already in ``proj_scale_T`` units from
  :mod:`~odmr_vector_tracking.training.targets`).

:func:`compute_losses` aggregates the three into a weighted total.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from odmr_vector_tracking.tracking.learned import LearnedTrackerOutput

_EPS = 1e-9


def association_loss(
    scores: torch.Tensor,
    targets: torch.Tensor,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    scores_are_probs: bool = False,
    seq_weight: torch.Tensor | None = None,
) -> torch.Tensor:
    """Weighted cross-entropy between association scores and nearest-anchor targets.

    Parameters
    ----------
    scores
        ``(..., L, K)`` association-head output (logits, or probabilities summing to 1 over
        the last dim when ``scores_are_probs``).
    targets
        ``(..., L)`` long — target anchor index per line-slot.
    line_collision
        Optional ``(..., L)`` bool; flagged entries get ``collision_weight``, others 1.
    seq_weight
        Optional per-sequence multiplier broadcastable onto the ``(..., L)`` NLL — e.g.
        ``(B, 1, 1)`` for ``(B, T, L)`` — for increment-7 arm 7a's geometry-weighted
        ("foveated") identity loss. ``None`` (or a constant) leaves the result unchanged from
        the plain weighted mean (the per-sequence factor cancels in the normalized ratio when
        constant, so the default path is byte-identical).
    """
    if scores_are_probs:
        logp = torch.log(scores + _EPS)
    else:
        logp = F.log_softmax(scores, dim=-1)
    nll = -torch.gather(logp, -1, targets.unsqueeze(-1)).squeeze(-1)  # (..., L)
    if line_collision is None:
        return nll.mean() if seq_weight is None else (nll * seq_weight).mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(nll.dtype)
    if seq_weight is not None:
        w = w * seq_weight.to(nll.dtype)
    return (nll * w).sum() / w.sum()


def distillation_loss(
    student_scores: torch.Tensor,
    teacher_scores: torch.Tensor,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    temperature: float = 2.0,
    scores_are_probs: bool = False,
) -> torch.Tensor:
    """Temperature-scaled soft-target KD on the association head (increment-7 arm 7b).

    Hinton, Vinyals, Dean 2015 (arXiv:1503.02531): ``T² · KL(p_teacher^T ‖ p_student^T)`` where
    ``p^T = softmax(logits / T)``. The ``T²`` factor keeps the soft-target gradient scale
    comparable to the hard-CE gradient so the two mix cleanly. Same collision upweighting as the
    hard association loss. Training-only — the teacher never joins the deployed graph, and the
    student's inference (argmax over its own logits) is unchanged.

    ``teacher_scores`` are treated as constants (the caller detaches them / runs the teacher
    under ``no_grad``); the direction is KL(teacher ‖ student), so gradient flows into the
    student only.
    """
    t = float(temperature)
    if scores_are_probs:
        log_ps = torch.log(student_scores + _EPS)  # already probabilities; T-scaling N/A
        log_pt = torch.log(teacher_scores + _EPS)
    else:
        log_ps = F.log_softmax(student_scores / t, dim=-1)
        log_pt = F.log_softmax(teacher_scores / t, dim=-1)
    pt = log_pt.exp().detach()
    kl = (pt * (log_pt.detach() - log_ps)).sum(dim=-1)  # (..., L) KL(teacher ‖ student)
    kl = kl * (t * t)
    if line_collision is None:
        return kl.mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(kl.dtype)
    return (kl * w).sum() / w.sum()


def logit_standardize(logits: torch.Tensor, dim: int = -1, eps: float = 1e-7) -> torch.Tensor:
    """Per-sample z-score of ``logits`` along ``dim`` (increment-8 B+C stack; arXiv:2403.01427).

    ``(x − mean) / (std + eps)`` over the class dimension, so a teacher whose logits live on a
    ~4× wider scale than the student maps onto the same standardized range before the temperature
    softmax. Used **only inside the KD/KL soft-target term** (both teacher and student), never on
    the hard-CE term — the hard label objective is unchanged. Training-only; the deployed argmax
    over the student's own raw logits is unaffected.
    """
    mean = logits.mean(dim=dim, keepdim=True)
    std = logits.std(dim=dim, keepdim=True)
    return (logits - mean) / (std + eps)


def ensemble_soft_targets(
    teacher_scores: torch.Tensor,
    temperature: float = 2.0,
    standardize: bool = True,
) -> torch.Tensor:
    """Average ``k`` teachers' **response** distributions into one KD soft target (increment-8).

    ``teacher_scores`` is a stacked ``(k, ..., L, K)`` tensor of teacher association logits
    (detached upstream). Each teacher's logits are (optionally) logit-standardized, temperature-
    scaled, softmaxed to a probability, and the ``k`` probabilities are **averaged** (response
    averaging, not logit averaging). Averaging responses is what buys the O(1/k) inter-student
    variance reduction (arXiv:2601.18909) that increment-8 is testing. Returns ``(..., L, K)``.
    """
    t = float(temperature)
    z = logit_standardize(teacher_scores) if standardize else teacher_scores
    probs = F.softmax(z / t, dim=-1)          # (k, ..., L, K)
    return probs.mean(dim=0)                   # (..., L, K) averaged response


def prob_distillation_loss(
    student_scores: torch.Tensor,
    teacher_prob: torch.Tensor,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    temperature: float = 2.0,
    standardize: bool = True,
) -> torch.Tensor:
    """KD against a PRE-AVERAGED teacher target distribution (increment-8 ensemble path).

    ``teacher_prob`` is a ``(..., L, K)`` soft target (from :func:`ensemble_soft_targets`); the
    student logits are logit-standardized (``standardize``) the same way the teacher targets were
    built, then temperature-softmaxed, and matched by ``T² · KL(teacher ‖ student)``. The ``T²``
    factor keeps the soft-target gradient scale comparable to the hard CE. Same collision
    upweighting as the hard association loss. Training-only — teachers never join the deployed
    graph, and the student's inference argmax over its own raw logits is unchanged.
    """
    t = float(temperature)
    z = logit_standardize(student_scores) if standardize else student_scores
    log_ps = F.log_softmax(z / t, dim=-1)
    tp = teacher_prob.clamp_min(_EPS)
    kl = (tp * (tp.log() - log_ps)).sum(dim=-1) * (t * t)  # (..., L) KL(teacher ‖ student)
    if line_collision is None:
        return kl.mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(kl.dtype)
    return (kl * w).sum() / w.sum()


def soft_association_loss(
    scores: torch.Tensor,
    target_dist: torch.Tensor,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    scores_are_probs: bool = False,
) -> torch.Tensor:
    """Soft cross-entropy ``−Σ_k p_target · log p_pred`` (2c lever 1).

    Same weighting and score-vs-prob handling as :func:`association_loss`, but the target is a
    full ``(..., L, K)`` distribution (from
    :func:`~odmr_vector_tracking.training.targets.soft_association_targets`) instead of a hard
    index. When ``target_dist`` is one-hot this is *identical* to :func:`association_loss`, so
    out-of-collision slots are supervised exactly as before; only in-collision slots see split
    mass.

    Parameters
    ----------
    scores
        ``(..., L, K)`` association-head output (logits, or probabilities when
        ``scores_are_probs``).
    target_dist
        ``(..., L, K)`` target distributions summing to 1 over the last axis.
    line_collision
        Optional ``(..., L)`` bool; flagged entries get ``collision_weight``, others 1.
    """
    if scores_are_probs:
        logp = torch.log(scores + _EPS)
    else:
        logp = F.log_softmax(scores, dim=-1)
    ce = -(target_dist * logp).sum(dim=-1)  # (..., L) soft cross-entropy
    if line_collision is None:
        return ce.mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(ce.dtype)
    return (ce * w).sum() / w.sum()


def log_sinkhorn(
    scores: torch.Tensor, n_iters: int = 20, dustbin_score: float = 1.0
) -> torch.Tensor:
    """Log-domain Sinkhorn / entropic optimal transport over a line×candidate score matrix.

    Augments ``scores (..., L, K)`` with a learnable-free **dustbin** row and column (filled
    with ``dustbin_score``) so unmatched candidates (K ≫ L spares) drain into the dustbin row
    and coasting/occluded lines drain into the dustbin column, then runs ``n_iters`` log-space
    Sinkhorn iterations toward the marginals ``μ = [1]*L ⊕ [K]``, ``ν = [1]*K ⊕ [L]`` (total
    mass L+K, SuperGlue convention, arXiv:1911.11763). The result is a doubly-stochastic-ish
    log-assignment: column mass is conserved, so two line-rows **cannot** both claim one
    candidate — mutual exclusivity is expressed by the transport, not bolted on.

    Returns ``(..., L+1, K+1)`` log-probabilities (``exp`` sums to 1 over the full matrix).
    Off-graph / training-only: inference assignment stays the exact one-to-one Hungarian/greedy.
    """
    *lead, n_lines, n_cand = scores.shape
    flat = scores.reshape(-1, n_lines, n_cand)
    m = flat.shape[0]
    device = flat.device
    dtype = flat.dtype
    d = torch.as_tensor(float(dustbin_score), device=device, dtype=dtype)
    row = d.expand(m, n_lines, 1)
    col = d.expand(m, 1, n_cand + 1)
    aug = torch.cat([torch.cat([flat, row], dim=-1), col], dim=1)  # (m, L+1, K+1)

    log_l = torch.log(torch.as_tensor(float(n_lines), device=device, dtype=dtype))
    log_k = torch.log(torch.as_tensor(float(n_cand), device=device, dtype=dtype))
    norm = torch.log(torch.as_tensor(float(n_lines + n_cand), device=device, dtype=dtype))
    log_mu = torch.cat([torch.zeros(n_lines, device=device, dtype=dtype), log_k[None]]) - norm
    log_nu = torch.cat([torch.zeros(n_cand, device=device, dtype=dtype), log_l[None]]) - norm
    log_mu = log_mu.expand(m, -1)  # (m, L+1)
    log_nu = log_nu.expand(m, -1)  # (m, K+1)

    u = torch.zeros(m, n_lines + 1, device=device, dtype=dtype)
    v = torch.zeros(m, n_cand + 1, device=device, dtype=dtype)
    for _ in range(int(n_iters)):
        u = log_mu - torch.logsumexp(aug + v.unsqueeze(1), dim=2)
        v = log_nu - torch.logsumexp(aug + u.unsqueeze(2), dim=1)
    log_p = aug + u.unsqueeze(2) + v.unsqueeze(1)
    return log_p.reshape(*lead, n_lines + 1, n_cand + 1)


def sinkhorn_assignment_loss(
    scores: torch.Tensor,
    targets: torch.Tensor | None = None,
    target_dist: torch.Tensor | None = None,
    line_collision: torch.Tensor | None = None,
    collision_weight: float = 5.0,
    n_iters: int = 20,
    dustbin_score: float = 1.0,
    scores_are_probs: bool = False,
) -> torch.Tensor:
    """One-to-one assignment loss via log-Sinkhorn, replacing independent per-slot CE (lever 2).

    Normalizes ``scores (..., L, K)`` with :func:`log_sinkhorn`, forms the per-line conditional
    over ``K`` candidates + dustbin, and cross-entropy-matches it to the GT assignment. Because
    the Sinkhorn transport conserves candidate-column mass, the loss *learns* mutual exclusivity
    — two lines are pushed onto distinct candidates during training — so no hard exclusivity
    gate is needed at inference (Hungarian there is unchanged). Accepts either a hard
    ``targets (..., L)`` index or a soft ``target_dist (..., L, K)`` (composes with lever 1).
    """
    if (targets is None) == (target_dist is None):
        raise ValueError("pass exactly one of targets / target_dist")
    if scores_are_probs:
        scores = torch.log(scores + _EPS)  # Sinkhorn runs on log-scores
    n_cand = int(scores.shape[-1])
    log_p = log_sinkhorn(scores, n_iters=n_iters, dustbin_score=dustbin_score)
    line_rows = log_p[..., : scores.shape[-2], :]  # (..., L, K+1) drop the dustbin row
    log_cond = line_rows - torch.logsumexp(line_rows, dim=-1, keepdim=True)  # per-line dist
    if target_dist is None:
        assert targets is not None
        target_dist = F.one_hot(targets, num_classes=n_cand).to(scores.dtype)  # (..., L, K)
    tgt = F.pad(target_dist, (0, 1))  # (..., L, K+1): present lines put 0 mass on the dustbin
    ce = -(tgt * log_cond).sum(dim=-1)  # (..., L)
    if line_collision is None:
        return ce.mean()
    w = 1.0 + (float(collision_weight) - 1.0) * line_collision.to(ce.dtype)
    return (ce * w).sum() / w.sum()


def position_loss(
    cand_pos: torch.Tensor,
    targets: torch.Tensor,
    res_norm: torch.Tensor,
    anchor_spacing: float,
) -> torch.Tensor:
    """Huber loss on target-anchor candidate positions vs true line centers.

    Gathers each line's *target* anchor position from ``cand_pos`` (differentiable through the
    offset head) and penalizes its distance to the true center, scaled by ``anchor_spacing`` so
    the residual is in anchor-cell units (Huber ``delta = 1`` → quadratic within one cell).

    Parameters
    ----------
    cand_pos
        ``(..., K)`` candidate positions (normalized window units).
    targets
        ``(..., L)`` long — target anchor per line (from :func:`association_targets`).
    res_norm
        ``(..., L)`` true line centers (normalized window units).
    anchor_spacing
        Anchor pitch in normalized units: ``2**n_downsample / (n_freq - 1)``.
    """
    pred = torch.gather(cand_pos, -1, targets)  # (..., L)
    residual = (pred - res_norm) / float(anchor_spacing)
    return F.smooth_l1_loss(residual, torch.zeros_like(residual))


def track_position_loss(
    track_pos: torch.Tensor, res_norm: torch.Tensor, anchor_spacing: float
) -> torch.Tensor:
    """Huber on the state's per-slot predicted line positions vs the true centers.

    This is the direct per-slot supervision of the recurrent state (KalmanNet flavor: the
    state predicts where each identity's line sits); the association's distance branch then
    scores candidates against these predictions. Same anchor-cell scaling as
    :func:`position_loss`.
    """
    residual = (track_pos - res_norm) / float(anchor_spacing)
    return F.smooth_l1_loss(residual, torch.zeros_like(residual))


def projection_loss(projections: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
    """MSE between regressed projections and exact ``B_true · n_i`` labels (scaled units)."""
    return F.mse_loss(projections, labels)


def compute_losses(
    output: LearnedTrackerOutput,
    assoc_targets: torch.Tensor,
    res_norm: torch.Tensor,
    proj_labels: torch.Tensor,
    line_collision: torch.Tensor | None,
    *,
    anchor_spacing: float,
    collision_weight: float = 5.0,
    w_assoc: float = 1.0,
    w_pos: float = 1.0,
    w_track: float = 1.0,
    w_proj: float = 1.0,
    scores_are_probs: bool = False,
    assoc_soft_targets: torch.Tensor | None = None,
    sinkhorn: bool = False,
    sinkhorn_iters: int = 20,
    sinkhorn_dustbin: float = 1.0,
    assoc_seq_weight: torch.Tensor | None = None,
    teacher_scores: torch.Tensor | None = None,
    teacher_prob: torch.Tensor | None = None,
    ensemble_standardize: bool = False,
    kd_alpha: float = 0.0,
    kd_temp: float = 2.0,
) -> dict[str, torch.Tensor]:
    """All four losses + weighted total for one forward pass over ``(B, T, ...)`` batches.

    Returns ``{"association", "position", "track_position", "projection", "total"}`` scalar
    tensors.

    Association-term levers (all training-only; inference assignment is unchanged):

    - ``assoc_soft_targets`` (2c lever 1): a ``(..., L, K)`` distribution supervising the CE via
      :func:`soft_association_loss` instead of the hard ``assoc_targets``.
    - ``sinkhorn`` (2c lever 2): replace the independent per-slot CE with
      :func:`sinkhorn_assignment_loss` (one-to-one transport), using the soft targets when
      lever 1 is also on, else the hard ``assoc_targets``.
    - ``assoc_seq_weight`` (increment-7 arm 7a): per-sequence geometry ("foveated") multiplier on
      the association term. ``None`` = unchanged.
    - ``teacher_scores`` + ``kd_alpha`` + ``kd_temp`` (increment-7 arm 7b, kd1): blend the hard
      association CE with the temperature-scaled single-teacher KD term
      ``(1−α)·CE + α·distillation_loss``. ``teacher_scores=None`` or ``kd_alpha=0`` = unchanged.
    - ``teacher_prob`` + ``ensemble_standardize`` (increment-8 bc/bc_sam): blend the hard CE with
      the ensemble KD term against a pre-averaged soft target via :func:`prob_distillation_loss`
      (student logits logit-standardized iff ``ensemble_standardize``). Takes precedence over
      ``teacher_scores`` when both are passed; ``teacher_prob=None`` = unchanged.

    Position supervision always gathers the hard nearest-anchor ``assoc_targets`` (the anchor a
    line's offset must refine toward is unambiguous even when its *identity* is not), so the
    levers touch only the association term.
    """
    if sinkhorn:
        assoc = sinkhorn_assignment_loss(
            output.scores,
            targets=None if assoc_soft_targets is not None else assoc_targets,
            target_dist=assoc_soft_targets,
            line_collision=line_collision,
            collision_weight=collision_weight,
            n_iters=sinkhorn_iters,
            dustbin_score=sinkhorn_dustbin,
            scores_are_probs=scores_are_probs,
        )
    elif assoc_soft_targets is None:
        assoc = association_loss(
            output.scores,
            assoc_targets,
            line_collision=line_collision,
            collision_weight=collision_weight,
            scores_are_probs=scores_are_probs,
            seq_weight=assoc_seq_weight,
        )
    else:
        assoc = soft_association_loss(
            output.scores,
            assoc_soft_targets,
            line_collision=line_collision,
            collision_weight=collision_weight,
            scores_are_probs=scores_are_probs,
        )
    if teacher_prob is not None and kd_alpha > 0.0:
        kd = prob_distillation_loss(
            output.scores,
            teacher_prob,
            line_collision=line_collision,
            collision_weight=collision_weight,
            temperature=kd_temp,
            standardize=ensemble_standardize,
        )
        assoc = (1.0 - float(kd_alpha)) * assoc + float(kd_alpha) * kd
    elif teacher_scores is not None and kd_alpha > 0.0:
        kd = distillation_loss(
            output.scores,
            teacher_scores,
            line_collision=line_collision,
            collision_weight=collision_weight,
            temperature=kd_temp,
            scores_are_probs=scores_are_probs,
        )
        assoc = (1.0 - float(kd_alpha)) * assoc + float(kd_alpha) * kd
    pos = position_loss(output.cand_pos, assoc_targets, res_norm, anchor_spacing)
    track = track_position_loss(output.track_pos, res_norm, anchor_spacing)
    proj = projection_loss(output.projections, proj_labels)
    total = w_assoc * assoc + w_pos * pos + w_track * track + w_proj * proj
    return {
        "association": assoc,
        "position": pos,
        "track_position": track,
        "projection": proj,
        "total": total,
    }
