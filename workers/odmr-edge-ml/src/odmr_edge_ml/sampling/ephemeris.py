"""SGP4/IGRF-14 ephemeris-derived importance sampler (P3-12).

Computes per-sample weights so that the *training distribution* of θ
matches the marginal θ-density observed in the v1 LEO benchmark
(``tychon_shared_data.orbit_in_the_loop``). The orbit benchmark ships
3 LEO orbits (ISS-like 51.6°, polar 85°, SSO 97.5°) at ~400 km, 24 h ×
dt=1 s — i.e. ~260K (orbit_id, t) rows of payload-frame B-vectors that
together span the realistic LEO attitude+field envelope.

Importance weight per training sample i:

    w_i = p_orbit(θ_i) / p_dataset(θ_i)

where both densities are 1-D Gaussian KDEs on θ. Weights normalized to
mean=1 so ``WeightedRandomSampler`` per-epoch count is preserved.

The orbit iterable is overridable for testability — the unit test
injects a synthetic 100-row orbit since the v1 parquet shards aren't
yet on disk.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from odmr_edge_ml.sampling.theta_utils import polar_theta_from_labels


def _kde_eval(samples: np.ndarray, query: np.ndarray, bw: float | None = None) -> np.ndarray:
    """Tiny 1-D Gaussian KDE evaluator (no scipy dependency).

    Returns ``p(query)`` with bandwidth from Silverman's rule if not given.
    Vectorized over ``query`` but loops over the kernel sum in a
    memory-friendly way to handle the 260K-row orbit benchmark without
    a 260K × N intermediate.
    """
    samples = np.asarray(samples, dtype=np.float64)
    query = np.asarray(query, dtype=np.float64)
    n = len(samples)
    if n == 0:
        raise ValueError("KDE requires at least one sample")
    std = float(samples.std()) or 1.0
    if bw is None:
        # Silverman's rule of thumb
        bw_eff: float = max(1.06 * std * n ** (-1.0 / 5.0), 1e-3)
    else:
        bw_eff = float(bw)
    norm = 1.0 / (n * bw_eff * np.sqrt(2.0 * np.pi))
    out = np.zeros_like(query)
    chunk = 8192
    for start in range(0, n, chunk):
        s = samples[start:start + chunk]
        # (chunk, len(query))
        z = (query[None, :] - s[:, None]) / bw_eff
        out += np.exp(-0.5 * z * z).sum(axis=0)
    return out * norm


def ephemeris_theta_weights(
    labels: np.ndarray,
    *,
    orbit_version: str = "v1",
    orbit_iter: Iterable[dict[str, Any]] | None = None,
    eps: float = 1e-3,
    max_weight_ratio: float = 50.0,
) -> np.ndarray:
    """Importance weights matching the marginal θ-density of the orbit benchmark.

    Parameters
    ----------
    labels
        ``(N, 3)`` training B-vectors (units irrelevant; only direction
        used).
    orbit_version
        Passed to ``tychon_shared_data.orbit_in_the_loop.load_orbit_dataset``
        if ``orbit_iter`` is not provided. Default ``"v1"`` (3 orbits ×
        86400 s).
    orbit_iter
        Optional pre-loaded orbit iterable for testability. Each yielded
        item must be a dict with keys
        ``B_payload_x``, ``B_payload_y``, ``B_payload_z`` (1-D arrays).
        If ``None``, the function loads via the canonical loader.
    eps
        Stability floor applied to the dataset-density denominator.
    max_weight_ratio
        Cap on max(w) / median(w) so a single under-represented bin
        doesn't dominate the epoch. Default 50× empirically keeps the
        effective sample size sane for the 50K production corpus.

    Returns
    -------
    np.ndarray
        ``(N,)`` non-negative float64 weights, normalized to mean=1.
    """
    if orbit_iter is None:
        from tychon_shared_data.orbit_in_the_loop import load_orbit_dataset
        orbits: Iterable[dict[str, Any]] = load_orbit_dataset(version=orbit_version)
    else:
        orbits = orbit_iter

    # Concatenate payload-frame B-vectors across all orbits.
    px, py, pz = [], [], []
    for orbit in orbits:
        px.append(np.asarray(orbit["B_payload_x"], dtype=np.float64))
        py.append(np.asarray(orbit["B_payload_y"], dtype=np.float64))
        pz.append(np.asarray(orbit["B_payload_z"], dtype=np.float64))
    if not px:
        raise ValueError(
            f"no orbits yielded for version={orbit_version!r}; "
            "is the v1 dataset on disk?"
        )
    orbit_b = np.stack(
        [np.concatenate(px), np.concatenate(py), np.concatenate(pz)], axis=1,
    )
    theta_orbit = polar_theta_from_labels(orbit_b)
    theta_dataset = polar_theta_from_labels(np.asarray(labels, dtype=np.float64))

    p_orbit = _kde_eval(theta_orbit, theta_dataset)
    p_dataset = _kde_eval(theta_dataset, theta_dataset)
    w = p_orbit / np.maximum(p_dataset, eps)

    # Cap extreme ratios — protects effective sample size.
    median_w = float(np.median(w))
    if median_w > 0:
        w = np.minimum(w, max_weight_ratio * median_w)

    # Normalize to mean=1.
    w *= len(w) / w.sum()
    return w.astype(np.float64)
