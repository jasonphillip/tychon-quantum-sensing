"""B2.1 — PCA fidelity: simulator CW-ODMR vs Sengottuvel Zenodo (record 7233869).

Quantifies how closely the dominant principal-component subspace of the
simulator's `production_50k` output matches the subspace spanned by the 25
Zenodo experimental ODMR spectra. The deliverable is a span-ratio between
the two top-k PC subspaces and a per-component overlap matrix.

Acceptance (per May-4 reorientation):
    span-ratio >= 0.80 -> defensible "sim-to-real validation" bullet
    span-ratio <  0.80 -> documented sim-to-real gap

Run:
    python experiments/pca_fidelity_zenodo.py \\
        --zenodo <nv-sensor-sim>/data/experimental/zenodo_odmr \\
        --sim data/production_50k/dataset.h5 \\
        --n-sim 1000 --k 5 \\
        --memo notes/pca_fidelity_zenodo.md
"""

from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np


# ---------------------------------------------------------------------------
# I/O


def load_zenodo(root: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Load all f*_odmr.csv files. Returns (freqs_Hz, pl, filenames)."""
    files = sorted(root.glob("f*_odmr.csv"), key=lambda p: int(p.stem.split("_")[0][1:]))
    if not files:
        raise FileNotFoundError(f"no f*_odmr.csv under {root}")

    freqs_ref: np.ndarray | None = None
    rows: list[np.ndarray] = []
    names: list[str] = []
    for path in files:
        with path.open("r", newline="") as fh:
            reader = csv.DictReader(fh)
            f, pl = [], []
            for row in reader:
                f.append(float(row["frequency_Hz"]))
                pl.append(float(row["pl_signal"]))
        freqs = np.asarray(f, dtype=np.float64)
        pls = np.asarray(pl, dtype=np.float64)
        if freqs_ref is None:
            freqs_ref = freqs
        elif not np.allclose(freqs, freqs_ref, rtol=0, atol=1.0):
            raise ValueError(f"frequency grid mismatch at {path.name}")
        rows.append(pls)
        names.append(path.name)
    assert freqs_ref is not None
    return freqs_ref, np.stack(rows, axis=0), names


def load_simulator(h5_path: Path, n_take: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Load the simulator train-split frequency grid and a random subsample of spectra."""
    with h5py.File(h5_path, "r") as h5:
        freqs_ds = h5["train/frequencies"]
        spec_ds = h5["train/spectra"]
        assert isinstance(freqs_ds, h5py.Dataset) and isinstance(spec_ds, h5py.Dataset)
        freqs = np.asarray(freqs_ds[:], dtype=np.float64)
        n_total = spec_ds.shape[0]
        idx = np.sort(rng.choice(n_total, size=min(n_take, n_total), replace=False))
        sub = np.asarray(spec_ds[idx, :], dtype=np.float64)
    return freqs, sub


# ---------------------------------------------------------------------------
# Preprocessing


def crop_and_resample(
    src_freqs: np.ndarray,
    src_spec: np.ndarray,
    target_freqs: np.ndarray,
) -> np.ndarray:
    """Linear-interpolate each row of src_spec onto target_freqs.

    Requires target_freqs to lie inside src_freqs (we error otherwise rather
    than silently extrapolating).
    """
    if target_freqs.min() < src_freqs.min() or target_freqs.max() > src_freqs.max():
        raise ValueError(
            "target grid is not contained in source grid: "
            f"target [{target_freqs.min():.3e}, {target_freqs.max():.3e}] "
            f"vs source [{src_freqs.min():.3e}, {src_freqs.max():.3e}]"
        )
    out = np.empty((src_spec.shape[0], target_freqs.size), dtype=np.float64)
    for i, row in enumerate(src_spec):
        out[i] = np.interp(target_freqs, src_freqs, row)
    return out


def normalize_unit_baseline(spec: np.ndarray) -> np.ndarray:
    """Divide each spectrum by its own 95th-percentile (a baseline-like value).

    Removes the absolute-PL-units mismatch between simulator (around 1.0) and
    Zenodo (around 1010 raw counts) while preserving the contrast structure.
    """
    baseline = np.percentile(spec, 95, axis=1, keepdims=True)
    return spec / baseline


def center(spec: np.ndarray) -> np.ndarray:
    """Subtract the mean spectrum across the population."""
    return spec - spec.mean(axis=0, keepdims=True)


# ---------------------------------------------------------------------------
# PCA + subspace metrics


@dataclass
class PCAResult:
    components: np.ndarray  # (k, n_features), unit-norm rows
    explained_variance_ratio: np.ndarray  # (k,)


def pca_top_k(spec: np.ndarray, k: int) -> PCAResult:
    """Top-k PCs of spec by SVD on the centred data."""
    X = center(spec)
    # economy SVD; rows of Vt are the principal components
    _, S, Vt = np.linalg.svd(X, full_matrices=False)
    var = (S ** 2) / max(X.shape[0] - 1, 1)
    var_ratio = var / var.sum()
    return PCAResult(components=Vt[:k], explained_variance_ratio=var_ratio[:k])


def principal_angles(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Cosines of principal angles between span(A^T) and span(B^T).

    A and B are (k, n) row matrices of orthonormal vectors. Returns k cosines
    in [0, 1], sorted descending (so the last entry is the worst alignment).
    """
    M = A @ B.T  # (k, k)
    s = np.linalg.svd(M, compute_uv=False)
    s = np.clip(s, 0.0, 1.0)
    return s


# ---------------------------------------------------------------------------
# Memo emitter


def write_memo(
    memo_path: Path,
    *,
    n_zenodo: int,
    n_sim: int,
    k: int,
    target_freqs: np.ndarray,
    cos_angles: np.ndarray,
    overlap_matrix: np.ndarray,
    sim_var_ratio: np.ndarray,
    zen_var_ratio: np.ndarray,
    span_ratio_product: float,
    span_ratio_min: float,
    pass_threshold: bool,
) -> None:
    memo_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# PCA fidelity — simulator CW-ODMR vs Sengottuvel Zenodo (record 7233869)")
    lines.append("")
    lines.append(f"- Date: 2026-05-17")
    lines.append(f"- Simulator subsample: {n_sim} spectra from `production_50k/train`")
    lines.append(f"- Experimental: {n_zenodo} spectra from `zenodo_odmr/f*.csv`")
    lines.append(
        f"- Common grid: {target_freqs.size} points, "
        f"{target_freqs[0] / 1e9:.4f}–{target_freqs[-1] / 1e9:.4f} GHz "
        "(simulator-native grid; Zenodo cropped+interpolated)"
    )
    lines.append(f"- PCA components compared: top-{k}")
    lines.append("")
    lines.append("## Span ratio")
    lines.append("")
    lines.append(
        f"- min cos(principal angle) = **{span_ratio_min:.3f}**  (worst-aligned direction)"
    )
    lines.append(
        f"- product of cos(principal angles) = **{span_ratio_product:.3f}**  "
        "(Frobenius-like overall fidelity)"
    )
    lines.append(
        f"- Acceptance threshold (≥ 0.80 on min cos): "
        f"**{'PASS' if pass_threshold else 'FAIL'}**"
    )
    lines.append("")
    if pass_threshold:
        lines.append(
            "**Conclusion.** The simulator's dominant PC subspace tracks the experimental "
            "subspace to within 0.80 on the worst-aligned canonical direction. Defensible "
            "to cite as a sim-to-real validation bullet in external materials."
        )
    else:
        lines.append(
            "**Conclusion.** The worst-aligned canonical direction falls below the 0.80 "
            "threshold. Document the sim-to-real gap honestly; do NOT cite the simulator "
            "as experimentally-validated without scope language. See per-component table "
            "below to locate the disagreement."
        )
    lines.append("")
    lines.append("## Per-component canonical cosines")
    lines.append("")
    lines.append("| i | cos θ_i |")
    lines.append("|---|---------|")
    for i, c in enumerate(cos_angles, start=1):
        lines.append(f"| {i} | {c:.4f} |")
    lines.append("")
    lines.append("## Cross-overlap matrix (|sim_i · zen_j|)")
    lines.append("")
    header = "| i\\j | " + " | ".join(f"zen {j+1}" for j in range(k)) + " |"
    sep = "|---|" + "---|" * k
    lines.append(header)
    lines.append(sep)
    for i in range(k):
        row = f"| sim {i+1} | " + " | ".join(f"{overlap_matrix[i, j]:.3f}" for j in range(k)) + " |"
        lines.append(row)
    lines.append("")
    lines.append("## Explained-variance ratios (top-k)")
    lines.append("")
    lines.append("| i | sim var ratio | zen var ratio |")
    lines.append("|---|---------------|---------------|")
    for i in range(k):
        lines.append(f"| {i+1} | {sim_var_ratio[i]:.4f} | {zen_var_ratio[i]:.4f} |")
    lines.append("")
    lines.append("## Method notes")
    lines.append("")
    lines.append(
        "- Each spectrum is normalized by its own 95th-percentile (removes the "
        "PL-counts vs unitless-contrast unit mismatch), then population-mean-centred."
    )
    lines.append(
        "- Zenodo (200 pts, 2.700–3.000 GHz) is linearly interpolated onto the "
        "simulator grid (100 pts, 2.820–2.920 GHz). The Zenodo points outside the "
        "simulator window are discarded — the simulator was designed for the ms=0↔±1 "
        "resonance neighbourhood at typical bias fields, so the comparison is fair on "
        "the simulator's native scope, not on the wider experimental window."
    )
    lines.append(
        "- Subspace alignment uses cosines of canonical (principal) angles between "
        "the top-k PC subspaces, computed via SVD of the inner-product matrix. The "
        "span-ratio is reported both as min(cos θ_i) (worst direction) and "
        "Π cos θ_i (Frobenius-like product)."
    )
    lines.append("")
    memo_path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Main


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zenodo", type=Path, required=True)
    ap.add_argument("--sim", type=Path, required=True)
    ap.add_argument("--n-sim", type=int, default=1000)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--memo", type=Path, required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--threshold", type=float, default=0.80)
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)

    print(f"[B2.1] loading Zenodo from {args.zenodo}")
    zen_loaded = load_zenodo(args.zenodo)
    zen_freqs, zen_pl = zen_loaded[0], zen_loaded[1]
    print(f"       {zen_pl.shape[0]} spectra × {zen_pl.shape[1]} pts; "
          f"{zen_freqs[0]/1e9:.4f}-{zen_freqs[-1]/1e9:.4f} GHz")

    print(f"[B2.1] loading simulator from {args.sim} (n={args.n_sim})")
    sim_freqs, sim_pl = load_simulator(args.sim, args.n_sim, rng)
    print(f"       {sim_pl.shape[0]} spectra × {sim_pl.shape[1]} pts; "
          f"{sim_freqs[0]/1e9:.4f}-{sim_freqs[-1]/1e9:.4f} GHz")

    print("[B2.1] interpolating Zenodo onto simulator grid")
    zen_resampled = crop_and_resample(zen_freqs, zen_pl, sim_freqs)

    print("[B2.1] normalizing (per-spectrum 95th-percentile baseline)")
    sim_n = normalize_unit_baseline(sim_pl)
    zen_n = normalize_unit_baseline(zen_resampled)

    print(f"[B2.1] PCA top-{args.k} on both populations")
    sim_pca = pca_top_k(sim_n, args.k)
    zen_pca = pca_top_k(zen_n, args.k)

    print("[B2.1] principal angles between subspaces")
    cos_angles = principal_angles(sim_pca.components, zen_pca.components)
    overlap = np.abs(sim_pca.components @ zen_pca.components.T)
    span_ratio_min = float(cos_angles.min())
    span_ratio_prod = float(np.prod(cos_angles))
    passes = span_ratio_min >= args.threshold

    print(f"       cos angles: {np.array2string(cos_angles, precision=4)}")
    print(f"       min cos = {span_ratio_min:.4f}  (threshold {args.threshold:.2f}: "
          f"{'PASS' if passes else 'FAIL'})")
    print(f"       prod cos = {span_ratio_prod:.4f}")

    write_memo(
        args.memo,
        n_zenodo=zen_pl.shape[0],
        n_sim=sim_pl.shape[0],
        k=args.k,
        target_freqs=sim_freqs,
        cos_angles=cos_angles,
        overlap_matrix=overlap,
        sim_var_ratio=sim_pca.explained_variance_ratio,
        zen_var_ratio=zen_pca.explained_variance_ratio,
        span_ratio_product=span_ratio_prod,
        span_ratio_min=span_ratio_min,
        pass_threshold=passes,
    )
    print(f"[B2.1] memo written -> {args.memo}")

    summary = {
        "span_ratio_min": span_ratio_min,
        "span_ratio_product": span_ratio_prod,
        "cos_angles": cos_angles.tolist(),
        "passes_threshold": passes,
        "threshold": args.threshold,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
