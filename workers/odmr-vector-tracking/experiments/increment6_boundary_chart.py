"""Increment-6 fieldcone boundary chart — lock-loss vs (off-bias angle x |B|), v2 -> v6.

Renders the tri-eval-3 artifact (`fieldcone_v6.json`, clean rung; snr30 is near-identical and
stated in the caption) as a dumbbell plot: one row per evaluated (angle, |B|) geometry,
v2 -> v6 pooled lock-loss with CV-KF (GT t=0 init) as an open reference marker. Rows are
grouped by bucket_class (failure / in-envelope control / beyond-envelope probes).

    python experiments/increment6_boundary_chart.py

Writes `artifacts/increment6/fieldcone_boundary.png`.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

_REPO = Path(__file__).resolve().parent.parent
FC = json.load(open(_REPO / "artifacts" / "increment6" / "fieldcone_v6.json"))
OUT = _REPO / "artifacts" / "increment6" / "fieldcone_boundary.png"

SURFACE, INK, INK2, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
C_V2, C_V6, C_KF = "#2a78d6", "#1baf7a", "#eda100"  # validated categorical slots 1-3

ROWS = [  # (bucket label filter) -> display label; order: mild -> extreme within class
    ("failure", 41.0, "41.1° · 3.92 mT  (0,2) merge"),
    ("failure", 52.8, "52.8° · 3.26 mT  (4,6) merge"),
    ("control", 10.0, "10° · 5.0 mT"),
    ("control", 30.0, "30° · 4.5 mT"),
    ("control", 45.0, "45° · 4.0 mT"),
    ("control", 52.0, "52° · 3.6 mT"),
    ("beyond", 40.0, "40° · 2.5 mT  (below |B| floor)"),
    ("beyond", 50.0, "50° · 2.0 mT  (below |B| floor)"),
    ("beyond", 66.0, "66° · 3.6 mT  (past cone)"),
    ("beyond", 70.0, "70° · 3.3 mT  (past cone)"),
]
CLASS_OF = {"failure": 0, "control": 1, "beyond": 2}
GROUPS = [("Directed failure geometries (the increment-5 gap)", 0, 2),
          ("In-envelope control ladder", 2, 6),
          ("Beyond-envelope probes (generalization statement)", 6, 10)]


def rate(names: list[str], idx: np.ndarray) -> float:
    lost = sum(sum(FC["cells"]["clean"][s]["lost_all"][i] for i in idx) for s in names)
    return lost / (len(idx) * len(names))


def main() -> int:
    bc = np.array(FC["bucket_class"])
    ang = np.array(FC["target_angle_deg"])

    v2r, v6r, kfr = [], [], []
    for cls_name, a, _label in ROWS:
        cls = CLASS_OF[cls_name]
        idx = (np.flatnonzero((bc == cls) & (np.abs(ang - a) < 3))
               if cls_name == "failure" else np.flatnonzero((bc == cls) & (ang == a)))
        v2r.append(rate(FC["gens"]["v2"], idx))
        v6r.append(rate(FC["gens"]["v6"], idx))
        kf_lost = sum(FC["cells"]["clean"]["kf"]["lost_all"][i] for i in idx)
        kfr.append(kf_lost / len(idx))

    fig, ax = plt.subplots(figsize=(8.6, 5.4), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ys = np.arange(len(ROWS))[::-1].astype(float)
    for g, (_, lo, hi) in enumerate(GROUPS):  # extra gap between class groups
        ys[lo:hi] += (2 - g) * 0.9

    ax.xaxis.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for y, a, b in zip(ys, v2r, v6r):
        ax.plot([a, b], [y, y], color=BASELINE, linewidth=2, zorder=2)
    ax.scatter(v2r, ys, s=110, color=C_V2, zorder=3, label="v2 (deployed)")
    ax.scatter(v6r, ys, s=52, color=C_V6, edgecolors=SURFACE, linewidths=1.6, zorder=4,
               label="v6 coverage retrain")
    ax.scatter(kfr, ys, s=46, facecolors="none", edgecolors=C_KF, linewidths=2, zorder=3,
               label="CV-KF ref (GT t=0 init)")

    for y, b in zip(ys, v6r):  # relief rule: direct-label the v6 value on every row
        ax.annotate(f"{b:.2f}", (b, y), textcoords="offset points", xytext=(0, 8),
                    ha="center", fontsize=8, color=INK2)

    ax.set_yticks(ys)
    ax.set_yticklabels([r[2] for r in ROWS], fontsize=9, color=INK)
    for (title, lo, hi) in GROUPS:
        ax.text(-0.02, ys[lo] + 0.62, title, transform=ax.get_yaxis_transform(),
                ha="right", va="bottom", fontsize=8.5, color=MUTED, style="italic")
    ax.set_xlim(-0.04, 1.06)
    ax.set_xlabel("field lock-loss rate (clean rung; pooled 3 seeds, 12 seqs/geometry)",
                  fontsize=9, color=INK2)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)

    ax.set_title("Field-acquisition boundary: v6 coverage retrain vs deployed (v2)",
                 fontsize=10.5, color=INK, loc="left", pad=30)
    ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.005), ncols=3, frameon=False,
              fontsize=8, labelcolor=INK2, columnspacing=1.2, handletextpad=0.4)
    fig.text(0.055, 0.012,
             "snr30 rung is near-identical (verdict Part 3). Beyond-envelope probes: v6 "
             "never-acquires in 135–144/144 — a cliff at the training envelope, not decay.",
             fontsize=7.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    fig.savefig(OUT, facecolor=SURFACE)
    print(f"[chart] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
