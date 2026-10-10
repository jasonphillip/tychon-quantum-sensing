"""B2.6 — Train 8 FCNN-v2 instances on production_50k_v3_vector windows.

Pipeline per axis-sign pair (axis_idx in 0..3, sign in {+1, -1}):

1. Compute expected dip frequencies for each spectrum from `labels` (the
   true lab-frame B-field vector) and the canonical NV-axis geometry.
2. Slice a 100-bin window centred on each spectrum's expected dip; mask
   out spectra where the dip is out of grid bounds for that pair.
3. Symmetric-normalize each window to [-1, +1]; set lock_bin = 50 (the
   window centre, since each window is dip-centred by construction).
4. Train OdmrFCNNv2 via :func:`cascade.train_stage.train_stage`, which
   handles FX-graph QAT, ONNX/TFLite INT8 export, and ops_guard against
   the V250 op whitelist.
5. Emit per-window MAE on val and persist a JSON summary.

The script supports a `--smoke` mode that trains *one* channel
(axis=0, sign=+1) for 2 epochs on a 1000-sample subset to verify the
end-to-end pipeline before kicking off the full 8-channel run.

Outputs (full run):
    exports/vector_v1/window_axis{i}_sign{p|m}/
        coarse_int8.tflite  (~7-8 KB; ONNX co-located alongside)
        checkpoints/best_model.pt
        sigma_trajectory.csv
    exports/vector_v1/training_summary.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import warnings
from pathlib import Path

import h5py
import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from odmr_edge_ml.vector.anchors import (  # noqa: E402
    bias_from_manifest,
    coarse_fit_field,
    coarse_fit_lock_bins,
    oracle_lock_bins,
    prior_lock_bins,
)
from odmr_edge_ml.cascade.train_stage import train_stage  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vector_v1_train")

DEFAULT_DATASET = Path(
    "~/projects/nv-sensor-sim/artifacts/datasets/production_50k_v3_vector/dataset.h5"
)
DEFAULT_OUT = _REPO / "exports/vector_v1"


def _symmetric_norm(spectra: np.ndarray) -> np.ndarray:
    """Per-spectrum min/max → [-1, +1] (matches the v2_dataset_a path).

    For the v3_vector full-spectrum FCNN-per-axis path, the *position* of
    the per-axis dip across the 800-bin spectrum encodes B·n_i, so the
    symmetric norm preserves the discriminative signal.
    """
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    return 2.0 * (spectra - s_min) / denom - 1.0


def _load_split(h5: h5py.File, split: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load (spectra, labels_T, frequencies) for one split."""
    spec_ds = h5[f"{split}/spectra"]
    lab_ds = h5[f"{split}/labels"]
    freq_ds = h5[f"{split}/frequencies"]
    assert (
        isinstance(spec_ds, h5py.Dataset)
        and isinstance(lab_ds, h5py.Dataset)
        and isinstance(freq_ds, h5py.Dataset)
    )
    return (
        np.asarray(spec_ds[:], dtype=np.float64),
        np.asarray(lab_ds[:], dtype=np.float64),
        np.asarray(freq_ds[:], dtype=np.float64),
    )


