#!/usr/bin/env python3
"""First training pass on the golden dataset.

Verifies gradient plumbing, data pipeline shapes, and that the network
can overfit 100 samples. Uses a throwaway MLP — NOT the production
architecture.

Usage:
    python scripts/run_first_train.py
    python scripts/run_first_train.py --data-dir ./data/golden --epochs 200
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import h5py
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from odmr_edge_ml.data.loaders import DatasetLoader
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train
from odmr_edge_ml.training.losses import angular_error_deg

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


class GoldenDataset(Dataset):
    """PyTorch Dataset for golden HDF5 data with µT conversion.

    Loads a single split from the HDF5 file, converts labels from Tesla
    to micro-Tesla (×1e6), normalizes spectra, and provides optional
    corruption parameter metadata.

    Parameters
    ----------
    data_dir : Path or str
        Directory containing dataset.h5 and manifest.json.
    split : str
        HDF5 group name: "train", "val", or "test".
    """

    def __init__(self, data_dir: Path | str, split: str = "train") -> None:
        data_dir = Path(data_dir)
        h5_path = data_dir / "dataset.h5"

        with h5py.File(h5_path, "r") as f:
            g = f[split]
            spectra_raw = g["spectra"][:]
            labels_T = g["labels"][:]
            corruption_params = g["corruption_params"][:]

        # Per-spectrum min-max normalization
        spectra = DatasetLoader.normalize_spectra(spectra_raw)

        # Convert labels: Tesla → micro-Tesla
        labels_uT = labels_T * 1e6

        # Sign ambiguity detection
        bz = labels_uT[:, 2]
        if bz.min() < 0 and bz.max() > 0:
            log.warning(
                "Bz spans negative values (min=%.2f µT, max=%.2f µT). "
                "Folding to Bz >= 0 hemisphere to avoid B → -B degeneracy.",
                bz.min(),
                bz.max(),
            )
            # Fold: if Bz < 0, negate entire vector (B → -B symmetry)
            neg_mask = labels_uT[:, 2] < 0
            labels_uT[neg_mask] *= -1.0

        self.spectra = torch.from_numpy(spectra).float()
        self.labels_uT = torch.from_numpy(labels_uT).float()
        self.corruption_params = torch.from_numpy(corruption_params).float()

        log.info(
            "Loaded %s split: %d samples, spectra %s, labels_uT %s (Bz: %.1f–%.1f µT)",
            split,
            len(self.spectra),
            tuple(self.spectra.shape),
            tuple(self.labels_uT.shape),
            self.labels_uT[:, 2].min().item(),
            self.labels_uT[:, 2].max().item(),
        )

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {
            "spectra": self.spectra[idx],
            "b_field_uT": self.labels_uT[idx],
            "meta": {"corruption_params": self.corruption_params[idx]},
        }


class ThrowawayMLP(nn.Module):
    """Minimal MLP for verifying training plumbing.

    2 hidden layers, 128 units, ReLU only. NOT the production architecture.
    Exists to confirm gradient flow, data pipeline shapes, and that the
    network can overfit 100 samples.
    """

    def __init__(self, input_dim: int = 100, output_dim: int = 3) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 128),
            nn.ReLU(),
            nn.Linear(128, output_dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def collate_with_meta(batch: list[dict]) -> dict:
    """Custom collate that stacks spectra, labels, and optional meta dicts.

    Parameters
    ----------
    batch : list[dict]
        List of sample dicts from GoldenDataset.__getitem__.

    Returns
    -------
    dict
        Collated batch with stacked tensors and nested meta.
    """
    spectra = torch.stack([s["spectra"] for s in batch])
    b_field_uT = torch.stack([s["b_field_uT"] for s in batch])

    result: dict = {"spectra": spectra, "b_field_uT": b_field_uT}

    if "meta" in batch[0] and batch[0]["meta"] is not None:
        meta_keys = batch[0]["meta"].keys()
        meta: dict = {}
        for key in meta_keys:
            values = [s["meta"][key] for s in batch]
            if isinstance(values[0], torch.Tensor):
                meta[key] = torch.stack(values)
            else:
                meta[key] = values
        result["meta"] = meta

    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="First training pass on the golden ODMR dataset."
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "data/golden",
        help="Directory containing dataset.h5 and manifest.json.",
    )
    parser.add_argument("--epochs", type=int, default=200)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--alpha", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--checkpoint-dir",
        type=Path,
        default=Path("artifacts/checkpoints"),
    )
    parser.add_argument(
        "--split",
        type=str,
        default="train",
        help="HDF5 group to use for training.",
    )
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device("cpu")
    log.info("Device: %s", device)

    # Load data
    train_ds = GoldenDataset(args.data_dir, split=args.split)
    val_ds = GoldenDataset(args.data_dir, split="val")

    train_loader = DataLoader(
        train_ds,
        batch_size=args.batch_size,
        shuffle=True,
        collate_fn=collate_with_meta,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collate_with_meta,
    )

    # Model
    model = ThrowawayMLP(input_dim=100, output_dim=3)
    init_weights_kaiming_he(model)
    n_params = sum(p.numel() for p in model.parameters())
    log.info("ThrowawayMLP: %d parameters", n_params)

    # Train
    config = TrainConfig(
        lr=args.lr,
        epochs=args.epochs,
        batch_size=args.batch_size,
        alpha=args.alpha,
        seed=args.seed,
        checkpoint_dir=str(args.checkpoint_dir),
    )

    results = train(model, train_loader, val_loader, config, device)

    # Diagnostics
    log.info("=" * 60)
    log.info("TRAINING COMPLETE")
    log.info("  Final train loss: %.6f", results["final_train_loss"])
    log.info("  Best val angle error: %.4f°", results["best_val_angle_err"])
    log.info("  Training time: %.1fs", results["training_time_s"])

    if results["final_val_metrics"]:
        vm = results["final_val_metrics"]
        log.info("  Final val metrics:")
        for k, v in vm.items():
            log.info("    %s: %.4f", k, v)

    # Overfit check on training data
    model.eval()
    with torch.no_grad():
        all_pred = []
        all_true = []
        for batch in train_loader:
            pred = model(batch["spectra"].to(device))
            all_pred.append(pred)
            all_true.append(batch["b_field_uT"].to(device))
        pred_cat = torch.cat(all_pred)
        true_cat = torch.cat(all_true)
        train_angle = angular_error_deg(pred_cat, true_cat).mean().item()

    log.info("  Train-set angular error: %.4f°", train_angle)
    log.info("=" * 60)

    # Diagnostic flags
    final_loss = results["final_train_loss"]
    if final_loss > 0.5:
        log.warning(
            "DIAGNOSTIC: Final loss %.4f > 0.5. Possible causes: "
            "sign ambiguity, unit scaling error (T vs µT), dead ReLU neurons.",
            final_loss,
        )

    if final_loss < 0.01 and train_angle > 10.0:
        log.error(
            "DIAGNOSTIC: Loss near zero (%.4f) but angular error %.1f° > 10°. "
            "Fundamental problem — model may be predicting magnitude only.",
            final_loss,
            train_angle,
        )

    if train_angle < 1.0:
        log.info(
            "SUCCESS: Train-set angular error %.4f° < 1°. "
            "Gradient plumbing and data pipeline verified.",
            train_angle,
        )


if __name__ == "__main__":
    main()
