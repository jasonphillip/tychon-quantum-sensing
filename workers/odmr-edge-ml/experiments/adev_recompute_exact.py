#!/usr/bin/env python3
"""Recompute OADEV at explicit τ values from existing time-series data.

Uses the time-series in adev_results.npz (PID and FCNN+PID error traces) and
re-runs allantools.oadev with an explicit τ array that includes 2700 s — the
half-orbit headline number — so the value is directly computed rather than
interpolated from octave-spaced points.

Output: experiments/adev_results_exact.npz (preserves the original).
"""

from __future__ import annotations

import logging
from pathlib import Path

import allantools
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DT_S = 1.0

# Source: original adev_results.npz from the tychon-odmr-ml workspace.
# (odmr-edge-ml is the public-scrubbed mirror; the .npz is gitignored.)
SRC_NPZ = Path(
    "~/Desktop/Shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/adev_results.npz"
)
OUT_NPZ = Path(__file__).resolve().parent / "adev_results_exact.npz"

# Explicit τ values requested. 2700 = T_orbit / 2; 5400 = T_orbit.
EXPLICIT_TAUS = np.array([1.0, 10.0, 100.0, 1000.0, 2700.0, 5400.0])


def main() -> None:
    log.info("Loading: %s", SRC_NPZ)
    src = np.load(SRC_NPZ)
    pid_error_uT = src["pid_error_uT"]
    cnn_error_uT = src["cnn_error_uT"]
    log.info("  pid_error_uT shape=%s, cnn_error_uT shape=%s",
             pid_error_uT.shape, cnn_error_uT.shape)

    octave_taus = src["taus_pid"]
    log.info("  Original octave τ grid: %s", octave_taus.tolist())
    nearest_below = octave_taus[octave_taus < 2700].max() if (octave_taus < 2700).any() else None
    nearest_above = octave_taus[octave_taus > 2700].min() if (octave_taus > 2700).any() else None
    log.info("  Nearest octave τ to 2700: below=%s, above=%s",
             nearest_below, nearest_above)

    # Recompute with explicit τ list. allantools accepts a list/array via taus=.
    taus_pid_x, adev_pid_x, aderr_pid_x, n_pid_x = allantools.oadev(
        pid_error_uT, rate=1.0 / DT_S, data_type="freq", taus=EXPLICIT_TAUS,
    )
    taus_cnn_x, adev_cnn_x, aderr_cnn_x, n_cnn_x = allantools.oadev(
        cnn_error_uT, rate=1.0 / DT_S, data_type="freq", taus=EXPLICIT_TAUS,
    )

    log.info("")
    log.info("%-8s  %12s  %12s  %12s  %10s  %10s",
             "tau (s)", "PID OADEV", "CNN OADEV", "Reduction", "n_pid", "n_cnn")
    log.info("-" * 76)
    for i, tau in enumerate(taus_pid_x):
        red = (1.0 - adev_cnn_x[i] / adev_pid_x[i]) * 100.0
        log.info("%-8.0f  %10.4f µT  %10.4f µT  %10.2f%%  %10d  %10d",
                 tau, adev_pid_x[i], adev_cnn_x[i], red,
                 int(n_pid_x[i]), int(n_cnn_x[i]))

    # Interpolation comparison at τ=2700 from the original octave grid.
    octave_pid = src["adev_pid"]
    octave_cnn = src["adev_cnn"]
    interp_pid_2700 = float(np.interp(2700.0, octave_taus, octave_pid))
    interp_cnn_2700 = float(np.interp(2700.0, octave_taus, octave_cnn))
    interp_red_2700 = (1.0 - interp_cnn_2700 / interp_pid_2700) * 100.0

    idx_2700 = int(np.where(taus_pid_x == 2700.0)[0][0])
    direct_pid_2700 = float(adev_pid_x[idx_2700])
    direct_cnn_2700 = float(adev_cnn_x[idx_2700])
    direct_red_2700 = (1.0 - direct_cnn_2700 / direct_pid_2700) * 100.0

    delta_pp = direct_red_2700 - interp_red_2700

    log.info("")
    log.info("=== τ = 2700 s comparison ===")
    log.info("  Interpolated  PID=%.4f µT  CNN=%.4f µT  reduction=%.2f%%",
             interp_pid_2700, interp_cnn_2700, interp_red_2700)
    log.info("  Direct        PID=%.4f µT  CNN=%.4f µT  reduction=%.2f%%",
             direct_pid_2700, direct_cnn_2700, direct_red_2700)
    log.info("  Delta (direct − interp): %+.2f percentage points", delta_pp)

    # Save exact-τ results alongside the originals (preserve the source data).
    out = {k: np.asarray(src[k]) for k in src.files}
    out["taus_pid_exact"] = np.asarray(taus_pid_x)
    out["adev_pid_exact"] = np.asarray(adev_pid_x)
    out["aderr_pid_exact"] = np.asarray(aderr_pid_x)
    out["n_pid_exact"] = np.asarray(n_pid_x)
    out["taus_cnn_exact"] = np.asarray(taus_cnn_x)
    out["adev_cnn_exact"] = np.asarray(adev_cnn_x)
    out["aderr_cnn_exact"] = np.asarray(aderr_cnn_x)
    out["n_cnn_exact"] = np.asarray(n_cnn_x)
    out["reduction_pct_2700_direct"] = np.asarray(direct_red_2700)
    out["reduction_pct_2700_interp"] = np.asarray(interp_red_2700)
    out["reduction_delta_pp_2700"] = np.asarray(delta_pp)
    np.savez(str(OUT_NPZ), **out)
    log.info("Saved: %s", OUT_NPZ)


if __name__ == "__main__":
    main()
