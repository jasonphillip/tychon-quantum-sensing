"""Training loop with physics-stratified validation.

AdamW optimizer, CosineAnnealingLR scheduler, gradient clipping,
checkpoint best model by angular error. Validation stratifies metrics
by corruption parameters to reveal regime-specific failures.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from tychon_odmr_ml.training.losses import (
    CompositeAngularHuberLoss,
    angular_error_deg,
    component_error_nT,
)


log = logging.getLogger(__name__)


@dataclass
class TrainConfig:
    """Training hyperparameters.

    Parameters
    ----------
    weight_decay : float
        Mandatory for INT8 QAT weight bounding. Keeps weights in a
        narrow range that quantizes cleanly.
    huber_delta : float
        Huber loss transition threshold in µT. Residuals below delta
        are penalized quadratically; above delta, linearly. Default 1.0 µT.
        For label ranges much larger than 1 µT (e.g. the golden dataset's
        5,000–15,000 µT), this puts Huber entirely in linear mode. Set
        delta to ~1-5% of the label range for mixed quadratic/linear
        behavior (e.g. delta=100–500 for the golden dataset).
    """

    lr: float = 1e-3
    weight_decay: float = 1e-3
    betas: tuple[float, float] = (0.9, 0.999)
    T_max: int = 200
    eta_min: float = 1e-5
    epochs: int = 200
    batch_size: int = 32
    val_every: int = 10
    log_every: int = 5
    alpha: float = 0.7
    huber_delta: float = 1.0
    seed: int = 42
    checkpoint_dir: str = "artifacts/checkpoints"


def init_weights_kaiming_he(model: nn.Module) -> None:
    """Apply Kaiming He Normal initialization to all Linear/Conv layers.

    Critical because VectorBlox requires strict ReLU (no Leaky/GeLU),
    so dead neurons from bad init are permanent.

    Parameters
    ----------
    model : nn.Module
        Model to initialize in-place.
    """
    for m in model.modules():
        if isinstance(m, (nn.Linear, nn.Conv2d)):
            nn.init.kaiming_normal_(m.weight, mode="fan_in", nonlinearity="relu")
            if m.bias is not None:
                nn.init.zeros_(m.bias)


def validate_physics_regimes(
    model: nn.Module,
    val_loader: DataLoader,
    device: torch.device,
) -> dict[str, float]:
    """Physics-stratified validation metrics.

    Stratifies by corruption parameters rather than computing monolithic
    val loss. DataLoader batches are dicts with keys "spectra",
    "b_field_uT", and optionally "meta" dict with "corruption_params".

    Parameters
    ----------
    model : nn.Module
        Trained model.
    val_loader : DataLoader
        Validation DataLoader yielding dict batches.
    device : torch.device
        Compute device.

    Returns
    -------
    dict[str, float]
        Keys: angle_err_deg, bx_err_nT, by_err_nT, bz_err_nT,
        magnitude_err_nT, fano_bias_nT, heading_bias_deg.
    """
    model.eval()

    all_pred: list[torch.Tensor] = []
    all_true: list[torch.Tensor] = []
    all_meta: list[torch.Tensor] = []

    with torch.no_grad():
        for batch in val_loader:
            spectra = batch["spectra"].to(device)
            b_true = batch["b_field_uT"].to(device)
            b_pred = model(spectra)

            all_pred.append(b_pred)
            all_true.append(b_true)

            if "meta" in batch and "corruption_params" in batch["meta"]:
                all_meta.append(batch["meta"]["corruption_params"])

    pred = torch.cat(all_pred, dim=0)
    true = torch.cat(all_true, dim=0)

    # Global metrics
    angle_errs = angular_error_deg(pred, true)
    comp_errs = component_error_nT(pred, true)

    pred_mag = pred.norm(dim=1)
    true_mag = true.norm(dim=1)
    mag_err = (pred_mag - true_mag).abs() * 1000.0  # nT

    metrics: dict[str, float] = {
        "angle_err_deg": angle_errs.mean().item(),
        "bx_err_nT": comp_errs[:, 0].mean().item(),
        "by_err_nT": comp_errs[:, 1].mean().item(),
        "bz_err_nT": comp_errs[:, 2].mean().item(),
        "magnitude_err_nT": mag_err.mean().item(),
    }

    # Regime-stratified metrics (require corruption_params in meta)
    if all_meta:
        meta = torch.cat(all_meta, dim=0)
        # corruption_params columns: [p1_ppm, T_K, b1_gradient, b_perp]

        # Fano bias: samples with b1_gradient > 0.1
        fano_mask = meta[:, 2] > 0.1
        if fano_mask.any():
            fano_pred = pred[fano_mask]
            fano_true = true[fano_mask]
            fano_comp = component_error_nT(fano_pred, fano_true)
            metrics["fano_bias_nT"] = fano_comp.mean().item()
        else:
            metrics["fano_bias_nT"] = 0.0

        # Heading bias: samples with b_perp > 10 µT (= 10e-6 T = 0.01 µT in corruption_params which is in T)
        # corruption_params b_perp is in Tesla, 10 µT = 10e-6 T = 1e-5 T
        heading_mask = meta[:, 3] > 1e-5
        if heading_mask.any():
            heading_pred = pred[heading_mask]
            heading_true = true[heading_mask]
            heading_angles = angular_error_deg(heading_pred, heading_true)
            metrics["heading_bias_deg"] = heading_angles.mean().item()
        else:
            metrics["heading_bias_deg"] = 0.0
    else:
        metrics["fano_bias_nT"] = 0.0
        metrics["heading_bias_deg"] = 0.0

    return metrics


def train(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader | None,
    config: TrainConfig,
    device: torch.device,
) -> dict:
    """Train with AdamW, CosineAnnealingLR, gradient clipping.

    Checkpoints best model by angular error on validation set.

    Parameters
    ----------
    model : nn.Module
        Model to train.
    train_loader : DataLoader
        Training DataLoader yielding dict batches with "spectra" and
        "b_field_uT" keys.
    val_loader : DataLoader or None
        Validation DataLoader. If None, skip validation.
    config : TrainConfig
        Training hyperparameters.
    device : torch.device
        Compute device.

    Returns
    -------
    dict
        Keys: final_train_loss, final_val_metrics, best_val_angle_err,
        training_time_s, epoch_history.
    """
    torch.manual_seed(config.seed)

    model.to(device)
    criterion = CompositeAngularHuberLoss(
        alpha=config.alpha, huber_delta=config.huber_delta
    )

    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.lr,
        weight_decay=config.weight_decay,
        betas=config.betas,
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer, T_max=config.T_max, eta_min=config.eta_min
    )

    ckpt_dir = Path(config.checkpoint_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)

    best_angle_err = float("inf")
    epoch_history: list[dict] = []
    final_train_loss = float("inf")

    t0 = time.monotonic()

    for epoch in range(1, config.epochs + 1):
        model.train()
        epoch_loss = 0.0
        epoch_angular = 0.0
        epoch_huber = 0.0
        n_batches = 0

        for batch in train_loader:
            spectra = batch["spectra"].to(device)
            b_true = batch["b_field_uT"].to(device)

            optimizer.zero_grad()
            b_pred = model(spectra)
            losses = criterion(b_pred, b_true)
            losses["loss"].backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
            optimizer.step()

            epoch_loss += losses["loss"].item()
            epoch_angular += losses["angular"].item()
            epoch_huber += losses["huber"].item()
            n_batches += 1

        scheduler.step()
        avg_loss = epoch_loss / max(n_batches, 1)
        avg_angular = epoch_angular / max(n_batches, 1)
        avg_huber = epoch_huber / max(n_batches, 1)
        final_train_loss = avg_loss
        current_lr = scheduler.get_last_lr()[0]

        # Per-epoch logging
        if epoch == 1 or epoch % config.log_every == 0:
            log.info(
                "epoch %3d | loss %.4f | angular %.4f | huber %.4f | lr %.2e",
                epoch, avg_loss, avg_angular, avg_huber, current_lr,
            )

        entry: dict = {"epoch": epoch, "train_loss": avg_loss}

        # Validation
        val_metrics: dict[str, float] | None = None
        if val_loader is not None and epoch % config.val_every == 0:
            val_metrics = validate_physics_regimes(model, val_loader, device)
            entry["val_metrics"] = val_metrics
            log.info(
                "  val | angle_err %.4f° | bz_err %.1f nT | mag_err %.1f nT",
                val_metrics["angle_err_deg"],
                val_metrics["bz_err_nT"],
                val_metrics["magnitude_err_nT"],
            )

            if val_metrics["angle_err_deg"] < best_angle_err:
                best_angle_err = val_metrics["angle_err_deg"]
                torch.save(
                    {
                        "epoch": epoch,
                        "model_state_dict": model.state_dict(),
                        "optimizer_state_dict": optimizer.state_dict(),
                        "best_angle_err": best_angle_err,
                    },
                    ckpt_dir / "best_model.pt",
                )

        epoch_history.append(entry)

    training_time = time.monotonic() - t0

    # Final validation if we have a val_loader
    final_val_metrics: dict[str, float] = {}
    if val_loader is not None:
        final_val_metrics = validate_physics_regimes(model, val_loader, device)

    return {
        "final_train_loss": final_train_loss,
        "final_val_metrics": final_val_metrics,
        "best_val_angle_err": best_angle_err,
        "training_time_s": training_time,
        "epoch_history": epoch_history,
    }
