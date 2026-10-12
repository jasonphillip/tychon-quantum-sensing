#!/usr/bin/env python3
"""Plot measured MPFS250T watchdog clear-to-trip times."""

import csv
from pathlib import Path
import statistics
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


HEADER = "event,trip_ns,trip_ticks,trip_count_delta,poll_gap_max_ns"
LOG = Path(__file__).with_name("watchdog_trip_run1.log")
DEFAULT_OUTPUT = Path("docs/figures/watchdog_trip_hist.png")


def trip_times_ms(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    try:
        start = lines.index(HEADER) + 1
    except ValueError as exc:
        raise ValueError(f"CSV header not found in {path}") from exc

    times = []
    for row in csv.reader(lines[start:]):
        if len(row) != 5:
            break  # The log's summary footer follows the CSV block.
        times.append(int(row[1]) / 1_000_000)
    if not times:
        raise ValueError(f"No trip measurements found in {path}")
    return times


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    times = trip_times_ms(LOG)
    median = statistics.median(times)
    print(
        f"N={len(times)} median_ms={median:.3f} "
        f"min_ms={min(times):.3f} max_ms={max(times):.3f}"
    )

    fig, ax = plt.subplots(figsize=(8, 14 / 3), dpi=150)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    counts, _, _ = ax.hist(
        times, bins=12, color="#3176a6", edgecolor="white", linewidth=1
    )
    ax.set_ylim(0, max(counts) * 1.3)
    ax.axvline(median, color="#b44732", linestyle="--", linewidth=1.5)
    ax.set_xlabel("watchdog trip time (ms)")
    ax.set_ylabel("count")
    ax.set_title(
        f"[HW] Watchdog trip time on MPFS250T silicon, "
        f"N={len(times)}, median {median:.3f} ms"
    )
    ax.text(
        0.5, 0.97,
        "120 clear-to-trip events, polled at 1 MHz timebase, "
        "2026-07-01 (watchdog_trip_run1.log)",
        transform=ax.transAxes, ha="center", va="top", fontsize=8,
    )
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=150, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
