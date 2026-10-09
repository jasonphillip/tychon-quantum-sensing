#!/usr/bin/env python3
"""GPU dry-run for v2 retrain readiness.

Tests that autocast(bf16) + QAT + torch.compile play together correctly,
in three configurations on a 100-sample slice of production_50k:

  A. autocast + torch.compile + QAT (target config for full v2 retrain)
  B. autocast + QAT (no compile)        — fallback if A errors
  C. fp32 + QAT (no autocast, no compile) — sanity baseline

Reports per-config: completion status, wall-clock for 1 epoch on 100 samples
(~2 batches at batch_size=64), peak GPU memory, final train loss.

Does NOT touch v1, v2 production data, checkpoints, or NAS artifacts.
Only allocates a fresh model per config.
"""

from __future__ import annotations

import logging
import sys
import time
import traceback
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch
from torch.utils.data import DataLoader

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")
warnings.filterwarnings("ignore", category=UserWarning, module="torch._dynamo")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from odmr_edge_ml.training.loop import TrainConfig, init_weights_kaiming_he, train  # noqa: E402
from odmr_edge_ml.training.qat import prepare_model_qat  # noqa: E402

# Reuse v2's dataset class & loss
sys.path.insert(0, str(Path(__file__).resolve().parent))
from scalar_residual_v2 import (  # noqa: E402
    OdmrFCNNv2,
    ScalarHuberLoss,
    collate_residual,
    validate_scalar,
)
from odmr_edge_ml.evaluation.residual_dataset import _normalize_symmetric  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path("~/projects/odmr-edge-ml/data/production_50k")
N_SAMPLES = 100
BATCH = 64
EPOCHS = 1
CLAMP_UT = 2.25


class TinyResidualDatasetV2(torch.utils.data.Dataset):
    """Same packing as ResidualDatasetV2 but only N_SAMPLES rows."""

    def __init__(self, n: int) -> None:
        npz = np.load(DATA_DIR / "pid_residuals.npz")
        lock_bins = npz["train_lock_bins"][:n]
        delta_b = npz["train_delta_b_uT"][:n]
        with h5py.File(DATA_DIR / "dataset.h5", "r") as f:
            spectra_raw = f["train"]["spectra"][:n]
        spectra_norm = _normalize_symmetric(spectra_raw)
        lock_col = lock_bins[:, None].astype(np.float32)
        combined = np.concatenate([spectra_norm, lock_col], axis=1)
        clipped = np.clip(delta_b, -CLAMP_UT, CLAMP_UT)
        self.spectra = torch.from_numpy(combined).float()
        self.labels = torch.from_numpy(clipped[:, None]).float()

    def __len__(self) -> int:
        return len(self.spectra)

    def __getitem__(self, idx: int) -> dict:
        return {"spectra": self.spectra[idx], "b_field_uT": self.labels[idx]}


