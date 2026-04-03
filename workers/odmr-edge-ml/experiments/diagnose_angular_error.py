#!/usr/bin/env python3
"""Diagnose why both architectures produce random-guess angular error (57.3 deg).

Three experiments:
1. Sign ambiguity test — do B and -B produce identical spectra?
2. Magnitude-only baseline — can the model learn scalar |B| from spectra?
3. Label normalization — does unit-vector + pure cosine loss help?

Usage:
    python experiments/diagnose_angular_error.py
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.models.mlp import OdmrMLP
from odmr_edge_ml.training.loop import (
    TrainConfig,
    init_weights_kaiming_he,
    train,
    validate_physics_regimes,
)
from odmr_edge_ml.training.losses import angular_error_deg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data/production_50k"


# ---------------------------------------------------------------------------
# Shared dataset utilities
# ---------------------------------------------------------------------------
def load_raw(split: str = "train") -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load raw spectra, labels (Tesla), and corruption_params from HDF5."""
    with h5py.File(DATA_DIR / "dataset.h5", "r") as f:
        g = f[split]
        spectra = g["spectra"][:]
        labels = g["labels"][:]
        corruption_params = g["corruption_params"][:]
    return spectra, labels, corruption_params


class FlexibleDataset(Dataset):
    """Configurable dataset: supports sign folding toggle and label transforms."""

    def __init__(
        self,
        split: str = "train",
        fold_sign: bool = True,
        label_transform: str = "raw",  # "raw", "unit_vector", "magnitude"
    ) -> None:
        spectra_raw, labels_T, corruption_params = load_raw(split)
        spectra = DatasetLoader.normalize_spectra(spectra_raw)
        labels_uT = labels_T * 1e6

        if fold_sign:
            if labels_uT[:, 2].min() < 0 and labels_uT[:, 2].max() > 0:
                neg_mask = labels_uT[:, 2] < 0
                labels_uT[neg_mask] *= -1.0

        if label_transform == "unit_vector":
            mag = np.linalg.norm(labels_uT, axis=1, keepdims=True)
            mag = np.clip(mag, 1e-8, None)
            self.labels = torch.from_numpy(labels_uT / mag).float()
        elif label_transform == "magnitude":
            mag = np.linalg.norm(labels_uT, axis=1, keepdims=True)
            self.labels = torch.from_numpy(mag).float()
        else:
            self.labels = torch.from_numpy(labels_uT).float()

        self.spectra = torch.from_numpy(spectra).float()
        self.corruption_params = torch.from_numpy(corruption_params).float()
        self.label_transform = label_transform

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {
            "spectra": self.spectra[idx],
            "b_field_uT": self.labels[idx],
            "meta": {"corruption_params": self.corruption_params[idx]},
        }


def collate_with_meta(batch: list[dict]) -> dict:
    spectra = torch.stack([s["spectra"] for s in batch])
    b_field_uT = torch.stack([s["b_field_uT"] for s in batch])
    result: dict = {"spectra": spectra, "b_field_uT": b_field_uT}
    if "meta" in batch[0]:
        meta: dict = {}
        for key in batch[0]["meta"]:
            values = [s["meta"][key] for s in batch]
            if isinstance(values[0], torch.Tensor):
                meta[key] = torch.stack(values)
            else:
                meta[key] = values
        result["meta"] = meta
    return result


