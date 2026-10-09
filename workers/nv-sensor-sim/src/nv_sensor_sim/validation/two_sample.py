"""Two-sample statistical tests for generator-vs-real spectra validation.

Extends the point-metric comparisons in ``reference_comparison`` with
distribution-level two-sample tests, following the methodology in
arXiv:2409.16336 ("Two-sample tests for validating generators in precision
sciences"): a synthetic dataset is judged not by matching a handful of
summary statistics but by failing to be statistically distinguishable from
real data under a battery of two-sample tests.

Data convention (shared with the dataset-generation pipelines, e.g.
``pipelines.batch_generate``, which build ``spectra = np.zeros((n_split,
n_freq_points))``): a set of spectra is a 2-D array of shape ``(n_samples,
n_features)`` — one row per spectrum, one column per frequency bin. The two
sets being compared must share the same frequency grid, i.e. the same
``n_features`` and (implicitly) the same bin-to-frequency mapping; this
module does not resample, interpolate, or align frequency grids itself
(unlike ``reference_comparison.compute_spectral_mse``, which does — see
module docstring in that file). ``n_samples`` may differ between the two
sets.

Provided statistics:
- ``sliced_wasserstein``: mean 1-D Wasserstein-1 distance over random
  projections (a cheap surrogate for the full-dimensional distance).
- ``mmd_rbf``: unbiased Maximum Mean Discrepancy with an RBF kernel.
- ``ks_max_per_bin``: worst-case (max over bins) per-frequency-bin
  Kolmogorov-Smirnov statistic.

``permutation_pvalue`` turns any of these into a calibrated p-value via a
label-permutation null; ``compare_spectra_sets`` runs all three and returns
one report dict. All three statistics are "distance-like" (0 = identical,
larger = more different), so every p-value here is one-sided and produced
by the same permutation-null machinery in this module — scipy's own
asymptotic ``ks_2samp`` p-value is deliberately not used, so all three
sub-tests are comparable on the same footing.
"""

from __future__ import annotations

from typing import Callable

import numpy as np
from scipy.spatial.distance import cdist, pdist
from scipy.stats import ks_2samp

__all__ = [
    "sliced_wasserstein",
    "mmd_rbf",
    "ks_max_per_bin",
    "permutation_pvalue",
    "compare_spectra_sets",
]


