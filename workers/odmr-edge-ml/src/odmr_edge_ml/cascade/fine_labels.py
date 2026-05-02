"""Generate FINE training labels from the deployed COARSE model.

FINE corrects the *deployment-quantized* COARSE residual (including
COARSE's INT8 quantization noise) — not the float COARSE residual. This
is the design call called out in the plan and what
``compose_quantized_then_dequant`` validates against at end-of-training.

Training label per sample:

    fine_label_uT = clip(b_true_uT - b_pid_uT - coarse_int8_pred_uT, ±clamp_uT)

The COARSE TFLite is invoked through ``tflite_runtime`` against the
NHWC ``(1, 1, input_dim, 2)`` input the static-batch Keras export
produces. The second channel — the Gaussian anchor — is computed
host-side using the *learned sigma* extracted from the COARSE
``OdmrFCNNv2`` instance, mirroring the deployment-time host pipeline.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from odmr_edge_ml.models.fcnn_v2 import OdmrFCNNv2


def _gaussian_anchor(
    lock_bins: np.ndarray, input_dim: int, sigma: float,
) -> np.ndarray:
    """Recreate OdmrFCNNv2's host-side anchor without invoking the model.

    Returns array of shape ``(N, input_dim)`` with one Gaussian per sample
    centered on the corresponding ``lock_bins[i]`` and width ``sigma``.
    """
    bins = np.arange(input_dim, dtype=np.float32)[None, :]            # (1, D)
    centers = lock_bins.astype(np.float32).reshape(-1, 1)              # (N, 1)
    sigma_eff = float(max(sigma, 0.1))
    return np.exp(-0.5 * ((bins - centers) / sigma_eff) ** 2).astype(np.float32)


def _run_tflite_int8(
    tflite_path: Path,
    spectra_norm: np.ndarray,    # (N, input_dim) float32 in symmetric-norm units
    anchors: np.ndarray,         # (N, input_dim) float32
) -> np.ndarray:
    """Run the deployed TFLite COARSE model batch-by-batch (batch_size=1).

    Returns float predictions in µT.
    """
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite.python.interpreter import Interpreter  # type: ignore[no-redef]

    interp = Interpreter(model_path=str(tflite_path))
    interp.allocate_tensors()
    in_det = interp.get_input_details()[0]
    out_det = interp.get_output_details()[0]
    in_scale, in_zp = in_det["quantization"]
    out_scale, out_zp = out_det["quantization"]

    input_dim = spectra_norm.shape[1]
    n = spectra_norm.shape[0]
    preds = np.empty(n, dtype=np.float32)
    for i in range(n):
        # NHWC (1, 1, input_dim, 2)
        nhwc = np.stack([spectra_norm[i], anchors[i]], axis=-1).reshape(
            1, 1, input_dim, 2,
        )
        if in_det["dtype"] == np.int8:
            q = np.round(nhwc / in_scale + in_zp).clip(-128, 127).astype(np.int8)
        else:
            q = nhwc.astype(in_det["dtype"])
        interp.set_tensor(in_det["index"], q)
        interp.invoke()
        out = interp.get_tensor(out_det["index"])
        if out_det["dtype"] == np.int8:
            out_f = (out.astype(np.float32) - out_zp) * out_scale
        else:
            out_f = out.astype(np.float32)
        preds[i] = float(out_f.reshape(-1)[0])
    return preds


def compute_fine_labels(
    coarse_tflite_path: Path,
    coarse_model: OdmrFCNNv2,
    spectra_norm: np.ndarray,
    lock_bins: np.ndarray,
    b_true_uT: np.ndarray,
    b_pid_uT: np.ndarray,
    clamp_uT: float = 2.25,
) -> np.ndarray:
    """Materialize FINE training labels.

    Parameters
    ----------
    coarse_tflite_path
        Path to the deployed-INT8 COARSE TFLite file.
    coarse_model
        The float OdmrFCNNv2 the COARSE TFLite was exported from. Used
        only to read the learned sigma for the host-side anchor — its
        weights are NOT invoked.
    spectra_norm
        ``(N, input_dim)`` symmetric-normalized spectra (matches what
        ``ResidualDatasetV2`` packs as the first 100 columns of its
        101-dim input).
    lock_bins
        ``(N,)`` lock bin indices (the +1 column in ResidualDatasetV2).
    b_true_uT, b_pid_uT
        ``(N,)`` ground truth and PID baseline magnitudes in µT.
    clamp_uT
        Sector clamp applied to FINE labels. Default ``2.25`` matches
        ``CLAMP_UT`` in scalar_residual_v2.py.

    Returns
    -------
    np.ndarray
        ``(N,)`` float32 FINE labels in µT, clipped to ±``clamp_uT``.
    """
    sigma = float(coarse_model.sigma.detach().cpu().item())
    input_dim = int(coarse_model.input_dim)
    anchors = _gaussian_anchor(lock_bins, input_dim, sigma)
    coarse_pred_uT = _run_tflite_int8(coarse_tflite_path, spectra_norm, anchors)
    raw = b_true_uT - b_pid_uT - coarse_pred_uT
    return np.clip(raw, -clamp_uT, clamp_uT).astype(np.float32)