def _prepare_channel(
    spectra: np.ndarray,
    labels_T: np.ndarray,
    freq_grid: np.ndarray,
    axis_idx: int,
    sign: int,
    window_size: int,  # unused in full-spectrum mode; kept for CLI compat
    anchor_source: str = "oracle",
    bias_B0_T: np.ndarray | None = None,
    coarse_fields_T: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Build per-axis-sign training data on the FULL spectrum.

    Each of the 8 FCNN-v2 instances sees the same 800-bin spectrum but is
    asked to predict its assigned ``B·n_i × sign`` projection. The model
    learns to specialize attention on its target resonance band. This
    avoids the label-leak that label-derived windowing would introduce on
    the v3_vector dataset (where bias direction + magnitude vary per
    spectrum and dip positions move ±50 bins from the linear-Zeeman
    prediction due to 2nd-order transverse-mixing corrections).

    ``window_size`` is preserved as the FCNN ``input_dim``; the caller
    should set it to ``spectra.shape[1]`` (typically 800) for this mode.
    """
    del window_size  # signature kept for backward-compat with main()
    spec_norm = _symmetric_norm(spectra)
    # Per-axis-sign label: signed projection of B onto NV axis i, in µT.
    from odmr_edge_ml.vector.windowing import NV_AXES_UNIT
    proj_T = (labels_T @ NV_AXES_UNIT.T)[:, axis_idx]
    labels_uT = (float(sign) * proj_T * 1e6).astype(np.float64)
    # Use either the label-derived anchor or the fixed bias-field prior.
    if anchor_source == "oracle":
        lock_bins = oracle_lock_bins(labels_T, freq_grid, axis_idx, sign)
    elif anchor_source == "prior":
        if bias_B0_T is None:
            raise ValueError("Prior anchor requires a bias vector")
        lock_bins = prior_lock_bins(bias_B0_T, freq_grid, axis_idx, sign, len(labels_T))
    elif anchor_source == "coarse_fit":
        fields = coarse_fields_T if coarse_fields_T is not None else coarse_fit_field(spectra, freq_grid)
        lock_bins = coarse_fit_lock_bins(fields, freq_grid, axis_idx, sign)
    else:
        raise ValueError(f"Unknown anchor source: {anchor_source}")
    return (
        spec_norm,
        lock_bins,
        labels_uT,
        int(spec_norm.shape[0]),
        int(spec_norm.shape[0]),
    )


def _channel_dirname(axis_idx: int, sign: int) -> str:
    return f"window_axis{axis_idx}_sign{'p' if sign > 0 else 'm'}"


def _run_one_channel(
    axis_idx: int,
    sign: int,
    train: tuple[np.ndarray, np.ndarray, np.ndarray],
    val: tuple[np.ndarray, np.ndarray, np.ndarray],
    out_root: Path,
    epochs: int,
    batch_size: int,
    huber_delta: float,
    window_size: int,
    seed: int,
    n_train_cap: int | None,
    n_val_cap: int | None,
    device: torch.device,
    use_compile: bool | None = None,
    use_autocast: bool | None = None,
    anchor_source: str = "oracle",
    bias_B0_T: np.ndarray | None = None,
    train_coarse_fields_T: np.ndarray | None = None,
    val_coarse_fields_T: np.ndarray | None = None,
) -> dict:
    train_spec, train_lab, freq = train
    val_spec, val_lab, _ = val

    t0 = time.time()
    tr_x, tr_lb, tr_y, n_tr_valid, n_tr_total = _prepare_channel(
        train_spec, train_lab, freq, axis_idx, sign, window_size, anchor_source, bias_B0_T,
        train_coarse_fields_T,
    )
    va_x, va_lb, va_y, n_va_valid, n_va_total = _prepare_channel(
        val_spec, val_lab, freq, axis_idx, sign, window_size, anchor_source, bias_B0_T,
        val_coarse_fields_T,
    )
    log.info(
        "channel axis=%d sign=%+d valid: train %d/%d (%.1f%%)  val %d/%d (%.1f%%)",
        axis_idx, sign, n_tr_valid, n_tr_total, 100 * n_tr_valid / n_tr_total,
        n_va_valid, n_va_total, 100 * n_va_valid / n_va_total,
    )

    if n_train_cap is not None and len(tr_y) > n_train_cap:
        rng = np.random.default_rng(seed)
        idx = rng.choice(len(tr_y), size=n_train_cap, replace=False)
        tr_x, tr_lb, tr_y = tr_x[idx], tr_lb[idx], tr_y[idx]
    if n_val_cap is not None and len(va_y) > n_val_cap:
        va_x, va_lb, va_y = va_x[:n_val_cap], va_lb[:n_val_cap], va_y[:n_val_cap]

    log.info(
        "channel axis=%d sign=%+d training on %d / %d (val); label range µT [%.2f, %.2f]",
        axis_idx, sign, len(tr_y), len(va_y), tr_y.min(), tr_y.max(),
    )

    out_dir = out_root / _channel_dirname(axis_idx, sign)
    out_dir.mkdir(parents=True, exist_ok=True)

    result = train_stage(
        name=f"axis{axis_idx}_sign{'p' if sign > 0 else 'm'}",
        train_spectra_norm=tr_x.astype(np.float32),
        train_lock_bins=tr_lb,
        train_labels_uT=tr_y.astype(np.float32),
        val_spectra_norm=va_x.astype(np.float32),
        val_lock_bins=va_lb,
        val_labels_uT=va_y.astype(np.float32),
        output_dir=out_dir,
        device=device,
        input_dim=window_size,
        epochs=epochs,
        batch_size=batch_size,
        huber_delta=huber_delta,
        seed=seed,
        num_workers=2,
        use_compile=use_compile,
        use_autocast=use_autocast,
    )

    elapsed = time.time() - t0
    return {
        "axis_idx": axis_idx,
        "sign": sign,
        "n_train_valid": n_tr_valid,
        "n_train_used": int(len(tr_y)),
        "n_val_valid": n_va_valid,
        "n_val_used": int(len(va_y)),
        "label_train_min_uT": float(tr_y.min()),
        "label_train_max_uT": float(tr_y.max()),
        "label_val_min_uT": float(va_y.min()),
        "label_val_max_uT": float(va_y.max()),
        "val_mae_uT": float(result.val_metrics.get("mae_uT", float("nan"))),
        "export_val_mae_uT": result.export_val_mae_uT,
        "val_rmse_uT": float(result.val_metrics.get("rmse_uT", float("nan"))),
        "learned_sigma": float(result.learned_sigma),
        "n_params": int(result.n_params),
        "tflite_path": str(result.tflite_path),
        "onnx_path": str(result.onnx_path),
        "wall_time_s": elapsed,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--anchor-source", choices=("oracle", "prior", "coarse_fit"), default="oracle")
    ap.add_argument("--smoke", action="store_true",
                    help="One channel (axis=0, sign=+1), 2 epochs, 1000 train samples")
    ap.add_argument("--epochs", type=int, default=100)
    ap.add_argument("--no-autocast", action="store_true",
                    help="train in fp32 (bf16 autocast on CUDA breaks checkpoint/validation parity)")
    ap.add_argument("--no-compile", action="store_true",
                    help="Disable torch.compile for every channel")
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--huber-delta", type=float, default=200.0)
    ap.add_argument("--window-size", type=int, default=800,
                    help="FCNN input_dim; use 800 for full v3_vector spectrum.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--channels",
        type=str,
        default=None,
        help='Comma-separated "axis,sign" pairs to train (e.g. "0,1" for axis=0 sign=+1, '
             '"0,-1;1,1" for two channels). Default: all 8.',
    )
    ap.add_argument(
        "--filter-target-axis",
        type=int,
        default=None,
        choices=[0, 1, 2, 3],
        help="If set, restrict train/val to samples within --filter-cone-deg of this NV axis. "
             "Both ±n_i half-spaces are kept (line-cone).",
    )
    ap.add_argument(
        "--filter-target-uvw",
        type=str,
        default=None,
        help='Lab-frame unit vector (e.g. "1,0,0") to use instead of an NV-axis target. '
             "Mutually exclusive with --filter-target-axis.",
    )
    ap.add_argument(
        "--filter-cone-deg",
        type=float,
        default=20.0,
        help="Half-angle of the direction-filter cone in degrees (used iff --filter-target-axis).",
    )
    ap.add_argument(
        "--filter-bmag-max-mT",
        type=float,
        default=None,
        help="If set, also restrict samples to |B| <= this magnitude in milliTesla "
             "(used to model a Path-B concentrator regime with low-magnitude bias).",
    )
    args = ap.parse_args()
    bias_B0_T = bias_from_manifest(args.dataset) if args.anchor_source == "prior" else None

    if not torch.cuda.is_available():
        raise SystemExit("CUDA not available — refusing to train on CPU per CLAUDE.md")
    device = torch.device("cuda")
    log.info("device=%s name=%s", device, torch.cuda.get_device_name(0))

    log.info("loading dataset: %s", args.dataset)
    with h5py.File(args.dataset, "r") as h5:
        train = _load_split(h5, "train")
        val = _load_split(h5, "val")
    log.info(
        "loaded train=%d val=%d  freq_grid n=%d %.4f-%.4f GHz",
        train[0].shape[0], val[0].shape[0], train[2].size,
        train[2][0] / 1e9, train[2][-1] / 1e9,
    )

    # Optional direction-cone + magnitude filter — restrict samples to within
    # args.filter_cone_deg of ±target direction (NV axis, lab-frame uvw, or
    # both half-spaces line-cone) and optionally |B| ≤ args.filter_bmag_max_mT.
    if (
        args.filter_target_axis is not None
        or args.filter_target_uvw is not None
        or args.filter_bmag_max_mT is not None
    ):
        from odmr_edge_ml.vector.windowing import NV_AXES_UNIT
        bmag_max_T = (args.filter_bmag_max_mT or float("inf")) * 1e-3
        cos_thresh = float(np.cos(np.radians(args.filter_cone_deg)))
        n_ref: np.ndarray | None = None
        target_label = None
        if args.filter_target_uvw is not None:
            if args.filter_target_axis is not None:
                raise SystemExit("--filter-target-uvw and --filter-target-axis are mutually exclusive")
            vec = np.array([float(x) for x in args.filter_target_uvw.split(",")], dtype=np.float64)
            n_ref = vec / np.linalg.norm(vec)
            target_label = f"uvw=[{','.join(f'{x:.3f}' for x in n_ref)}]"
        elif args.filter_target_axis is not None:
            n_ref = NV_AXES_UNIT[args.filter_target_axis]
            target_label = f"nv-axis={args.filter_target_axis}"

        def _filter(split):
            spec, lab, freq = split
            mag = np.linalg.norm(lab, axis=1)
            keep_mag = mag <= bmag_max_T
            if n_ref is not None:
                unit = lab / np.where(mag[:, None] == 0, 1.0, mag[:, None])
                cos_angle = np.abs(unit @ n_ref)  # line-cone (axis is bidirectional)
                keep_dir = cos_angle >= cos_thresh
            else:
                keep_dir = np.ones_like(mag, dtype=bool)
            keep = keep_mag & keep_dir
            log.info(
                "  filter: target=%s cone=%.1f° |B|≤%.2fmT keeps %d/%d (%.1f%%)",
                target_label, args.filter_cone_deg,
                args.filter_bmag_max_mT or float('inf'),
                int(keep.sum()), len(keep), 100 * keep.mean(),
            )
            return spec[keep], lab[keep], freq

        train = _filter(train)
        val = _filter(val)

    train_coarse_fields_T = None
    val_coarse_fields_T = None
    if args.anchor_source == "coarse_fit":
        train_coarse_fields_T = coarse_fit_field(train[0], train[2])
        val_coarse_fields_T = coarse_fit_field(val[0], val[2])

    args.out.mkdir(parents=True, exist_ok=True)

    if args.channels is not None:
        channel_list: list[tuple[int, int]] = []
        for tok in args.channels.split(";"):
            ax_str, sg_str = tok.strip().split(",")
            channel_list.append((int(ax_str), int(sg_str)))
        log.info("CHANNEL FILTER: training only %s", channel_list)
    else:
        channel_list = [(i, s) for i in range(4) for s in (+1, -1)]

    if args.smoke:
        log.info("SMOKE MODE: axis=0, sign=+1, epochs=%d, n_train_cap=5000", args.epochs)
        results = [
            _run_one_channel(
                axis_idx=0, sign=+1,
                train=train, val=val,
                out_root=args.out, epochs=args.epochs, batch_size=args.batch_size,
                huber_delta=args.huber_delta, window_size=args.window_size,
                seed=args.seed, n_train_cap=5000, n_val_cap=1000,
                device=device,
                use_compile=False if args.no_compile else None,
                use_autocast=False if args.no_autocast else None,
                anchor_source=args.anchor_source, bias_B0_T=bias_B0_T,
                train_coarse_fields_T=train_coarse_fields_T,
                val_coarse_fields_T=val_coarse_fields_T,
            )
        ]
    else:
        results = []
        for axis_idx, sign in channel_list:
            results.append(
                _run_one_channel(
                    axis_idx=axis_idx, sign=sign,
                    train=train, val=val,
                    out_root=args.out, epochs=args.epochs,
                    batch_size=args.batch_size,
                    huber_delta=args.huber_delta,
                    window_size=args.window_size,
                    seed=args.seed,
                    n_train_cap=None, n_val_cap=None,
                    device=device,
                    use_compile=False if args.no_compile else None,
                use_autocast=False if args.no_autocast else None,
                    anchor_source=args.anchor_source, bias_B0_T=bias_B0_T,
                    train_coarse_fields_T=train_coarse_fields_T,
                    val_coarse_fields_T=val_coarse_fields_T,
                )
            )

    summary = {
        "dataset": str(args.dataset),
        "anchor_source": args.anchor_source,
        "smoke": args.smoke,
        "epochs": args.epochs,
        "use_compile": not args.no_compile,
        "use_autocast": not args.no_autocast,
        "huber_delta": args.huber_delta,
        "window_size": args.window_size,
        "seed": args.seed,
        "filter_target_axis": args.filter_target_axis,
        "filter_cone_deg": args.filter_cone_deg if args.filter_target_axis is not None else None,
        "channels": results,
    }
    summary_path = args.out / ("smoke_summary.json" if args.smoke else "training_summary.json")
    summary_path.write_text(json.dumps(summary, indent=2))
    log.info("wrote %s", summary_path)

    log.info("=== per-channel val MAE ===")
    for r in results:
        log.info(
            "  axis=%d sign=%+d  val_mae=%.3f µT  val_rmse=%.3f µT  σ=%.3f  wall=%.1fs",
            r["axis_idx"], r["sign"], r["val_mae_uT"], r["val_rmse_uT"],
            r["learned_sigma"], r["wall_time_s"],
        )


if __name__ == "__main__":
    main()
