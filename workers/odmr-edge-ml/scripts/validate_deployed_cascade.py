#!/usr/bin/env python3
"""Post-Phase-3b validation of the deployed cascade artifacts.

Independent re-check of exports/cascade_v1/ contents:

  1. cascade_manifest.json parses + structural invariants hold;
  2. coarse/fine TFLite SHA256s match on-disk file bytes;
  3. verify_bit_exact returns ok=True on the saved fixture;
  4. compose_quantized_then_dequant on the AIC val split:
        - cascade output min / max / mean / std (vs ±2.18 µT
          representable range — flags whether composition.output_quant
          is the binding authority constraint);
        - cascade deployed val MAE on field vs PID-only baseline.

Usage:
    python scripts/validate_deployed_cascade.py \\
        --cascade exports/cascade_v1/ \\
        --dataset production_50k_v2_aic
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import h5py
import numpy as np
from tychon_shared_data.cascade import (
    CascadeManifest,
    compose_quantized_then_dequant,
    verify_bit_exact,
)

REPO_ROOT = Path(__file__).resolve().parent.parent

# Local imports
sys.path.insert(0, str(REPO_ROOT / "src"))
from odmr_edge_ml.cascade.runners import make_float_runner, make_int8_runner  # noqa: E402
from odmr_edge_ml.evaluation.residual_dataset import _normalize_symmetric  # noqa: E402


def _build_anchor(lock_bins: np.ndarray, sigma: float, input_dim: int = 100) -> np.ndarray:
    bins = np.arange(input_dim, dtype=np.float32)[None, :]
    centers = lock_bins.astype(np.float32).reshape(-1, 1)
    sigma_eff = float(max(sigma, 0.1))
    return np.exp(-0.5 * ((bins - centers) / sigma_eff) ** 2).astype(np.float32)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cascade", default=REPO_ROOT / "exports/cascade_v1", type=Path)
    parser.add_argument("--dataset", default="production_50k_v2_aic")
    args = parser.parse_args()

    cascade_dir = Path(args.cascade)
    if not cascade_dir.exists():
        print(f"ERROR: cascade dir not found: {cascade_dir}", file=sys.stderr)
        return 2

    print("=" * 70)
    print(f"VALIDATING DEPLOYED CASCADE: {cascade_dir}")
    print("=" * 70)

    # ---- (1) Manifest parses + structural invariants ---------------------
    manifest_path = cascade_dir / "cascade_manifest.json"
    manifest = CascadeManifest.from_json(manifest_path)
    raw = json.loads(manifest_path.read_text())
    assert raw["coarse_model"]["quantization_granularity"] == "per_tensor"
    assert raw["fine_model"]["quantization_granularity"] == "per_tensor"
    assert raw["composition"]["mode"] == "additive_raw_x"
    assert raw["composition"]["rounding_mode"] == "TBD_AFTER_VECTORBLOX_DOC_CHECK"
    assert raw["composition"]["saturate_int8"] is True
    print("[1] manifest structural invariants: OK")

    # ---- (2) SHA256 match -------------------------------------------------
    for stage in ("coarse_model", "fine_model"):
        block = getattr(manifest, stage)
        path = cascade_dir / block["tflite_path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != block["tflite_sha256"]:
            print(f"FAIL: {stage} SHA256 drift", file=sys.stderr)
            return 3
        print(f"[2] {stage} SHA256: {actual[:16]}…  ({path.stat().st_size} bytes) OK")

    # ---- (3) verify_bit_exact on saved fixture ---------------------------
    fixture = np.load(cascade_dir / "bit_exact_fixture.npz")
    self_check_mode = str(fixture["self_check_rounding_mode"])
    bx_manifest = CascadeManifest.from_json(manifest_path)
    bx_manifest.composition["rounding_mode"] = self_check_mode
    coarse_int8_runner = make_int8_runner(cascade_dir / "coarse_int8.tflite")
    fine_int8_runner = make_int8_runner(cascade_dir / "fine_int8.tflite")
    ok, report = verify_bit_exact(
        fixture["x_int8"], fixture["expected_y_int8"], bx_manifest,
        coarse_runner=coarse_int8_runner, fine_runner=fine_int8_runner,
    )
    print(f"[3] verify_bit_exact (rounding={self_check_mode}): ok={ok} report={report}")
    if not ok:
        return 4

    # ---- (4) Cascade output stats + deployed MAE on val set --------------
    eval_report = json.loads((cascade_dir / "cascade_eval_report.json").read_text())
    coarse_sigma = float(eval_report["coarse_learned_sigma"])

    data_dir = REPO_ROOT / f"data/{args.dataset}" if not Path(args.dataset).is_absolute() else Path(args.dataset)
    npz = np.load(data_dir / "pid_residuals.npz")
    with h5py.File(data_dir / "dataset.h5", "r") as f:
        val_spectra_norm = _normalize_symmetric(f["val"]["spectra"][:])
    val_lock_bins = npz["val_lock_bins"]
    val_b_true = npz["val_b_mag_uT"].astype(np.float32)
    val_b_pid = npz["val_b_pid_uT"].astype(np.float32)

    val_anchors = _build_anchor(val_lock_bins, coarse_sigma)
    val_x = np.stack([val_spectra_norm, val_anchors], axis=-1)[:, None, :, :].astype(np.float32)
    cr = make_float_runner(cascade_dir / "coarse_int8.tflite")
    fr = make_float_runner(cascade_dir / "fine_int8.tflite")
    cascade_pred = compose_quantized_then_dequant(
        val_x, manifest, coarse_runner=cr, fine_runner=fr,
    ).reshape(-1)

    # Composition output_quant representable envelope
    comp_scale = float(manifest.composition["output_quant"]["scale"])
    comp_zp = int(manifest.composition["output_quant"]["zero_point"])
    rep_min = (-128 - comp_zp) * comp_scale
    rep_max = (127 - comp_zp) * comp_scale

    pred_min, pred_max = float(cascade_pred.min()), float(cascade_pred.max())
    pred_mean, pred_std = float(cascade_pred.mean()), float(cascade_pred.std())
    boundary_frac = float(
        ((cascade_pred <= rep_min + 1e-9) | (cascade_pred >= rep_max - 1e-9)).mean()
    )

    pid_only_err = np.abs(val_b_pid - val_b_true)
    cascade_err = np.abs(val_b_pid + cascade_pred - val_b_true)
    pid_mae = float(pid_only_err.mean())
    cascade_mae = float(cascade_err.mean())
    reduction_pct = (1.0 - cascade_mae / pid_mae) * 100.0

    print("[4] Cascade output stats on val (n={}):".format(len(cascade_pred)))
    print(f"    min={pred_min:.4f}  max={pred_max:.4f}  mean={pred_mean:.4f}  std={pred_std:.4f} µT")
    print(f"    representable range from composition.output_quant: "
          f"[{rep_min:.4f}, {rep_max:.4f}] µT")
    print(f"    fraction at representable boundary: {boundary_frac:.4f}")
    print(f"[4] PID-only val MAE:    {pid_mae:.4f} µT")
    print(f"[4] Cascade deployed MAE:{cascade_mae:.4f} µT")
    print(f"[4] Reduction vs PID:    {reduction_pct:+.2f} %")

    # ---- (5) Recover FINE clip fraction from training.log ---------------
    log_path = cascade_dir / "training.log"
    fine_clip = None
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            m = re.search(r"FINE label stats:.*clipped frac=([\d.]+)", line)
            if m:
                fine_clip = float(m.group(1))
    print(f"[5] FINE label clip fraction (from training.log): "
          f"{fine_clip:.4f}" if fine_clip is not None else "[5] FINE clip fraction: N/A (training.log absent)")

    print("=" * 70)
    print("ALL CHECKS PASSED")
    print("=" * 70)

    out = {
        "manifest_path": str(manifest_path),
        "cascade_pred_min": pred_min,
        "cascade_pred_max": pred_max,
        "cascade_pred_mean": pred_mean,
        "cascade_pred_std": pred_std,
        "representable_min": rep_min,
        "representable_max": rep_max,
        "fraction_at_boundary": boundary_frac,
        "pid_only_val_mae_uT": pid_mae,
        "cascade_deployed_val_mae_uT": cascade_mae,
        "reduction_pct_vs_pid": reduction_pct,
        "fine_label_clip_fraction": fine_clip,
        "verify_bit_exact_ok": bool(ok),
        "verify_bit_exact_report": report,
    }
    out_path = cascade_dir / "deployed_cascade_validation.json"
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"validation report: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
