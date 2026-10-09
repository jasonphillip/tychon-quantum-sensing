"""Training loop for the learned tracker: full-BPTT epochs, early stopping, checkpointing.

The tracker is a pure observation-driven filter (state consumes only current-frame candidate
features, never its own outputs), so training is plain full-sequence BPTT — no teacher forcing
or scheduled sampling is needed (there is no exposure bias to correct), and no curriculum at
sanity scale (a single scenario family). See ``docs/design/02_approach_and_testbed.md``.

Model selection: early stopping on the **validation total loss** with a patience window; the
best-validation weights are restored into the tracker and checkpointed. The per-epoch
``assoc_acc*`` numbers logged here are *anchor-level* proxies (predicted anchor index vs target
anchor index) for monitoring only — the reportable physical metrics (association accuracy via
``resolve_true_axis``, ID switches, angular error, dynamic range) come from
``evaluation/metrics.py`` at evaluation time.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import torch

from odmr_vector_tracking.data.loaders import SequenceDataset
from odmr_vector_tracking.tracking.learned import LearnedTracker, LearnedTrackerOutput
from odmr_vector_tracking.training.losses import compute_losses, ensemble_soft_targets
from odmr_vector_tracking.training.targets import (
    association_targets,
    normalize_freqs,
    projection_labels,
    soft_association_targets,
)


@dataclass
class TrainSettings:
    """Optimization hyperparameters (defaults = the approved Increment-2a design)."""

    lr: float = 1.0e-3
    weight_decay: float = 1.0e-4
    epochs: int = 2000
    batch_size: int = 16
    patience: int = 200          # early-stop epochs without val-total improvement
    grad_clip: float = 1.0
    collision_weight: float = 5.0
    w_assoc: float = 1.0
    w_pos: float = 1.0
    w_track: float = 1.0
    w_proj: float = 1.0
    seed: int = 20260701
    device: str = "cuda"
    log_every: int = 25
    val_every: int = 1           # evaluate val split every N epochs (early-stop bookkeeping
                                 # happens only on evaluated epochs; >1 for large val splits)
    # --- 2c association levers (all training-only; inference assignment unchanged) ---
    soft_targets: bool = False          # lever 1: soft/merged CE targets in the ambiguity
                                        # radius (soft_radius_linewidths · Γ)
    soft_radius_linewidths: float = 1.0  # ambiguity radius in linewidths (matches k=1 collision)
    sinkhorn: bool = False              # lever 2: log-Sinkhorn one-to-one assignment loss
    sinkhorn_iters: int = 20
    sinkhorn_dustbin: float = 1.0
    scheduled_sampling: bool = False    # lever 3: ramp model-own previous-position feedback
    ss_final_prob: float = 0.5          # peak P(use model-own prev) at the end of the ramp
    ss_ramp_frac: float = 1.0           # ramp reaches ss_final_prob at this fraction of epochs
    # --- increment-7 training-signal arms (all training-only; deployed graph unchanged) ---
    foveated: bool = False              # arm 7a: geometry-weighted identity loss (per-seq
                                        # assoc weight supplied via SplitTensors.assoc_seq_weight)
    distill: bool = False               # arm 7b: knowledge distillation from an FP32 teacher
                                        # (teacher passed to train(); students byte-identical)
    kd_alpha: float = 0.5               # arm 7b: hard-CE / soft-KD blend, assoc = (1−α)CE + α·KD
    kd_temp: float = 2.0                # arm 7b: KD softmax temperature (Hinton 2015)
    pcgrad: bool = False                # arm 7c: project conflicting field/identity gradients
    # --- increment-8 B+C reliability stack (all training-only; deployed graph unchanged) ---
    ensemble_kd: bool = False           # bc/bc_sam: distill from AVERAGED multi-teacher soft
                                        # targets (a list of teachers is passed to train()); the
                                        # per-teacher responses are averaged (ensemble_soft_targets)
    logit_standardize: bool = False     # bc/bc_sam: z-score logits inside the KD/KL term only
                                        # (teacher + student), repairing the ~4x scale mismatch
                                        # (2403.01427); hard-CE term unchanged
    ema_decay: float = 0.0              # bc/bc_sam: weight-EMA decay (>0 enables). The EMA
                                        # weights are evaluated for early-stopping AND become the
                                        # deployed candidate (2411.18704 churn reduction)
    sam_rho: float = 0.0                # bc_sam only: SAM neighborhood radius (>0 enables; ~2x
                                        # step cost) — flat-minima trajectory control (2010.01412)
    start_epoch: int = 0               # shared-trunk branch: warm-started students resume at
                                        # start_epoch+1 on the SAME cosine schedule (1912.05671)
    stop_epoch: int = 0                # 0 = run to `epochs`; >0 stops early at this epoch on the
                                        # full-length cosine (used to train the shared trunk)
    noise_photons: float | None = None
    # Photon budget (photons/point) for per-epoch shot-noise augmentation of the TRAIN split:
    # a fresh Gaussian realization each epoch with sigma from the upstream physics model
    # (nv_sensor_sim.physics.shot_noise.shot_noise_sigma; sigma computed once on the clean
    # spectra, noise drawn on-device). None = no augmentation. The VAL split is NOT noised
    # here - the caller supplies a fixed noisy realization so early stopping is stable.


@dataclass
class SplitTensors:
    """One split's training tensors, resident on the training device."""

    spectra: torch.Tensor        # (N, T, F) float32
    res_norm: torch.Tensor       # (N, T, L) float32 — GT centers, normalized window units
    assoc_targets: torch.Tensor  # (N, T, L) long — nearest-anchor index per line
    proj_labels: torch.Tensor    # (N, T, 4) float32 — B_true·n_i in proj_scale_T units
    line_collision: torch.Tensor  # (N, T, L) bool
    assoc_seq_weight: torch.Tensor | None = None  # (N,) increment-7 arm 7a foveated multiplier;
                                                  # None = plain association weighting (default)

    @property
    def n_sequences(self) -> int:
        return int(self.spectra.shape[0])