def build_loaders() -> tuple[DataLoader, DataLoader]:
    train_ds = TinyResidualDatasetV2(N_SAMPLES)
    val_ds = TinyResidualDatasetV2(N_SAMPLES // 2)
    return (
        DataLoader(train_ds, batch_size=BATCH, shuffle=True,
                   collate_fn=collate_residual,
                   pin_memory=True, num_workers=4),
        DataLoader(val_ds, batch_size=BATCH, shuffle=False,
                   collate_fn=collate_residual,
                   pin_memory=True, num_workers=4),
    )


def make_qat_model() -> torch.nn.Module:
    model = OdmrFCNNv2(input_dim=100, output_dim=1)
    init_weights_kaiming_he(model)
    qat = prepare_model_qat(model, example_input=torch.randn(1, 101))
    return qat


def run_config(
    name: str,
    *,
    use_autocast: bool,
    use_compile: bool,
    device: torch.device,
) -> dict:
    log.info("")
    log.info("=" * 60)
    log.info("CONFIG %s: autocast=%s  compile=%s", name, use_autocast, use_compile)
    log.info("=" * 60)

    train_loader, val_loader = build_loaders()
    qat_model = make_qat_model().to(device)

    if use_compile:
        try:
            qat_model = torch.compile(qat_model)
            log.info("  torch.compile applied")
        except Exception as exc:
            log.warning("  torch.compile failed at compile-time: %s", exc)
            return {
                "name": name, "ok": False,
                "phase": "compile-time",
                "error": f"{type(exc).__name__}: {exc}",
                "elapsed_s": None, "peak_mem_mb": None, "train_loss": None,
            }

    config = TrainConfig(
        lr=1e-3, weight_decay=1e-3, epochs=EPOCHS, T_max=EPOCHS, eta_min=1e-5,
        batch_size=BATCH, val_every=EPOCHS, log_every=1, alpha=0.7,
        huber_delta=10.0, seed=42,
        checkpoint_dir="/tmp/gpu_dry_run_ckpt",
    )
    criterion = ScalarHuberLoss(delta=10.0)

    if device.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()

    t0 = time.perf_counter()
    try:
        if use_autocast:
            with torch.autocast(device_type=device.type,
                                dtype=torch.bfloat16,
                                enabled=device.type == "cuda"):
                results = train(
                    qat_model, train_loader, val_loader, config, device,
                    criterion=criterion, val_fn=validate_scalar,
                )
        else:
            results = train(
                qat_model, train_loader, val_loader, config, device,
                criterion=criterion, val_fn=validate_scalar,
            )
    except Exception as exc:
        log.error("  Training failed: %s", exc)
        log.error("  %s", traceback.format_exc())
        return {
            "name": name, "ok": False,
            "phase": "train-time",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_s": time.perf_counter() - t0,
            "peak_mem_mb": None, "train_loss": None,
        }

    elapsed = time.perf_counter() - t0
    peak_mem = (
        torch.cuda.max_memory_allocated() / 1024 / 1024
        if device.type == "cuda" else None
    )
    train_loss = float(results["final_train_loss"])

    log.info("  OK   elapsed=%.2fs   peak_mem=%.1f MB   final_train_loss=%.6f",
             elapsed, peak_mem if peak_mem is not None else float("nan"), train_loss)

    return {
        "name": name, "ok": True, "phase": "complete", "error": None,
        "elapsed_s": elapsed, "peak_mem_mb": peak_mem, "train_loss": train_loss,
    }


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("Device: %s", device)
    if device.type == "cuda":
        log.info("  GPU: %s  cc=%s", torch.cuda.get_device_name(0),
                 torch.cuda.get_device_capability(0))
        free, total = torch.cuda.mem_get_info(0)
        log.info("  Memory: %.1f GB free / %.1f GB total",
                 free / 1024 / 1024 / 1024, total / 1024 / 1024 / 1024)

    results = []
    results.append(run_config("A", use_autocast=True, use_compile=True, device=device))
    results.append(run_config("B", use_autocast=True, use_compile=False, device=device))
    results.append(run_config("C", use_autocast=False, use_compile=False, device=device))

    log.info("")
    log.info("=" * 80)
    log.info("DRY-RUN SUMMARY")
    log.info("=" * 80)
    log.info("%-30s %6s %12s %12s %14s %s",
             "config", "ok", "elapsed", "peak_mem", "final_loss", "error")
    for r in results:
        log.info("%-30s %6s %10.2f s %10s %14s %s",
                 f"{r['name']}: {('autocast+compile' if r['name']=='A' else 'autocast' if r['name']=='B' else 'fp32')}",
                 "✓" if r["ok"] else "✗",
                 r["elapsed_s"] if r["elapsed_s"] is not None else float("nan"),
                 f"{r['peak_mem_mb']:.1f} MB" if r["peak_mem_mb"] is not None else "—",
                 f"{r['train_loss']:.4f}" if r["train_loss"] is not None else "—",
                 r["error"] or "")

    # Recommendation
    log.info("")
    a_ok, b_ok = results[0]["ok"], results[1]["ok"]
    if a_ok:
        log.info(">>> RECOMMENDATION: run v2 retrain with autocast + torch.compile (config A)")
    elif b_ok:
        log.info(">>> RECOMMENDATION: run v2 retrain with autocast only (compile incompatible with QAT)")
        log.info(">>>   Set V2_USE_COMPILE=0 in environment, or rely on the try/except fallback")
    else:
        log.info(">>> RECOMMENDATION: drop autocast and compile, run v2 retrain in fp32 on GPU")


if __name__ == "__main__":
    main()
