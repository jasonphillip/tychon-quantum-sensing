"""B2.6 — Vector eval: 8 FCNN-v2 → BLUE → 3D residual on v3_vector test split.

For each test spectrum:

1. Symmetric-normalise the full 800-point spectrum.
2. For each of the 8 (axis_idx, sign) channels:
   - Compute the linear-Zeeman lock-bin anchor from the *label* (oracle
     anchor — see §1 of the closing memo for the explicit acknowledgement
     of this leak; equivalent to a fixed-bias-direction Path-A/B PID lock).
   - Run the channel's INT8 TFLite FCNN over the (spectrum, anchor) pair.
   - Output: scalar prediction of ``B · n_i × sign`` in µT.
3. Mask channels whose dip lies outside the 80 MHz spectral grid via the
   windowing utility's `valid_mask` — those FCNN outputs are unreliable
   because the dip isn't visible.
4. BLUE inversion per spectrum with per-channel σ from training_summary
   (val MAE per channel) for in-grid channels, large σ for out-of-grid
   channels. Recovers a 3D B̂.

Headline metrics:
- 3D vector residual ‖B̂ − B_true‖ on test: RMS / mean / p50 / p90.
- Per-axis residual decomposition.
- Per-channel test MAE (sanity check vs val MAE).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
import warnings
from pathlib import Path

import h5py
import numpy as np

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))

from odmr_edge_ml.vector.blue_projection import (  # noqa: E402
    blue_project,
    nv_axis_geometry_matrix,
)
from odmr_edge_ml.vector.anchors import (  # noqa: E402
    bias_from_manifest,
    coarse_fit_field,
    coarse_fit_lock_bins,
    jitter_bins,
    oracle_lock_bins,
    prior_lock_bins,
    spectrum_lock_bins,
)
from odmr_edge_ml.vector.windowing import (  # noqa: E402
    NV_AXES_UNIT,
    build_windows_for_axis_sign,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vector_v1_eval")

DEFAULT_DATASET = Path(
    "~/projects/nv-sensor-sim/artifacts/datasets/production_50k_v3_vector/dataset.h5"
)
DEFAULT_MODELS = _REPO / "exports/vector_v1"
MASKED_SIGMA_UT = 1e6  # effectively infinity for out-of-grid resonances


def _symmetric_norm(spectra: np.ndarray) -> np.ndarray:
    s_min = spectra.min(axis=1, keepdims=True)
    s_max = spectra.max(axis=1, keepdims=True)
    denom = np.where(s_max == s_min, 1.0, s_max - s_min)
    return 2.0 * (spectra - s_min) / denom - 1.0


def _channel_dirname(axis_idx: int, sign: int) -> str:
    return f"window_axis{axis_idx}_sign{'p' if sign > 0 else 'm'}"


def _channel_tag(axis_idx: int, sign: int) -> str:
    return f"axis{axis_idx}_sign{'p' if sign > 0 else 'm'}"


def _load_tflite(tflite_path: Path):
    import tensorflow as tf
    interp = tf.lite.Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    return interp


def _tflite_predict_batch(
    interp,
    spectra_norm: np.ndarray,
    lock_bins: np.ndarray,
    sigma_anchor: float,
    *,
    spectrum_scale: float = 1.0,
    anchor_scale: float = 1.0,
) -> np.ndarray:
    in_det = interp.get_input_details()[0]
    out_det = interp.get_output_details()[0]
    input_dim = spectra_norm.shape[1]
    in_scale, in_zp = in_det["quantization"]
    out_scale, out_zp = out_det["quantization"]

    bins = np.arange(input_dim, dtype=np.float32)[None, :]
    preds = np.zeros(len(spectra_norm), dtype=np.float64)
    for i in range(len(spectra_norm)):
        anchor = np.exp(
            -0.5 * ((bins - float(lock_bins[i])) / max(sigma_anchor, 0.1)) ** 2
        ).astype(np.float32)
        chan0 = spectra_norm[i].astype(np.float32) * spectrum_scale
        nhwc = np.stack([chan0, anchor[0] * anchor_scale], axis=-1).reshape(1, 1, input_dim, 2)
        q = np.clip(np.round(nhwc / in_scale + in_zp), -128, 127).astype(np.int8)
        interp.set_tensor(in_det["index"], q)
        interp.invoke()
        y = interp.get_tensor(out_det["index"])
        preds[i] = (float(y.flatten()[0]) - out_zp) * out_scale
    return preds


def _dataset_md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _assemble_results(
    metrics: dict,
    *,
    anchor_source: str,
    condition: str,
    anchor_noise_bins: float,
    dataset_md5: str,
    regenerated_dataset: bool,
    wall_s: float,
) -> dict:
    """Attach ablation provenance to the measured evaluation results."""
    return {
        **metrics,
        "anchor_source": anchor_source,
        "condition": condition,
        "anchor_noise_bins": anchor_noise_bins,
        "oracle_conditioned": anchor_source == "oracle",
        "dataset_md5": dataset_md5,
        "regenerated_dataset": regenerated_dataset,
        "wall_s": wall_s,
    }


def _coarse_fit_diagnostics(coarse_fields: np.ndarray, labels_T: np.ndarray) -> dict:
    """Summarize field error with the spectrum's B/-B ambiguity."""
    coarse_mag = np.linalg.norm(coarse_fields, axis=1)
    true_mag = np.linalg.norm(labels_T, axis=1)
    dot = np.sum(coarse_fields * labels_T, axis=1)
    cosine = np.abs(dot) / np.maximum(coarse_mag * true_mag, 1e-30)
    return {
        "coarse_fit_angle_err_deg_median": float(np.median(
            np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
        )),
        "coarse_fit_mag_err_T_median": float(np.median(np.abs(coarse_mag - true_mag))),
    }


