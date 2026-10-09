"""Increment-8 training driver — B+C reliability-stack arms on the FROZEN v6 recipe.

One isolated variable vs increment-6: the training SIGNAL + trajectory control. Everything else is
byte-matched to the v6 chain: gated core + linear assoc, snr10 shot-noise augmentation, epochs 800
/ batch 32 / patience 100 / val_every 5, cues OFF, v3 data ONLY, input_gain from the data's nominal
contrast. The arms touch only the loss / optimizer; the deployed forward graph and the 175,790-param
student shape are unchanged (asserted for every student). All hyperparameters are pre-declared in
`increment8_verdict.py`, committed before any training result exists.

Arms (`--arm`):
  teacher      — the wider FP32 teacher (throwaway, off-target) — NOT a candidate. 5 seeds -> the
                 KD ensemble. `--run-name teacher_e{i}`.
  trunk        — v6-shape student trained (baseline recipe) to the shared branch epoch, then
                 stopped; writes last.pt = the shared init all bc/bc_sam branches warm-start from.
  baseline_v6  — the UNCHANGED increment-6 v6 recipe rerun in-environment (the baseline-env arm).
  kd1          — increment-7 7b verbatim: single-teacher KD (teacher_e1, alpha=0.5, T=2.0).
  bc           — ensemble-KD (5 teachers, averaged) + logit standardization + weight-EMA, warm-
                 started from the shared trunk.
  bc_sam       — bc + SAM on the student.

    python experiments/increment8_train.py --arm teacher --seed 30260701 \
        --run-name teacher_e1 --out /opt/fanout/out
    python experiments/increment8_train.py --arm trunk --seed 20260700 \
        --run-name student_trunk --out /opt/fanout/out
    python experiments/increment8_train.py --arm baseline_v6 --seed 20260701 \
        --run-name baseline_s20260701 --out /opt/fanout/out
    python experiments/increment8_train.py --arm kd1 --seed 20260701 \
        --teacher-dir data/staged/teachers --run-name kd1_s20260701 --out /opt/fanout/out
    python experiments/increment8_train.py --arm bc --seed 20260701 \
        --trunk-ckpt data/staged/student_trunk.pt --teacher-dir data/staged/teachers \
        --run-name bc_s20260701 --out /opt/fanout/out
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "experiments"))

import increment2a_train as base  # noqa: E402  (reuse frozen-recipe helpers)
import increment8_verdict as v8  # noqa: E402  (pre-declared arm specs + hyperparameters)
from odmr_vector_tracking.config import load_config  # noqa: E402
from odmr_vector_tracking.data import SequenceDatasetLoader  # noqa: E402
from odmr_vector_tracking.tracking.learned import (  # noqa: E402
    LearnedTrackerConfig, build_tracker, config_from_checkpoint, load_tracker_state,
)
from odmr_vector_tracking.training import (  # noqa: E402
    TrainSettings, build_split_tensors, set_seed, train,
)

DATASET = _REPO_ROOT / "data" / "sequence_train_v3"

STUDENT_ARMS = ("trunk", "baseline_v6", "kd1", "bc", "bc_sam",
                "ema_only", "trunk_only", "std_only", "ens_only")
TEACHER_NAMES = tuple(f"teacher_e{i + 1}" for i in range(v8.N_TEACHERS))


def load_teacher(ckpt_path: Path, device: torch.device):
    """Rebuild a teacher tracker from a checkpoint (trusted, self-produced; weights_only=False)."""
    ck = torch.load(ckpt_path, map_location=device, weights_only=False)
    cfg = config_from_checkpoint(ck["model_cfg"], ck["model_state"])
    meta = ck["meta"]
    t = build_tracker(cfg, core=meta["core"], association=meta["association"]).to(device)
    load_tracker_state(t, ck["model_state"])
    t.eval()
    return t


def configure_arm(settings: TrainSettings, arm: str, branch_epoch: int) -> None:
    """Set the training levers for one arm, independent of checkpoint and data I/O."""
    settings.distill = arm == "kd1"
    settings.ensemble_kd = arm in ("bc", "bc_sam", "std_only", "ens_only")
    settings.logit_standardize = arm in ("bc", "bc_sam", "std_only")
    settings.ema_decay = v8.EMA_DECAY if arm in ("bc", "bc_sam", "ema_only") else 0.0
    settings.sam_rho = v8.SAM_RHO if arm == "bc_sam" else 0.0
    settings.start_epoch = branch_epoch if arm in ("bc", "bc_sam", "trunk_only") else 0
    settings.stop_epoch = branch_epoch if arm == "trunk" else 0
    if settings.distill or settings.ensemble_kd:
        settings.kd_alpha = v8.KD_ALPHA
        settings.kd_temp = v8.KD_TEMP


def main() -> int:
    ap = argparse.ArgumentParser(description="Increment-8 B+C reliability-stack training arms")
    ap.add_argument("--arm", required=True,
                    choices=("teacher", *STUDENT_ARMS))
    ap.add_argument("--seed", type=int, required=True)
    ap.add_argument("--trunk-seed", type=int, default=20260700)
    ap.add_argument("--run-name", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--teacher-dir", type=Path, default=None,
                    help="dir with teacher_e1..teacher_eN/best.pt (required for KD arms)")
    ap.add_argument("--trunk-ckpt", type=Path, default=None,
                    help="shared-trunk checkpoint (last.pt) to warm-start from (bc/bc_sam/trunk_only)")
    ap.add_argument("--epochs", type=int, default=None,
                    help="override the frozen 800 (smoke-test only; omit for real runs)")
    ap.add_argument("--branch-epoch", type=int, default=None,
                    help="override the pre-declared trunk branch epoch (smoke-test only)")
    ap.add_argument("--limit", type=int, default=None,
                    help="subset train/val to the first N sequences (smoke-test only; omit for "
                         "real runs — the matrix never passes it)")
    args = ap.parse_args()

    arm = args.arm
    is_teacher = arm == "teacher"
    branch_epoch = args.branch_epoch if args.branch_epoch is not None else v8.TRUNK_BRANCH_EPOCH

    # --- frozen recipe: settings byte-matched to the v6 chain -------------------------------
    settings = load_config(_REPO_ROOT / "configs" / "train_increment2a.yaml", TrainSettings)
    settings.epochs = v8.EPOCHS if args.epochs is None else args.epochs
    settings.batch_size = v8.BATCH_SIZE
    settings.patience = v8.PATIENCE
    settings.val_every = v8.VAL_EVERY
    settings.seed = args.trunk_seed if arm == "trunk" else args.seed

    device = base.preflight_device(settings.device)
    loader = SequenceDatasetLoader(DATASET)
    m = loader.manifest
    freq_range = (float(m["freq_range_Hz"][0]), float(m["freq_range_Hz"][1]))
    model_cfg = load_config(_REPO_ROOT / "configs" / "model.yaml", LearnedTrackerConfig)
    model_cfg.n_freq = int(m["n_freq_points"])
    model_cfg.n_lines = int(m["n_lines"])
    model_cfg.dt_s = float(m["dt_s"])
    if is_teacher:
        for k, val in v8.TEACHER_CFG_OVERRIDES.items():
            setattr(model_cfg, k, val)

    train_ds = loader.load_split("train")
    val_ds = loader.load_split("val")
    if args.limit is not None:  # smoke-test only
        train_ds = base._subset(train_ds, args.limit)
        val_ds = base._subset(val_ds, args.limit)
        print(f"[smoke] --limit {args.limit}: train/val subset to {args.limit} sequences")
    contrast = base.nominal_contrast(train_ds.spectra)
    model_cfg.input_gain = 1.0 / contrast

    # snr10 shot-noise augmentation (photons from the faintest-line depth) — frozen recipe.
    from nv_sensor_sim.physics.shot_noise import apply_shot_noise, photons_for_dip_snr
    faintest = float(np.min(np.asarray(m["line_depths"])))
    settings.noise_photons = float(photons_for_dip_snr(faintest, v8.TRAIN_SNR))
    val_ds = dataclasses.replace(
        val_ds,
        spectra=apply_shot_noise(val_ds.spectra, settings.noise_photons,
                                 seed=settings.seed + 1).astype(np.float32),
    )

    # --- arm wiring (only the training signal + trajectory control change) ------------------
    configure_arm(settings, arm, branch_epoch)
    kd_single = settings.distill
    kd_ensemble = settings.ensemble_kd

    # teachers (kd1 uses teacher_e1 only; bc/bc_sam average all N).
    teachers = None
    if kd_single or kd_ensemble:
        if args.teacher_dir is None:
            raise SystemExit(f"--arm {arm} requires --teacher-dir")
        names = ((v8.KD1_TEACHER,) if arm in ("kd1", "std_only")
                 else TEACHER_NAMES)
        teachers = [load_teacher(args.teacher_dir / n / "best.pt", device) for n in names]
        tp = sum(p.numel() for p in teachers[0].parameters() if p.requires_grad)
        print(f"[{arm}] {len(teachers)} teacher(s) from {args.teacher_dir} "
              f"({tp:,} params each) | KD alpha={settings.kd_alpha} T={settings.kd_temp} "
              f"| ensemble={kd_ensemble} logit_std={settings.logit_standardize}")

    set_seed(settings.seed)
    tracker = build_tracker(model_cfg, core="gated", association="linear").to(device)

    # shared-trunk warm-start (bc/bc_sam): all branches start from the SAME trunk weights.
    if arm in ("bc", "bc_sam", "trunk_only"):
        if args.trunk_ckpt is None:
            raise SystemExit(f"--arm {arm} requires --trunk-ckpt")
        tck = torch.load(args.trunk_ckpt, map_location=device, weights_only=False)
        if arm == "trunk_only":
            settings.start_epoch = int(tck["final_epoch"])
        load_tracker_state(tracker, tck["model_state"])
        print(f"[{arm}] warm-started from trunk {args.trunk_ckpt} "
              f"(branch epoch {settings.start_epoch}, resume on the frozen cosine)")

    n_params = sum(p.numel() for p in tracker.parameters() if p.requires_grad)
    print(f"[model] arm={arm} core=gated assoc=linear | {n_params:,} trainable params")
    if not is_teacher and n_params != v8.STUDENT_PARAMS:
        raise SystemExit(f"FATAL: student params {n_params} != {v8.STUDENT_PARAMS} (v6 shape) "
                         "— increment-8 is deployment-neutral; an arm must not change the shape.")

    anchors = tracker.extractor.get_buffer("anchors").cpu()
    train_t = build_split_tensors(train_ds, anchors, freq_range, model_cfg.proj_scale_T, device)
    val_t = build_split_tensors(val_ds, anchors, freq_range, model_cfg.proj_scale_T, device)
    print(f"[data] {DATASET.name} | config_hash {m.get('config_hash')} | "
          f"train {train_t.n_sequences} | val {val_t.n_sequences} | "
          f"noise {settings.noise_photons:.3e} ph/pt")

    out_dir = args.out / args.run_name
    levers = [name for name, on in (
        ("teacher", is_teacher), ("trunk", arm in ("trunk", "trunk_only")), ("kd1", kd_single),
        ("ensemble_kd", kd_ensemble), ("logit_std", settings.logit_standardize),
        ("ema", settings.ema_decay > 0), ("sam", settings.sam_rho > 0)) if on]
    meta = {
        "core": "gated", "association": "linear", "dataset": str(DATASET),
        "dataset_config_hash": m.get("config_hash"), "freq_range_Hz": list(freq_range),
        "overfit_one": False, "noise_photons": settings.noise_photons,
        "increment8_arm": arm, "levers": levers or [arm],
    }
    meta["run_key"] = base.run_key(model_cfg, settings, meta)
    print(f"[run] {args.run_name} | arm {arm} | levers {levers or [arm]} "
          f"| run_key {meta['run_key']}")

    result = train(tracker, train_t, val_t, settings, scores_are_probs=False,
                   out_dir=out_dir, ckpt_meta=meta, teachers=teachers)

    with open(out_dir / "summary.json", "w") as fh:
        json.dump({
            "run_name": args.run_name, "arm": arm, "run_key": meta["run_key"],
            "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
            "settings": dataclasses.asdict(settings), "model_cfg": dataclasses.asdict(model_cfg),
            "best_epoch": result.best_epoch, "best_val_total": result.best_val_total,
            "epochs_run": result.epochs_run, "wall_s": result.wall_s,
            "n_trainable_params": n_params, "dataset_config_hash": m.get("config_hash"),
            "levers": levers or [arm],
        }, fh, indent=2)
    print(f"[result] best val {result.best_val_total:.4f} @ {result.best_epoch} "
          f"({result.epochs_run} ep, {result.wall_s:.0f}s) -> {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
