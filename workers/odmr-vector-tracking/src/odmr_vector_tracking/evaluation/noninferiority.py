"""Paired, sequence-blocked non-inferiority comparisons.

Each row is one sequence and model seed. ``item_id`` must identify the same
sequence in both models; ``seed`` identifies matched training seeds. Bootstrap
draws sequence IDs once and retains every seed for each draw. This preserves
within-sequence correlation across seeds. Binary rows may hold one Bernoulli
outcome or event counts with exposure denominators. The latter estimates a
pooled event-rate difference while resampling whole sequences.

Margins below are PROPOSED defaults, NOT APPROVED by Jason. Callers must
record the chosen margin and obtain approval before treating a verdict as a
deployment or policy decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Hashable, Mapping

import numpy as np
from scipy.optimize import brentq


# PROPOSED, NOT APPROVED by Jason. One extra lost sequence per 100 is a small
# but measurable lock cost; zero would reject equal models due to sampling noise.
PROPOSED_LOCK_LOSS_MARGIN = 0.01
# PROPOSED, NOT APPROVED by Jason. One additional wrong association per 100
# collision frames is a conservative identity tolerance.
PROPOSED_MISASSOC_MARGIN = 0.01
# PROPOSED, NOT APPROVED by Jason. One additional switch per 100 opportunities
# is a conservative identity tolerance on the same rate scale.
PROPOSED_IDSW_OPP_MARGIN = 0.01
# PROPOSED, NOT APPROVED by Jason. 0.1 degree is below the reported angular
# differences of concern while allowing small numerical and sample variation.
PROPOSED_AE_POST_MARGIN_DEG = 0.1
PROPOSED_MARGINS = {
    "lock_loss": PROPOSED_LOCK_LOSS_MARGIN,
    "misassoc": PROPOSED_MISASSOC_MARGIN,
    "idsw_opp": PROPOSED_IDSW_OPP_MARGIN,
    "ae_post": PROPOSED_AE_POST_MARGIN_DEG,
}


@dataclass(frozen=True)
class Outcome:
    item_id: Hashable
    seed: Hashable
    value: float
    exposure: float = 1.0


@dataclass(frozen=True)
class Comparison:
    estimate: float
    ci_low: float
    ci_high: float
    margin: float
    verdict: str
    n_sequences: int
    n_pairs: int


def _tango_score_interval(b: float, c: float, n: int,
                          confidence: float) -> tuple[float, float]:
    """Invert Tango's paired-proportion score test (1998, equations 24-26).

    b and c count candidate-only and baseline-only events. Fractional counts
    allow seed-averaged discordances with the sequence as the sampling unit.
    """
    z = NormalDist().inv_cdf((1 + confidence) / 2)
    estimate = (b - c) / n

    def score(theta: float) -> float:
        delta = -theta
        aa = 2 * n
        bb = -b - c - (2 * n - b + c) * delta
        cc = c * delta * (delta + 1)
        q21 = (np.sqrt(max(0.0, bb * bb - 4 * aa * cc)) - bb) / (2 * aa)
        variance = n * (2 * q21 - delta * (delta + 1))
        if variance <= 0:
            if theta == estimate:
                return 0.0
            return float("inf") if theta < estimate else -float("inf")
        return (b - c - n * theta) / np.sqrt(variance)

    lo = -1.0 if estimate == -1 else brentq(lambda x: score(x) - z, -1, estimate)
    hi = 1.0 if estimate == 1 else brentq(lambda x: score(x) + z, estimate, 1)
    return float(lo), float(hi)


def compare_paired(
    candidate: list[Outcome],
    baseline: list[Outcome],
    *,
    margin: float,
    binary: bool,
    confidence: float = 0.95,
    bootstrap_samples: int = 10_000,
    bootstrap_seed: int = 0,
    min_sequences: int = 30,
) -> Comparison:
    """Return CI for candidate-worse minus baseline; smaller values are better.

    Both inputs must contain exactly the same ``(seed, item_id)`` keys. For
    binary counts, ``value`` is an event count and ``exposure`` is its number
    of opportunities. Continuous metrics use ``exposure=1`` and estimate the
    mean paired difference. Insufficient unique sequences yield inconclusive.
    """
    if not np.isfinite(margin) or margin <= 0:
        raise ValueError("margin must be finite and positive")
    if not 0 < confidence < 1 or bootstrap_samples < 1 or min_sequences < 1:
        raise ValueError("invalid confidence, bootstrap_samples, or min_sequences")

    def index(rows: list[Outcome]) -> Mapping[tuple[Hashable, Hashable], Outcome]:
        out = {}
        for row in rows:
            key = (row.seed, row.item_id)
            if key in out:
                raise ValueError(f"duplicate paired key: {key!r}")
            if not np.isfinite(row.value) or not np.isfinite(row.exposure):
                raise ValueError("outcomes must be finite")
            if binary and (row.exposure <= 0 or row.value < 0 or row.value > row.exposure):
                raise ValueError("binary count must be within positive exposure")
            if not binary and row.exposure != 1:
                raise ValueError("continuous outcomes require exposure=1")
            out[key] = row
        return out

    a, b = index(candidate), index(baseline)
    if not a or a.keys() != b.keys():
        raise ValueError("candidate and baseline need identical nonempty seed/item keys")
    seeds = {key[0] for key in a}
    ids = sorted({key[1] for key in a}, key=repr)
    if any((seed, item_id) not in a for seed in seeds for item_id in ids):
        raise ValueError("every seed must contain the same sequence IDs")

    # Rows are ordered by sequence block, then seed. Each bootstrap draw keeps
    # every seed in the sampled block, including the matching baseline row.
    ordered_seeds = sorted(seeds, key=repr)
    keys = [(seed, item_id) for item_id in ids for seed in ordered_seeds]
    av = np.array([a[key].value for key in keys]).reshape(len(ids), len(seeds))
    bv = np.array([b[key].value for key in keys]).reshape(len(ids), len(seeds))
    if binary:
        ae = np.array([a[key].exposure for key in keys]).reshape(av.shape)
        be = np.array([b[key].exposure for key in keys]).reshape(bv.shape)
        estimate = float(av.sum() / ae.sum() - bv.sum() / be.sum())
    else:
        estimate = float(np.mean(av - bv))

    # A zero-variance handful of equal rows would otherwise produce a zero
    # width CI and certify equality without meaningful sequence coverage.
    if len(ids) < min_sequences:
        return Comparison(estimate, float("nan"), float("nan"), margin,
                          "inconclusive", len(ids), len(keys))
    if binary and np.all(ae == 1) and np.all(be == 1) \
            and np.all((av == 0) | (av == 1)) and np.all((bv == 0) | (bv == 1)):
        # Average discordances over matched seeds. The effective sample size
        # remains the number of independent sequence blocks.
        b_only = float(np.sum((av == 1) & (bv == 0)) / len(seeds))
        a_only = float(np.sum((av == 0) & (bv == 1)) / len(seeds))
        lo, hi = _tango_score_interval(b_only, a_only, len(ids), confidence)
    else:
        rng = np.random.default_rng(bootstrap_seed)
        boot = np.empty(bootstrap_samples)
        for i in range(bootstrap_samples):
            sampled = rng.integers(0, len(ids), size=len(ids))
            if binary:
                boot[i] = (av[sampled].sum() / ae[sampled].sum()
                           - bv[sampled].sum() / be[sampled].sum())
            else:
                boot[i] = np.mean(av[sampled] - bv[sampled])
        tail = (1 - confidence) / 2
        lo, hi = np.quantile(boot, [tail, 1 - tail])
    verdict = "superior" if hi < 0 else "non-inferior" if hi < margin else "inconclusive"
    return Comparison(estimate, float(lo), float(hi), margin, verdict, len(ids), len(keys))
