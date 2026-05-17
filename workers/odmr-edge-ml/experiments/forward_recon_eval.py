"""B2.2 — Forward-reconstruction metric (NVRNet Component 6 pattern).

For each held-out test spectrum, runs three SimOS forward passes:

1. ``s_pid``     — simulator at the PID estimate ``b_pid * dir_true``.
2. ``s_fcnn``    — simulator at the FCNN-corrected magnitude
                    ``(b_pid + delta_b_pred) * dir_true``.
3. ``s_oracle``  — simulator at the true magnitude ``b_mag * dir_true``
                    (best achievable reconstruction on this freq grid).

For each reconstruction, reports the normalized FFT error
``||FFT(s_orig - s_recon)|| / ||FFT(s_orig)||``. The FCNN row is the new
sixth eval metric; PID and oracle are reported as the lower and upper
bounds of "achievable" by this pipeline.

NVRNet headline target for the FCNN row: 0.10 – 0.19.

Run::

    python experiments/forward_recon_eval.py \\
        --dataset $(pwd)/data/production_50k/dataset.h5 \\
        --pid $(pwd)/data/production_50k/pid_residuals.npz \\
        --ckpt $(pwd)/experiments/scalar_residual_v2_dataset_a/checkpoints/best_model_dataset_a.pt \\
        --out $(pwd)/experiments/forward_recon_results.npz \\
        --n 5000

Caveats (documented in the output summary):

- ``mw_scale`` (corruption_params[4]) is honored; ``b1_gradient_frac``
  (corruption_params[2]) is NOT re-applied — it would require the
  multi-shot averaging path from ``physics/lineshape.apply_b1_gradient``.
  This means the oracle reconstruction has a non-zero error floor
  reflecting un-modelled corruption, not just stochastic noise.
- The simulator's freq step (1.01 MHz) is coarser than the line FWHM
  (~1.91 MHz). The dip is under-resolved on the native grid; this aliasing
  also contributes to the floor.
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
warnings.filterwarnings("ignore", message=".*Grid aliasing risk.*")

# nv-sensor-sim is a sibling repo, not pip-installed in this env
sys.path.insert(0, "~/projects/nv-sensor-sim/src")
from nv_sensor_sim.adapters.simos_adapter import SimOSAdapter  # noqa: E402
from nv_sensor_sim.config import SimulationConfig  # noqa: E402

# odmr-edge-ml internals
_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "src"))
from odmr_edge_ml.models.fcnn import OdmrFCNN  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("forward_recon_eval")

SIGMA_V2_DATASET_A = 1.267999


def strip_compile_qat_keys(sd: dict) -> dict:
    """torch.compile prefix + FX-QAT observer-key strip.

    Mirrors `experiments/v2_dataset_a_phase_c_eval.py:strip_compile_qat_keys`.
    """
    skip = ("fake_quant", "activation_post_process", "observer")
    out: dict = {}
    for k, v in sd.items():
        if any(p in k for p in skip):
            continue
        nk = k[len("_orig_mod."):] if k.startswith("_orig_mod.") else k
        out[nk] = v
    return out


def load_fcnn(ckpt_path: Path, device: torch.device) -> OdmrFCNN:
    """Load the v2-dataset-a checkpoint into a vanilla OdmrFCNN (in_channels=2).

    The "v2" in the filename refers to *Dataset A v2*, not the FCNN-v2 architecture;
    the checkpoint was trained against `OdmrFCNN(in_channels=2)` with the Gaussian
    anchor computed externally as the second channel.
    """
    blob = torch.load(ckpt_path, map_location="cpu", weights_only=False)
    sd = blob["model_state_dict"] if isinstance(blob, dict) else blob
    if not isinstance(sd, dict):
        raise TypeError(f"unexpected checkpoint structure at {ckpt_path}")
    clean = strip_compile_qat_keys(sd)
    model = OdmrFCNN(input_dim=100, output_dim=1, in_channels=2)
    target_keys = set(model.state_dict().keys())
    export_sd = {k: v for k, v in clean.items() if k in target_keys}
    model.load_state_dict(export_sd, strict=True)
    model.eval()
    return model.to(device)


def fcnn_predict_delta(
    model: OdmrFCNN,
    spectra: np.ndarray,
    lock_bins: np.ndarray,
    device: torch.device,
    sigma: float = SIGMA_V2_DATASET_A,
) -> np.ndarray:
    """FCNN ΔB predictions, mirroring `v2_dataset_a_phase_c_eval.preprocess_batch`.

    Per-spectrum min/max normalize to [-1, 1], compute external Gaussian anchor
    with the canonical σ=1.267999, concatenate to a (N, 200) input.
    """
    bs = 512
    out: list[np.ndarray] = []
    bins = np.arange(spectra.shape[1])[None, :]
    with torch.inference_mode():
        for i0 in range(0, len(spectra), bs):
            chunk = spectra[i0:i0 + bs]
            lb = lock_bins[i0:i0 + bs]
            s_min = chunk.min(axis=1, keepdims=True)
            s_max = chunk.max(axis=1, keepdims=True)
            denom = np.where(s_max == s_min, 1.0, s_max - s_min)
            spec_norm = 2.0 * (chunk - s_min) / denom - 1.0
            anchor = np.exp(-0.5 * ((bins - lb[:, None]) / sigma) ** 2)
            x = np.concatenate([spec_norm, anchor], axis=1).astype(np.float32)
            xt = torch.from_numpy(x).to(device)
            yt = model(xt).cpu().numpy().reshape(-1)
            out.append(yt)
    return np.concatenate(out, axis=0)


def make_adapter(freq_min: float, freq_max: float, n_pts: int) -> SimOSAdapter:
    """One-shot adapter; we re-issue B_field per call."""
    cfg = SimulationConfig(
        B_field_T=np.array([0.0, 0.0, 30e-6]),  # placeholder; overridden per call
        mw_freq_range_Hz=(freq_min, freq_max),
        n_freq_points=n_pts,
        temperature_K=298.0,
        p1_concentration_ppm=50.0,
        b_perp_T=0.0,
        use_optics=False,
        include_nitrogen=False,
    )
    return SimOSAdapter(cfg)


def forward_one(
    adapter: SimOSAdapter,
    b_vec_T: np.ndarray,
    p1_ppm: float,
    temperature_K: float,
    mw_scale: float,
    freq_range: tuple[float, float],
    n_pts: int,
) -> np.ndarray:
    _, pl = adapter.generate_odmr_spectrum(
        B_field=b_vec_T,
        freq_range=freq_range,
        n_points=n_pts,
        temperature_K=temperature_K,
        p1_ppm=p1_ppm,
        mw_scale=mw_scale,
    )
    return pl


def normalized_fft_error(orig: np.ndarray, recon: np.ndarray) -> float:
    """||FFT(s_orig_ac - s_recon_ac)|| / ||FFT(s_orig_ac)||.

    Both spectra are mean-centred before FFT so the DC bin (which equals
    sum(s) ≈ N for baseline-near-1 spectra) does not dominate the ratio.
    Equivalent to dropping FFT bin 0; this is the meaningful "AC content"
    fidelity that the NVRNet-style metric is trying to capture.
    """
    o_ac = orig - orig.mean()
    r_ac = recon - recon.mean()
    diff = np.fft.rfft(o_ac - r_ac)
    denom = np.fft.rfft(o_ac)
    num = float(np.linalg.norm(diff))
    den = float(np.linalg.norm(denom))
    return num / max(den, 1e-12)


def relative_dip_error(orig: np.ndarray, recon: np.ndarray) -> float:
    """||s_orig - s_recon|| / max(s_orig - min(s_orig)) — fraction of dip depth.

    Reported alongside the FFT metric as a more interpretable companion.
    """
    dip_depth = float(orig.max() - orig.min())
    return float(np.linalg.norm(orig - recon)) / max(dip_depth, 1e-12)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--pid", type=Path, required=True)
    ap.add_argument("--ckpt", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument(
        "--device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
    )
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    log.info("device=%s cuda=%s", device, torch.cuda.is_available())

    log.info("loading dataset + PID residuals + checkpoint")
    with h5py.File(args.dataset, "r") as h5:
        ds_freq = h5["test/frequencies"]
        ds_spec = h5["test/spectra"]
        ds_lab = h5["test/labels"]
        ds_cp = h5["test/corruption_params"]
        assert isinstance(ds_freq, h5py.Dataset)
        assert isinstance(ds_spec, h5py.Dataset)
        assert isinstance(ds_lab, h5py.Dataset)
        assert isinstance(ds_cp, h5py.Dataset)
        freq = np.asarray(ds_freq[:], dtype=np.float64)
        n_total = ds_spec.shape[0]
        take = min(args.n, n_total)
        idx = np.sort(rng.choice(n_total, size=take, replace=False))
        spectra = np.asarray(ds_spec[idx, :], dtype=np.float64)
        labels = np.asarray(ds_lab[idx, :], dtype=np.float64)
        cps = np.asarray(ds_cp[idx, :], dtype=np.float64)

    pid_npz = np.load(args.pid)
    b_pid = pid_npz["test_b_pid_uT"][idx]
    lock_bins = pid_npz["test_lock_bins"][idx]
    delta_b_true = pid_npz["test_delta_b_uT"][idx]
    b_mag_true = pid_npz["test_b_mag_uT"][idx]

    log.info(
        "test sample n=%d  b_mag stats µT min=%.2f mean=%.2f max=%.2f  "
        "delta_b µT min=%.2f mean=%.2f max=%.2f",
        take, b_mag_true.min(), b_mag_true.mean(), b_mag_true.max(),
        delta_b_true.min(), delta_b_true.mean(), delta_b_true.max(),
    )

    model = load_fcnn(args.ckpt, device)
    delta_b_pred = fcnn_predict_delta(model, spectra, lock_bins, device)
    log.info(
        "FCNN delta_b_pred µT  mean=%.3f std=%.3f  vs true mean=%.3f std=%.3f",
        delta_b_pred.mean(), delta_b_pred.std(),
        delta_b_true.mean(), delta_b_true.std(),
    )

    # FCNN scalar MAE — a sanity baseline before we forward-simulate
    fcnn_mae_ut = float(np.mean(np.abs(delta_b_pred - delta_b_true)))
    pid_mae_ut = float(np.mean(np.abs(b_pid - b_mag_true)))
    log.info("scalar MAE  PID=%.3f µT  FCNN-residual=%.3f µT", pid_mae_ut, fcnn_mae_ut)

    # Forward-reconstruct
    freq_min, freq_max = float(freq[0]), float(freq[-1])
    n_pts = int(freq.size)
    adapter = make_adapter(freq_min, freq_max, n_pts)
    freq_range = (freq_min, freq_max)

    err_pid = np.zeros(take, dtype=np.float64)
    err_fcnn = np.zeros(take, dtype=np.float64)
    err_oracle = np.zeros(take, dtype=np.float64)
    dip_err_pid = np.zeros(take, dtype=np.float64)
    dip_err_fcnn = np.zeros(take, dtype=np.float64)
    dip_err_oracle = np.zeros(take, dtype=np.float64)

    t0 = time.time()
    UT_TO_T = 1e-6
    for i in range(take):
        b_true_vec = labels[i]
        b_norm = float(np.linalg.norm(b_true_vec))
        if b_norm < 1e-12:
            continue
        unit_dir = b_true_vec / b_norm
        p1_ppm = float(cps[i, 0])
        T_K = float(cps[i, 1])
        # cps[i,2] = b1_gradient_frac (un-modelled here, see caveats)
        mw_scale = float(cps[i, 4])

        b_pid_vec = (b_pid[i] * UT_TO_T) * unit_dir
        b_fcnn_vec = ((b_pid[i] + delta_b_pred[i]) * UT_TO_T) * unit_dir
        b_oracle_vec = (b_mag_true[i] * UT_TO_T) * unit_dir

        s_pid = forward_one(adapter, b_pid_vec, p1_ppm, T_K, mw_scale, freq_range, n_pts)
        s_fcnn = forward_one(adapter, b_fcnn_vec, p1_ppm, T_K, mw_scale, freq_range, n_pts)
        s_oracle = forward_one(adapter, b_oracle_vec, p1_ppm, T_K, mw_scale, freq_range, n_pts)

        s_orig = spectra[i]
        err_pid[i] = normalized_fft_error(s_orig, s_pid)
        err_fcnn[i] = normalized_fft_error(s_orig, s_fcnn)
        err_oracle[i] = normalized_fft_error(s_orig, s_oracle)
        dip_err_pid[i] = relative_dip_error(s_orig, s_pid)
        dip_err_fcnn[i] = relative_dip_error(s_orig, s_fcnn)
        dip_err_oracle[i] = relative_dip_error(s_orig, s_oracle)

        if i % max(1, take // 20) == 0:
            elapsed = time.time() - t0
            log.info(
                "  i=%d/%d  err pid=%.3f fcnn=%.3f oracle=%.3f  elapsed=%.1fs",
                i, take, err_pid[i], err_fcnn[i], err_oracle[i], elapsed,
            )

    elapsed = time.time() - t0
    log.info("forward-recon done in %.1fs (%.2f ms/spectrum × 3 sims)", elapsed, 1000 * elapsed / max(take, 1) / 3)

    summary = {
        "n": int(take),
        "fft_err_pid": {
            "mean": float(np.mean(err_pid)),
            "p50": float(np.median(err_pid)),
            "p90": float(np.percentile(err_pid, 90)),
        },
        "fft_err_fcnn": {
            "mean": float(np.mean(err_fcnn)),
            "p50": float(np.median(err_fcnn)),
            "p90": float(np.percentile(err_fcnn, 90)),
        },
        "fft_err_oracle": {
            "mean": float(np.mean(err_oracle)),
            "p50": float(np.median(err_oracle)),
            "p90": float(np.percentile(err_oracle, 90)),
        },
        "dip_err_pid_p50": float(np.median(dip_err_pid)),
        "dip_err_fcnn_p50": float(np.median(dip_err_fcnn)),
        "dip_err_oracle_p50": float(np.median(dip_err_oracle)),
        "scalar_pid_mae_uT": pid_mae_ut,
        "scalar_fcnn_residual_mae_uT": fcnn_mae_ut,
        "scalar_fcnn_corrected_mae_uT": float(
            np.mean(np.abs((b_pid + delta_b_pred) - b_mag_true))
        ),
        "nvrnet_headline_target_fft": [0.10, 0.19],
        "fcnn_fft_in_target_band": bool(
            0.10 <= float(np.median(err_fcnn)) <= 0.19
        ),
        "elapsed_s": elapsed,
    }
    print(json.dumps(summary, indent=2))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.out,
        indices=idx,
        err_pid=err_pid,
        err_fcnn=err_fcnn,
        err_oracle=err_oracle,
        dip_err_pid=dip_err_pid,
        dip_err_fcnn=dip_err_fcnn,
        dip_err_oracle=dip_err_oracle,
        delta_b_pred_uT=delta_b_pred,
        delta_b_true_uT=delta_b_true,
        b_pid_uT=b_pid,
        b_mag_true_uT=b_mag_true,
        summary_json=json.dumps(summary),
    )
    log.info("wrote %s", args.out)


if __name__ == "__main__":
    main()