# ===================================================================
# EXPERIMENT 1: Sign Ambiguity Test
# ===================================================================
def experiment_sign_ambiguity() -> None:
    """Find nearest (B, -B) pairs in dataset and compare their spectra."""
    log.info("=" * 60)
    log.info("EXPERIMENT 1: Sign Ambiguity Test")
    log.info("=" * 60)

    spectra_raw, labels_T, _ = load_raw("train")
    spectra = DatasetLoader.normalize_spectra(spectra_raw)
    labels_uT = labels_T * 1e6
    N = len(labels_uT)

    # For 100 random samples, find nearest neighbor with opposite B
    rng = np.random.default_rng(42)
    indices = rng.choice(N, size=100, replace=False)

    max_diffs = []
    mean_diffs = []
    b_match_errors = []
    correlations = []

    for idx in indices:
        b_target = labels_uT[idx]
        b_neg = -b_target

        # Find nearest to -B among all other samples
        dists = np.linalg.norm(labels_uT - b_neg, axis=1)
        dists[idx] = np.inf  # exclude self
        nearest_idx = np.argmin(dists)
        b_match_err = dists[nearest_idx]  # uT

        # Compare spectra
        s1 = spectra[idx]
        s2 = spectra[nearest_idx]
        diff = np.abs(s1 - s2)
        corr = np.corrcoef(s1, s2)[0, 1]

        max_diffs.append(diff.max())
        mean_diffs.append(diff.mean())
        b_match_errors.append(b_match_err)
        correlations.append(corr)

    max_diffs = np.array(max_diffs)
    mean_diffs = np.array(mean_diffs)
    b_match_errors = np.array(b_match_errors)
    correlations = np.array(correlations)

    log.info("")
    log.info("B-field match quality (ideal: 0 uT):")
    log.info("  |B_nearest - (-B_target)|: mean=%.2f uT, median=%.2f uT, max=%.2f uT",
             b_match_errors.mean(), np.median(b_match_errors), b_match_errors.max())
    log.info("")
    log.info("Spectrum differences (B vs nearest -B):")
    log.info("  max |s(B) - s(-B)|:  mean=%.6f, median=%.6f, max=%.6f",
             max_diffs.mean(), np.median(max_diffs), max_diffs.max())
    log.info("  mean |s(B) - s(-B)|: mean=%.6f, median=%.6f",
             mean_diffs.mean(), np.median(mean_diffs))
    log.info("  correlation s(B) vs s(-B): mean=%.4f, min=%.4f, max=%.4f",
             correlations.mean(), correlations.min(), correlations.max())
    log.info("")

    # Also compare random pairs (not opposite) as a baseline
    rand_max_diffs = []
    rand_correlations = []
    for i in range(100):
        i1, i2 = rng.choice(N, size=2, replace=False)
        s1 = spectra[i1]
        s2 = spectra[i2]
        rand_max_diffs.append(np.abs(s1 - s2).max())
        rand_correlations.append(np.corrcoef(s1, s2)[0, 1])

    rand_max_diffs = np.array(rand_max_diffs)
    rand_correlations = np.array(rand_correlations)

    log.info("Random pair baseline (for comparison):")
    log.info("  max |s1 - s2|:  mean=%.6f", rand_max_diffs.mean())
    log.info("  correlation:     mean=%.4f", rand_correlations.mean())
    log.info("")

    if correlations.mean() > 0.95:
        log.info("CONCLUSION: B and -B produce nearly identical spectra (corr > 0.95).")
        log.info("  Direction is UNRECOVERABLE from spectra — physics constraint.")
    elif correlations.mean() > 0.80:
        log.info("CONCLUSION: B and -B produce similar but distinguishable spectra (corr %.2f).",
                 correlations.mean())
        log.info("  Directional signal EXISTS but is WEAK. Models need help extracting it.")
    else:
        log.info("CONCLUSION: B and -B produce distinct spectra (corr %.2f).",
                 correlations.mean())
        log.info("  Direction should be learnable.")

    # Bonus: what does a constant-prediction model score?
    log.info("")
    log.info("--- Constant-prediction baseline ---")
    labels_t = torch.from_numpy(labels_uT).float()

    # After sign folding
    folded = labels_uT.copy()
    neg = folded[:, 2] < 0
    folded[neg] *= -1.0
    folded_t = torch.from_numpy(folded).float()

    # Mean prediction
    mean_vec = folded_t.mean(dim=0, keepdim=True).expand_as(folded_t)
    angle_err = angular_error_deg(mean_vec, folded_t)
    log.info("  Predict mean([folded labels]): angular error = %.2f deg", angle_err.mean().item())

    # Zero prediction
    zero_pred = torch.zeros_like(folded_t)
    zero_pred[:, 2] = 1.0  # predict [0, 0, 1]
    angle_err_z = angular_error_deg(zero_pred, folded_t)
    log.info("  Predict [0, 0, 1] constant:    angular error = %.2f deg", angle_err_z.mean().item())

    # Without sign folding
    mean_raw = labels_t.mean(dim=0, keepdim=True).expand_as(labels_t)
    angle_err_raw = angular_error_deg(mean_raw, labels_t)
    log.info("  Predict mean([raw labels]):     angular error = %.2f deg (no folding)",
             angle_err_raw.mean().item())