def _validate_two_sample(X: np.ndarray, Y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Validate and cast a pair of spectra matrices for a two-sample test.

    Parameters
    ----------
    X, Y : np.ndarray
        Candidate spectra matrices, expected shape ``(n_samples, n_features)``.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        ``(X, Y)`` cast to ``float64``.

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share ``n_features``, or either has fewer
        than 2 samples. The 2-sample floor is a hard requirement (not just a
        statistical-power preference): the unbiased MMD estimator divides
        by ``n * (n - 1)`` per group.
    """
    X = np.asarray(X, dtype=np.float64)
    Y = np.asarray(Y, dtype=np.float64)
    if X.ndim != 2 or Y.ndim != 2:
        raise ValueError(
            "X and Y must be 2-D (n_samples, n_features) spectra matrices "
            f"(row = one spectrum); got shapes {X.shape} and {Y.shape}"
        )
    if X.shape[1] != Y.shape[1]:
        raise ValueError(
            "X and Y must be evaluated on the same aligned frequency grid "
            f"(n_features); got {X.shape[1]} and {Y.shape[1]} features"
        )
    if X.shape[0] < 2 or Y.shape[0] < 2:
        raise ValueError(
            "Two-sample statistics require at least 2 samples per group "
            "(the unbiased MMD estimator divides by n*(n-1)); got "
            f"{X.shape[0]} sample(s) in X and {Y.shape[0]} sample(s) in Y"
        )
    return X, Y


def _w1_1d(a: np.ndarray, b: np.ndarray) -> float:
    """1-D Wasserstein-1 distance between two empirical samples.

    Computed by sorting both samples and differencing order statistics ("W1
    via sorted differences"). When the two samples are the same size this is
    the exact discrete-OT solution (monotone rearrangement): mean absolute
    difference of matched order statistics. When sizes differ, both
    empirical quantile functions are linearly interpolated onto a shared
    grid of quantile levels before differencing.
    """
    a_sorted = np.sort(a)
    b_sorted = np.sort(b)
    if a_sorted.size == b_sorted.size:
        return float(np.mean(np.abs(a_sorted - b_sorted)))

    n = max(a_sorted.size, b_sorted.size)
    q = (np.arange(n) + 0.5) / n
    a_q = np.interp(q, (np.arange(a_sorted.size) + 0.5) / a_sorted.size, a_sorted)
    b_q = np.interp(q, (np.arange(b_sorted.size) + 0.5) / b_sorted.size, b_sorted)
    return float(np.mean(np.abs(a_q - b_q)))


def sliced_wasserstein(
    X: np.ndarray,
    Y: np.ndarray,
    n_projections: int = 128,
    rng: int | np.random.Generator | None = None,
) -> float:
    """Mean sliced Wasserstein-1 distance between two sets of spectra.

    Projects both spectra sets onto ``n_projections`` random 1-D directions
    (uniform on the unit sphere in feature space) and averages the 1-D
    Wasserstein-1 distance (via sorted differences, see ``_w1_1d``) over
    projections. This is a cheap surrogate for the generally-intractable
    full-dimensional Wasserstein distance.

    Parameters
    ----------
    X, Y : np.ndarray
        Spectra matrices of shape ``(n_samples, n_features)``; row = one
        spectrum. Must share the same ``n_features`` (aligned frequency
        grid); ``n_samples`` may differ between X and Y.
    n_projections : int
        Number of random projection directions.
    rng : int, np.random.Generator, or None
        Seed or generator for the random directions.

    Returns
    -------
    float
        Mean W1 distance over the random projections. Exactly ``0.0`` when
        X and Y hold identical values (every projection then differences a
        sorted array against itself, including when called as
        ``sliced_wasserstein(X, X)``).

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share n_features, or have <2 samples.
    """
    X, Y = _validate_two_sample(X, Y)
    rng = np.random.default_rng(rng)
    n_features = X.shape[1]

    directions = rng.standard_normal((n_projections, n_features))
    norms = np.linalg.norm(directions, axis=1, keepdims=True)
    directions /= norms

    x_proj = X @ directions.T  # (n_samples_X, n_projections)
    y_proj = Y @ directions.T  # (n_samples_Y, n_projections)

    distances = np.empty(n_projections)
    for p in range(n_projections):
        distances[p] = _w1_1d(x_proj[:, p], y_proj[:, p])
    return float(np.mean(distances))


def mmd_rbf(
    X: np.ndarray,
    Y: np.ndarray,
    bandwidth: float | None = None,
) -> float:
    """Unbiased squared Maximum Mean Discrepancy with an RBF kernel.

    Uses the Gretton et al. (2012) unbiased U-statistic estimator::

        MMD_u^2 = mean_{i!=j} k(x_i, x_j) + mean_{i!=j} k(y_i, y_j)
                  - 2 * mean_{i,j} k(x_i, y_j)

    with ``k(u, v) = exp(-||u - v||^2 / (2 * bandwidth^2))``. The estimator
    is unbiased, so a small negative value for two nearly-identical
    distributions is expected and not a bug.

    Parameters
    ----------
    X, Y : np.ndarray
        Spectra matrices of shape ``(n_samples, n_features)``; row = one
        spectrum. Must share the same ``n_features``; ``n_samples`` may
        differ between X and Y.
    bandwidth : float or None
        RBF kernel bandwidth (the ``sigma`` in the exponent above). If None
        (default), uses the median pairwise-Euclidean-distance heuristic
        computed on the pooled sample ``vstack([X, Y])``.

    Returns
    -------
    float
        Unbiased MMD^2 estimate.

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share n_features, or have <2 samples.
    """
    X, Y = _validate_two_sample(X, Y)
    m, n = X.shape[0], Y.shape[0]

    if bandwidth is None:
        pooled = np.vstack([X, Y])
        bandwidth = float(np.median(pdist(pooled, metric="euclidean")))
        if bandwidth <= 0.0:
            # Degenerate pooled sample (e.g. many duplicate rows): fall back
            # to a small positive bandwidth rather than dividing by zero.
            bandwidth = 1e-12

    gamma = 1.0 / (2.0 * bandwidth**2)
    Kxx = np.exp(-gamma * cdist(X, X, metric="sqeuclidean"))
    Kyy = np.exp(-gamma * cdist(Y, Y, metric="sqeuclidean"))
    Kxy = np.exp(-gamma * cdist(X, Y, metric="sqeuclidean"))
    np.fill_diagonal(Kxx, 0.0)
    np.fill_diagonal(Kyy, 0.0)

    term_x = Kxx.sum() / (m * (m - 1))
    term_y = Kyy.sum() / (n * (n - 1))
    term_xy = Kxy.sum() / (m * n)
    return float(term_x + term_y - 2.0 * term_xy)


def ks_max_per_bin(X: np.ndarray, Y: np.ndarray) -> tuple[float, int]:
    """Worst-case per-frequency-bin two-sample Kolmogorov-Smirnov statistic.

    Runs ``scipy.stats.ks_2samp`` independently on each frequency bin
    (column) — comparing ``X[:, j]`` vs ``Y[:, j]`` across samples — and
    reports the bin with the largest KS statistic. This flags a single
    frequency bin where the two spectra sets diverge even when aggregate
    statistics (e.g. mean-spectrum MSE) look fine.

    Parameters
    ----------
    X, Y : np.ndarray
        Spectra matrices of shape ``(n_samples, n_features)``; row = one
        spectrum. Must share the same ``n_features`` (aligned frequency
        grid); ``n_samples`` may differ between X and Y.

    Returns
    -------
    tuple[float, int]
        ``(max_ks_statistic, argmax_bin)`` — the largest per-bin KS
        statistic and the column index (frequency bin) it occurred at.

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share n_features, or have <2 samples.
    """
    X, Y = _validate_two_sample(X, Y)
    n_features = X.shape[1]
    stats = np.empty(n_features)
    for j in range(n_features):
        stats[j] = ks_2samp(X[:, j], Y[:, j]).statistic
    argmax_bin = int(np.argmax(stats))
    return float(stats[argmax_bin]), argmax_bin


def permutation_pvalue(
    stat_fn: Callable[[np.ndarray, np.ndarray], float],
    X: np.ndarray,
    Y: np.ndarray,
    n_permutations: int = 200,
    rng: int | np.random.Generator | None = None,
) -> tuple[float, float]:
    """Permutation-test p-value for any two-sample statistic.

    Computes the observed statistic ``stat_fn(X, Y)``, then repeatedly pools
    X and Y, randomly relabels the pooled rows into groups of the original
    sizes (``n_samples`` of X, ``n_samples`` of Y), and recomputes the
    statistic on the relabeled groups. ``stat_fn`` is assumed to be
    "distance-like" (larger = more disagreement between the two groups —
    true of ``sliced_wasserstein``, ``mmd_rbf``, and ``ks_max_per_bin``), so
    the test is one-sided: the p-value is the fraction of relabelings whose
    statistic is at least as large as the observed one.

    The p-value uses the standard ``(1 + #{permuted >= observed}) /
    (n_permutations + 1)`` correction (Phipson & Smyth 2010), which is
    always > 0 and is itself an unbiased estimate of the true (exhaustive)
    permutation p-value.

    Parameters
    ----------
    stat_fn : callable
        ``stat_fn(A, B) -> float`` for two spectra matrices A, B sharing
        n_features with X, Y. Any extra randomness ``stat_fn`` itself needs
        (e.g. ``sliced_wasserstein``'s random projections) must be closed
        over by the caller — this function calls ``stat_fn`` with exactly
        two positional arguments.
    X, Y : np.ndarray
        Spectra matrices of shape ``(n_samples, n_features)``; row = one
        spectrum. Must share the same ``n_features``; ``n_samples`` may
        differ between X and Y.
    n_permutations : int
        Number of random relabelings.
    rng : int, np.random.Generator, or None
        Seed or generator for the relabelings.

    Returns
    -------
    tuple[float, float]
        ``(observed_statistic, p_value)``.

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share n_features, or have <2 samples.
    """
    X, Y = _validate_two_sample(X, Y)
    rng = np.random.default_rng(rng)
    n_x = X.shape[0]
    n_total = n_x + Y.shape[0]
    pooled = np.vstack([X, Y])

    observed = float(stat_fn(X, Y))

    count_ge = 0
    for _ in range(n_permutations):
        perm = rng.permutation(n_total)
        X_perm = pooled[perm[:n_x]]
        Y_perm = pooled[perm[n_x:]]
        if float(stat_fn(X_perm, Y_perm)) >= observed:
            count_ge += 1

    p_value = (1.0 + count_ge) / (n_permutations + 1.0)
    return observed, p_value


def compare_spectra_sets(
    X: np.ndarray,
    Y: np.ndarray,
    n_permutations: int = 200,
    rng: int | np.random.Generator | None = None,
) -> dict:
    """Run all three two-sample tests and report statistics + p-values.

    A single deterministic (given ``rng``) report combining
    ``sliced_wasserstein``, ``mmd_rbf``, and ``ks_max_per_bin``, each with a
    ``permutation_pvalue`` p-value. One internal ``np.random.default_rng(rng)``
    is threaded sequentially through every random draw in this function, so
    two calls with the same ``rng`` seed produce bit-identical output.
    ``sliced_wasserstein``'s random projection directions are drawn once
    (seeded from ``rng``) and reused, unchanged, across every permutation
    replicate of its own p-value test — this isolates label-permutation
    variance from projection Monte-Carlo variance in that sub-test's null
    distribution.

    Parameters
    ----------
    X, Y : np.ndarray
        Spectra matrices of shape ``(n_samples, n_features)``; row = one
        spectrum, aligned frequency grid (same n_features). ``n_samples``
        may differ between X and Y.
    n_permutations : int
        Number of relabelings for each of the three permutation tests.
    rng : int, np.random.Generator, or None
        Seed or generator for every random draw in this function
        (projections + all three permutation tests).

    Returns
    -------
    dict
        ``{"sliced_wasserstein": {"statistic": float, "p_value": float},
           "mmd_rbf": {"statistic": float, "p_value": float},
           "ks_max_per_bin": {"statistic": float, "argmax_bin": int,
                               "p_value": float},
           "n_samples": {"X": int, "Y": int}}``

    Raises
    ------
    ValueError
        If X/Y are not 2-D, don't share n_features, or have <2 samples.
    """
    X, Y = _validate_two_sample(X, Y)
    rng = np.random.default_rng(rng)

    sw_seed = int(rng.integers(0, 2**63 - 1))

    def _sw_stat(a: np.ndarray, b: np.ndarray) -> float:
        return sliced_wasserstein(a, b, rng=np.random.default_rng(sw_seed))

    sw_obs, sw_p = permutation_pvalue(_sw_stat, X, Y, n_permutations=n_permutations, rng=rng)

    def _mmd_stat(a: np.ndarray, b: np.ndarray) -> float:
        return mmd_rbf(a, b)

    mmd_obs, mmd_p = permutation_pvalue(_mmd_stat, X, Y, n_permutations=n_permutations, rng=rng)

    ks_obs, ks_argbin = ks_max_per_bin(X, Y)

    def _ks_stat(a: np.ndarray, b: np.ndarray) -> float:
        return ks_max_per_bin(a, b)[0]

    _, ks_p = permutation_pvalue(_ks_stat, X, Y, n_permutations=n_permutations, rng=rng)

    return {
        "sliced_wasserstein": {"statistic": sw_obs, "p_value": sw_p},
        "mmd_rbf": {"statistic": mmd_obs, "p_value": mmd_p},
        "ks_max_per_bin": {"statistic": ks_obs, "argmax_bin": ks_argbin, "p_value": ks_p},
        "n_samples": {"X": int(X.shape[0]), "Y": int(Y.shape[0])},
    }
