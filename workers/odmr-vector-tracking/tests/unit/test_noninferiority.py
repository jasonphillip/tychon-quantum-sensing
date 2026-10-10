"""Tests for paired, sequence-blocked non-inferiority verdicts."""

import pytest

from odmr_vector_tracking.evaluation.noninferiority import Outcome, compare_paired
from odmr_vector_tracking.evaluation.metrics import wilson_ci


def rows(values, seed=1):
    return [Outcome(i, seed, value) for i, value in enumerate(values)]


def test_overlapping_wilson_intervals_do_not_establish_noninferiority():
    baseline = [0] * 30 + [1] * 30
    candidate = [0] * 24 + [1] * 36
    assert wilson_ci(30, 60)[1] >= wilson_ci(36, 60)[0]
    result = compare_paired(rows(candidate), rows(baseline), margin=0.01, binary=True)
    assert result.verdict == "inconclusive"
    assert result.ci_low > 0  # paired evidence of worsening, despite Wilson overlap


def test_equal_requires_enough_distinct_sequences():
    small = compare_paired(rows([0, 1] * 5), rows([0, 1] * 5),
                           margin=0.01, binary=True)
    large = compare_paired(rows([0, 1] * 20), rows([0, 1] * 20),
                           margin=0.01, binary=True)
    assert small.verdict == "inconclusive"
    assert large.verdict == "inconclusive"
    assert large.ci_high > 0.01


def test_zero_discordant_288_pairs_does_not_certify_one_percent_margin():
    result = compare_paired(rows([0] * 288), rows([0] * 288),
                            margin=0.01, binary=True)
    # Tango's 95% score bound: z^2 / (n + z^2) = 0.013162827640106801.
    assert result.ci_high == pytest.approx(0.013162827640106801)
    assert result.ci_low == pytest.approx(-0.013162827640106801)
    assert result.verdict == "inconclusive"


def test_pairing_detects_worsening_hidden_by_marginal_overlap():
    baseline = [0] * 40 + [1] * 40
    candidate = [0] * 32 + [1] * 48
    assert wilson_ci(40, 80)[1] >= wilson_ci(48, 80)[0]
    result = compare_paired(rows(candidate), rows(baseline), margin=0.02,
                            binary=True)
    assert result.ci_low > 0
    assert result.verdict == "inconclusive"


def test_continuous_blocks_and_seed_strata():
    base = rows([2.0] * 40, seed=1) + rows([4.0] * 40, seed=2)
    candidate = rows([1.5] * 40, seed=1) + rows([3.5] * 40, seed=2)
    result = compare_paired(candidate, base, margin=0.1, binary=False)
    assert result.verdict == "superior"
    assert result.n_sequences == 40
    assert result.n_pairs == 80


def test_binary_counts_use_exposure_and_match_by_id():
    base = [Outcome(i, 1, 0, 100 if i < 20 else 1) for i in range(40)]
    candidate = [Outcome(i, 1, 0 if i < 20 else 1,
                         100 if i < 20 else 1) for i in range(40)]
    result = compare_paired(candidate[::-1], base, margin=0.02, binary=True)
    assert result.estimate == pytest.approx(20 / 2020)
    assert result.n_sequences == 40


def test_rejects_unmatched_ids_and_seeds():
    with pytest.raises(ValueError, match="identical"):
        compare_paired(rows([0] * 40), rows([0] * 39), margin=0.01, binary=True)
    with pytest.raises(ValueError, match="every seed"):
        compare_paired(rows([0] * 40, 1) + rows([0] * 39, 2),
                       rows([0] * 40, 1) + rows([0] * 39, 2),
                       margin=0.01, binary=True)