# ===================================================================
# EXPERIMENT 2: Magnitude-Only Baseline
# ===================================================================
def experiment_magnitude_only() -> None:
    """Train MLP to predict scalar |B| only. Tests if spectra contain physics info."""
    log.info("")
    log.info("=" * 60)
    log.info("EXPERIMENT 2: Magnitude-Only Baseline (50 epochs)")
    log.info("=" * 60)

    train_ds = FlexibleDataset("train", fold_sign=False, label_transform="magnitude")
    val_ds = FlexibleDataset("val", fold_sign=False, label_transform="magnitude")

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True, collate_fn=collate_with_meta)
    val_loader = DataLoader(val_ds, batch_size=64, shuffle=False, collate_fn=collate_with_meta)

    # 1-output MLP for magnitude prediction
    model = OdmrMLP(input_dim=100, output_dim=1, hidden_dims=[64, 32])
    init_weights_kaiming_he(model)

    # Simple MSE training loop (can't use existing train() — it expects 3-output + angular loss)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-3)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=50, eta_min=1e-5)
    criterion = nn.HuberLoss(delta=5.0)  # delta=5 uT for magnitude range [20, 70]

    device = torch.device("cpu")
    model.to(device)

    log.info("  Label: scalar |B| in uT, range [20, 70]")
    log.info("  Loss: Huber (delta=5 uT)")
    log.info("")

    for epoch in range(1, 51):
        model.train()
        epoch_loss = 0.0
        n_batches = 0
        for batch in train_loader:
            x = batch["spectra"].to(device)
            y = batch["b_field_uT"].to(device)  # (batch, 1) magnitude
            optimizer.zero_grad()
            pred = model(x)
            loss = criterion(pred, y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=10.0)
            optimizer.step()
            epoch_loss += loss.item()
            n_batches += 1
        scheduler.step()
        avg_loss = epoch_loss / n_batches

        if epoch == 1 or epoch % 10 == 0:
            # Validate
            model.eval()
            all_pred, all_true = [], []
            with torch.no_grad():
                for batch in val_loader:
                    x = batch["spectra"].to(device)
                    y = batch["b_field_uT"].to(device)
                    pred = model(x)
                    all_pred.append(pred)
                    all_true.append(y)
            pred_t = torch.cat(all_pred)
            true_t = torch.cat(all_true)
            mae = (pred_t - true_t).abs().mean().item()
            rmse = ((pred_t - true_t) ** 2).mean().sqrt().item()
            log.info("  epoch %3d | loss %.4f | val MAE %.2f uT | val RMSE %.2f uT",
                     epoch, avg_loss, mae, rmse)

    # Final assessment
    model.eval()
    all_pred, all_true = [], []
    with torch.no_grad():
        for batch in val_loader:
            pred = model(batch["spectra"].to(device))
            all_pred.append(pred)
            all_true.append(batch["b_field_uT"].to(device))
    pred_t = torch.cat(all_pred)
    true_t = torch.cat(all_true)
    mae = (pred_t - true_t).abs().mean().item()
    # Naive baseline: always predict mean magnitude
    mean_mag = true_t.mean().item()
    naive_mae = (true_t - mean_mag).abs().mean().item()

    log.info("")
    log.info("  Final val MAE: %.2f uT", mae)
    log.info("  Naive baseline (predict mean=%.1f uT): MAE %.2f uT", mean_mag, naive_mae)
    if mae < naive_mae * 0.8:
        log.info("  CONCLUSION: Model extracts magnitude from spectra (%.0f%% better than naive).",
                 (1 - mae / naive_mae) * 100)
    else:
        log.info("  CONCLUSION: Model barely beats naive baseline.")


# ===================================================================
# EXPERIMENT 3: Label Normalization (Unit Vectors + Pure Cosine Loss)
# ===================================================================
def experiment_unit_vectors() -> None:
    """Train with unit-vector labels and alpha=1.0 (pure angular loss)."""
    log.info("")
    log.info("=" * 60)
    log.info("EXPERIMENT 3: Unit Vectors + Pure Cosine Loss (50 epochs)")
    log.info("=" * 60)

    # Run two sub-experiments: with and without sign folding
    for fold_sign, label in [(True, "WITH sign folding"), (False, "WITHOUT sign folding")]:
        log.info("")
        log.info("--- %s ---", label)

        train_ds = FlexibleDataset("train", fold_sign=fold_sign, label_transform="unit_vector")
        val_ds = FlexibleDataset("val", fold_sign=fold_sign, label_transform="unit_vector")

        train_loader = DataLoader(
            train_ds, batch_size=64, shuffle=True, collate_fn=collate_with_meta,
        )
        val_loader = DataLoader(
            val_ds, batch_size=64, shuffle=False, collate_fn=collate_with_meta,
        )

        model = OdmrMLP(input_dim=100, output_dim=3, hidden_dims=[64, 32])
        init_weights_kaiming_he(model)

        config = TrainConfig(
            lr=1e-3,
            weight_decay=1e-3,
            epochs=50,
            T_max=50,
            eta_min=1e-5,
            batch_size=64,
            val_every=10,
            log_every=10,
            alpha=1.0,  # Pure angular loss — no Huber component
            huber_delta=1.0,
            seed=42,
            checkpoint_dir=f"/tmp/diag_unit_vec_{'folded' if fold_sign else 'raw'}",
        )

        device = torch.device("cpu")
        results = train(model, train_loader, val_loader, config, device)

        log.info("  Final train loss: %.6f", results["final_train_loss"])
        log.info("  Best val angle err: %.4f deg", results["best_val_angle_err"])
        if results["final_val_metrics"]:
            log.info("  Final val angle err: %.4f deg",
                     results["final_val_metrics"]["angle_err_deg"])

    log.info("")
    log.info("  INTERPRETATION:")
    log.info("  - If sign-folded stays ~57 deg: hemisphere trap confirmed.")
    log.info("  - If no-folding improves: sign folding was destroying signal.")
    log.info("  - If both stay ~57 deg: model lacks capacity or spectra lack directional info.")


# ===================================================================
# Main
# ===================================================================
def main() -> None:
    log.info("=" * 60)
    log.info("DIAGNOSTIC: Why is angular error stuck at 57.3 degrees?")
    log.info("=" * 60)

    experiment_sign_ambiguity()
    experiment_magnitude_only()
    experiment_unit_vectors()

    log.info("")
    log.info("=" * 60)
    log.info("DIAGNOSTICS COMPLETE")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
