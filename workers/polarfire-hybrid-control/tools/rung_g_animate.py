#!/usr/bin/env python3
"""rung_g_animate.py — animated (moving) time-series from Rung G telemetry CSV.

Renders the closed-loop replay as a moving visual (GIF; + MP4 if ffmpeg is
present): ODMR error in, PID-only vs PID+NN actuator (top), and NN u_ai with the
clamp / watchdog flags (bottom), revealed sample-by-sample behind a moving
playhead. Works on either the software dry-run telemetry (real actuator dynamics)
or the on-silicon telemetry (actuator flat at 0 while M0 is gated).

Usage:
  python3 tools/rung_g_animate.py sim/rung_g/rung_g_dryrun_2026-06-18.csv \
      --out sim/rung_g/rung_g_dryrun_2026-06-18_anim \
      --title "Rung G - closed-loop ODMR replay (software model)"
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402


def load(path: Path) -> list[dict[str, str]]:
    with path.open() as fh:
        return list(csv.DictReader(fh))


def col(rows: list[dict[str, str]], name: str) -> list[float]:
    return [float(r[name]) for r in rows]


def main() -> int:
    ap = argparse.ArgumentParser(description="Animate Rung G telemetry into a moving time-series.")
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, required=True, help="output base path (no extension)")
    ap.add_argument("--title", default="Rung G - closed-loop ODMR replay")
    ap.add_argument("--fps", type=int, default=15)
    ap.add_argument("--tail", type=int, default=0,
                    help="0 = cumulative reveal; >0 = scrolling window of N samples")
    args = ap.parse_args()

    rows = load(args.csv)
    n = len(rows)
    idx = [int(float(r["sample_idx"])) for r in rows]
    err = col(rows, "error_in")
    pido = col(rows, "pid_only_out")
    pidnn = col(rows, "pidnn_out")
    uai = col(rows, "nn_u_ai")
    clamp = [int(float(r["clamp_active"])) for r in rows]
    wd = [int(float(r["watchdog_timeout"])) for r in rows]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True)
    fig.suptitle(args.title)

    ax1.set_xlim(min(idx), max(idx))
    lo = min(min(err), min(pido), min(pidnn)) - 0.05
    hi = max(max(err), max(pido), max(pidnn)) + 0.05
    ax1.set_ylim(lo, hi)
    ax1.set_ylabel("normalized")
    ax2.set_xlim(min(idx), max(idx))
    ax2.set_ylim(-0.3, 1.15)
    ax2.set_ylabel("flags / u_ai")
    ax2.set_xlabel("sample")

    (l_err,) = ax1.plot([], [], "k-", lw=1.2, label="ODMR error in")
    (l_pido,) = ax1.plot([], [], "C0-", lw=1.2, label="PID-only (actuator)")
    (l_pidnn,) = ax1.plot([], [], "C3-", lw=1.6, label="PID+NN (actuator)")
    ax1.legend(loc="upper right", fontsize=8)
    vline1 = ax1.axvline(idx[0], color="0.6", lw=0.8)

    (l_uai,) = ax2.plot([], [], "C3.", ms=4, label="NN u_ai")
    (l_clamp,) = ax2.plot([], [], "C1-", lw=2.5, label="clamp active")
    (l_wd,) = ax2.plot([], [], "C2-", lw=2.5, label="watchdog timeout")
    ax2.legend(loc="upper right", fontsize=8)
    vline2 = ax2.axvline(idx[0], color="0.6", lw=0.8)

    def frame(i: int):
        start = max(0, i - args.tail) if args.tail > 0 else 0
        s = slice(start, i + 1)
        l_err.set_data(idx[s], err[s])
        l_pido.set_data(idx[s], pido[s])
        l_pidnn.set_data(idx[s], pidnn[s])
        l_uai.set_data(idx[s], uai[s])
        l_clamp.set_data(idx[s], clamp[s])
        l_wd.set_data(idx[s], wd[s])
        vline1.set_xdata([idx[i], idx[i]])
        vline2.set_xdata([idx[i], idx[i]])
        return l_err, l_pido, l_pidnn, l_uai, l_clamp, l_wd, vline1, vline2

    anim = FuncAnimation(fig, frame, frames=n, interval=1000 / args.fps, blit=False)

    gif = args.out.with_suffix(".gif")
    anim.save(str(gif), writer=PillowWriter(fps=args.fps))
    print(f"gif -> {gif}")
    try:
        from matplotlib.animation import FFMpegWriter
        mp4 = args.out.with_suffix(".mp4")
        anim.save(str(mp4), writer=FFMpegWriter(fps=args.fps))
        print(f"mp4 -> {mp4}")
    except Exception as exc:  # ffmpeg not installed -> GIF is enough
        print(f"(mp4 skipped: {exc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
