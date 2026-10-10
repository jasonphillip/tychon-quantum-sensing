#!/usr/bin/env python3
"""Validation orientation audit: PID error distribution, val split vs heading sweep.

Compares |PID baseline error| histograms over:
  i)  the production_50k validation split (5,000 samples)
  ii) the 1440-angle heading sweep

If the val split's P90/P99 are below the heading sweep's median, the
val set is quantitatively OOD relative to the sweep — confirming the
"orientation diversity gap" claim.
"""

from __future__ import annotations

import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)
# (No FCNN forward pass in this script; pure PID-error histogram. No GPU needed.)

VAL_NPZ = Path("~/projects/odmr-edge-ml/data/production_50k/pid_residuals.npz")
SWEEP_NPZ = Path(
    "~/Desktop/Shared/codex-review/ws1_projects/"
    "tychon-odmr-ml/experiments/heading_sweep_results.npz"
)
OUT_PNG = (
    Path(__file__).resolve().parent / "figures" / "validation_vs_sweep_histogram.png"
)


def summary(name: str, x: np.ndarray) -> dict[str, float]:
    s = {
        "n": int(x.size),
        "mean": float(x.mean()),
        "median": float(np.median(x)),
        "P90": float(np.percentile(x, 90)),
        "P99": float(np.percentile(x, 99)),
        "max": float(x.max()),
    }
    log.info(
        "  %-20s n=%5d  mean=%7.3f  median=%7.3f  P90=%7.3f  P99=%7.3f  max=%7.3f",
        name, s["n"], s["mean"], s["median"], s["P90"], s["P99"], s["max"],
    )
    return s


def main() -> None:
    log.info("Loading: %s", VAL_NPZ)
    val = np.load(VAL_NPZ)
    val_pid_err = np.abs(val["val_b_pid_uT"] - val["val_b_mag_uT"])

    log.info("Loading: %s", SWEEP_NPZ)
    sweep = np.load(SWEEP_NPZ)
    sweep_pid_err = np.abs(sweep["pid_error_uT"])  # already signed; abs to be safe

    log.info("=== |PID error| (µT) summary ===")
    val_s = summary("val (production_50k)", val_pid_err)
    sweep_s = summary("heading sweep 1440", sweep_pid_err)

    log.info("")
    log.info("=== OOD comparison ===")
    log.info("  val P90 (%.3f) < sweep median (%.3f)?  %s",
             val_s["P90"], sweep_s["median"], val_s["P90"] < sweep_s["median"])
    log.info("  val P99 (%.3f) < sweep median (%.3f)?  %s",
             val_s["P99"], sweep_s["median"], val_s["P99"] < sweep_s["median"])

    # --- Histogram ---
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=False)

    upper = float(np.percentile(np.concatenate([val_pid_err, sweep_pid_err]), 99.5))
    bins = np.linspace(0.0, upper, 60)

    for ax, data, label, color in (
        (axes[0], val_pid_err, "Validation split (production_50k, n=5,000)", "#2176FF"),
        (axes[1], sweep_pid_err, "Heading sweep (1440 angles, all orientations)", "#D7263D"),
    ):
        ax.hist(data, bins=bins, color=color, alpha=0.85, edgecolor="black", linewidth=0.4)
        ax.axvline(np.median(data), color="black", linestyle="-", linewidth=1.2,
                   label=f"median={np.median(data):.2f}")
        ax.axvline(np.percentile(data, 90), color="black", linestyle="--", linewidth=1.0,
                   label=f"P90={np.percentile(data, 90):.2f}")
        ax.axvline(np.percentile(data, 99), color="black", linestyle=":", linewidth=1.0,
                   label=f"P99={np.percentile(data, 99):.2f}")
        ax.set_xlabel("|PID baseline error| (µT)")
        ax.set_ylabel("Count")
        ax.set_title(label, fontsize=11)
        ax.legend(loc="upper right", fontsize=9)
        ax.grid(True, alpha=0.3)

    fig.suptitle(
        "PID baseline error distribution — val split vs all-orientation sweep",
        fontsize=13, fontweight="bold",
    )
    fig.tight_layout()
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    log.info("Saved: %s", OUT_PNG)


if __name__ == "__main__":
    main()