def _per_channel_sigma_from_summary(summary_path: Path) -> dict[tuple[int, int], float]:
    """Read val MAE per channel from training_summary.json — used as Σ diag."""
    if not summary_path.exists():
        log.warning("training_summary.json not found at %s; defaulting σ=100 µT", summary_path)
        return {}
    blob = json.loads(summary_path.read_text())
    out: dict[tuple[int, int], float] = {}
    for ch in blob.get("channels", []):
        out[(int(ch["axis_idx"]), int(ch["sign"]))] = float(ch["val_mae_uT"])
    return out


def main() -> None:
    wall_start = time.monotonic()
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    ap.add_argument("--models", type=Path, default=DEFAULT_MODELS)
    ap.add_argument("--split", choices=("val", "test"), default="test")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--sigma-anchor", type=float, default=1.5)
    ap.add_argument("--anchor-source", choices=("oracle", "prior", "spectrum", "coarse_fit"), default="oracle")
    ap.add_argument("--spectrum-window-bins", type=int, default=25)
    ap.add_argument("--condition", choices=("full", "spectrum_only", "anchor_only", "noisy_anchor"), default="full")
    ap.add_argument("--anchor-noise-bins", type=float, default=0.0)
    ap.add_argument("--bias-B0-T", type=float, nargs=3, metavar=("X", "Y", "Z"), default=None)
    ap.add_argument("--regenerated-dataset", action="store_true")
    ap.add_argument("--default-sigma-uT", type=float, default=100.0,
                    help="Per-channel BLUE Σ when training_summary not found")
    ap.add_argument("--out-json", type=Path, default=None)
    ap.add_argument(
        "--filter-target-uvw",
        type=str,
        default=None,
        help='Lab-frame target direction (e.g. "1,0,0") for filtering the test '
             "split to a Path-A/B-like fixed-direction subset.",
    )
    ap.add_argument("--filter-cone-deg", type=float, default=30.0)
    ap.add_argument("--filter-bmag-max-mT", type=float, default=None)
    args = ap.parse_args()
    if args.anchor_noise_bins < 0:
        ap.error("--anchor-noise-bins must be non-negative")
    if args.spectrum_window_bins < 0:
        ap.error("--spectrum-window-bins must be non-negative")
    bias_B0_T = None
    if args.anchor_source in ("prior", "spectrum"):
        try:
            bias_B0_T = (
                np.asarray(args.bias_B0_T, dtype=np.float64)
                if args.bias_B0_T is not None else bias_from_manifest(args.dataset)
            )
        except ValueError as exc:
            ap.error(f"{exc}; supply --bias-B0-T X Y Z")
    rng = np.random.default_rng(0)

    log.info("loading split=%s from %s", args.split, args.dataset)
    with h5py.File(args.dataset, "r") as h5:
        spec_ds = h5[f"{args.split}/spectra"]
        lab_ds = h5[f"{args.split}/labels"]
        freq_ds = h5[f"{args.split}/frequencies"]
        assert (
            isinstance(spec_ds, h5py.Dataset)
            and isinstance(lab_ds, h5py.Dataset)
            and isinstance(freq_ds, h5py.Dataset)
        )
        n_total = spec_ds.shape[0]
        take = min(args.n, n_total)
        spec_raw = np.asarray(spec_ds[:take], dtype=np.float64)
        lab_T = np.asarray(lab_ds[:take], dtype=np.float64)
        freq = np.asarray(freq_ds[:], dtype=np.float64)

    # Optional Path-A/B subset filter
    if args.filter_target_uvw is not None or args.filter_bmag_max_mT is not None:
        bmag_max_T = (args.filter_bmag_max_mT or float("inf")) * 1e-3
        cos_thresh = float(np.cos(np.radians(args.filter_cone_deg)))
        if args.filter_target_uvw is not None:
            vec = np.array([float(x) for x in args.filter_target_uvw.split(",")], dtype=np.float64)
            n_ref = vec / np.linalg.norm(vec)
        else:
            n_ref = None
        mag = np.linalg.norm(lab_T, axis=1)
        keep_mag = mag <= bmag_max_T
        if n_ref is not None:
            unit = lab_T / np.where(mag[:, None] == 0, 1.0, mag[:, None])
            keep_dir = np.abs(unit @ n_ref) >= cos_thresh
        else:
            keep_dir = np.ones_like(mag, dtype=bool)
        keep = keep_mag & keep_dir
        log.info(
            "split filter: uvw=%s cone=%.1f° |B|≤%.2fmT keeps %d/%d (%.1f%%)",
            args.filter_target_uvw, args.filter_cone_deg,
            args.filter_bmag_max_mT or float('inf'),
            int(keep.sum()), len(keep), 100 * keep.mean(),
        )
        spec_raw = spec_raw[keep]
        lab_T = lab_T[keep]
        take = int(keep.sum())

    log.info(
        "split=%s n=%d |B| range µT min=%.0f mean=%.0f max=%.0f",
        args.split, take,
        np.linalg.norm(lab_T, axis=1).min() * 1e6,
        np.linalg.norm(lab_T, axis=1).mean() * 1e6,
        np.linalg.norm(lab_T, axis=1).max() * 1e6,
    )

    spec_norm = _symmetric_norm(spec_raw)
    coarse_fields = coarse_fit_field(spec_raw, freq) if args.anchor_source == "coarse_fit" else None

    # Per-channel σ from training_summary.json (val MAE = posterior uncertainty)
    sigma_map = _per_channel_sigma_from_summary(args.models / "training_summary.json")

    pred_matrix = np.zeros((take, 8), dtype=np.float64)
    valid_matrix = np.zeros((take, 8), dtype=bool)
    true_matrix = np.zeros((take, 8), dtype=np.float64)
    per_channel: list[dict] = []
    sigma_for_blue = np.zeros((take, 8), dtype=np.float64)

    for ch_idx, (axis_idx, sign) in enumerate(
        [(i, s) for i in range(4) for s in (+1, -1)]
    ):
        dirname = _channel_dirname(axis_idx, sign)
        tag = _channel_tag(axis_idx, sign)
        tflite_path = args.models / dirname / f"{tag}_int8.tflite"
        if not tflite_path.exists():
            log.warning("missing TFLite for %s at %s — skipping", tag, tflite_path)
            sigma_for_blue[:, ch_idx] = MASKED_SIGMA_UT
            continue

        if args.anchor_source == "oracle":
            lock_bins = oracle_lock_bins(lab_T, freq, axis_idx, sign)
        elif args.anchor_source == "coarse_fit":
            assert coarse_fields is not None
            lock_bins = coarse_fit_lock_bins(coarse_fields, freq, axis_idx, sign)
        else:
            assert bias_B0_T is not None
            lock_bins = prior_lock_bins(bias_B0_T, freq, axis_idx, sign, take)
            if args.anchor_source == "spectrum":
                lock_bins = spectrum_lock_bins(spec_norm, freq, lock_bins,
                                               window_bins=args.spectrum_window_bins)
        if args.condition == "noisy_anchor":
            lock_bins = jitter_bins(lock_bins, args.anchor_noise_bins, rng, len(freq))

        # Truth label = signed projection
        proj_T = (lab_T @ NV_AXES_UNIT.T)[:, axis_idx]
        true_matrix[:, ch_idx] = sign * proj_T * 1e6

        # In-grid mask: only channels whose dip lies in the 80 MHz window are
        # informative — the others get a large σ in BLUE
        wb = build_windows_for_axis_sign(
            spec_raw, lab_T, freq, axis_idx=axis_idx, sign=sign, window_size=100,
        )
        valid_matrix[:, ch_idx] = wb.valid_mask

        interp = _load_tflite(tflite_path)
        t0 = time.time()
        preds = _tflite_predict_batch(
            interp, spec_norm, lock_bins, sigma_anchor=args.sigma_anchor,
            spectrum_scale=0.0 if args.condition == "anchor_only" else 1.0,
            anchor_scale=0.0 if args.condition == "spectrum_only" else 1.0,
        )
        log.info("  CH%d %s  TFLite over %d samples in %.1fs",
                 ch_idx, tag, take, time.time() - t0)
        pred_matrix[:, ch_idx] = preds

        # Per-channel σ for BLUE: val MAE from training summary, with masked
        # rows blown up to effective infinity.
        per_sigma = float(sigma_map.get((axis_idx, sign), args.default_sigma_uT))
        sigma_for_blue[:, ch_idx] = np.where(
            valid_matrix[:, ch_idx], per_sigma, MASKED_SIGMA_UT
        )

        # Per-channel test MAE — sanity check that the model generalises to
        # the inverse-crime-shifted test distribution.
        in_window = valid_matrix[:, ch_idx]
        if in_window.any():
            err = np.abs(preds[in_window] - true_matrix[in_window, ch_idx])
            test_mae = float(np.mean(err))
            test_rmse = float(np.sqrt(np.mean(err ** 2)))
        else:
            test_mae = float("nan")
            test_rmse = float("nan")
        per_channel.append(
            {
                "axis_idx": axis_idx,
                "sign": sign,
                "n_in_grid": int(in_window.sum()),
                "test_mae_uT": test_mae,
                "test_rmse_uT": test_rmse,
                "val_mae_uT_from_summary": sigma_map.get((axis_idx, sign), None),
                "label_range_uT": [
                    float(true_matrix[:, ch_idx].min()),
                    float(true_matrix[:, ch_idx].max()),
                ],
            }
        )
        log.info(
            "    test MAE=%.2f µT (val σ=%.2f µT)  in-grid n=%d/%d",
            test_mae,
            sigma_map.get((axis_idx, sign), args.default_sigma_uT),
            int(in_window.sum()), take,
        )

    # BLUE per spectrum
    A = nv_axis_geometry_matrix()
    b_hat_uT = np.zeros((take, 3), dtype=np.float64)
    used_blue = np.zeros(take, dtype=bool)
    for i in range(take):
        if valid_matrix[i].sum() < 3:
            continue
        out = blue_project(pred_matrix[i], A, sigma=sigma_for_blue[i])
        b_hat_uT[i] = out.b_hat
        used_blue[i] = True

    lab_uT = lab_T * 1e6
    err_per_axis = b_hat_uT - lab_uT
    err_3d = np.linalg.norm(err_per_axis, axis=1)
    n_used = int(used_blue.sum())

    blue_rms = float(np.sqrt(np.mean(err_3d[used_blue] ** 2)))
    b_norm_mean = float(np.linalg.norm(lab_uT[used_blue], axis=1).mean())

    metrics = {
        "dataset": str(args.dataset),
        "models_dir": str(args.models),
        "split": args.split,
        "n_total": take,
        "n_blue_used": n_used,
        "constant_zero_baseline_mae_uT": float(
            np.mean(np.abs(true_matrix[valid_matrix]))
        ) if valid_matrix.any() else float("nan"),
        "per_channel": per_channel,
        "blue_3d_residual_uT": {
            "rms": blue_rms,
            "mean": float(np.mean(err_3d[used_blue])),
            "p50": float(np.median(err_3d[used_blue])),
            "p90": float(np.percentile(err_3d[used_blue], 90)),
            "max": float(err_3d[used_blue].max()),
        },
        "blue_3d_residual_pct_of_B": {
            "rms_over_b_mean": blue_rms / max(b_norm_mean, 1e-12),
        },
        "blue_per_axis_residual_uT": {
            "x_p50": float(np.median(np.abs(err_per_axis[used_blue, 0]))),
            "y_p50": float(np.median(np.abs(err_per_axis[used_blue, 1]))),
            "z_p50": float(np.median(np.abs(err_per_axis[used_blue, 2]))),
            "x_mae": float(np.mean(np.abs(err_per_axis[used_blue, 0]))),
            "y_mae": float(np.mean(np.abs(err_per_axis[used_blue, 1]))),
            "z_mae": float(np.mean(np.abs(err_per_axis[used_blue, 2]))),
        },
        "b_norm_true_uT": {
            "mean": b_norm_mean,
            "p50": float(np.median(np.linalg.norm(lab_uT[used_blue], axis=1))),
            "min": float(np.linalg.norm(lab_uT[used_blue], axis=1).min()),
            "max": float(np.linalg.norm(lab_uT[used_blue], axis=1).max()),
        },
    }
    if coarse_fields is not None:
        metrics.update(_coarse_fit_diagnostics(coarse_fields, lab_T))
    summary = _assemble_results(
        metrics,
        anchor_source=args.anchor_source,
        condition=args.condition,
        anchor_noise_bins=args.anchor_noise_bins,
        dataset_md5=_dataset_md5(args.dataset),
        regenerated_dataset=args.regenerated_dataset,
        wall_s=time.monotonic() - wall_start,
    )
    log.info("=== BLUE 3D vector residual (n=%d / %d) ===", n_used, take)
    log.info("  RMS=%.2f µT  mean=%.2f µT  p50=%.2f µT  p90=%.2f µT",
             summary["blue_3d_residual_uT"]["rms"],
             summary["blue_3d_residual_uT"]["mean"],
             summary["blue_3d_residual_uT"]["p50"],
             summary["blue_3d_residual_uT"]["p90"])
    log.info("  RMS as %% of <|B|>=%.1f µT: %.1f%%",
             b_norm_mean,
             100.0 * summary["blue_3d_residual_pct_of_B"]["rms_over_b_mean"])
    log.info("  per-axis |err| p50: x=%.2f y=%.2f z=%.2f µT",
             summary["blue_per_axis_residual_uT"]["x_p50"],
             summary["blue_per_axis_residual_uT"]["y_p50"],
             summary["blue_per_axis_residual_uT"]["z_p50"])

    noise_suffix = f"_n{args.anchor_noise_bins:g}" if args.anchor_noise_bins else ""
    out_path = args.out_json or (
        args.models / f"vector_v1_{args.split}_eval_{args.anchor_source}_{args.condition}{noise_suffix}.json"
    )
    out_path.write_text(json.dumps(summary, indent=2))
    log.info("wrote %s", out_path)


if __name__ == "__main__":
    main()