def set_seed(seed: int) -> None:
    """Seed torch / numpy / random (soft determinism; no cudnn hard-determinism flags)."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)


def build_split_tensors(
    ds: SequenceDataset,
    anchors: torch.Tensor,
    freq_range_hz: tuple[float, float],
    proj_scale_T: float,
    device: torch.device | str,
    assoc_seq_weight: np.ndarray | None = None,
) -> SplitTensors:
    """Precompute all supervision targets for a split and move everything to ``device``.

    Anchors are fixed (non-learned) buffers, so targets never change during training.

    ``assoc_seq_weight`` (increment-7 arm 7a) is an optional per-sequence ``(N,)`` multiplier on
    the association loss; stored reshaped to ``(N, 1, 1)`` so it broadcasts onto the ``(N, T, L)``
    NLL. ``None`` leaves the association term unweighted (default).
    """
    spectra = torch.from_numpy(np.ascontiguousarray(ds.spectra)).float()
    res_hz = torch.from_numpy(np.ascontiguousarray(ds.resonance_freqs)).float()
    b_true = torch.from_numpy(np.ascontiguousarray(ds.B_true)).float()
    lcoll = torch.from_numpy(np.ascontiguousarray(ds.line_collision)).bool()

    res_norm = normalize_freqs(res_hz, freq_range_hz)
    targets = association_targets(res_norm, anchors.cpu())
    labels = projection_labels(b_true, proj_scale_T)

    sw = None
    if assoc_seq_weight is not None:
        sw = torch.from_numpy(
            np.ascontiguousarray(assoc_seq_weight, dtype=np.float32)
        ).reshape(-1, 1, 1).to(device)

    return SplitTensors(
        spectra=spectra.to(device),
        res_norm=res_norm.to(device),
        assoc_targets=targets.to(device),
        proj_labels=labels.to(device),
        line_collision=lcoll.to(device),
        assoc_seq_weight=sw,
    )


def anchor_assoc_accuracy(
    scores: torch.Tensor, targets: torch.Tensor, line_collision: torch.Tensor
) -> dict[str, float]:
    """Anchor-level association accuracy (monitoring proxy, not the physical metric)."""
    pred = scores.argmax(dim=-1)
    correct = (pred == targets).float()
    mask = line_collision.bool()
    out = {"assoc_acc": float(correct.mean())}
    out["assoc_acc_in_coll"] = float(correct[mask].mean()) if mask.any() else float("nan")
    out["assoc_acc_out_coll"] = (
        float(correct[~mask].mean()) if (~mask).any() else float("nan")
    )
    return out


def _split_losses(
    tracker: LearnedTracker,
    tensors: SplitTensors,
    settings: TrainSettings,
    anchor_spacing: float,
    scores_are_probs: bool,
    indices: torch.Tensor | None = None,
    *,
    soft_radius_norm: float | None = None,
    ss_prob: float = 1.0,
    teacher_force: bool = False,
    teachers: list[LearnedTracker] | None = None,
) -> tuple[dict[str, torch.Tensor], LearnedTrackerOutput]:
    """Forward one batch (or the whole split) and compute the loss dict.

    ``teacher_force`` (with a scheduled-sampling model) feeds the split's ground-truth centers
    as the teacher signal at probability ``1 − ss_prob``; ``teacher_force=False`` runs
    free-running (the honest val / inference condition). ``soft_radius_norm`` (lever 1) enables
    the soft/merged CE targets, built per batch from the ground-truth centers.

    ``teachers`` are distillation teachers run on the SAME (possibly noised) ``spectra`` under
    ``no_grad``, only on the TRAIN call — val/early-stopping stays the honest hard-CE metric.
    With ``settings.ensemble_kd`` (increment-8 bc) all teachers' responses are averaged into one
    soft target; otherwise (``settings.distill``, increment-7 kd1) the first teacher's raw scores
    are the KD target.
    """
    if indices is None:
        sl = slice(None)
        spectra = tensors.spectra
    else:
        sl = indices
        spectra = tensors.spectra[indices]

    res_norm = tensors.res_norm[sl]
    teacher_pos = (
        res_norm if (teacher_force and tracker.cfg.scheduled_sampling) else None
    )
    out = tracker(spectra, teacher_pos=teacher_pos, ss_prob=ss_prob)

    assoc_soft = None
    if settings.soft_targets and soft_radius_norm is not None:
        anchors = tracker.extractor.get_buffer("anchors")
        assoc_soft = soft_association_targets(
            res_norm, anchors, radius=soft_radius_norm, hard_targets=tensors.assoc_targets[sl]
        )

    teacher_scores = None
    teacher_prob = None
    if teachers:
        if settings.ensemble_kd:
            with torch.no_grad():
                stacked = torch.stack([t(spectra).scores.detach() for t in teachers], dim=0)
            teacher_prob = ensemble_soft_targets(
                stacked, temperature=settings.kd_temp, standardize=settings.logit_standardize
            )
        elif settings.distill:
            with torch.no_grad():
                teacher_scores = teachers[0](spectra).scores.detach()

    seq_w = None if tensors.assoc_seq_weight is None else tensors.assoc_seq_weight[sl]

    kd_on = settings.distill or settings.ensemble_kd
    losses = compute_losses(
        out,
        tensors.assoc_targets[sl],
        res_norm,
        tensors.proj_labels[sl],
        tensors.line_collision[sl],
        anchor_spacing=anchor_spacing,
        collision_weight=settings.collision_weight,
        w_assoc=settings.w_assoc,
        w_pos=settings.w_pos,
        w_track=settings.w_track,
        w_proj=settings.w_proj,
        scores_are_probs=scores_are_probs,
        assoc_soft_targets=assoc_soft,
        sinkhorn=settings.sinkhorn,
        sinkhorn_iters=settings.sinkhorn_iters,
        sinkhorn_dustbin=settings.sinkhorn_dustbin,
        assoc_seq_weight=seq_w,
        teacher_scores=teacher_scores,
        teacher_prob=teacher_prob,
        ensemble_standardize=settings.logit_standardize,
        kd_alpha=(settings.kd_alpha if kd_on else 0.0),
        kd_temp=settings.kd_temp,
    )
    return losses, out


def _pcgrad_backward(
    losses: dict[str, torch.Tensor],
    params: list[torch.Tensor],
    settings: TrainSettings,
) -> None:
    """Arm 7c — PCGrad (Yu et al. 2020) two-task gradient surgery, writing ``param.grad``.

    Tasks: **identity** (``w_assoc·association``) vs **field** (``w_proj·projection``); the shared
    position/track supervision is added plain. If the two task gradients conflict (negative inner
    product) each is projected onto the other's normal plane before summing, so a wide-angle-lock
    update and an in-cone-identity update stop overwriting each other. Reduces exactly to
    ``total.backward()`` when the gradients don't conflict. Deployment-neutral — this is optimizer
    math, never in the exported graph.
    """
    l_id = settings.w_assoc * losses["association"]
    l_field = settings.w_proj * losses["projection"]
    l_shared = settings.w_pos * losses["position"] + settings.w_track * losses["track_position"]

    def flat(grads: tuple[torch.Tensor | None, ...]) -> torch.Tensor:
        return torch.cat([
            (g if g is not None else torch.zeros_like(p)).reshape(-1)
            for g, p in zip(grads, params)
        ])

    g_id = flat(torch.autograd.grad(l_id, params, retain_graph=True, allow_unused=True))
    g_field = flat(torch.autograd.grad(l_field, params, retain_graph=True, allow_unused=True))
    g_shared = flat(torch.autograd.grad(l_shared, params, retain_graph=False, allow_unused=True))

    dot = torch.dot(g_id, g_field)
    if float(dot) < 0.0:
        g_id_p = g_id - (dot / (g_field.dot(g_field) + 1e-12)) * g_field
        g_field_p = g_field - (dot / (g_id.dot(g_id) + 1e-12)) * g_id
    else:
        g_id_p, g_field_p = g_id, g_field
    g_total = g_id_p + g_field_p + g_shared

    off = 0
    for p in params:
        num = p.numel()
        p.grad = g_total[off:off + num].view_as(p).clone()
        off += num


class _WeightEMA:
    """Exponential moving average of a tracker's state_dict (increment-8 bc/bc_sam).

    Updated once per optimizer step. Floating-point tensors decay toward the live weights;
    non-float buffers (e.g. the fixed anchor grid) are copied exactly so the EMA snapshot is a
    loadable, self-consistent state_dict. The EMA weights are what gets evaluated for early
    stopping and checkpointed as the deployed candidate — the whole point of the lever is to
    deploy a lower-variance running average, not the last noisy SGD iterate (arXiv:2411.18704).
    """

    def __init__(self, tracker: LearnedTracker, decay: float) -> None:
        self.decay = float(decay)
        self.shadow = {k: v.detach().clone() for k, v in tracker.state_dict().items()}

    @torch.no_grad()
    def update(self, tracker: LearnedTracker) -> None:
        d = self.decay
        for k, v in tracker.state_dict().items():
            s = self.shadow[k]
            if torch.is_floating_point(v):
                s.mul_(d).add_(v.detach(), alpha=1.0 - d)
            else:
                s.copy_(v.detach())

    def state_dict(self) -> dict[str, torch.Tensor]:
        return {k: v.clone() for k, v in self.shadow.items()}


@dataclass
class TrainResult:
    """Outcome of :func:`train` — best-val weights are already restored into the tracker."""

    best_epoch: int
    best_val_total: float
    epochs_run: int
    wall_s: float
    history: list[dict] = field(default_factory=list)
    checkpoint_path: Path | None = None


def train(
    tracker: LearnedTracker,
    train_tensors: SplitTensors,
    val_tensors: SplitTensors,
    settings: TrainSettings,
    *,
    scores_are_probs: bool = False,
    soft_radius_norm: float | None = None,
    out_dir: Path | str | None = None,
    ckpt_meta: dict | None = None,
    teacher: LearnedTracker | None = None,
    teachers: list[LearnedTracker] | None = None,
    log: Callable[[str], None] = print,
) -> TrainResult:
    """Train with full-BPTT minibatches; early-stop and checkpoint on best val total loss.

    ``ckpt_meta`` (e.g. ``{"core": "relu", "association": "linear"}``) is embedded in the
    checkpoint alongside the model config so evaluation can rebuild the exact variant.

    Increment-8 B+C stack (all opt-in via ``settings``; the default path is byte-identical):
    ``teachers`` is a list of distillation teachers (``settings.ensemble_kd`` averages their
    responses; ``settings.distill`` uses the first — a single ``teacher=`` is normalized to a
    one-element list). ``settings.ema_decay`` maintains a weight-EMA that is evaluated for early
    stopping and checkpointed as the deployed candidate. ``settings.sam_rho`` runs SAM (2x step
    cost). ``settings.start_epoch`` resumes a warm-started (shared-trunk) student on the same
    cosine; ``settings.stop_epoch`` stops the trunk early and writes ``last.pt`` (the branch seed).

    ``soft_radius_norm`` (lever 1) is the ambiguity radius in normalized window units; required
    when ``settings.soft_targets``. Scheduled sampling (lever 3) is driven from
    ``settings.ss_*``: the train split is teacher-forced at a schedule that ramps
    ``P(use model-own previous position)`` from 0 to ``ss_final_prob`` over ``ss_ramp_frac`` of
    the epochs, while the **val split is always evaluated free-running** so early stopping
    tracks the deployed (free-running) behavior — not a teacher-forced objective that the
    tracker never sees at inference (the B3 val/test dissonance this lever targets).
    """
    device = torch.device(settings.device)
    tracker = tracker.to(device)
    cfg = tracker.cfg
    anchor_spacing = float(2**cfg.n_downsample) / float(cfg.n_freq - 1)
    if settings.soft_targets and soft_radius_norm is None:
        raise ValueError("settings.soft_targets requires soft_radius_norm to be provided")
    teacher_list: list[LearnedTracker] = list(teachers) if teachers else (
        [teacher] if teacher is not None else []
    )
    if (settings.distill or settings.ensemble_kd) and not teacher_list:
        raise ValueError("settings.distill/ensemble_kd requires teacher(s) to be provided")
    for t in teacher_list:
        t.to(device).eval()
        for p in t.parameters():
            p.requires_grad_(False)
    ss_ramp_epochs = max(1.0, settings.ss_ramp_frac * settings.epochs)

    params = [p for p in tracker.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=settings.lr, weight_decay=settings.weight_decay)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=settings.epochs)
    if settings.start_epoch > 0:
        # Shared-trunk branch: advance the cosine to the branch point so epochs
        # start_epoch+1..epochs continue the exact schedule the trunk began (1912.05671).
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for _ in range(settings.start_epoch):
                sched.step()

    ema = _WeightEMA(tracker, settings.ema_decay) if settings.ema_decay > 0.0 else None

    out_path = Path(out_dir) if out_dir is not None else None
    if out_path is not None:
        out_path.mkdir(parents=True, exist_ok=True)
    ckpt_path = out_path / "best.pt" if out_path is not None else None

    n = train_tensors.n_sequences
    run_to = settings.stop_epoch if settings.stop_epoch else settings.epochs
    best_val = float("inf")
    best_epoch = settings.start_epoch - 1  # patience from the branch point (=-1 in the default)
    best_state: dict[str, torch.Tensor] | None = None
    history: list[dict] = []
    t0 = time.perf_counter()

    clean_spectra = train_tensors.spectra
    noise_sigma: torch.Tensor | None = None
    if settings.noise_photons is not None:
        # Physics stays upstream: sigma comes from the nv-sensor-sim shot-noise model,
        # computed once on the clean spectra; fresh realizations are drawn per epoch.
        from nv_sensor_sim.physics.shot_noise import shot_noise_sigma

        sig = shot_noise_sigma(clean_spectra.cpu().numpy(), float(settings.noise_photons))
        noise_sigma = torch.from_numpy(np.ascontiguousarray(sig)).float().to(device)
        log(f"shot-noise augmentation ON: {settings.noise_photons:.3e} photons/point "
            f"(baseline sigma {float(noise_sigma.max()):.2e}), fresh realization per epoch")

    epoch = settings.start_epoch
    for epoch in range(settings.start_epoch + 1, run_to + 1):
        tracker.train()
        if noise_sigma is not None:
            train_tensors.spectra = clean_spectra + noise_sigma * torch.randn_like(
                clean_spectra
            )
        perm = torch.randperm(n, device=device)
        # Scheduled sampling (lever 3): ramp P(use model-own previous position) 0 → ss_final_prob.
        ss_prob = (
            settings.ss_final_prob * min(1.0, epoch / ss_ramp_epochs)
            if settings.scheduled_sampling else 1.0
        )
        train_sums = {
            "association": 0.0, "position": 0.0, "track_position": 0.0,
            "projection": 0.0, "total": 0.0,
        }
        n_batches = 0
        for start in range(0, n, settings.batch_size):
            idx = perm[start : start + settings.batch_size]

            def _batch_losses():
                loss_dict, _ = _split_losses(
                    tracker, train_tensors, settings, anchor_spacing, scores_are_probs, idx,
                    soft_radius_norm=soft_radius_norm, ss_prob=ss_prob, teacher_force=True,
                    teachers=teacher_list,
                )
                return loss_dict

            if settings.sam_rho > 0.0:
                # SAM (Foret 2020, arXiv:2010.01412; bc_sam only): perturb the weights toward the
                # worst-case neighbor e = rho * g/||g||, then take the AdamW step with the gradient
                # measured there — biasing toward flat minima. Two forward/backward passes (~2x).
                losses = _batch_losses()
                grads = torch.autograd.grad(losses["total"], params, allow_unused=True)
                with torch.no_grad():
                    gnorm = torch.norm(
                        torch.stack([g.norm() for g in grads if g is not None])
                    )
                    scale = settings.sam_rho / (gnorm + 1e-12)
                    eps_w: list[torch.Tensor | None] = []
                    for p, g in zip(params, grads):
                        if g is None:
                            eps_w.append(None)
                            continue
                        e = g * scale
                        p.add_(e)
                        eps_w.append(e)
                opt.zero_grad(set_to_none=True)
                _batch_losses()["total"].backward()
                with torch.no_grad():
                    for p, e in zip(params, eps_w):
                        if e is not None:
                            p.sub_(e)   # restore the clean weights; the perturbed grad stays
            elif settings.pcgrad:
                # Arm 7c: PCGrad (Yu 2020) between the identity task (association term) and the
                # field task (projection term); the shared position/track terms are added plain.
                # Deployment-neutral — gradient surgery lives in the optimizer, not the graph.
                losses = _batch_losses()
                opt.zero_grad(set_to_none=True)
                _pcgrad_backward(losses, params, settings)
            else:
                losses = _batch_losses()
                opt.zero_grad(set_to_none=True)
                losses["total"].backward()
            torch.nn.utils.clip_grad_norm_(params, settings.grad_clip)
            opt.step()
            if ema is not None:
                ema.update(tracker)
            for k in train_sums:
                train_sums[k] += float(losses[k].detach())
            n_batches += 1
        sched.step()

        evaluate_val = (epoch % settings.val_every == 0) or (epoch == run_to)
        row = {
            "epoch": epoch,
            "lr": float(sched.get_last_lr()[0]),
            "val_evaluated": evaluate_val,
            **{f"train_{k}": v / n_batches for k, v in train_sums.items()},
        }
        if evaluate_val:
            # With weight-EMA (bc/bc_sam), early stopping and the checkpoint track the EMA
            # weights — the deployed candidate — not the last noisy SGD iterate. Swap the EMA
            # weights in for the eval, then restore the live training weights before the next
            # epoch. Default path (ema=None) is unchanged.
            train_backup = None
            if ema is not None:
                train_backup = {
                    k: v.detach().clone() for k, v in tracker.state_dict().items()
                }
                tracker.load_state_dict(ema.state_dict())
            tracker.eval()
            with torch.no_grad():
                # Val is always free-running (teacher_force=False) — the honest deployed metric.
                val_losses, val_out = _split_losses(
                    tracker, val_tensors, settings, anchor_spacing, scores_are_probs,
                    soft_radius_norm=soft_radius_norm,
                )
                acc = anchor_assoc_accuracy(
                    val_out.scores, val_tensors.assoc_targets, val_tensors.line_collision
                )
            row.update({f"val_{k}": float(v) for k, v in val_losses.items()})
            row.update(acc)

            val_total = float(val_losses["total"])
            if val_total < best_val:
                best_val = val_total
                best_epoch = epoch
                best_state = {
                    k: v.detach().cpu().clone() for k, v in tracker.state_dict().items()
                }
                # Persist on every improvement (not only at run end): a run killed
                # mid-training (crash, power loss) then still leaves its best-so-far
                # checkpoint on disk. Same payload as the final save; ~1 MB, and
                # improvements are sparse after warmup, so the IO is negligible.
                if ckpt_path is not None:
                    torch.save(
                        {
                            "model_state": best_state,
                            "model_cfg": asdict(cfg),
                            "settings": asdict(settings),
                            "meta": ckpt_meta or {},
                            "best_epoch": best_epoch,
                            "best_val_total": best_val,
                        },
                        ckpt_path,
                    )
            if train_backup is not None:
                tracker.load_state_dict(train_backup)  # resume training from the live weights
        history.append(row)

        if epoch % settings.log_every == 0 or epoch == 1:
            val_str = (
                f"val total {row['val_total']:.4f} | "
                f"val assoc in-coll {row['assoc_acc_in_coll']:.3f}"
                if evaluate_val else "val (skipped this epoch)"
            )
            log(
                f"epoch {epoch:5d} | train total {row['train_total']:.4f} | "
                f"{val_str} (best {best_val:.4f} @ {best_epoch}) | lr {row['lr']:.2e}"
            )

        if epoch - best_epoch >= settings.patience:
            log(f"early stop at epoch {epoch} (no val improvement for {settings.patience})")
            break

    wall = time.perf_counter() - t0
    train_tensors.spectra = clean_spectra  # restore caller's tensors after augmentation
    if out_path is not None and settings.stop_epoch > 0:
        # Shared-trunk arm: persist the final-epoch weights (the branch seed all bc/bc_sam
        # students warm-start from). tracker still holds the last iterate here (best not yet
        # restored). Only produced by the trunk (stop_epoch>0) — never on the default path.
        torch.save(
            {
                "model_state": {
                    k: v.detach().cpu().clone() for k, v in tracker.state_dict().items()
                },
                "model_cfg": asdict(cfg),
                "settings": asdict(settings),
                "meta": ckpt_meta or {},
                "final_epoch": epoch,
            },
            out_path / "last.pt",
        )
    if best_state is not None:
        tracker.load_state_dict(best_state)
    if ckpt_path is not None and best_state is not None:
        torch.save(
            {
                "model_state": best_state,
                "model_cfg": asdict(cfg),
                "settings": asdict(settings),
                "meta": ckpt_meta or {},
                "best_epoch": best_epoch,
                "best_val_total": best_val,
            },
            ckpt_path,
        )
    if out_path is not None:
        with open(out_path / "history.json", "w") as fh:
            json.dump(history, fh)

    log(
        f"done: {epoch} epochs in {wall:.1f}s | best val total {best_val:.4f} "
        f"@ epoch {best_epoch}" + (f" | saved {ckpt_path}" if ckpt_path else "")
    )
    return TrainResult(
        best_epoch=best_epoch,
        best_val_total=best_val,
        epochs_run=epoch,
        wall_s=wall,
        history=history,
        checkpoint_path=ckpt_path,
    )
