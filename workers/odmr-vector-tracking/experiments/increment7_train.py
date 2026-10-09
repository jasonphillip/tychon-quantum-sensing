"""Increment-7 training driver — identity-recovery arms on the FROZEN v6 recipe.

One isolated variable vs increment-6: the training signal. Everything else is byte-matched to the
v6 chain (`artifacts/increment6/train_chain.sh`): gated core + linear assoc, snr10 shot-noise
augmentation (photons data-derived from the faintest-line depth), epochs 800, batch 32, patience
100, val_every 5, cues OFF, v3 data ONLY, input_gain from the data's nominal contrast. The arms
touch only the loss / optimizer (gated hooks in `training/losses.py` + `training/loop.py`); the
deployed forward graph and the 175,790-param student shape are unchanged.

Arms (`--arm`):
  foveated  — 7a: per-sequence geometry-weighted association loss (schedule pre-declared in
              `increment7_verdict.foveated_weights`, keyed on v3 `max_offbias_angle_deg`).
  teacher   — 7b: train the wider FP32 teacher (throwaway, off-target) — NOT a candidate.
  distill   — 7b: student byte-identical to v6, KD soft targets from the teacher (--teacher-ckpt).
  pcgrad    — 7c: PCGrad field/identity gradient surgery (OPTIONAL).

    python experiments/increment7_train.py --arm foveated --seed 20260701 \
        --run-name fov_gated_linear_snr10 --out artifacts/increment7/runs/7a
    python experiments/increment7_train.py --arm teacher  --seed 20260701 \
        --run-name teacher_v3 --out artifacts/increment7/runs/7b
    python experiments/increment7_train.py --arm distill --seed 20260701 \
        --teacher-ckpt artifacts/increment7/runs/7b/teacher_v3/best.pt \
        --run-name kd_gated_linear_snr10 --out artifacts/increment7/runs/7b
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "experiments"))

import increment2a_train as base  # noqa: E402  (reuse frozen-recipe helpers)
import increment7_verdict as v7  # noqa: E402  (pre-declared arm specs)
from odmr_vector_tracking.config import load_config  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.tracking.learned import (  # noqa: E402
    LearnedTrackerConfig, build_tracker, config_from_checkpoint, load_tracker_state,
)
from odmr_vector_tracking.training import (  # noqa: E402
    TrainSettings, build_split_tensors, set_seed, train,
)

DATASET = _REPO_ROOT / "data" / "sequence_train_v3"


def load_teacher(ckpt_path: Path, device: torch.device):
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = config_from_checkpoint(ck["model_cfg"], ck["model_state"])
    meta = ck["meta"]
    t = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    load_tracker_state(t, ck["model_state"])
    t.eval()
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-7 identity-recovery training arms")
    ap.add_argument("--arm", required=True,
                    choices=("foveated", "teacher", "distill", "pcgrad"))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--teacher-ckpt", type=Path, default=None, help="required for --arm distill")
    ap.add_argument("--epochs", type=int, default=None,
                    help="override the frozen 800 (smoke-test only; omit for real runs)")
    args = ap.parse_args()

    # --- frozen recipe: settings byte-matched to the v6 chain -------------------------------
    settings = load_config(_REPO_ROOT / "configs" / "train_increment2a.yaml", TrainSettings)
    settings.epochs = 800 if args.epochs is None else args.epochs
    settings.batch_size = 32
    settings.patience = 100
    settings.val_every = 5
    settings.seed = args.seed

    device = base.preflight_device(settings.device)
    loader = SequenceDatasetLoader(DATASET)
    m = loader.manifest
    freq_range = (float(m["freq_range_Hz"][0]), float(m["freq_range_Hz"][1]))
    model_cfg = load_config(_REPO_ROOT / "configs" / "model.yaml", LearnedTrackerConfig)
    model_cfg.n_freq = int(m["n_freq_points"])
    model_cfg.n_lines = int(m["n_lines"])
    model_cfg.dt_s = float(m["dt_s"])

    is_teacher = args.arm == "teacher"
    if is_teacher:
        for k, val in v7.TEACHER_CFG_OVERRIDES.items():
            setattr(model_cfg, k, val)

    train_ds = loader.load_split("train")
    val_ds = loader.load_split("val")
    contrast = base.nominal_contrast(train_ds.spectra)
    model_cfg.input_gain = 1.0 / contrast

    # snr10 shot-noise augmentation (photons from the faintest-line depth) — frozen recipe.
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
    faintest = float(np.min(np.asarray(m["line_depths"])))
    settings.noise_photons = float(photons_for_dip_snr(faintest, 10.0))
    val_ds = dataclasses.replace(
        val_ds,
        spectra=apply_shot_noise(val_ds.spectra, settings.noise_photons,
                                 seed=settings.seed + 1).astype(np.float32),
    )

    # --- arm wiring (only the training signal changes) --------------------------------------
    settings.foveated = args.arm == "foveated"
    settings.distill = args.arm == "distill"
    settings.pcgrad = args.arm == "pcgrad"
    if settings.distill:
        settings.kd_alpha = v7.KD_ALPHA
        settings.kd_temp = v7.KD_TEMP

    assoc_seq_weight = None
    if settings.foveated:
        with h5py.File(DATASET / "dataset.h5", "r") as f:
            angles = f["train/max_offbias_angle_deg"][:]
        assert len(angles) == train_ds.spectra.shape[0], "angle array misaligned with train split"
        assoc_seq_weight = v7.foveated_weights(angles)
        print(f"[7a] foveated weights: mean {assoc_seq_weight.mean():.4f} "
              f"(bins {v7.FOVEATED_BINS}); "
              f"<=30deg n={int((angles<=30).sum())} >45deg n={int((angles>45).sum())}")

    teacher = None
    if settings.distill:
        if args.teacher_ckpt is None:
            raise SystemExit("--arm distill requires --teacher-ckpt")
        teacher = load_teacher(args.teacher_ckpt, device)
        tp = sum(p.numel() for p in teacher.parameters() if p.requires_grad)
        print(f"[7b] teacher loaded from {args.teacher_ckpt} ({tp:,} params) | "
              f"KD alpha={settings.kd_alpha} temp={settings.kd_temp}")

    set_seed(settings.seed)
    tracker = build_tracker(model_cfg, core="gated", association="linear").to(device)
    n_params = sum(p.numel() for p in tracker.parameters() if p.requires_grad)
    print(f"[model] arm={args.arm} core=gated assoc=linear | {n_params:,} trainable params")
    if not is_teacher and n_params != v7.STUDENT_PARAMS:
        raise SystemExit(f"FATAL: student params {n_params} != {v7.STUDENT_PARAMS} (v6 shape) "
                         "— an arm must not change the deployed shape (increment-8, not -7).")

    anchors = tracker.extractor.get_buffer("anchors").cpu()
    train_t = build_split_tensors(train_ds, anchors, freq_range, model_cfg.proj_scale_T, device,
                                  assoc_seq_weight=assoc_seq_weight)
    val_t = build_split_tensors(val_ds, anchors, freq_range, model_cfg.proj_scale_T, device)
    print(f"[data] {DATASET.name} | config_hash {m.get('config_hash')} | "
          f"train {train_t.n_sequences} | val {val_t.n_sequences} | "
          f"noise {settings.noise_photons:.3e} ph/pt")

    out_dir = args.out / args.run_name
    meta = {
        "core": "gated", "association": "linear", "dataset": str(DATASET),
        "dataset_config_hash": m.get("config_hash"), "freq_range_Hz": list(freq_range),
        "overfit_one": False, "noise_photons": settings.noise_photons,
        "levers": [args.arm], "increment7_arm": args.arm,
    }
    meta["run_key"] = base.run_key(model_cfg, settings, meta)
    print(f"[run] {args.run_name} | arm {args.arm} | run_key {meta['run_key']}")

    result = train(tracker, train_t, val_t, settings, scores_are_probs=False,
                   out_dir=out_dir, ckpt_meta=meta, teacher=teacher)

    with open(out_dir / "summary.json", "w") as fh:
        json.dump({
            "run_name": args.run_name, "arm": args.arm, "run_key": meta["run_key"],
            "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
            "settings": dataclasses.asdict(settings), "model_cfg": dataclasses.asdict(model_cfg),
            "best_epoch": result.best_epoch, "best_val_total": result.best_val_total,
            "epochs_run": result.epochs_run, "wall_s": result.wall_s,
            "n_trainable_params": n_params, "dataset_config_hash": m.get("config_hash"),
        }, fh, indent=2)
    print(f"[result] best val {result.best_val_total:.4f} @ {result.best_epoch} "
          f"({result.epochs_run} ep, {result.wall_s:.0f}s) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
