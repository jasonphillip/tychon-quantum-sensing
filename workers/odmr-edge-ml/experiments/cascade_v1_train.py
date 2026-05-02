#!/usr/bin/env python3
"""Hierarchical INT8 cascade trainer (P3-11B Path B).

Trains COARSE + FINE OdmrFCNNv2 stages and emits a cascade_manifest.json
against tychon_shared_data.cascade.CascadeManifest. FINE corrects the
deployment-quantized COARSE residual (including COARSE's INT8 noise) so
the composed deployed cascade widens authority via composition rather
than via any single model gaining more clamp authority — preserves the
Lur'e/Circle Criterion sector bound per stage.

Usage:
    python experiments/cascade_v1_train.py \\
        --dataset production_50k_v2_aic --output exports/cascade_v1/

    python experiments/cascade_v1_train.py --quick     # smoke mode
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import warnings
from copy import deepcopy
from pathlib import Path

import h5py
import numpy as np
import torch

warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch.ao")

from tychon_shared_data.cascade import (
    CascadeManifest,
    compose_int8,
    compose_quantized_then_dequant,
    verify_bit_exact,
)

from odmr_edge_ml.cascade import (
    compute_fine_labels,
    emit_cascade_manifest,
    make_float_runner,
    make_int8_runner,
    quantize_input,
    train_stage,
)
from odmr_edge_ml.evaluation.residual_dataset import (
    _normalize_symmetric,
    generate_pid_labels,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "exports/cascade_v1"
CLAMP_UT = 2.25
INPUT_DIM = 100
BIT_EXACT_FIXTURE_SAMPLES = 32

# Self-check rounding mode for the local verify_bit_exact roundtrip. The
# DEPLOYED rounding mode is resolved by polarfire-hybrid-control after
# verifying VectorBlox SDK 2.0.x docs — so this is a wiring sanity test,
# not a deployment guarantee. The on-disk cascade_manifest.json keeps the
# canonical TBD placeholder per LOCKED CONTRACT #1.
SELF_CHECK_ROUNDING_MODE = "round_half_to_even"


def _resolve_dataset_dir(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.is_absolute() and p.exists():
        return p
    candidate = REPO_ROOT / "data" / name_or_path
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"dataset not found: {name_or_path}")


def _quant_from_tflite(tflite_path: Path) -> tuple[tuple[float, int], tuple[float, int]]:
    """Return (input_quant, output_quant) tuples extracted from the TFLite.

    Each tuple is ``(scale, zero_point)``. These are the model-design
    outputs that pin the manifest's per-stage quant blocks.
    """
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter  # type: ignore[no-redef]
    interp = Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    in_s, in_zp = interp.get_input_details()[0]["quantization"]
    out_s, out_zp = interp.get_output_details()[0]["quantization"]
    return (float(in_s), int(in_zp)), (float(out_s), int(out_zp))


def _build_anchor(
    lock_bins: np.ndarray, sigma: float, input_dim: int = INPUT_DIM,
) -> np.ndarray:
    bins = np.arange(input_dim, dtype=np.float32)[None, :]
    centers = lock_bins.astype(np.float32).reshape(-1, 1)
    sigma_eff = float(max(sigma, 0.1))
    return np.exp(-0.5 * ((bins - centers) / sigma_eff) ** 2).astype(np.float32)


def _stack_nhwc(spectra_norm: np.ndarray, anchors: np.ndarray) -> np.ndarray:
    """(N, 100) + (N, 100) → (N, 1, 100, 2) NHWC."""
    return np.stack([spectra_norm, anchors], axis=-1)[:, None, :, :].astype(np.float32)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset", default="production_50k_v2_aic",
        help="dataset name under data/ or absolute path to dataset dir",
    )
    parser.add_argument(
        "--output", default=str(DEFAULT_OUTPUT), type=Path,
        help="output dir for cascade artifacts",
    )
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument(
        "--quick", action="store_true",
        help="smoke mode: epochs=2, num_workers=0, batch_size=16",
    )
    parser.add_argument(
        "--no-cuda", action="store_true",
        help="DEBUG only: train on CPU. Production runs MUST use CUDA.",
    )
    parser.add_argument(
        "--seed", type=int, default=42,
    )
    args = parser.parse_args(argv)

    # ----- Device / GPU verification ---------------------------------------
    if args.no_cuda:
        device = torch.device("cpu")
        log.warning("Running on CPU (--no-cuda). Production runs require GPU.")
    else:
        if not torch.cuda.is_available():
            log.error("CUDA not available. Cascade training requires GPU; "
                      "pass --no-cuda only for local debugging.")
            return 2
        device = torch.device("cuda")
        log.info("device: cuda (%s)", torch.cuda.get_device_name(0))

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    epochs = 2 if args.quick else args.epochs
    num_workers = 0 if args.quick else 4
    batch_size = 16 if args.quick else 64

    # ----- Load dataset (PID labels + spectra) -----------------------------
    data_dir = _resolve_dataset_dir(args.dataset)
    log.info("dataset: %s", data_dir)
    npz_path = data_dir / "pid_residuals.npz"
    if not npz_path.exists():
        log.info("PID labels not present, generating via generate_pid_labels...")
        generate_pid_labels(data_dir)
    npz = np.load(npz_path)
    with h5py.File(data_dir / "dataset.h5", "r") as f:
        train_spectra_norm = _normalize_symmetric(f["train"]["spectra"][:])
        val_spectra_norm = _normalize_symmetric(f["val"]["spectra"][:])

    train_lock_bins = npz["train_lock_bins"]
    val_lock_bins = npz["val_lock_bins"]
    train_b_true = npz["train_b_mag_uT"].astype(np.float32)
    val_b_true = npz["val_b_mag_uT"].astype(np.float32)
    train_b_pid = npz["train_b_pid_uT"].astype(np.float32)
    val_b_pid = npz["val_b_pid_uT"].astype(np.float32)

    # COARSE labels: same recipe as the monolithic v2 production model.
    coarse_train_labels = np.clip(
        train_b_true - train_b_pid, -CLAMP_UT, CLAMP_UT,
    ).astype(np.float32)
    coarse_val_labels = np.clip(
        val_b_true - val_b_pid, -CLAMP_UT, CLAMP_UT,
    ).astype(np.float32)

    log.info("=" * 70)
    log.info("STAGE 1: COARSE")
    log.info("=" * 70)
    coarse_dir = output_dir / "coarse_artifacts"
    coarse = train_stage(
        name="coarse",
        train_spectra_norm=train_spectra_norm,
        train_lock_bins=train_lock_bins,
        train_labels_uT=coarse_train_labels,
        val_spectra_norm=val_spectra_norm,
        val_lock_bins=val_lock_bins,
        val_labels_uT=coarse_val_labels,
        output_dir=coarse_dir,
        device=device,
        input_dim=INPUT_DIM,
        epochs=epochs,
        batch_size=batch_size,
        seed=args.seed,
        num_workers=num_workers,
    )
    coarse_tflite = output_dir / "coarse_int8.tflite"
    coarse_onnx = output_dir / "coarse.onnx"
    coarse_tflite.write_bytes(coarse.tflite_path.read_bytes())
    coarse_onnx.write_bytes(coarse.onnx_path.read_bytes())

    # ----- FINE labels via deployed COARSE TFLite -------------------------
    log.info("=" * 70)
    log.info("STAGE 2: FINE — generating residual labels via deployed COARSE")
    log.info("=" * 70)
    fine_train_labels = compute_fine_labels(
        coarse_tflite,
        coarse_learned_sigma=coarse.learned_sigma,
        input_dim=INPUT_DIM,
        spectra_norm=train_spectra_norm,
        lock_bins=train_lock_bins,
        b_true_uT=train_b_true,
        b_pid_uT=train_b_pid,
        clamp_uT=CLAMP_UT,
    )
    fine_val_labels = compute_fine_labels(
        coarse_tflite,
        coarse_learned_sigma=coarse.learned_sigma,
        input_dim=INPUT_DIM,
        spectra_norm=val_spectra_norm,
        lock_bins=val_lock_bins,
        b_true_uT=val_b_true,
        b_pid_uT=val_b_pid,
        clamp_uT=CLAMP_UT,
    )
    log.info(
        "FINE label stats: train mean=%.4f std=%.4f µT (clipped frac=%.3f)",
        float(fine_train_labels.mean()),
        float(fine_train_labels.std()),
        float((np.abs(fine_train_labels) >= CLAMP_UT - 1e-6).mean()),
    )

    fine = train_stage(
        name="fine",
        train_spectra_norm=train_spectra_norm,
        train_lock_bins=train_lock_bins,
        train_labels_uT=fine_train_labels,
        val_spectra_norm=val_spectra_norm,
        val_lock_bins=val_lock_bins,
        val_labels_uT=fine_val_labels,
        output_dir=output_dir / "fine_artifacts",
        device=device,
        input_dim=INPUT_DIM,
        epochs=epochs,
        batch_size=batch_size,
        seed=args.seed + 1,  # different init from COARSE
        num_workers=num_workers,
    )
    fine_tflite = output_dir / "fine_int8.tflite"
    fine_onnx = output_dir / "fine.onnx"
    fine_tflite.write_bytes(fine.tflite_path.read_bytes())
    fine_onnx.write_bytes(fine.onnx_path.read_bytes())

    # ----- Extract quantization parameters --------------------------------
    coarse_iq, coarse_oq = _quant_from_tflite(coarse_tflite)
    fine_iq, fine_oq = _quant_from_tflite(fine_tflite)
    # Composition output_quant: deployed authority is COARSE+FINE so it
    # spans up to ±4.5 µT. Use the finer of the two stage scales so the
    # composed sum can be represented without loss.
    composition_oq = coarse_oq if coarse_oq[0] <= fine_oq[0] else fine_oq
    log.info("COARSE input_quant=(%.3e, %d) output_quant=(%.3e, %d)",
             coarse_iq[0], coarse_iq[1], coarse_oq[0], coarse_oq[1])
    log.info("FINE   input_quant=(%.3e, %d) output_quant=(%.3e, %d)",
             fine_iq[0], fine_iq[1], fine_oq[0], fine_oq[1])
    log.info("COMP   output_quant=(%.3e, %d)", composition_oq[0], composition_oq[1])

    # ----- Emit cascade_manifest.json -------------------------------------
    manifest_path = emit_cascade_manifest(
        output_dir=output_dir,
        coarse_tflite=coarse_tflite,
        fine_tflite=fine_tflite,
        input_dim=2 * INPUT_DIM,
        output_dim=1,
        coarse_input_quant=coarse_iq,
        coarse_output_quant=coarse_oq,
        fine_input_quant=fine_iq,
        fine_output_quant=fine_oq,
        composition_output_quant=composition_oq,
        notes=(
            f"P3-11B Path B cascade. dataset={data_dir.name} "
            f"epochs={epochs} clamp_uT={CLAMP_UT} "
            f"coarse_sigma={coarse.learned_sigma:.4f} "
            f"fine_sigma={fine.learned_sigma:.4f}"
        ),
    )
    log.info("manifest: %s", manifest_path)

    # ----- Deployed cascade MAE on val set --------------------------------
    log.info("=" * 70)
    log.info("DEPLOYED CASCADE EVAL (val split)")
    log.info("=" * 70)
    coarse_runner = make_float_runner(coarse_tflite)
    fine_runner = make_float_runner(fine_tflite)
    manifest = CascadeManifest.from_json(manifest_path)
    val_anchors_coarse = _build_anchor(val_lock_bins, coarse.learned_sigma)
    # COARSE and FINE may settle on different sigmas. Deployment uses ONE
    # host-side anchor pipeline that feeds both stages; we use COARSE's
    # sigma here to match. If FINE's learned sigma diverges substantially
    # we log a warning so DLOG can flag it.
    sigma_drift = abs(fine.learned_sigma - coarse.learned_sigma)
    if sigma_drift > 0.5:
        log.warning(
            "FINE sigma %.4f drifts from COARSE sigma %.4f by %.4f — host "
            "anchor uses COARSE's sigma; check that FINE accuracy holds.",
            fine.learned_sigma, coarse.learned_sigma, sigma_drift,
        )
    val_x = _stack_nhwc(val_spectra_norm, val_anchors_coarse)
    cascade_pred_uT = compose_quantized_then_dequant(
        val_x, manifest, coarse_runner=coarse_runner, fine_runner=fine_runner,
    ).reshape(-1)
    pid_only_err = np.abs(val_b_pid - val_b_true)
    cascade_err = np.abs(val_b_pid + cascade_pred_uT - val_b_true)
    log.info("PID-only val MAE:      %.4f µT", float(pid_only_err.mean()))
    log.info("COARSE-only val MAE:   %.4f µT", float(coarse.val_metrics.get("mae_uT", float("nan"))))
    log.info("Cascade deployed MAE:  %.4f µT", float(cascade_err.mean()))
    cascade_reduction = (1.0 - cascade_err.mean() / pid_only_err.mean()) * 100.0
    log.info("Cascade reduction vs PID: %.2f%%", cascade_reduction)

    # ----- Bit-exact fixture (32 spectra) for FPGA-handoff CI -------------
    log.info("=" * 70)
    log.info("BIT-EXACT FIXTURE")
    log.info("=" * 70)
    fixture_n = min(BIT_EXACT_FIXTURE_SAMPLES, val_spectra_norm.shape[0])
    fx_x = val_x[:fixture_n]
    fx_x_int8 = quantize_input(fx_x, coarse_iq[0], coarse_iq[1])
    coarse_int8_runner = make_int8_runner(coarse_tflite)
    fine_int8_runner = make_int8_runner(fine_tflite)

    # Self-check: substitute a real rounding_mode in-memory and run
    # compose_int8 → expected_y_int8. The on-disk manifest keeps TBD.
    self_check_manifest = deepcopy(manifest)
    self_check_manifest.composition["rounding_mode"] = SELF_CHECK_ROUNDING_MODE
    expected_y_int8 = compose_int8(
        fx_x_int8, self_check_manifest,
        coarse_runner=coarse_int8_runner, fine_runner=fine_int8_runner,
    )
    fixture_path = output_dir / "bit_exact_fixture.npz"
    np.savez(
        fixture_path,
        x_int8=fx_x_int8,
        expected_y_int8=expected_y_int8,
        self_check_rounding_mode=SELF_CHECK_ROUNDING_MODE,
        notes=(
            "Self-check fixture; rounding_mode is wiring-test only. "
            "FPGA bit-exact CI must rebuild the fixture using the "
            "rounding_mode that polarfire-hybrid-control resolves "
            "in cascade_manifest.json."
        ),
    )
    ok, report = verify_bit_exact(
        fx_x_int8, expected_y_int8, self_check_manifest,
        coarse_runner=coarse_int8_runner, fine_runner=fine_int8_runner,
    )
    log.info("verify_bit_exact (self-check): ok=%s report=%s", ok, report)
    if not ok:
        log.error("verify_bit_exact failed — INT8 cascade composition is broken")
        return 3

    # ----- Eval report ---------------------------------------------------
    eval_report = {
        "dataset": str(data_dir),
        "epochs": epochs,
        "coarse_val_mae_uT": float(coarse.val_metrics.get("mae_uT", float("nan"))),
        "fine_val_mae_uT": float(fine.val_metrics.get("mae_uT", float("nan"))),
        "cascade_deployed_val_mae_uT": float(cascade_err.mean()),
        "pid_only_val_mae_uT": float(pid_only_err.mean()),
        "cascade_reduction_pct_vs_pid": float(cascade_reduction),
        "coarse_learned_sigma": float(coarse.learned_sigma),
        "fine_learned_sigma": float(fine.learned_sigma),
        "coarse_n_params": int(coarse.n_params),
        "fine_n_params": int(fine.n_params),
        "coarse_training_time_s": float(coarse.training_time_s),
        "fine_training_time_s": float(fine.training_time_s),
        "self_check_bit_exact_report": report,
    }
    eval_report_path = output_dir / "cascade_eval_report.json"
    eval_report_path.write_text(json.dumps(eval_report, indent=2, default=str))
    log.info("eval report: %s", eval_report_path)

    log.info("=" * 70)
    log.info("Done. Artifacts: %s", output_dir)
    log.info("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
