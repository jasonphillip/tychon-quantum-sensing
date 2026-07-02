"""Increment-2a training harness: learned through-crossing tracker on sequence_sanity_v0.

Trains a :class:`LearnedTracker` variant on a v1-contract sequence dataset with the losses and
loop from ``odmr_vector_tracking.training``. Two modes:

- ``--overfit-one`` — the sanity gate: fit a single training sequence (val = the same sequence)
  to near-zero association error. Proves the harness end-to-end before any full run.
- default — train on the full train split, early-stop on the val split, checkpoint best-val.

Run from the repo root, e.g.::

    python experiments/increment2a_train.py --overfit-one
    python experiments/increment2a_train.py --core relu --assoc linear
    python experiments/increment2a_train.py --core gated --assoc attention

GPU preflight is mandatory: if the requested device is CUDA and unavailable, the script exits —
a silent CPU fallback is a bug. The device actually used is logged.

Outputs land in ``artifacts/increment2a/<run-name>/`` (gitignored): ``best.pt``,
``history.json``, ``summary.json``. Evaluation against the Increment-1 bar is
``experiments/increment2a_report.py``'s job — this script reports only training-time
(anchor-level proxy) numbers.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from odmr_vector_tracking.config import load_config
from odmr_vector_tracking.data import SequenceDatasetLoader
from odmr_vector_tracking.data.loaders import SequenceDataset
from odmr_vector_tracking.evaluation.metrics import association_accuracy, resolve_true_axis
from odmr_vector_tracking.tracking.learned import LearnedTrackerConfig, build_tracker
from odmr_vector_tracking.training import (
    TrainSettings,
    anchor_assoc_accuracy,
    build_split_tensors,
    set_seed,
    train,
)
from odmr_vector_tracking.vector.geometry import LINE_AXIS_8

DEFAULT_DATASET = _REPO_ROOT / "data" / "sequence_sanity_v0"
DEFAULT_TRAIN_CFG = _REPO_ROOT / "configs" / "train_increment2a.yaml"
DEFAULT_MODEL_CFG = _REPO_ROOT / "configs" / "model.yaml"
DEFAULT_OUT = _REPO_ROOT / "artifacts" / "increment2a"


def preflight_device(requested: str) -> torch.device:
    """Resolve the training device; refuse a silent CUDA→CPU fallback."""
    print(f"[preflight] torch {torch.__version__} | cuda available: {torch.cuda.is_available()}")
    if requested.startswith("cuda"):
        if not torch.cuda.is_available():
            print("[preflight] FATAL: --device cuda requested but CUDA is unavailable. "
                  "A silent CPU fallback is a bug; pass --device cpu to opt in explicitly.")
            raise SystemExit(2)
        print(f"[preflight] device: {requested} ({torch.cuda.get_device_name(0)})")
    else:
        print(f"[preflight] device: {requested} (explicit non-CUDA request)")
    return torch.device(requested)


def nominal_contrast(spectra: np.ndarray) -> float:
    """Median per-frame max dip depth of ``(N, T, F)`` contract-normalized PL.

    On the real sequence_sanity_v0 this is ~0.004 (dips are only ~0.4% of the PL baseline);
    ``input_gain = 1 / contrast`` rescales ``1 - PL`` so dips enter the extractor O(1). At
    INT8 deployment this gain must fold into the input quantization scale (Increment 3).
    """
    return float(np.median(1.0 - spectra.min(axis=-1)))


def run_key(model_cfg: LearnedTrackerConfig, settings: TrainSettings, meta: dict) -> str:
    """Config-addressable run identity: hash of everything that determines the result.

    Covers model config, training settings (minus non-semantic ``device``/``log_every``),
    variant choice, dataset identity, and mode — so (config, seed) fully determines a run and
    variant x seed sweeps can dispatch across machines without collisions.
    """
    s = dataclasses.asdict(settings)
    s.pop("device", None)
    s.pop("log_every", None)
    payload = {"model_cfg": dataclasses.asdict(model_cfg), "settings": s, **meta}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _subset(ds: SequenceDataset, n: int) -> SequenceDataset:
    """First-``n``-sequences view of a split (for the overfit-one gate)."""
    return dataclasses.replace(
        ds,
        spectra=ds.spectra[:n],
        B_true=ds.B_true[:n],
        resonance_freqs=ds.resonance_freqs[:n],
        line_axis=ds.line_axis[:n],
        line_transition=ds.line_transition[:n],
        collision_mask=ds.collision_mask[:n],
        line_collision=ds.line_collision[:n],
        seeds=ds.seeds[:n],
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Increment-2a training harness: learned tracker on sequence_sanity_v0"
    )
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--core", choices=("relu", "gated"), default="relu")
    ap.add_argument("--assoc", choices=("linear", "attention"), default="linear")
    ap.add_argument("--train-config", type=Path, default=DEFAULT_TRAIN_CFG)
    ap.add_argument("--model-config", type=Path, default=DEFAULT_MODEL_CFG)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--run-name", type=str, default=None,
                    help="default: <core>_<assoc>[_overfit1]")
    ap.add_argument("--overfit-one", action="store_true",
                    help="sanity gate: fit one training sequence (val = same sequence)")
    # Optional overrides of the YAML TrainSettings.
    ap.add_argument("--epochs", type=int, default=None)
    ap.add_argument("--batch-size", type=int, default=None)
    ap.add_argument("--lr", type=float, default=None)
    ap.add_argument("--patience", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--device", type=str, default=None)
    ap.add_argument("--val-every", type=int, default=None)
    ap.add_argument("--noise-snr", type=float, default=None,
                    help="shot-noise augmentation: photon budget sized so the FAINTEST line "
                         "(manifest line_depths) has this dip SNR; train gets fresh "
                         "realizations per epoch, val a fixed realization (seeded)")
    args = ap.parse_args()

    settings = load_config(args.train_config, TrainSettings)
    for name in ("epochs", "batch_size", "lr", "patience", "seed", "device", "val_every"):
        val = getattr(args, name)
        if val is not None:
            setattr(settings, name, val)
    if args.overfit_one and args.epochs is None:
        settings.epochs = 800  # the gate converges fast; keep the loop short by default

    device = preflight_device(settings.device)

    # Dataset + model config (n_freq/dt_s come from the manifest, not the YAML).
    loader = SequenceDatasetLoader(args.dataset)
    m = loader.manifest
    freq_range = (float(m["freq_range_Hz"][0]), float(m["freq_range_Hz"][1]))
    model_cfg = load_config(args.model_config, LearnedTrackerConfig)
    model_cfg.n_freq = int(m["n_freq_points"])
    model_cfg.n_lines = int(m["n_lines"])
    model_cfg.dt_s = float(m["dt_s"])
    print(f"[data] {args.dataset} | config_hash {m.get('config_hash')} | "
          f"T={m['n_timesteps']} F={model_cfg.n_freq} L={model_cfg.n_lines} | "
          f"K={model_cfg.n_candidates} anchors")

    train_ds = loader.load_split("train")
    # Input normalization from the data itself (deterministic given the dataset): dips are
    # ~0.4% of baseline on the real data, so rescale them to O(1) for the extractor.
    contrast = nominal_contrast(train_ds.spectra)
    model_cfg.input_gain = 1.0 / contrast
    print(f"[data] nominal contrast {contrast:.5f} -> input_gain {model_cfg.input_gain:.1f}")

    noise_photons: float | None = None
    if args.noise_snr is not None:
        from nv_sensor_sim.physics.shot_noise import photons_for_dip_snr

        faintest = float(np.min(np.asarray(m["line_depths"])))
        noise_photons = float(photons_for_dip_snr(faintest, args.noise_snr))
        settings.noise_photons = noise_photons
        print(f"[noise] augmentation: SNR_faintest={args.noise_snr:g} on depth {faintest:.5f} "
              f"-> {noise_photons:.3e} photons/point")

    set_seed(settings.seed)
    tracker = build_tracker(model_cfg, core=args.core, association=args.assoc).to(device)
    n_params = sum(p.numel() for p in tracker.parameters() if p.requires_grad)
    print(f"[model] core={args.core} assoc={args.assoc} | {n_params:,} trainable params")

    if args.overfit_one:
        train_ds = _subset(train_ds, 1)
        val_ds = train_ds
        print("[mode] overfit-one sanity gate: 1 training sequence, val = same sequence")
    else:
        val_ds = loader.load_split("val")
    if noise_photons is not None:
        # Fixed noisy realization for the val split (stable early stopping); train-side
        # noise is drawn fresh per epoch inside the loop.
        from nv_sensor_sim.physics.shot_noise import apply_shot_noise

        val_ds = dataclasses.replace(
            val_ds,
            spectra=apply_shot_noise(
                val_ds.spectra, noise_photons, seed=settings.seed + 1
            ).astype(np.float32),
        )
        print("[noise] val split: fixed shot-noise realization (seed = train seed + 1)")
    anchors = tracker.extractor.get_buffer("anchors").cpu()
    train_t = build_split_tensors(train_ds, anchors, freq_range, model_cfg.proj_scale_T, device)
    val_t = build_split_tensors(val_ds, anchors, freq_range, model_cfg.proj_scale_T, device)
    print(f"[data] train {train_t.n_sequences} seqs | val {val_t.n_sequences} seqs")

    run_name = args.run_name or f"{args.core}_{args.assoc}{'_overfit1' if args.overfit_one else ''}"
    out_dir = args.out / run_name
    meta = {
        "core": args.core,
        "association": args.assoc,
        "dataset": str(args.dataset),
        "dataset_config_hash": m.get("config_hash"),
        "freq_range_Hz": list(freq_range),
        "overfit_one": bool(args.overfit_one),
        "noise_photons": noise_photons,  # None = trained noiseless
    }
    key = run_key(model_cfg, settings, meta)
    meta["run_key"] = key
    print(f"[run] {run_name} | run_key {key} (config+seed fully determine this run)")
    result = train(
        tracker,
        train_t,
        val_t,
        settings,
        scores_are_probs=(args.assoc == "attention"),
        out_dir=out_dir,
        ckpt_meta=meta,
    )

    # Final numbers on the (best-weights) tracker: anchor-level proxy + physical association
    # (the evaluation/metrics.py pipeline the Increment-1 bar uses).
    tracker.eval()
    with torch.no_grad():
        out = tracker(val_t.spectra)
        acc = anchor_assoc_accuracy(out.scores, val_t.assoc_targets, val_t.line_collision)
    label = "train-seq" if args.overfit_one else "val"
    print(f"[result] best val total {result.best_val_total:.4f} @ epoch {result.best_epoch} "
          f"({result.epochs_run} epochs, {result.wall_s:.1f}s)")
    print(f"[result] {label} anchor-level assoc acc (proxy): overall {acc['assoc_acc']:.4f} | "
          f"in-collision {acc['assoc_acc_in_coll']:.4f} | "
          f"out {acc['assoc_acc_out_coll']:.4f}")

    tracked_hz = out.tracked_freqs.cpu().numpy() * (freq_range[1] - freq_range[0]) + freq_range[0]
    phys = {"overall": [], "in_collision": [], "out_collision": []}
    for n in range(val_ds.spectra.shape[0]):
        ta = resolve_true_axis(tracked_hz[n], val_ds.resonance_freqs[n], val_ds.line_axis[n])
        pred = np.broadcast_to(LINE_AXIS_8, ta.shape)
        a = association_accuracy(pred, ta, line_collision=val_ds.line_collision[n])
        for k in phys:
            phys[k].append(a[k])
    phys_med = {k: float(np.nanmedian(v)) for k, v in phys.items()}
    print(f"[result] {label} PHYSICAL assoc acc (median/seq): overall {phys_med['overall']:.4f} | "
          f"in-collision {phys_med['in_collision']:.4f} | out {phys_med['out_collision']:.4f}")

    if args.overfit_one:
        ok = phys_med["overall"] >= 0.95 and phys_med["out_collision"] >= 0.98
        print(f"[gate] overfit-one {'PASS' if ok else 'FAIL'} "
              f"(require physical assoc overall >= 0.95 and out-of-collision >= 0.98; "
              f"in-collision attribution is ambiguous within k*Gamma of a merge)")
        if not ok:
            return 1

    with open(out_dir / "summary.json", "w") as fh:
        json.dump(
            {
                "run_name": run_name,
                "run_key": key,
                "device": str(device),
                "device_name": torch.cuda.get_device_name(0) if device.type == "cuda" else "cpu",
                "settings": dataclasses.asdict(settings),
                "model_cfg": dataclasses.asdict(model_cfg),
                "core": args.core,
                "association": args.assoc,
                "overfit_one": bool(args.overfit_one),
                "best_epoch": result.best_epoch,
                "best_val_total": result.best_val_total,
                "epochs_run": result.epochs_run,
                "wall_s": result.wall_s,
                "final_anchor_acc": acc,
                "final_physical_assoc_median": phys_med,
                "n_trainable_params": n_params,
                "dataset_config_hash": m.get("config_hash"),
            },
            fh,
            indent=2,
        )
    print(f"[artifacts] {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
